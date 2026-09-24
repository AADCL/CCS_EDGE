"""Linux supervisor harness: no ROS nodes, sockets or flight commands are created."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

SCRIPTS = Path(os.environ.get("UAV_PROFILE_SCRIPTS",
    str(Path(__file__).resolve().parents[1] / "devices/uav/profiles/uav_001/scripts")))
sys.path.insert(0, str(SCRIPTS))
from session_log import SessionLog


class LogTests(unittest.TestCase):
    def test_repeated_warning_is_throttled_but_changes_are_immediate(self):
        log = SessionLog()
        with tempfile.TemporaryDirectory() as directory:
            log.attach(Path(directory))
            output = io.StringIO()
            with contextlib.redirect_stdout(output), mock.patch("session_log.time.monotonic",
                    side_effect=[0, 2, 29, 30, 31]):
                for _ in range(4):
                    log.repeated("guard", "WARN", "retaining controller")
                log.repeated("guard", "WARN", "state changed")
            self.assertEqual(output.getvalue().count("retaining controller"), 2)
            self.assertIn("state changed", output.getvalue())
            saved = (Path(directory) / "startup.log").read_text()
            self.assertEqual(saved.count("[WARN]"), 3)
            self.assertRegex(saved, r"\d{4}-\d{2}-\d{2}T")

    def test_exception_details_go_to_file(self):
        with tempfile.TemporaryDirectory() as directory:
            log = SessionLog()
            log.attach(Path(directory))
            try:
                raise ValueError("diagnostic detail")
            except ValueError:
                log.exception()
            self.assertIn("Traceback", (Path(directory) / "runtime_monitor.log").read_text())


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux process ownership and locks")
class SupervisorTests(unittest.TestCase):
    def setUp(self):
        with mock.patch.dict(sys.modules, {"preflight": types.SimpleNamespace(check=mock.Mock())}):
            spec = importlib.util.spec_from_file_location("uav_supervisor_test", SCRIPTS / "supervisor.py")
            self.mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.mod)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.mod.ROOT = Path(self.directory.name)
        self.mod.LOG = SessionLog()
        self.output, self.errors = io.StringIO(), io.StringIO()

    def invoke(self, *args):
        with mock.patch.object(sys, "argv", ["supervisor.py"] + list(args)), \
                contextlib.redirect_stdout(self.output), contextlib.redirect_stderr(self.errors):
            return self.mod.run()

    def test_both_preflight_aliases_are_read_only(self):
        for flag in ("--check", "--preflight"):
            self.assertEqual(self.invoke(flag), 0)
        self.assertEqual(list(self.mod.ROOT.iterdir()), [])
        self.assertEqual(self.output.getvalue().count("[OK]"), 2)

    def test_duplicate_start_is_concise_and_does_not_launch(self):
        with mock.patch.object(self.mod.fcntl, "flock", side_effect=BlockingIOError), \
                mock.patch.object(self.mod.subprocess, "Popen") as spawn:
            self.assertEqual(self.invoke(), 1)
            spawn.assert_not_called()
        self.assertIn("already running", self.errors.getvalue())
        self.assertNotIn("Traceback", self.errors.getvalue())
        self.assertFalse((self.mod.ROOT / "logs").exists())

    def test_stale_stop_does_not_signal_any_process(self):
        record = self.mod.ROOT / "run/managed/startup.json"
        record.parent.mkdir(parents=True)
        record.write_text(json.dumps({"pid": 999999999}))
        with mock.patch.object(self.mod.os, "kill") as kill:
            self.assertEqual(self.invoke("--stop"), 0)
            kill.assert_not_called()
        self.assertIn("stale PID", self.output.getvalue())

    def exercise(self, failure=False, node_mode="healthy", airborne=False):
        clock = [0.]
        signals = {}
        state_callback = []
        monitors = [0]
        safe = [not airborne]
        children = [mock.Mock(pid=70001, returncode=None), mock.Mock(pid=70002, returncode=None)]
        for child in children:
            child.poll.return_value = None
        if failure:
            children[1].poll.return_value = 7
            children[1].returncode = 7
        rospy = types.SimpleNamespace(init_node=mock.Mock(),
            Subscriber=lambda topic, cls, callback: state_callback.append(callback))
        required = ["/mavros", "/livox_lidar_publisher2", "/epgeneral_mqtav",
            "/epgeneral_udp_telemetry", "/epgeneral_map_stream", "/epgeneral_relocalization",
            "/epgeneral_task_control", "/epgeneral_video_srt", "/uav_stage_manager", "/uav_task_adapter"]

        def sleep(seconds):
            clock[0] += 3
            if airborne:
                safe[0] = clock[0] >= 39
                if state_callback:
                    state_callback[0](types.SimpleNamespace(data=json.dumps(
                        {"controller": True, "ground_safe": safe[0]})))
                signals[self.mod.signal.SIGTERM](None, None)
            elif monitors[0] >= 2 and node_mode != "missing":
                signals[self.mod.signal.SIGTERM](None, None)
            if clock[0] > 90:
                raise AssertionError("harness timed out")

        def node_state(*args):
            monitors[0] += 1
            nodes = [] if node_mode == "missing" or (node_mode == "recover" and monitors[0] == 1) else required
            return [1, "ok", [[["/test", nodes]], [], []]]

        def signal_children(*args):
            if airborne:
                self.assertTrue(safe[0], "airborne controller must not be stopped")

        proxy = mock.Mock()
        proxy.getSystemState.side_effect = node_state
        with mock.patch.dict(sys.modules, {"rospy": rospy,
                "std_msgs": types.ModuleType("std_msgs"),
                "std_msgs.msg": types.SimpleNamespace(String=object)}), \
                mock.patch.dict(os.environ, {"ROS_MASTER_URI": "http://unused:11311"}), \
                mock.patch.object(self.mod, "port_free"), \
                mock.patch.object(self.mod.subprocess, "Popen", side_effect=children) as spawn, \
                mock.patch.object(self.mod.socket, "create_connection", return_value=mock.MagicMock()), \
                mock.patch.object(self.mod.socket, "setdefaulttimeout"), \
                mock.patch.object(self.mod.signal, "signal", side_effect=lambda n, f: signals.update({n: f})), \
                mock.patch.object(self.mod.os, "killpg", side_effect=signal_children) as kill, \
                mock.patch.object(self.mod.time, "monotonic", side_effect=lambda: clock[0]), \
                mock.patch.object(self.mod.time, "sleep", side_effect=sleep), \
                mock.patch("xmlrpc.client.ServerProxy", return_value=proxy):
            code = self.invoke("--flight" if airborne else "--static")
        self.assertEqual(spawn.call_count, 2)
        self.assertGreater(kill.call_count, 0)
        self.assertFalse((self.mod.ROOT / "run/managed/startup.json").exists())
        self.assertFalse((self.mod.ROOT / "run/managed/startup.pid").exists())
        return code, (self.mod.ROOT / "logs/latest").resolve()

    def test_normal_lifecycle_has_durable_summary_and_no_poll_spam(self):
        code, logs = self.exercise()
        self.assertEqual(code, 0)
        text = (logs / "startup.log").read_text()
        self.assertIn("mode=static", text)
        self.assertIn("required ROS nodes are registered", text)
        self.assertIn("processes stopped", text)
        self.assertTrue((logs / "roscore.log").exists())
        self.assertTrue((logs / "bringup.log").exists())
        self.assertNotIn("Traceback", self.errors.getvalue())

    def test_child_failure_is_nonzero_and_preserves_details(self):
        code, logs = self.exercise(failure=True)
        self.assertEqual(code, 1)
        self.assertIn("exit=7", self.errors.getvalue())
        self.assertNotIn("Traceback", self.errors.getvalue())
        self.assertIn("Traceback", (logs / "runtime_monitor.log").read_text())

    def test_monitor_recovery_keeps_retry_detail_out_of_console(self):
        code, logs = self.exercise(node_mode="recover")
        self.assertEqual(code, 0)
        self.assertIn("monitoring recovered", self.output.getvalue())
        self.assertNotIn("Missing runtime nodes", self.output.getvalue())
        self.assertIn("attempt=1/3", (logs / "runtime_monitor.log").read_text())

    def test_missing_nodes_report_failure_after_retries(self):
        code, logs = self.exercise(node_mode="missing")
        self.assertEqual(code, 1)
        self.assertIn("after repeated checks", self.errors.getvalue())
        self.assertIn("attempt=3/3", (logs / "runtime_monitor.log").read_text())

    def test_airborne_shutdown_is_retained_with_bounded_warning(self):
        code, logs = self.exercise(airborne=True)
        self.assertEqual(code, 0)
        self.assertIn("Shutdown refused", self.output.getvalue())
        self.assertLessEqual(self.output.getvalue().count("Shutdown refused"), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
