import ast
import io
import json
import logging
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import yaml

from epgeneral_mqtav.config import ConfigError, load_config
from epgeneral_mqtav.fields import extract
from epgeneral_mqtav.node import config_paths, parse_args, run
from epgeneral_mqtav.ros_bridge import RosBridge
from epgeneral_mqtav.state import HealthState, normalize_percentage

ROOT = Path(__file__).resolve().parents[2]
SHARED = ROOT / "EPGeneral_device_config/config"


class GenericDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mqtav profile ")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.data = yaml.safe_load((SHARED / "epgeneral_mqtav.yaml").read_text(encoding="utf-8"))
        self.data["schema_version"] = 2
        self.data["ros"]["connection_mode"] = "field"
        self.data["ros"]["battery"]["percentage_unit"] = "fraction"
        self.device = {"schema_version": 1, "device": {"id": "NewVendor_42", "ip": "192.0.2.42"}}

    def files(self):
        for filename, content in (("epgeneral_mqtav.yaml", self.data), ("device.yaml", self.device)):
            (self.folder / filename).write_text(yaml.safe_dump(content), encoding="utf-8")
        return self.folder / "epgeneral_mqtav.yaml", self.folder / "device.yaml"

    def config(self):
        return load_config(*self.files())

    def bridge(self, config, resolver=lambda _name: object):
        self.health = HealthState(config.device)
        self.ros = MagicMock()
        self.bridge_instance = RosBridge(config, self.health, logging.getLogger("test"), self.ros, resolver)
        return self.bridge_instance

    def test_new_device_only_requires_config_changes(self):
        self.data["ros"]["state"]["topic"] = "/devices/{device_id}/state"
        first = self.config()
        self.device["device"]["id"] = "Another_99"
        second = self.config()
        self.assertEqual(first.ros.state.topic, "/devices/NewVendor_42/state")
        self.assertEqual(second.ros.state.topic, "/devices/Another_99/state")
        self.assertEqual(second.client_id, "mqtav-Another_99")
        self.assertEqual(second.topic("status"), "mqtav/Another_99/status")

    def test_invalid_identifiers_are_rejected_without_normalizing(self):
        for value in (" bad", "bad ", "a/b", "a#", "a+", "{id}", "设备", "a" * 65, "../x", "-x", None, 123):
            with self.subTest(value=value):
                self.device["device"]["id"] = value
                with self.assertRaisesRegex(ConfigError, "device.id"):
                    self.config()

    def test_id_case_and_safe_punctuation_are_preserved(self):
        self.device["device"]["id"] = "aB_2-3"
        self.assertEqual(self.config().device.device_id, "aB_2-3")

    def test_strict_templates_and_unique_topics(self):
        for value in ("constant/status", "m/{other}", "m/{device_id.__class__}", "m/{device_id!r}", "m/{device_id:>5}", "m/{{device_id}}", "m/{device_id}/#", "m/{device_id}/\x00"):
            with self.subTest(value=value):
                self.data["mqtt"]["topics"]["status"] = value
                with self.assertRaises(ConfigError):
                    self.config()
        self.data["mqtt"]["topics"]["status"] = self.data["mqtt"]["topics"]["heartbeat"]
        with self.assertRaisesRegex(ConfigError, "distinct"):
            self.config()

    def test_ros_topic_template_must_expand_to_valid_name(self):
        self.device["device"]["id"] = "a-b"
        self.data["ros"]["state"]["topic"] = "/{device_id}/state"
        with self.assertRaisesRegex(ConfigError, "ros.state.topic"):
            self.config()

    def test_schema_rejects_unknown_keys_and_missing_mode_or_units(self):
        self.data["ros"]["connection_mod"] = "field"
        with self.assertRaisesRegex(ConfigError, "unknown keys"):
            self.config()
        del self.data["ros"]["connection_mod"]
        del self.data["ros"]["connection_mode"]
        with self.assertRaisesRegex(ConfigError, "connection_mode"):
            self.config()
        self.data["ros"]["connection_mode"] = "field"
        del self.data["ros"]["battery"]["percentage_unit"]
        with self.assertRaisesRegex(ConfigError, "percentage_unit"):
            self.config()

    def test_bad_mode_combinations_fail_before_runtime(self):
        self.data["ros"]["connection_mode"] = "heartbeat"
        with self.assertRaisesRegex(ConfigError, "ros.connection"):
            self.config()
        self.data["ros"]["connection_mode"] = "field"
        self.data["ros"]["state"]["mapping"]["connected"] = None
        with self.assertRaisesRegex(ConfigError, "mapping.connected"):
            self.config()
        self.data["ros"]["state"] = {"enabled": False}
        self.data["ros"]["connection_mode"] = "freshness"
        with self.assertRaisesRegex(ConfigError, "state must be enabled"):
            self.config()

    def test_disabled_mode_has_no_ros_sources_and_unknown_connection(self):
        self.data["ros"]["connection_mode"] = "disabled"
        for key in ("state", "battery", "mission"):
            self.data["ros"][key] = {"enabled": False}
        resolver = MagicMock()
        bridge = self.bridge(self.config(), resolver)
        bridge.start()
        resolver.assert_not_called()
        self.ros.Subscriber.assert_not_called()
        self.ros.Timer.assert_not_called()
        self.assertIsNone(self.health.payload("status")["health"]["fcu_connected"])

    def test_disabled_mode_ignores_connected_field(self):
        self.data["ros"]["connection_mode"] = "disabled"
        bridge = self.bridge(self.config())
        bridge.start()
        bridge._on_state(SimpleNamespace(connected=True, armed=False, system_status=2, mode="manual"))
        health = self.health.payload("status")["health"]
        self.assertIsNone(health["fcu_connected"])
        self.assertFalse(health["armed"])

    def test_field_mode_parses_false_string_instead_of_truthiness(self):
        bridge = self.bridge(self.config())
        bridge.start()
        bridge._on_state(SimpleNamespace(connected="false", armed="0", system_status=2, mode="manual"))
        health = self.health.payload("status")["health"]
        self.assertFalse(health["fcu_connected"])
        self.assertFalse(health["armed"])
        self.ros.Timer.assert_not_called()

    def test_freshness_mode_overrides_legacy_flag_and_recovers(self):
        self.data["ros"]["connection_mode"] = "freshness"
        bridge = self.bridge(self.config())
        bridge.start()
        with patch("epgeneral_mqtav.ros_bridge.time.monotonic", return_value=10):
            bridge._on_state(SimpleNamespace(connected=False, armed=True, system_status=2, mode="manual"))
        self.assertTrue(self.health.payload("status")["health"]["fcu_connected"])
        with patch("epgeneral_mqtav.ros_bridge.time.monotonic", return_value=14):
            bridge._check_state_freshness(None)
        self.assertFalse(self.health.payload("status")["health"]["fcu_connected"])
        with patch("epgeneral_mqtav.ros_bridge.time.monotonic", return_value=15):
            bridge._on_state(SimpleNamespace(connected=False, armed=True, system_status=2, mode="manual"))
        self.assertTrue(self.health.payload("status")["health"]["fcu_connected"])

    def test_qrd002_latched_armed_is_independent_of_periodic_connection(self):
        folder = ROOT / "devices/go2/profiles/go2_robot2/config"
        config = load_config(folder / "epgeneral_mqtav.yaml", folder / "device.yaml")
        self.assertEqual(config.ros.connection_mode, "heartbeat")
        self.assertEqual(config.ros.connection.topic, "/go2/state/low_state")
        bridge = self.bridge(config)
        bridge.start()
        with patch("epgeneral_mqtav.ros_bridge.time.monotonic", return_value=10):
            bridge._on_state(SimpleNamespace(data=True))
        for timestamp in (10, 12, 14, 16):
            with patch("epgeneral_mqtav.ros_bridge.time.monotonic", return_value=timestamp):
                bridge._on_connection(object())
                bridge._check_connection_freshness(None)
        health = self.health.payload("status")["health"]
        self.assertTrue(health["fcu_connected"])
        self.assertTrue(health["armed"])
        with patch("epgeneral_mqtav.ros_bridge.time.monotonic", return_value=20):
            bridge._check_connection_freshness(None)
        self.assertFalse(self.health.payload("status")["health"]["fcu_connected"])

    def test_units_conversion_and_invalid_values_reach_wire_safely(self):
        self.data["ros"]["battery"]["percentage_unit"] = "percent"
        self.data["ros"]["battery"]["mapping"] = {
            "percentage": "soc", "voltage": {"field": "millivolts", "scale": 0.001},
            "current": {"field": "milliamps", "scale": 0.001, "invalid_values": [-999]}}
        bridge = self.bridge(self.config())
        bridge._on_battery(SimpleNamespace(soc=0.5, millivolts=24500, milliamps=-999))
        payload = self.health.payload("status")
        self.assertEqual(payload["health"]["battery"], {"percentage": 0.5, "voltage": 24.5, "current": None})
        json.dumps(payload, allow_nan=False)

    def test_enum_and_offset_conversion(self):
        self.assertEqual(extract({"mode": 1}, {"field": "mode", "values": {0: "manual", 1: "auto"}}), "auto")
        self.assertIsNone(extract({"mode": 3}, {"field": "mode", "values": {0: "manual"}}))
        self.assertEqual(extract({"raw": 10}, {"field": "raw", "scale": 2, "offset": -5}), 15)

    def test_malformed_fields_and_conversions_fail_in_config(self):
        for value in ("a..b", "__class__", "a[0]", {"field": "x", "scale": float("inf")}, {"field": "x", "scale": True}, {"field": "x", "invalid_values": "bad"}, {"field": "x", "values": []}, {"field": "x", "expression": "eval"}):
            with self.subTest(value=value):
                self.data["ros"]["battery"]["mapping"]["voltage"] = value
                with self.assertRaisesRegex(ConfigError, "mapping.voltage"):
                    self.config()

    def test_nonfinite_and_invalid_state_never_break_json(self):
        health = HealthState(self.config().device)
        for value in (float("nan"), float("inf"), -float("inf"), True, "invalid", {}, [1]):
            health.update_state(value, value, value, None)
            health.update_battery(value, value, value)
            payload = health.payload("status")
            json.dumps(payload, allow_nan=False)
            self.assertEqual(payload["health"]["battery"], {"percentage": None, "voltage": None, "current": None})

    def test_percentage_units_are_unambiguous_and_reject_out_of_range(self):
        self.assertEqual(normalize_percentage(0.5, "percent"), 0.5)
        self.assertEqual(normalize_percentage(0.5, "fraction"), 50)
        self.assertIsNone(normalize_percentage(1.1, "fraction"))
        self.assertIsNone(normalize_percentage(101, "percent"))

    def test_missing_ros_type_cannot_create_partial_subscriptions(self):
        def resolver(name):
            if name == "sensor_msgs/BatteryState":
                raise RuntimeError("not installed")
            return object
        bridge = self.bridge(self.config(), resolver)
        with self.assertRaisesRegex(RuntimeError, "not installed"):
            bridge.start()
        self.ros.Subscriber.assert_not_called()

    def test_real_message_field_contract_is_checked_before_subscriptions(self):
        class WrongState(object):
            __slots__ = ("connected",)
            def __init__(self):
                self.connected = False
        bridge = self.bridge(self.config(), lambda _name: WrongState)
        with self.assertRaisesRegex(RuntimeError, "field armed"):
            bridge.start()
        self.ros.Subscriber.assert_not_called()

    def test_offline_validation_uses_only_selected_directory_with_spaces(self):
        self.files()
        output = io.StringIO()
        with patch("epgeneral_mqtav.node.MqttPublisher") as mqtt, patch("epgeneral_mqtav.node.build_logger") as logger, redirect_stdout(output):
            self.assertEqual(run(["--config-dir", str(self.folder), "--check-config"]), 0)
        mqtt.assert_not_called()
        logger.assert_not_called()
        result = json.loads(output.getvalue())
        self.assertEqual(result["device_id"], "NewVendor_42")
        self.assertEqual(result["connection_mode"], "field")

    def test_missing_files_and_no_profile_do_not_fall_back(self):
        for args in ([], ["--config-dir", str(self.folder)], ["--config-file", "missing"]):
            with patch("epgeneral_mqtav.node.MqttPublisher") as mqtt, patch("epgeneral_mqtav.node.build_logger") as logger, redirect_stderr(io.StringIO()):
                self.assertEqual(run(args), 2)
            mqtt.assert_not_called()
            logger.assert_not_called()

    def test_ambiguous_configuration_selection_is_rejected(self):
        with self.assertRaisesRegex(ConfigError, "not both"):
            config_paths(parse_args(["--config-dir", str(self.folder), "--config-file", "elsewhere"]))

    def test_check_ros_does_not_start_network_or_subscriptions(self):
        self.files()
        with patch("epgeneral_mqtav.node.RosBridge") as bridge, patch("epgeneral_mqtav.node.MqttPublisher") as mqtt, redirect_stdout(io.StringIO()):
            self.assertEqual(run(["--config-dir", str(self.folder), "--check-ros"]), 0)
        bridge.return_value.validate_sources.assert_called_once_with()
        bridge.return_value.start.assert_not_called()
        mqtt.assert_not_called()

    def test_startup_failure_cleans_up_resources(self):
        self.files()
        ros = MagicMock()
        with patch("epgeneral_mqtav.node.build_logger"), patch("epgeneral_mqtav.node.RosBridge") as bridge, patch("epgeneral_mqtav.node.MqttPublisher") as mqtt:
            mqtt.return_value.start.side_effect = RuntimeError("broker setup failed")
            self.assertEqual(run(["--config-dir", str(self.folder)], rospy_module=ros), 1)
        bridge.return_value.stop.assert_called_once_with()
        mqtt.return_value.stop.assert_called_once_with()

    def test_message_validation_failure_does_not_initialize_ros_or_mqtt(self):
        self.files()
        ros = MagicMock()
        with patch("epgeneral_mqtav.node.build_logger"), patch("epgeneral_mqtav.node.RosBridge") as bridge, patch("epgeneral_mqtav.node.MqttPublisher") as mqtt:
            bridge.return_value.validate_sources.side_effect = RuntimeError("missing ROS message")
            self.assertEqual(run(["--config-dir", str(self.folder)], rospy_module=ros), 1)
        ros.init_node.assert_not_called()
        mqtt.assert_not_called()

    def test_shutdown_hook_and_finally_cleanup_are_idempotent(self):
        self.files()
        ros = MagicMock()
        hook = []
        ros.on_shutdown.side_effect = hook.append
        ros.spin.side_effect = lambda: hook[0]()
        with patch("epgeneral_mqtav.node.build_logger"), patch("epgeneral_mqtav.node.RosBridge") as bridge, patch("epgeneral_mqtav.node.MqttPublisher") as mqtt:
            self.assertEqual(run(["--config-dir", str(self.folder)], rospy_module=ros), 0)
        bridge.return_value.stop.assert_called_once_with()
        mqtt.return_value.stop.assert_called_once_with()
        self.assertEqual(ros.Timer.return_value.shutdown.call_count, 2)

    def test_bridge_stop_releases_timers_and_subscribers_once(self):
        self.data["ros"]["connection_mode"] = "freshness"
        bridge = self.bridge(self.config())
        bridge.start()
        bridge.stop()
        bridge.stop()
        self.ros.Timer.return_value.shutdown.assert_called_once_with()
        self.assertEqual(self.ros.Subscriber.return_value.unregister.call_count, 2)

    def test_all_declared_profiles_load_with_explicit_modes_and_units(self):
        layout = json.loads((ROOT / "edge-layout.json").read_text(encoding="utf-8"))
        ids = set()
        for name, profile in layout["profiles"].items():
            with self.subTest(profile=name):
                folder = ROOT / profile["path"] / "config"
                config = load_config(folder / "epgeneral_mqtav.yaml", folder / "device.yaml")
                self.assertEqual(config.schema_version, 2)
                if config.ros.battery.enabled:
                    self.assertNotEqual(config.ros.battery.percentage_unit, "legacy_auto")
                self.assertNotIn(config.device.device_id, ids)
                ids.add(config.device.device_id)
                self.assertEqual(config.topic("status"), "mqtav/{0}/status".format(config.device.device_id))
                if config.ros.mission.enabled:
                    task = yaml.safe_load((folder / "task_control.yaml").read_text(encoding="utf-8"))
                    self.assertEqual(config.ros.mission.topic, task["ros"]["status_topic"])
        self.assertEqual(len(ids), len(layout["profiles"]))

    def test_generic_template_loads_without_device_specific_code(self):
        folder = SHARED / "templates/mqtav_generic"
        config = load_config(folder / "epgeneral_mqtav.yaml", folder / "device.yaml")
        self.assertEqual(config.ros.connection_mode, "heartbeat")
        self.assertFalse(config.ros.state.enabled)
        self.assertEqual(config.ros.connection.topic, "/devices/DEVICE_EXAMPLE/heartbeat")

    def test_source_retains_python36_syntax_compatibility(self):
        for path in (ROOT / "epgeneral_mqtav/src/epgeneral_mqtav").glob("*.py"):
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 6))

    def test_extreme_numeric_config_is_reported_as_config_error(self):
        self.data["mqtt"]["heartbeat_hz"] = 10 ** 400
        with self.assertRaisesRegex(ConfigError, "heartbeat_hz"):
            self.config()

    def test_boolean_schema_is_not_an_integer_version(self):
        self.device["schema_version"] = True
        with self.assertRaisesRegex(ConfigError, "schema_version"):
            self.config()

    def test_retry_after_failed_type_validation_still_opens_no_subscriptions(self):
        def resolver(name):
            if name == "sensor_msgs/BatteryState":
                raise RuntimeError("missing battery message")
            return object
        bridge = self.bridge(self.config(), resolver)
        for _ in range(2):
            with self.assertRaisesRegex(RuntimeError, "missing battery"):
                bridge.start()
        self.ros.Subscriber.assert_not_called()

    def test_ignored_connected_field_is_not_required_by_disabled_mode(self):
        self.data["ros"]["connection_mode"] = "disabled"
        self.data["ros"]["battery"] = {"enabled": False}
        class StateWithoutConnection(object):
            __slots__ = ("armed", "system_status", "mode")
            def __init__(self):
                self.armed, self.system_status, self.mode = False, 0, ""
        bridge = self.bridge(self.config(), lambda _name: StateWithoutConnection)
        bridge.start()
        self.assertEqual(self.ros.Subscriber.call_count, 1)

    def test_uav_bringup_explicitly_selects_installed_profile_configuration(self):
        from xml.etree import ElementTree
        path = ROOT / "devices/uav/profiles/uav_001/launch/uav_001_bringup.launch"
        launch = ElementTree.parse(path).getroot()
        mqtt = [item for item in launch.findall("include")
                if item.attrib["file"].endswith("/epgeneral_mqtav.launch")]
        self.assertEqual(len(mqtt), 1)
        arguments = {arg.attrib["name"]: arg.attrib["value"] for arg in mqtt[0].findall("arg")}
        self.assertEqual(arguments["config_dir"], "$(find epgeneral_device_config)/config")
        self.assertNotIn("config_file", arguments)
        self.assertNotIn("device_config_file", arguments)
