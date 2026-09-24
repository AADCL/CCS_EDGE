import json
import os
import tempfile
import time
import types
import unittest
from unittest.mock import Mock, patch

from epgeneral_task_control.wheeltec_control import (
    WheeltecControlAuthority,
    localization_is_healthy,
    localized_state_available,
)


def response(success=True, message="ok"):
    return types.SimpleNamespace(success=success, message=message)


class WheeltecStateTests(unittest.TestCase):
    def test_localized_state_requires_schema_status_and_map(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "state.json")
            with open(path, "w") as stream:
                json.dump(
                    {"schema_version": 2, "status": "localized", "map_id": "factory_a"},
                    stream,
                )
            self.assertTrue(localized_state_available(path))
            with open(path, "w") as stream:
                json.dump(
                    {"schema_version": 2, "status": "standby", "map_id": "factory_a"},
                    stream,
                )
            self.assertFalse(localized_state_available(path))

    def test_localization_requires_fresh_odom(self):
        self.assertTrue(localization_is_healthy(True, 9.5, 10.0, 0.5))
        self.assertFalse(localization_is_healthy(True, 9.49, 10.0, 0.5))
        self.assertFalse(localization_is_healthy(False, 9.9, 10.0, 0.5))


class WheeltecAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.node = WheeltecControlAuthority(Mock(), {
            "state_file": "/unused",
            "odom_timeout_seconds": 1.0,
        })
        self.node.safety_reset = Mock(return_value=response())
        self.node.safety_arm = Mock(return_value=response())
        self.node.safety_stop = Mock(return_value=response())
        self.node.driver_enable = Mock(return_value=response())
        self.node.driver_stop = Mock(return_value=response())
        self.node.driver_reset = Mock(return_value=response())
        self.node._publish_state = Mock()
        self.responses = types.SimpleNamespace(
            SetBoolResponse=lambda **kwargs: types.SimpleNamespace(**kwargs),
            TriggerResponse=lambda **kwargs: types.SimpleNamespace(**kwargs),
        )

    def modules(self):
        return patch.dict(
            "sys.modules",
            {"std_srvs.srv": self.responses},
        )

    def test_native_auto_release_keeps_gate_eligible_only_with_fresh_driver(self):
        self.node.config["driver_auto_acquire"] = True
        self.node.desired_enabled = True
        self.node.driver_enabled = False
        self.node.driver_received_at = 99.5
        self.node.enabled_pub = Mock()
        msgs = types.SimpleNamespace(Bool=lambda **kw: types.SimpleNamespace(**kw))
        with patch.dict("sys.modules", {"std_msgs.msg": msgs}), patch.object(self.node, "_localized", return_value=True), patch("epgeneral_task_control.wheeltec_control.time.monotonic", return_value=100.0):
            WheeltecControlAuthority._publish_state(self.node)
            self.assertTrue(self.node.enabled_pub.publish.call_args[0][0].data)
            self.node.driver_received_at = 98.0
            WheeltecControlAuthority._publish_state(self.node)
            self.assertFalse(self.node.enabled_pub.publish.call_args[0][0].data)
            self.node.driver_received_at = 99.5
            self.node.desired_enabled = False
            WheeltecControlAuthority._publish_state(self.node)
            self.assertFalse(self.node.enabled_pub.publish.call_args[0][0].data)

    def test_enable_checks_localization_then_arms_driver_and_gate(self):
        with patch.object(self.node, "_localized", return_value=True), self.modules():
            result = self.node._enable_callback(types.SimpleNamespace(data=True))
        self.assertTrue(result.success)
        self.node.safety_reset.assert_called_once_with()
        self.node.driver_enable.assert_called_once_with(True)
        self.node.safety_arm.assert_called_once_with()
        self.assertTrue(self.node.desired_enabled)

    def test_failed_arm_latches_both_stop_interfaces(self):
        self.node.safety_arm.return_value = response(False, "arm denied")
        with patch.object(self.node, "_localized", return_value=True), self.modules():
            result = self.node._enable_callback(types.SimpleNamespace(data=True))
        self.assertFalse(result.success)
        self.node.safety_stop.assert_called_once_with()
        self.node.driver_stop.assert_called_once_with()
        self.assertFalse(self.node.desired_enabled)

    def test_release_stops_gate_before_restoring_manual_driver(self):
        order = []
        self.node.safety_stop.side_effect = lambda: order.append("safety") or response()
        self.node.driver_enable.side_effect = (
            lambda enabled: order.append(("driver", enabled)) or response())
        with self.modules():
            result = self.node._enable_callback(types.SimpleNamespace(data=False))
        self.assertTrue(result.success)
        self.assertEqual(order, ["safety", ("driver", False)])

    def test_release_succeeds_when_absent_gate_and_driver_confirms_manual(self):
        self.node.safety_stop.side_effect = RuntimeError("service unavailable")
        with self.modules():
            result = self.node._enable_callback(types.SimpleNamespace(data=False))
        self.assertTrue(result.success)
        self.assertIn("safety gate was unavailable", result.message)
        self.node.driver_enable.assert_called_once_with(False)
        self.assertFalse(self.node.desired_enabled)

    def test_release_fails_when_driver_cannot_confirm_manual(self):
        self.node.driver_enable.return_value = response(False, "manual denied")
        with self.modules():
            result = self.node._enable_callback(types.SimpleNamespace(data=False))
        self.assertFalse(result.success)
        self.assertIn("driver manual release refused", result.message)

    def test_fault_stop_latches_gate_and_driver(self):
        with self.modules():
            result = self.node._stop_callback(object())
        self.assertTrue(result.success)
        self.node.safety_stop.assert_called_once_with()
        self.node.driver_stop.assert_called_once_with()

    def test_reset_returns_to_manual(self):
        self.node.desired_enabled = True
        with self.modules():
            result = self.node._reset_callback(object())
        self.assertTrue(result.success)
        self.node.driver_reset.assert_called_once_with()
        self.node.safety_reset.assert_called_once_with()
        self.assertFalse(self.node.desired_enabled)

    def test_reset_succeeds_without_running_safety_gate(self):
        self.node.desired_enabled = True
        self.node.safety_reset.side_effect = RuntimeError("service unavailable")
        with self.modules():
            result = self.node._reset_callback(object())
        self.assertTrue(result.success)
        self.assertIn("safety gate was unavailable", result.message)
        self.node.driver_reset.assert_called_once_with()
        self.assertFalse(self.node.desired_enabled)

    def test_reset_fails_when_driver_reset_is_refused(self):
        self.node.driver_reset.return_value = response(False, "fault persists")
        with self.modules():
            result = self.node._reset_callback(object())
        self.assertFalse(result.success)
        self.assertIn("driver authority reset refused", result.message)

    def test_driver_only_mode_uses_chassis_services_for_full_lifecycle(self):
        self.node.config["safety_gate_enabled"] = False
        self.node.safety_reset = self.node.safety_arm = self.node.safety_stop = None
        with patch.object(self.node, "_localized", return_value=True), self.modules():
            self.assertTrue(self.node._enable_callback(types.SimpleNamespace(data=True)).success)
            self.assertTrue(self.node._enable_callback(types.SimpleNamespace(data=False)).success)
            self.assertTrue(self.node._stop_callback(object()).success)
            self.assertTrue(self.node._reset_callback(object()).success)
        self.node.driver_enable.assert_any_call(True)
        self.node.driver_enable.assert_any_call(False)
        self.node.driver_stop.assert_called_once_with()
        self.node.driver_reset.assert_called_once_with()
        self.assertFalse(self.node.desired_enabled)

    def test_driver_only_enable_failure_latches_chassis_stop(self):
        self.node.config["safety_gate_enabled"] = False
        self.node.safety_reset = self.node.safety_arm = self.node.safety_stop = None
        self.node.driver_enable.return_value = response(False, "authority denied")
        with patch.object(self.node, "_localized", return_value=True), self.modules():
            result = self.node._enable_callback(types.SimpleNamespace(data=True))
        self.assertFalse(result.success)
        self.node.driver_stop.assert_called_once_with()
        self.assertFalse(self.node.desired_enabled)

    def test_driver_only_stop_reports_driver_failure(self):
        self.node.config["safety_gate_enabled"] = False
        self.node.safety_stop = None
        self.node.driver_stop.return_value = response(False, "serial stop denied")
        with self.modules():
            result = self.node._stop_callback(object())
        self.assertFalse(result.success)
        self.assertIn("serial stop denied", result.message)


if __name__ == "__main__":
    unittest.main()
