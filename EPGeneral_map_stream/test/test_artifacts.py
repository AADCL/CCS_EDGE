import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
import zipfile
from unittest import mock

import yaml


from epgeneral_map_stream.artifacts import (
    ArtifactError, ArtifactHttpServer, CommandRunner, SessionPaths, build_archive, file_fingerprint,
    require_fresh_file,
    validate_artifacts, wait_for_stable_artifacts,
)
from epgeneral_map_stream.config import load_config

try:
    from .test_paths import device_config_path
except ImportError:
    from test_paths import device_config_path


PACKAGE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAPPING = os.path.join(
    os.path.dirname(PACKAGE), "EPGeneral_device_config", "config", "map_stream.yaml")
DEVICE = device_config_path(PACKAGE)


def write_outputs(paths):
    with io.open(paths.pcd_path, "w", encoding="ascii") as stream:
        stream.write("VERSION .7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\n")
        stream.write("COUNT 1 1 1\nWIDTH 1\nHEIGHT 1\nPOINTS 1\nDATA ascii\n0 0 0\n")
    with io.open(paths.pgm_path, "wb") as stream:
        stream.write(b"P5\n2 2\n255\n" + bytes((0, 254, 205, 254)))
    with io.open(paths.yaml_path, "w", encoding="utf-8") as stream:
        yaml.safe_dump({
            "image": "map.pgm", "resolution": 0.1, "origin": [0.0, 0.0, 0.0],
            "negate": 0, "occupied_thresh": 0.65, "free_thresh": 0.196,
        }, stream)


class ArtifactTests(unittest.TestCase):
    def test_integration_checks_use_dedicated_timeout(self):
        runner = CommandRunner(self.config)
        commands = {
            "check_fast_lio": [sys.executable],
            "check_save_map": [sys.executable],
            "check_pgm": [sys.executable],
        }
        completed = mock.Mock(returncode=0, stdout="")
        with mock.patch("epgeneral_map_stream.artifacts.subprocess.run",
                        return_value=completed) as run:
            runner.check(commands)
        self.assertEqual(
            [call.kwargs["timeout"] for call in run.call_args_list],
            [self.config["integration_check_timeout_seconds"]] * 3)

    def test_path_command_is_resolved_without_mutating_arguments(self):
        runner = CommandRunner(self.config)
        arguments = ["rosrun", "epgeneral_uav_integration", "uav_stage_client.py"]
        resolved = os.path.join(self.temp.name, "rosrun")
        completed = mock.Mock(returncode=0, stdout="native packages available")
        with mock.patch("epgeneral_map_stream.artifacts.shutil.which", return_value=resolved), \
                mock.patch("epgeneral_map_stream.artifacts.os.path.isfile", return_value=True), \
                mock.patch("epgeneral_map_stream.artifacts.os.access", return_value=True), \
                mock.patch("epgeneral_map_stream.artifacts.subprocess.run",
                           return_value=completed) as run:
            output = runner.run(arguments, timeout=3.0)
        self.assertEqual(output, "native packages available")
        self.assertEqual(arguments[0], "rosrun")
        self.assertEqual(run.call_args.args[0][0], resolved)
        self.assertEqual(run.call_args.args[0][1:], arguments[1:])

    def test_missing_path_command_is_rejected(self):
        runner = CommandRunner(self.config)
        with mock.patch("epgeneral_map_stream.artifacts.shutil.which", return_value=None), \
                mock.patch("epgeneral_map_stream.artifacts.subprocess.run") as run:
            with self.assertRaisesRegex(ArtifactError, "unavailable: missing-command"):
                runner.run(["missing-command"])
        run.assert_not_called()

    def test_non_executable_path_command_is_rejected(self):
        runner = CommandRunner(self.config)
        resolved = os.path.join(self.temp.name, "rosrun")
        with mock.patch("epgeneral_map_stream.artifacts.shutil.which", return_value=resolved), \
                mock.patch("epgeneral_map_stream.artifacts.os.path.isfile", return_value=True), \
                mock.patch("epgeneral_map_stream.artifacts.os.access", return_value=False), \
                mock.patch("epgeneral_map_stream.artifacts.subprocess.run") as run:
            with self.assertRaisesRegex(ArtifactError, "unavailable: rosrun"):
                runner.run(["rosrun"])
        run.assert_not_called()

    def test_explicit_command_path_is_checked_without_path_lookup(self):
        runner = CommandRunner(self.config)
        executable = os.path.join(self.temp.name, "integration-check")
        completed = mock.Mock(returncode=0, stdout="ok")
        with mock.patch("epgeneral_map_stream.artifacts.shutil.which") as which, \
                mock.patch("epgeneral_map_stream.artifacts.os.path.isfile", return_value=True) as isfile, \
                mock.patch("epgeneral_map_stream.artifacts.os.access", return_value=True) as access, \
                mock.patch("epgeneral_map_stream.artifacts.subprocess.run",
                           return_value=completed) as run:
            self.assertEqual(runner.run([executable]), "ok")
        which.assert_not_called()
        isfile.assert_called_once_with(executable)
        access.assert_called_once_with(executable, os.X_OK)
        self.assertEqual(run.call_args.args[0], [executable])

    def test_source_pcd_must_change_after_session_start(self):
        source = os.path.join(self.temp.name, "source.pcd")
        with io.open(source, "wb") as stream:
            stream.write(b"old")
        baseline = file_fingerprint(source)
        with self.assertRaisesRegex(ArtifactError, "not regenerated"):
            require_fresh_file(source, baseline, baseline["mtime_ns"])
        with io.open(source, "wb") as stream:
            stream.write(b"new mapping data")
        current = require_fresh_file(source, baseline, baseline["mtime_ns"])
        self.assertNotEqual(current["sha256"], baseline["sha256"])

    def test_optional_log_root_is_separate_from_artifacts(self):
        log_root = os.path.join(self.temp.name, "runtime-logs")
        paths = SessionPaths(self.config, self.identity, log_root=log_root)
        paths.prepare(1)
        self.assertEqual(paths.session_dir, os.path.join(self.temp.name, self.identity["session_id"]))
        self.assertEqual(paths.log_dir, os.path.join(log_root, self.identity["session_id"]))
        self.assertTrue(os.path.isdir(paths.log_dir))
        paths.reset()
        self.assertTrue(os.path.isdir(paths.log_dir))
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = dict(load_config(MAPPING, DEVICE))
        self.config.update(
            workspace_root=self.temp.name, min_free_bytes=1,
            artifact_poll_seconds=0.001, artifact_stable_polls=2,
            artifact_generation_timeout_seconds=1.0,
        )
        self.identity = {"map_id": "map-1", "session_id": "b" * 32}
        self.paths = SessionPaths(self.config, self.identity)
        self.paths.prepare(1)


    def test_joint_identity_is_recorded_in_manifest(self):
        write_outputs(self.paths)
        identity = dict(
            self.identity, job_id="job-1", role="secondary",
            primary_device_id="UGV_001",
        )
        build_archive(self.paths, self.config, identity)
        with zipfile.ZipFile(self.paths.archive_path) as archive:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        self.assertEqual(manifest["job_id"], "job-1")
        self.assertEqual(manifest["role"], "secondary")
        self.assertEqual(manifest["primary_device_id"], "UGV_001")

    def test_invalid_yaml_and_symlink_are_rejected(self):
        write_outputs(self.paths)
        with io.open(self.paths.yaml_path, "w", encoding="utf-8") as stream:
            stream.write("image: wrong.pgm\n")
        with self.assertRaises(ArtifactError):
            validate_artifacts(self.paths, self.config["max_artifact_bytes"])

    def test_http_token_and_range(self):
        write_outputs(self.paths)
        build_archive(self.paths, self.config, self.identity)
        server = ArtifactHttpServer("127.0.0.1", 0)
        server.start()
        self.addCleanup(server.close)
        token, unused_expiry = server.register(self.paths.archive_path, 60)
        url = "http://127.0.0.1:%d/mapping/result.zip?token=%s" % (server.port, token)
        request = urllib.request.Request(url, headers={"Range": "bytes=10-19"})
        with urllib.request.urlopen(request, timeout=2) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(len(response.read()), 10)
            self.assertTrue(response.headers["Content-Range"].startswith("bytes 10-19/"))
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(url.replace(token, "wrong"), timeout=2)
        self.assertEqual(caught.exception.code, 404)

    def test_invalid_range_returns_416(self):
        write_outputs(self.paths)
        build_archive(self.paths, self.config, self.identity)
        server = ArtifactHttpServer("127.0.0.1", 0)
        server.start()
        self.addCleanup(server.close)
        token, unused_expiry = server.register(self.paths.archive_path, 60)
        url = "http://127.0.0.1:%d/mapping/result.zip?token=%s" % (server.port, token)
        request = urllib.request.Request(url, headers={"Range": "bytes=999999-"})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=2)
        self.assertEqual(caught.exception.code, 416)
