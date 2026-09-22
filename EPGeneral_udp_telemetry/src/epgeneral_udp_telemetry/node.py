import socket
import ipaddress
import threading
import time
import uuid

from .config import LEVEL_RATES, ConfigError, source_mode
from .protocol import ProtocolError, encode_envelope
from .smoothing import TelemetrySampler
from .sources import extract_sample, file_snapshot, validate_ros_sources


class RosUdpTelemetryNode(object):
    def __init__(self, rospy, config):
        self.rospy = rospy
        self.config = config
        namespace = "/epgeneral_udp_telemetry"
        self.config.setdefault("link_status_topic", namespace + "/link/udp_tx")
        self.config.setdefault("diagnostics_topic", namespace + "/diagnostics")
        self.session_id = uuid.uuid4().hex
        self.socket = None
        self._classes = None
        self._closed = False
        self.destination = (config["destination_host"], config["destination_port"])
        self.sequences = {"heartbeat": 0, 1: 0, 2: 0, 3: 0}
        self.samplers = {item["name"]: TelemetrySampler(item) for item in config["descriptors"]}
        self.subscribers = []
        self.timers = []
        self.last_send_ok = False
        self.last_send_error = "not sent"
        self.link_publisher = None
        self.diagnostics_publisher = None
        self.sample_states = {item["name"]: None for item in config["descriptors"]}
        self.level_stats = {
            level: {"sent_count": 0, "failure_count": 0, "byte_count": 0}
            for level in LEVEL_RATES
        }
        self.send_lock = threading.Lock()

    def start(self):
        if self._closed or self.socket is not None:
            raise RuntimeError("UDP telemetry node cannot be started twice or after close")
        try:
            import roslib.message
            from diagnostic_msgs.msg import DiagnosticArray
            from std_msgs.msg import Bool

            if self._classes is None:
                self._classes = validate_ros_sources(self.config)
            family = socket.AF_INET6 if ipaddress.ip_address(self.destination[0]).version == 6 else socket.AF_INET
            self.socket = socket.socket(family, socket.SOCK_DGRAM)
            self.rospy.on_shutdown(self.close)
            self.link_publisher = self.rospy.Publisher(
                self.config["link_status_topic"], Bool, queue_size=1, latch=True)
            self.diagnostics_publisher = self.rospy.Publisher(
                self.config["diagnostics_topic"], DiagnosticArray, queue_size=1, latch=False)

            for descriptor in self.config["descriptors"]:
                source = descriptor["source"]
                if source_mode(descriptor) == "disabled":
                    self.rospy.loginfo("UDP telemetry source disabled: %s", descriptor["name"])
                    continue
                if source_mode(descriptor) == "file_status":
                    self.rospy.loginfo("UDP telemetry file source name=%s state=%s root=%s",
                                       descriptor["name"], source["state_file"], source["map_root"])
                    continue
                if source_mode(descriptor) == "topic_freshness":
                    message_class = self.rospy.AnyMsg
                else:
                    message_class = self._classes[source["message_type"]]
                    if message_class is None:
                        raise ConfigError("ROS message type is unavailable: %s" % source["message_type"])
                callback = self._callback_for(descriptor)
                self.subscribers.append(self.rospy.Subscriber(source["topic"], message_class, callback, queue_size=source.get("queue_size", 50)))
                self.rospy.loginfo(
                    "UDP telemetry source name=%s type=%s level=%d topic=%s message_type=%s mapping=%s",
                    descriptor["name"], descriptor["type"], descriptor["level"], source["topic"],
                    source.get("message_type", "AnyMsg"), source.get("mapping", {}))
            self.timers.append(self.rospy.Timer(self.rospy.Duration(1.0), self._send_heartbeat))
            self.timers.append(self.rospy.Timer(self.rospy.Duration(1.0), self._publish_link_status))
            for level, rate in LEVEL_RATES.items():
                self.timers.append(self.rospy.Timer(self.rospy.Duration(1.0 / rate), lambda event, selected=level: self._send_level(selected)))
            self.rospy.loginfo(
                "ROS UDP telemetry started device=%s session=%s destination=%s:%d descriptor_hash=%s rates=%s",
                self.config["device_id"], self.session_id, self.destination[0], self.destination[1],
                self.config["descriptor_hash"], LEVEL_RATES)

        except Exception:
            self.close()
            raise

    def _callback_for(self, descriptor):
        sampler = self.samplers[descriptor["name"]]
        if source_mode(descriptor) == "topic_freshness":
            def touch_callback(_message):
                sampler.touch(time.monotonic())
                self._record_sample_result(descriptor, True, "")
            return touch_callback

        def fields_callback(message):
            try:
                sample = extract_sample(descriptor, message)
                accepted = sampler.add(sample, time.monotonic())
                self._record_sample_result(descriptor, accepted, sampler.last_rejection_reason)
            except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
                sampler.reject(exc)
                self._record_sample_result(descriptor, False, exc)
                self.rospy.logwarn_throttle(5.0, "%s mapping failed: %s" % (descriptor["name"], exc))
        return fields_callback

    def _record_sample_result(self, descriptor, accepted, reason):
        name = descriptor["name"]
        previous = self.sample_states[name]
        self.sample_states[name] = bool(accepted)
        if accepted and previous is None:
            self.rospy.loginfo("UDP telemetry source first valid sample: %s", name)
        elif accepted and previous is False:
            self.rospy.loginfo_throttle(5.0, "UDP telemetry source recovered: %s" % name)
        elif not accepted:
            self.rospy.logwarn_throttle(
                5.0, "UDP telemetry source rejected name=%s reason=%s" % (name, reason))

    def _send_heartbeat(self, event):
        self._send("heartbeat", "heartbeat", None, None)

    def _send_level(self, level):
        now = time.monotonic()
        payload = {}
        for descriptor in self.config["descriptors"]:
            if descriptor["level"] != level:
                continue
            sampler = self.samplers[descriptor["name"]]
            try:
                if source_mode(descriptor) == "file_status":
                    value = file_snapshot(descriptor)
                    payload[descriptor["name"]] = value
                    sampler.touch(now)
                    self._record_sample_result(descriptor, value["status"] == "available", "artifact unavailable")
                else:
                    payload[descriptor["name"]] = sampler.snapshot(now)
            except Exception as exc:
                sampler.reject("snapshot failed: %s" % exc, received=False)
                payload[descriptor["name"]] = {"valid": False, "sample_age_seconds": None}
                self._record_sample_result(descriptor, False, exc)
        self._send("telemetry", level, level, payload)

    # Backward-compatible helper for existing integrations/tests.
    _pgm_file_snapshot = staticmethod(file_snapshot)

    def _send(self, message_type, sequence_key, level, payload):
        with self.send_lock:
            if self._closed or self.socket is None:
                return
            sequence = self.sequences[sequence_key]
            try:
                encoded = encode_envelope(self.config, self.session_id, message_type, sequence, payload, level)
                self.socket.sendto(encoded, self.destination)
                self.last_send_ok = True
                self.last_send_error = ""
                if level in self.level_stats:
                    self.level_stats[level]["sent_count"] += 1
                    self.level_stats[level]["byte_count"] += len(encoded)
            except (OSError, ProtocolError) as exc:
                self.last_send_ok = False
                self.last_send_error = str(exc)
                if level in self.level_stats:
                    self.level_stats[level]["failure_count"] += 1
                self.rospy.logerr_throttle(5.0, "UDP send failed: %s" % exc)
            self.sequences[sequence_key] += 1

    def _publish_link_status(self, event):
        from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
        from std_msgs.msg import Bool

        with self.send_lock:
            last_send_ok = self.last_send_ok
            last_send_error = self.last_send_error
            level_statistics = {
                level: dict(stats) for level, stats in self.level_stats.items()
            }
            next_sequences = dict(self.sequences)
        self.link_publisher.publish(Bool(data=last_send_ok))
        report = DiagnosticArray()
        report.header.stamp = self.rospy.Time.now()
        status = DiagnosticStatus()
        status.name = "epgeneral_udp_telemetry/udp_tx"
        status.hardware_id = self.config["device_id"]
        status.level = DiagnosticStatus.OK if last_send_ok else DiagnosticStatus.ERROR
        status.message = "sendto succeeded" if last_send_ok else last_send_error
        status.values = [
            KeyValue(key="destination", value="%s:%d" % self.destination),
            KeyValue(key="session_id", value=self.session_id),
            KeyValue(key="descriptor_hash", value=self.config["descriptor_hash"]),
        ]
        for level in sorted(level_statistics):
            stats = level_statistics[level]
            status.values.extend([
                KeyValue(key="level_%d_sent_count" % level, value=str(stats["sent_count"])),
                KeyValue(key="level_%d_failure_count" % level, value=str(stats["failure_count"])),
                KeyValue(key="level_%d_byte_count" % level, value=str(stats["byte_count"])),
                KeyValue(key="level_%d_next_sequence" % level, value=str(next_sequences[level])),
            ])
        report.status = [status]
        now = time.monotonic()
        source_statistics = {}
        for descriptor in self.config["descriptors"]:
            source_status = DiagnosticStatus()
            source_status.name = "epgeneral_udp_telemetry/source/%s" % descriptor["name"]
            source_status.hardware_id = self.config["device_id"]
            stats = self.samplers[descriptor["name"]].statistics(now)
            source_statistics[descriptor["name"]] = stats
            mode = source_mode(descriptor)
            source = descriptor["source"]
            age = stats["last_sample_age_seconds"]
            stale = age is not None and (
                (mode == "topic_freshness" and age > source.get("timeout_seconds", 3.0)) or
                (source.get("stale_policy") == "invalidate" and age > source.get("max_age_seconds", 3.0)))
            if mode == "disabled":
                source_status.level = DiagnosticStatus.OK
                source_status.message = "source disabled"
            elif stale:
                source_status.level = DiagnosticStatus.WARN
                source_status.message = "source stale"
            elif stats["accepted_count"] == 0:
                source_status.level = DiagnosticStatus.WARN
                source_status.message = "waiting for valid sample"
            elif self.sample_states[descriptor["name"]] is False:
                source_status.level = DiagnosticStatus.WARN
                source_status.message = "artifact unavailable" if mode == "file_status" else stats["last_rejection_reason"] or "latest sample rejected"
            else:
                source_status.level = DiagnosticStatus.OK
                source_status.message = "receiving valid samples"
            age = stats["last_sample_age_seconds"]
            source = descriptor["source"]
            source_status.values = [
                KeyValue(key="mode", value=mode),
                KeyValue(key="topic", value=source.get("topic", source.get("state_file", "file"))),
                KeyValue(key="message_type", value=source.get("message_type", "AnyMsg")),
                KeyValue(key="level", value=str(descriptor["level"])),
                KeyValue(key="dropped_count", value=str(stats["dropped_count"])),
                KeyValue(key="received_count", value=str(stats["received_count"])),
                KeyValue(key="accepted_count", value=str(stats["accepted_count"])),
                KeyValue(key="rejected_count", value=str(stats["rejected_count"])),
                KeyValue(key="last_sample_age_seconds", value="unknown" if age is None else "%.3f" % age),
                KeyValue(key="last_rejection_reason", value=stats["last_rejection_reason"]),
            ]
            report.status.append(source_status)
        self.diagnostics_publisher.publish(report)
        summary = ", ".join(
            "%s rx=%d ok=%d rejected=%d age=%s" % (
                descriptor["name"],
                source_statistics[descriptor["name"]]["received_count"],
                source_statistics[descriptor["name"]]["accepted_count"],
                source_statistics[descriptor["name"]]["rejected_count"],
                "unknown" if source_statistics[descriptor["name"]]["last_sample_age_seconds"] is None
                else "%.2fs" % source_statistics[descriptor["name"]]["last_sample_age_seconds"],
            ) for descriptor in self.config["descriptors"])
        self.rospy.loginfo_throttle(30.0, "UDP telemetry source summary: %s" % summary)

    def close(self):
        with self.send_lock:
            if self._closed:
                return
            self._closed = True
            sock, self.socket = self.socket, None
        # Mark closed before shutdown: timer callbacks cannot send on a closed socket.
        actions = [timer.shutdown for timer in self.timers]
        actions.extend(subscriber.unregister for subscriber in self.subscribers)
        actions.extend(publisher.unregister for publisher in (self.link_publisher, self.diagnostics_publisher) if publisher is not None)
        if sock is not None:
            actions.append(sock.close)
        self.timers, self.subscribers = [], []
        for action in actions:
            try:
                action()
            except Exception as exc:
                self.rospy.logwarn_throttle(5.0, "UDP resource cleanup failed: %s" % exc)
        self.rospy.loginfo("ROS UDP telemetry stopped")


def run(argv=None):
    from .application import run as run_application
    return run_application(argv)
