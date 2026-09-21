"""Unit tests for the UAV read-only mapping integration preflight."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "devices/uav/profiles/uav_001/scripts"
SPEC = importlib.util.spec_from_file_location("uav_preflight_test", SCRIPTS / "preflight.py")
PREFLIGHT = importlib.util.module_from_spec(SPEC)
with mock.patch.dict(sys.modules, {"rospkg": types.SimpleNamespace()}):
    SPEC.loader.exec_module(PREFLIGHT)


class MappingIntegrationPreflightTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.install = Path(self.directory.name) / "install"
        (self.install / "share/epgeneral_uav_integration").mkdir(parents=True)
        self.client = self.install / "lib/epgeneral_uav_integration/uav_stage_client.py"
        self.client.parent.mkdir(parents=True)
        self.client.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        self.client.chmod(0o755)
        self.find_node = mock.Mock(return_value=[str(self.client)])
        roslib = types.ModuleType("roslib")
        packages = types.ModuleType("roslib.packages")
        packages.find_node = self.find_node
        roslib.packages = packages
        modules = mock.patch.dict(
            sys.modules, {"roslib": roslib, "roslib.packages": packages})
        modules.start()
        self.addCleanup(modules.stop)

    def test_resolves_install_space_client_and_runs_only_offline_check(self):
        completed = subprocess.CompletedProcess([], 0, "native packages available\n", "")
        before = sorted(path.relative_to(self.install) for path in self.install.rglob("*"))
        with mock.patch.object(PREFLIGHT.shutil, "which",
                return_value="/opt/ros/noetic/bin/rosrun"), \
                mock.patch.object(PREFLIGHT.subprocess, "run",
                    return_value=completed) as run:
            PREFLIGHT._check_mapping_integration()

        self.find_node.assert_called_once_with(
            "epgeneral_uav_integration", "uav_stage_client.py")
        run.assert_called_once()
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["/opt/ros/noetic/bin/rosrun",
            "epgeneral_uav_integration", "uav_stage_client.py", "offline_check"])
        self.assertIs(kwargs["stdin"], subprocess.DEVNULL)
        self.assertIs(kwargs["stdout"], subprocess.PIPE)
        self.assertIs(kwargs["stderr"], subprocess.PIPE)
        self.assertEqual(kwargs["timeout"], 10)
        self.assertEqual(kwargs["env"]["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertEqual(
            before, sorted(path.relative_to(self.install) for path in self.install.rglob("*")))
        self.assertFalse(
            (self.install / "share/epgeneral_uav_integration/scripts").exists())

    def test_missing_rosrun_is_concise_and_does_not_spawn(self):
        with mock.patch.object(PREFLIGHT.shutil, "which", return_value=None), \
                mock.patch.object(PREFLIGHT.subprocess, "run") as run:
            with self.assertRaisesRegex(
                    RuntimeError,
                    r"^mapping integration unavailable: rosrun not found in PATH$"):
                PREFLIGHT._check_mapping_integration()
        run.assert_not_called()
        self.find_node.assert_not_called()

    def test_unresolvable_client_is_concise_and_does_not_spawn(self):
        self.find_node.return_value = []
        with mock.patch.object(PREFLIGHT.shutil, "which",
                return_value="/usr/bin/rosrun"), \
                mock.patch.object(PREFLIGHT.subprocess, "run") as run:
            with self.assertRaisesRegex(
                    RuntimeError,
                    r"^mapping integration unavailable: uav_stage_client.py could not be resolved by ROS$"):
                PREFLIGHT._check_mapping_integration()
        run.assert_not_called()

    def test_offline_failure_keeps_only_a_short_final_line(self):
        completed = subprocess.CompletedProcess(
            [], 1, "", "verbose detail\nmissing native package\n")
        with mock.patch.object(PREFLIGHT.shutil, "which",
                return_value="/usr/bin/rosrun"), \
                mock.patch.object(PREFLIGHT.subprocess, "run",
                    return_value=completed):
            with self.assertRaisesRegex(
                    RuntimeError,
                    r"^mapping integration offline_check failed: missing native package$"):
                PREFLIGHT._check_mapping_integration()

    def test_offline_check_timeout_is_bounded_and_concise(self):
        with mock.patch.object(PREFLIGHT.shutil, "which",
                return_value="/usr/bin/rosrun"), \
                mock.patch.object(PREFLIGHT.subprocess, "run",
                    side_effect=subprocess.TimeoutExpired("rosrun", 10)):
            with self.assertRaisesRegex(
                    RuntimeError,
                    r"^mapping integration offline_check timed out after 10s$"):
                PREFLIGHT._check_mapping_integration()


if __name__ == "__main__":
    unittest.main(verbosity=2)
