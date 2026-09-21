"""Optional region transfer. Never changes localization state or TF."""
import os
import tempfile
import threading

from .artifacts import download
from .trusted_regions_codec import MAX_BYTES, atomic_write, read_xml, safe_id


class TrustedRegionsReceiver(object):
    def _regions_reply(self, message, state, reason=""):
        payload = dict(state=state, reason=reason,
                       revision=message['payload'].get('revision', ''),
                       sha256=message['payload'].get('sha256', ''))
        key = tuple(message[k] for k in ('map_id', 'device_id', 'session_id', 'request_id'))
        self.region_responses[key] = payload
        if len(self.region_responses) > 128:
            self.region_responses.pop(next(iter(self.region_responses)))
        self._send(message, 'trusted_regions_status', payload)

    def _receive_regions(self, message):
        with self.lock:
            if (self.identity is None or any(message[k] != self.identity[k]
                    for k in ('map_id', 'device_id', 'session_id'))):
                self._regions_reply(message, 'error', 'SESSION_MISMATCH')
                return
            key = tuple(message[k] for k in ('map_id', 'device_id', 'session_id', 'request_id'))
            cached = self.region_responses.get(key)
            if cached is not None:
                self._send(message, 'trusted_regions_status', cached)
                return
            if not self.config.get('trusted_regions_enabled', True):
                self._regions_reply(message, 'error', 'TRUSTED_REGIONS_DISABLED')
                return
            if self.state != 'localized':
                self._regions_reply(message, 'error', 'LOCALIZATION_REQUIRED')
                return
            if self.region_operation is not None:
                self._regions_reply(message, 'error', 'TRUSTED_REGIONS_BUSY')
                return
            try:
                safe_id(message['map_id'])
                safe_id(message['device_id'])
                safe_id(message['payload']['revision'])
                size = message['payload']['byte_count']
                if type(size) is not int or not 0 < size <= MAX_BYTES:
                    raise ValueError('invalid trusted-region file size')
                digest = message['payload']['sha256']
                if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                    raise ValueError('invalid trusted-region digest')
            except (KeyError, TypeError, ValueError) as exc:
                self._regions_reply(message, 'error', str(exc))
                return
            operation = (key, self.operation_generation)
            self.region_operation = operation
            self._regions_reply(message, 'downloading')
            worker = threading.Thread(target=self._regions_worker, args=(message, operation),
                                      name='trusted-regions-download')
            worker.daemon = True
            worker.start()

    def _regions_worker(self, message, operation):
        temporary = None
        try:
            root = os.path.abspath(os.path.expanduser(self.config.get(
                'trusted_regions_root', '~/.ros/ccs_edge_dev/trusted_regions')))
            directory = os.path.join(root, safe_id(message['map_id']))
            os.makedirs(directory, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix='.download-', suffix='.xml.part', dir=directory)
            os.close(fd)
            payload = message['payload']
            download(payload['url'], temporary, self.config['ground_station_ip'],
                     payload['byte_count'], payload['sha256'],
                     self.config['download_timeout_seconds'], MAX_BYTES)
            document = read_xml(temporary, map_id=message['map_id'],
                                device_id=message['device_id'], frame_id=self.config['map_frame'])
            if document['revision'] != payload['revision']:
                raise ValueError('trusted-region revision mismatch')
            with open(temporary, 'rb') as stream:
                data = stream.read(MAX_BYTES + 1)
            with self.lock:
                if (self.region_operation != operation or self.operation_generation != operation[1]
                        or self.state != 'localized' or self.identity is None
                        or any(message[k] != self.identity[k] for k in ('map_id', 'device_id', 'session_id'))):
                    raise ValueError('trusted-region operation expired')
                destination = os.path.join(directory, safe_id(message['device_id']) + '.xml')
                atomic_write(destination, data)
                self._regions_reply(message, 'ready')
                self.logger.info('trusted_regions_saved map=%s device=%s revision=%s',
                                 message['map_id'], message['device_id'], document['revision'])
        except Exception as exc:
            with self.lock:
                self._regions_reply(message, 'error', str(exc)[:300])
            self.logger.warning('trusted_regions_failed error=%s', exc)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
            with self.lock:
                if self.region_operation == operation:
                    self.region_operation = None
