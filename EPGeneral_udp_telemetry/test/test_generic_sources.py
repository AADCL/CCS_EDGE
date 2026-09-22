import copy
import io
import json
import math
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

PACKAGE = Path(__file__).resolve().parents[1]
ROOT = PACKAGE.parent
sys.path.insert(0, str(PACKAGE / "src"))

from epgeneral_udp_telemetry.application import parse_args, run, select_config
from epgeneral_udp_telemetry.config import ConfigError, load_config
from epgeneral_udp_telemetry.node import RosUdpTelemetryNode
from epgeneral_udp_telemetry.sources import extract_sample, file_snapshot, validate_ros_sources
from epgeneral_udp_telemetry.smoothing import TelemetrySampler


class GenericSourcesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.device = {"schema_version": 1, "device": {"id": "Robot_A", "ip": "192.0.2.20"}}
        self.raw = {
            "schema_version": 2, "protocol_id": "ccs-udp-telemetry-v1",
            "network": {"destination_host": "192.0.2.10", "destination_port": 14560},
            "runtime": {"diagnostics_topic": "/devices/{device_id}/diagnostics"},
            "descriptors": [{"name": "global_pose", "display_name": "Global", "type": "pose", "level": 1,
                             "source": {"mode": "ros_fields", "topic": "/devices/{device_id}/pose",
                                        "message_type": "geometry_msgs/PoseStamped", "units": {"position": "cm"},
                                        "max_age_seconds": 2.0}}]}

    def load(self):
        for name, value in (("device.yaml", self.device), ("udp_telemetry.yaml", self.raw)):
            (self.folder / name).write_bytes(yaml.safe_dump(value).encode("utf-8"))
        return load_config(self.folder / "udp_telemetry.yaml", self.folder / "device.yaml")

    def status(self):
        item = self.raw["descriptors"][0]
        item.update(type="availability", level=3)
        item["source"] = {"mode": "value_status", "topic": "/ready", "message_type": "std_msgs/Bool",
                          "values": {True: "available", False: "unavailable"}, "max_age_seconds": 2}
        return self.load()["descriptors"][0]

    @staticmethod
    def pose(x=100):
        return {"pose": {"position": {"x": x, "y": 200, "z": 300},
                         "orientation": {"x": 0, "y": 0, "z": 0, "w": 1}}}

    def test_profile_hashes_preserved_from_remote_main(self):
        expected = json.loads((PACKAGE / "test/fixtures/descriptor_hashes.json").read_text(encoding="utf-8"))
        folders = [("shared", ROOT / "EPGeneral_device_config/config")]
        folders.extend((folder.parent.name, folder) for folder in ROOT.glob("devices/*/profiles/*/config"))
        self.assertEqual(len(folders), 9)
        for name, folder in folders:
            with self.subTest(profile=name):
                result = load_config(folder / "udp_telemetry.yaml", folder / "device.yaml")
                self.assertEqual(result["descriptor_hash"], expected[name])

    def test_placeholders_preserve_case_and_expand_runtime(self):
        config = self.load()
        self.assertEqual(config["descriptors"][0]["source"]["topic"], "/devices/Robot_A/pose")
        self.assertEqual(config["diagnostics_topic"], "/devices/Robot_A/diagnostics")

    def test_source_changes_and_disabled_mode_preserve_wire_hash(self):
        before = self.load()
        self.raw["descriptors"][0]["source"] = {"mode": "disabled"}
        after = self.load()
        self.assertEqual(before["descriptor_hash"], after["descriptor_hash"])
        self.assertFalse(TelemetrySampler(after["descriptors"][0]).snapshot(100)["valid"])
        self.assertEqual(validate_ros_sources(after, lambda name: self.fail("disabled source resolved")), {})

    def test_no_implicit_identity_or_ambiguous_config_selection(self):
        for args in ([], ["--device-config-file", "device.yaml"],
                     ["--config-dir", str(self.folder), "--device-config-file", "device.yaml"]):
            with self.subTest(args=args), self.assertRaises(ConfigError):
                select_config(parse_args(args))

    def test_empty_launch_overrides_do_not_replace_yaml_destination(self):
        self.load()
        args = parse_args(["--config-dir", str(self.folder), "--destination-host", "", "--destination-port", ""])
        config = select_config(args)
        self.assertEqual(config["destination_host"], "192.0.2.10")
        self.assertEqual(config["destination_port"], 14560)
        config = select_config(parse_args(["--config-dir", str(self.folder), "--destination-host", "::1", "--destination-port", "14561"]))
        self.assertEqual((config["destination_host"], config["destination_port"]), ("::1", 14561))

    def test_config_check_never_initializes_ros_or_socket(self):
        self.load()
        ros = MagicMock()
        with patch("epgeneral_udp_telemetry.node.socket.socket") as socket, redirect_stdout(io.StringIO()) as output:
            self.assertEqual(run(["--config-dir", str(self.folder), "--check-config"], ros), 0)
        ros.init_node.assert_not_called()
        socket.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())["device_id"], "Robot_A")

    def test_preflight_failure_precedes_ros_initialization(self):
        self.load()
        ros = MagicMock()
        with patch("epgeneral_udp_telemetry.application.validate_ros_sources", side_effect=ConfigError("bad fields")), redirect_stderr(io.StringIO()):
            self.assertEqual(run(["--config-dir", str(self.folder)], ros), 2)
        ros.init_node.assert_not_called()

    def test_invalid_deployment_fields_fail_closed(self):
        cases = [("destination_host", "host.invalid"), ("destination_port", True),
                 ("destination_port", 0), ("destination_port", 65536)]
        original = copy.deepcopy(self.raw)
        for key, value in cases:
            with self.subTest(key=key, value=value):
                self.raw = copy.deepcopy(original)
                self.raw["network"][key] = value
                with self.assertRaises(ConfigError):
                    self.load()

    def test_invalid_source_fields_fail_closed(self):
        cases = [{"mode": "invented"}, {"mode": "value_status"}, {"units": {}},
                 {"units": {"position": "feet"}}, {"mapping": {"position": "pose.__dict__"}},
                 {"topic": "/devices/{other}/pose"}, {"max_samples": 0}, {"text_limit": 129},
                 {"max_age_seconds": float("nan")}, {"unknown_setting": 1}]
        original = copy.deepcopy(self.raw)
        for changes in cases:
            with self.subTest(changes=changes):
                self.raw = copy.deepcopy(original)
                self.raw["descriptors"][0]["source"].update(changes)
                with self.assertRaises(ConfigError):
                    self.load()

    def test_component_mapping_units_and_expected_frame(self):
        source = self.raw["descriptors"][0]["source"]
        source.update(mapping={"position": {"x": "east", "y": "north", "z": "up"}}, expected_frame="map")
        descriptor = self.load()["descriptors"][0]
        message = self.pose()
        message.update(east=100, north=200, up=300, header={"frame_id": "map"})
        sample = extract_sample(descriptor, message)
        self.assertEqual((sample["x"], sample["y"], sample["z"]), (1, 2, 3))
        message["header"]["frame_id"] = "odom"
        with self.assertRaises(ValueError):
            extract_sample(descriptor, message)

    def test_imu_unit_conversion(self):
        item = self.raw["descriptors"][0]
        item["type"] = "imu"
        item["source"]["message_type"] = "sensor_msgs/Imu"
        item["source"]["units"] = {"angular_velocity": "deg/s", "linear_acceleration": "g"}
        message = {"orientation": {"x": 0, "y": 0, "z": 0, "w": 1},
                   "angular_velocity": {"x": 180, "y": 0, "z": 0}, "linear_acceleration": {"x": 1, "y": 0, "z": 0}}
        sample = extract_sample(self.load()["descriptors"][0], message)
        self.assertAlmostEqual(sample["angular_velocity_x"], math.pi)
        self.assertAlmostEqual(sample["linear_acceleration_x"], 9.80665)

    def test_bool_false_is_unavailable_and_enum_types_are_distinct(self):
        descriptor = self.status()
        self.assertEqual(extract_sample(descriptor, {"data": False})["status"], "unavailable")
        self.assertEqual(extract_sample(descriptor, {"data": True})["status"], "available")
        self.assertEqual(extract_sample(descriptor, {"data": 1})["status"], "unknown")
        self.assertEqual(extract_sample(descriptor, {"data": "true"})["status"], "unknown")
        descriptor["source"]["values"] = {2: "available", 3: "unavailable"}
        self.assertEqual(extract_sample(descriptor, {"data": 3})["status"], "unavailable")

    def test_status_expiry_and_explicit_latched_hold(self):
        descriptor = self.status()
        sampler = TelemetrySampler(descriptor)
        sampler.add(extract_sample(descriptor, {"data": False}), 1)
        self.assertEqual(sampler.snapshot(2)["status"], "unavailable")
        self.assertFalse(sampler.snapshot(4)["valid"])
        descriptor["source"]["stale_policy"] = "hold"
        self.assertEqual(sampler.snapshot(1000)["status"], "unavailable")
        self.assertTrue(sampler.snapshot(1000)["valid"])

    def test_freshness_intentionally_ignores_bool_value(self):
        descriptor = self.status()
        descriptor["source"] = {"mode": "topic_freshness", "topic": "/ready", "timeout_seconds": 2}
        node = RosUdpTelemetryNode(MagicMock(), dict(self.load(), descriptors=[descriptor]))
        with patch("epgeneral_udp_telemetry.node.time.monotonic", return_value=1):
            node._callback_for(descriptor)({"data": False})
        self.assertEqual(node.samplers[descriptor["name"]].snapshot(2)["status"], "available")
        self.assertEqual(node.samplers[descriptor["name"]].snapshot(4)["status"], "unavailable")

    def test_bounded_buffer_latest_and_expiry(self):
        self.raw["descriptors"][0]["source"].update(max_samples=2, aggregation="latest")
        descriptor = self.load()["descriptors"][0]
        sampler = TelemetrySampler(descriptor)
        for index in range(3):
            sampler.add(extract_sample(descriptor, self.pose(index * 100)), index)
        self.assertEqual(sampler.statistics(2)["dropped_count"], 1)
        self.assertEqual(sampler.snapshot(2)["x"], 2)
        self.assertEqual(sampler.samples.maxlen, 2)
        self.assertFalse(sampler.snapshot(5)["valid"])

    def test_schema_one_preserves_hold_and_si_defaults(self):
        self.raw["schema_version"] = 1
        del self.raw["descriptors"][0]["source"]["mode"]
        del self.raw["descriptors"][0]["source"]["units"]
        descriptor = self.load()["descriptors"][0]
        sampler = TelemetrySampler(descriptor)
        sampler.add(extract_sample(descriptor, self.pose()), 1)
        self.assertTrue(sampler.snapshot(1000)["valid"])
        self.assertEqual(sampler.snapshot(1000)["x"], 100)

    def test_message_class_and_field_preflight(self):
        config = dict(self.load(), descriptors=[self.status()])
        class BoolMessage(object):
            __slots__ = ("data",)
            def __init__(self):
                self.data = False
        self.assertEqual(validate_ros_sources(config, lambda name: BoolMessage), {"std_msgs/Bool": BoolMessage})
        with self.assertRaises(ConfigError):
            validate_ros_sources(config, lambda name: None)
        config["descriptors"][0]["source"]["mapping"]["value"] = "missing"
        with self.assertRaises(ConfigError):
            validate_ros_sources(config, lambda name: BoolMessage)

    def test_file_status_configurable_state_field_and_ot_filename(self):
        descriptor = self.raw["descriptors"][0]
        descriptor.update(type="availability", level=3)
        descriptor["source"] = {"mode": "file_status", "state_file": str(self.folder / "state.json"),
                                "state_field": "active.id", "map_root": str(self.folder / "maps"),
                                "path_template": "{map_id}/occupancy.ot"}
        source = self.load()["descriptors"][0]
        (self.folder / "state.json").write_bytes(b'{"active":{"id":"map_1"}}')
        artifact = self.folder / "maps/map_1/occupancy.ot"
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(b"octomap")
        self.assertEqual(file_snapshot(source)["status"], "available")
        artifact.unlink()
        self.assertEqual(file_snapshot(source)["status"], "unavailable")
        (self.folder / "state.json").write_bytes(b'{"active":{"id":"../outside"}}')
        self.assertIsNone(file_snapshot(source)["map_id"])
        for template in ("../escape", "/absolute", "{other}/map.pgm", "x\\map.pgm"):
            descriptor["source"]["path_template"] = template
            with self.subTest(template=template), self.assertRaises(ConfigError):
                self.load()

    def test_partial_start_failure_releases_created_resources(self):
        config = self.load()
        ros = MagicMock()
        subscriber = MagicMock()
        ros.Subscriber.return_value = subscriber
        timer = MagicMock()
        ros.Timer.side_effect = [timer, RuntimeError("timer failed")]
        node = RosUdpTelemetryNode(ros, config)
        node._classes = {"geometry_msgs/PoseStamped": object}
        modules = {"roslib": MagicMock(), "roslib.message": MagicMock(), "diagnostic_msgs": MagicMock(),
                   "diagnostic_msgs.msg": MagicMock(), "std_msgs": MagicMock(), "std_msgs.msg": MagicMock()}
        with patch.dict(sys.modules, modules), patch("epgeneral_udp_telemetry.node.socket.socket") as socket:
            with self.assertRaises(RuntimeError):
                node.start()
            node.close()
            socket.return_value.close.assert_called_once_with()
        timer.shutdown.assert_called_once_with()
        subscriber.unregister.assert_called_once_with()
        self.assertTrue(node._closed)
        self.assertIsNone(node.socket)

    def test_generic_template_is_loadable_without_ros(self):
        folder = ROOT / "EPGeneral_device_config/config/templates/udp_generic"
        config = load_config(folder / "udp_telemetry.yaml", folder / "device.yaml")
        self.assertEqual(config["device_id"], "DEVICE_EXAMPLE")
        self.assertEqual(config["descriptors"][0]["source"]["stale_policy"], "invalidate")

    def test_successful_start_uses_ipv6_and_configured_queue_then_closes(self):
        self.raw["network"]["destination_host"] = "::1"
        self.raw["descriptors"][0]["source"]["queue_size"] = 7
        config = self.load()
        ros = MagicMock()
        node = RosUdpTelemetryNode(ros, config)
        node._classes = {"geometry_msgs/PoseStamped": object}
        modules = {"roslib": MagicMock(), "roslib.message": MagicMock(), "diagnostic_msgs": MagicMock(),
                   "diagnostic_msgs.msg": MagicMock(), "std_msgs": MagicMock(), "std_msgs.msg": MagicMock()}
        with patch.dict(sys.modules, modules), patch("epgeneral_udp_telemetry.node.socket.socket") as socket:
            node.start()
            import socket as socket_module
            socket.assert_called_once_with(socket_module.AF_INET6, socket_module.SOCK_DGRAM)
            self.assertEqual(ros.Subscriber.call_args[1]["queue_size"], 7)
            self.assertEqual(ros.Timer.call_count, 5)
            with self.assertRaises(RuntimeError):
                node.start()
            node.close()
            with self.assertRaises(RuntimeError):
                node.start()
            socket.return_value.close.assert_called_once_with()

    def test_cleanup_continues_after_one_resource_failure(self):
        node = RosUdpTelemetryNode(MagicMock(), self.load())
        timer, subscriber, socket = MagicMock(), MagicMock(), MagicMock()
        timer.shutdown.side_effect = RuntimeError("shutdown failed")
        node.timers, node.subscribers, node.socket = [timer], [subscriber], socket
        node.close()
        node.close()
        subscriber.unregister.assert_called_once_with()
        socket.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
