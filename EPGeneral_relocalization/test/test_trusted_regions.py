import hashlib
import logging
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from epgeneral_relocalization.node import RelocalizationNode
from epgeneral_relocalization.config import load_config
from epgeneral_relocalization.trusted_regions_codec import encode_xml, read_xml, decode_xml, validate_polygon


class ImmediateThread:
    def __init__(self, target, args, **kwargs):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


class TrustedRegionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.node = object.__new__(RelocalizationNode)
        self.node.config = dict(device_id='UGV_001', map_frame='map', trusted_regions_root=self.temp.name,
                                ground_station_ip='127.0.0.1', download_timeout_seconds=2)
        self.node.identity = dict(map_id='map-1', device_id='UGV_001', session_id='s1')
        self.node.lock = threading.RLock()
        self.node.state = 'localized'
        self.node.operation_generation = 0
        self.node.region_operation = None
        self.node.region_responses = {}
        self.node.logger = logging.getLogger('regions-test')
        self.replies = []
        self.node._send = lambda request, kind, payload: self.replies.append((kind, payload))
        self.doc = dict(map_id='map-1', device_id='UGV_001', frame_id='map', revision='rev1',
                        regions=[dict(id=1, points=[(0., 0.), (4., 0.), (2., 3.)])])
        self.data = encode_xml(self.doc)
        self.destination = Path(self.temp.name) / 'map-1/UGV_001.xml'

    def message(self, request='r1'):
        return dict(self.node.identity, message_type='trusted_regions_offer', request_id=request,
                    payload=dict(url='http://127.0.0.1/file', revision=self.doc['revision'],
                                 byte_count=len(self.data), sha256=hashlib.sha256(self.data).hexdigest()))

    def receive(self, message, after_download=None):
        def download(url, path, *args):
            Path(path).write_bytes(self.data)
            if after_download:
                after_download()
        with mock.patch('epgeneral_relocalization.trusted_regions.download', side_effect=download), \
                mock.patch('epgeneral_relocalization.trusted_regions.threading',
                           SimpleNamespace(Thread=ImmediateThread)):
            self.node._handle(message)

    def test_install_duplicate_request_replace_and_clear(self):
        message = self.message()
        self.receive(message)
        self.assertEqual(read_xml(self.destination), self.doc)
        self.assertEqual(self.replies[-1][1]['state'], 'ready')
        before = self.destination.stat().st_mtime_ns
        self.receive(message)
        self.assertEqual(self.destination.stat().st_mtime_ns, before)
        self.doc['revision'] = 'rev2'
        self.doc['regions'] = []
        self.data = encode_xml(self.doc)
        self.receive(self.message('r2'))
        self.assertEqual(read_xml(self.destination)['regions'], [])
        self.assertEqual(self.node.state, 'localized')

    def test_invalid_xml_and_atomic_write_failure_keep_previous_regions(self):
        self.receive(self.message())
        before = self.destination.read_bytes()
        self.data = b'<invalid/>'
        self.receive(self.message('bad-xml'))
        self.assertEqual(self.replies[-1][1]['state'], 'error')
        self.assertEqual(self.destination.read_bytes(), before)
        self.data = encode_xml(self.doc)
        with mock.patch('epgeneral_relocalization.trusted_regions_codec.os.replace', side_effect=OSError('disk full')):
            self.receive(self.message('bad-write'))
        self.assertEqual(self.destination.read_bytes(), before)
        self.assertEqual(self.node.state, 'localized')

    def test_disabled_wrong_device_wrong_map_and_stale_session(self):
        self.node.config['trusted_regions_enabled'] = False
        self.receive(self.message())
        self.assertEqual(self.replies[-1][1]['reason'], 'TRUSTED_REGIONS_DISABLED')
        self.node.config['trusted_regions_enabled'] = True
        wrong = self.message('wrong-device')
        wrong['device_id'] = 'OTHER'
        count = len(self.replies)
        self.receive(wrong)
        self.assertEqual(len(self.replies), count)
        wrong = self.message('wrong-map')
        wrong['map_id'] = 'map-2'
        self.receive(wrong)
        self.assertEqual(self.replies[-1][1]['reason'], 'SESSION_MISMATCH')
        self.receive(self.message('stale'), lambda: self.node.identity.update(session_id='s2'))
        self.assertEqual(self.replies[-1][1]['state'], 'error')
        self.assertFalse(self.destination.exists())
        self.assertEqual(self.node.state, 'localized')

    def test_revision_frame_and_geometry_validation(self):
        for change in (dict(revision='wrong'), dict(frame_id='odom'), dict(device_id='OTHER')):
            self.data = encode_xml(dict(self.doc, **change))
            self.receive(self.message('case-' + next(iter(change))))
            self.assertEqual(self.replies[-1][1]['state'], 'error')
        for points in ([(0, 0), (1, 1), (2, 2)], [(0, 0), (3, 3), (0, 2), (3, 0)]):
            with self.assertRaises(ValueError):
                validate_polygon(points)
        validate_polygon([(0, 0), (3, 0), (1, 1), (3, 3), (0, 3)])
        with self.assertRaises(ValueError):
            decode_xml(b'<!DOCTYPE foo><trusted_regions/>')

    def test_ndt_consumer_ack_required_and_failure_rolls_back(self):
        self.node.config['trusted_regions_apply_to_ndt'] = True
        bridge = mock.Mock()
        bridge.snapshot.return_value = 'previous'
        self.node.ros = SimpleNamespace(region_bridge=bridge)
        self.receive(self.message())
        bridge.apply.assert_called_once_with(self.doc)
        self.assertEqual(self.replies[-1][1]['state'], 'ready')
        before = self.destination.read_bytes()
        bridge.apply.side_effect = RuntimeError('NDT_REGION_APPLICATION_TIMEOUT')
        self.receive(self.message('timeout'))
        bridge.restore.assert_called_once_with('previous')
        self.assertEqual(self.replies[-1][1]['state'], 'error')
        self.assertEqual(self.destination.read_bytes(), before)
        self.assertEqual(self.node.state, 'localized')
        bridge.apply.side_effect = None
        self.doc['regions'] = []
        self.data = encode_xml(self.doc)
        self.receive(self.message('clear'))
        self.assertEqual(bridge.apply.call_args[0][0]['regions'], [])
        self.assertEqual(self.node.state, 'localized')

    def test_optional_config_defaults_allow_existing_profiles(self):
        shared = Path(__file__).resolve().parents[2] / 'EPGeneral_device_config/config'
        import yaml
        data = yaml.safe_load((shared / 'relocalization.yaml').read_text(encoding='utf-8'))
        data.pop('trusted_regions', None)
        config_path = Path(self.temp.name) / 'old.yaml'
        config_path.write_text(yaml.safe_dump(data), encoding='utf-8')
        config = load_config(str(config_path), str(shared / 'device.yaml'))
        self.assertTrue(config['trusted_regions_enabled'])
        self.assertTrue(config['enabled'])
        self.assertEqual(config['trusted_regions_root'], '~/.ros/ccs_edge_dev/trusted_regions')


if __name__ == '__main__':
    unittest.main()
