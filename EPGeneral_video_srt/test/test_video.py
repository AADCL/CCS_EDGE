import copy
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from epgeneral_video_srt.config import ConfigError, normalize, load_config, listener_uri, capture_command
from epgeneral_video_srt.application import run, native_command, runtime_environment, required_plugins
from epgeneral_video_srt.rtsp_backend import pipeline_description

ROOT = Path(__file__).resolve().parents[2]
IDENTITY = {"schema_version": 1, "device": {"id": "ROBOT_09", "ip": "192.0.2.9"}}


class VideoConfigTests(unittest.TestCase):
    def base(self, **changes):
        c = dict(schema_version=2, enabled=True, input_mode="ros_image",
                 image_topic="/devices/{device_id}/image", output_width=640, output_height=480)
        c.update(changes)
        return c

    def test_identity_and_topics_are_resolved_per_instance(self):
        first = normalize(self.base(runtime={"status_topic": "/video/{device_id}/status"}), IDENTITY)
        other = {"schema_version": 1, "device": {"id": "SECOND", "ip": "2001:db8::9"}}
        second = normalize(self.base(), other)
        self.assertEqual(first["image_topic"], "/devices/ROBOT_09/image")
        self.assertEqual(first["runtime"]["status_topic"], "/video/ROBOT_09/status")
        self.assertEqual(second["image_topic"], "/devices/SECOND/image")
        self.assertEqual(second["device_ip"], "2001:db8::9")

    def test_invalid_inputs_fail_before_starting(self):
        cases = [dict(framerate=True), dict(framerate=0), dict(bitrate_kbps=float("inf")),
                 dict(output_width=641), dict(output_height=0), dict(rotation_degrees=90),
                 dict(srt_port=65536), dict(srt_bind_address='0.0.0.0" ! fakesink'),
                 dict(frame_timeout_seconds=float("nan")), dict(enabled="false"),
                 dict(image_topic="/{unknown}/image"), dict(input_mode="usb"),
                 dict(schema_version=99), dict(framrate=30), dict(srt_bind_address=1),
                 dict(deployment={"enabled": 1}),
                 dict(image_message_type="sensor_msgs/CompressedImage"),
                 dict(runtime={"reconnect_interval_seconds": 0}),
                 dict(runtime={"decoder_preload": "/lib/a.so"}),
                 dict(runtime={"decoder_preload": ["/lib/a b.so"]}),
                 dict(runtime={"unknown": 1})]
        for values in cases:
            with self.subTest(values=values), self.assertRaises(ConfigError):
                normalize(self.base(**values), IDENTITY)

    def test_identity_ip_must_be_text_not_packed_integer(self):
        for ip in [True, 1, None]:
            identity = copy.deepcopy(IDENTITY)
            identity["device"]["ip"] = ip
            with self.subTest(ip=ip), self.assertRaises(ConfigError):
                normalize(self.base(), identity)

    def test_rtsp_environment_name_has_valid_type(self):
        with self.assertRaises(ConfigError):
            normalize(self.base(input_mode="rtsp", rtsp_uri_env=123), IDENTITY)

    def test_schema2_does_not_infer_input_source(self):
        with self.assertRaises(ConfigError):
            normalize({"schema_version": 2}, IDENTITY)

    def test_legacy_raw_compressed_and_rtsp_are_supported(self):
        for mode, raw in [
                ("ros_image", {"image_topic": "/raw"}),
                ("ros_compressed", {"image_topic": "/compressed", "image_message_type": "sensor_msgs/CompressedImage"}),
                ("rtsp", {"input_mode": "rtsp", "rtsp_uri": "rtsp://192.0.2.1/live"})]:
            with self.subTest(mode=mode):
                self.assertEqual(normalize(raw, IDENTITY)["input_mode"], mode)

    def test_conflicting_enable_flags_rejected(self):
        with self.assertRaises(ConfigError):
            normalize(self.base(enabled=True, deployment={"enabled": False}), IDENTITY)

    def test_disabled_legacy_deployment_is_respected(self):
        self.assertFalse(normalize({"deployment": {"enabled": False}}, IDENTITY)["enabled"])

    def test_rtsp_codec_transport_rotation_and_address_are_effective(self):
        c = normalize(self.base(input_mode="rtsp", rtsp_uri="rtsp://192.0.2.2/live",
                                rtsp_codec="h264", rtsp_transport="udp", rtsp_latency_ms=250,
                                rotation_degrees=180, srt_bind_address="::1", srt_latency_ms=500), IDENTITY)
        pipe = pipeline_description(c)
        for fragment in ["rtph264depay", "avdec_h264", "protocols=udp", "latency=250",
                         "videoflip method=rotate-180", "srt://[::1]:9000", "latency=500"]:
            self.assertIn(fragment, pipe)
        self.assertNotIn("latency=500000", pipe)
        self.assertEqual(listener_uri(c), "srt://[::1]:9000?mode=listener&transtype=live")

    def test_rtsp_rejects_pipeline_injection_and_invalid_uris(self):
        for uri in ['rtsp://host/x" ! filesink', "rtsp://host/x\n", "https://host/live", "rtsp://host:99999/live"]:
            with self.subTest(uri=uri), self.assertRaises(ConfigError):
                normalize(self.base(input_mode="rtsp", rtsp_uri=uri), IDENTITY)

    def test_environment_secret_redacted_in_check_output(self):
        from epgeneral_video_srt.config import describe
        with patch.dict(os.environ, {"CAMERA_URL": "rtsp://user:secret@192.0.2.5/live"}):
            c = normalize(self.base(input_mode="rtsp", rtsp_uri_env="CAMERA_URL"), IDENTITY)
        self.assertIn("secret", c["rtsp_uri"])
        self.assertNotIn("secret", json.dumps(describe(c)))

    def test_all_profiles_preserve_expected_output_and_enabled_state(self):
        paths = list((ROOT / "devices").glob("*/profiles/*/config/video.yaml"))
        self.assertEqual(len(paths), 8)
        expected = {"go2_robot2": (30, 0, True), "go2_robot3": (15, 0, True),
                    "wheeltec_r550p": (30, 180, True), "wheeltec_r550p_02": (30, 0, True),
                    "uav_001": (15, 0, True)}
        for path in paths:
            c = load_config(path, path.with_name("device.yaml"))
            self.assertEqual(c["schema_version"], 2)
            name = path.parent.parent.name
            if name in expected:
                self.assertEqual((c["framerate"], c["rotation_degrees"], c["enabled"]), expected[name])

    def test_capture_uses_configuration_and_environment_without_shell(self):
        c = normalize(self.base(capture={"enabled": True, "package": "driver", "launch": "camera.launch",
                                       "args": {"fps": 15, "depth": False},
                                       "arg_env": {"serial_no": "TEST_CAMERA_SERIAL"}}), IDENTITY)
        with patch.dict(os.environ, {"TEST_CAMERA_SERIAL": "a; echo not-a-shell"}):
            self.assertEqual(capture_command(c), ["roslaunch", "driver", "camera.launch",
                                                  "depth:=false", "fps:=15", "serial_no:=a; echo not-a-shell"])

    def test_invalid_capture_names_cannot_inject_ros_options(self):
        for section in [{"enabled": True, "package": "--dump-params", "launch": "x.launch"},
                        {"enabled": True, "package": "driver", "launch": "x.launch",
                         "args": {"__name": "other"}}]:
            with self.assertRaises(ConfigError):
                normalize(self.base(capture=section), IDENTITY)

    def test_native_command_has_private_identity_and_ros_remaps(self):
        c = normalize(self.base(), IDENTITY)
        args = native_command(c, ["__name:=video_a", "/old:=/new"], executable="/tmp/backend")
        self.assertIn('_device_id:=ROBOT_09', args)
        self.assertIn("__name:=video_a", args)
        self.assertNotIn("/edge_device", " ".join(args))
        with self.assertRaises(ConfigError):
            native_command(c, ["_framerate:=9999"], executable="/tmp/backend")

    def test_preload_is_checked_without_mutating_process_environment(self):
        c = normalize(self.base(runtime={"decoder_preload": ["/not-installed/lib.so"]}), IDENTITY)
        with self.assertRaises(ConfigError):
            runtime_environment(c)
        self.assertNotEqual(os.environ.get("LD_PRELOAD"), "/not-installed/lib.so")

    def test_plugins_follow_selected_mode(self):
        raw = normalize(self.base(), IDENTITY)
        rtsp = normalize(self.base(input_mode="rtsp", rtsp_uri="rtsp://host/live", rotation_degrees=180), IDENTITY)
        self.assertIn("appsrc", required_plugins(raw))
        self.assertNotIn("rtspsrc", required_plugins(raw))
        self.assertIn("avdec_h265", required_plugins(rtsp))
        self.assertIn("videoflip", required_plugins(rtsp))


class EntrypointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        import yaml
        (self.folder / "device.yaml").write_text(yaml.safe_dump(IDENTITY))
        self.write_video(dict(schema_version=2, enabled=True, input_mode="ros_image", image_topic="/raw"))

    def write_video(self, c):
        import yaml
        (self.folder / "video.yaml").write_text(yaml.safe_dump(c))

    def invoke(self, args, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return run(args, **kwargs)

    def test_requires_explicit_files_and_rejects_ambiguous_selection(self):
        self.assertEqual(self.invoke(["--check-config"]), 2)
        self.assertEqual(self.invoke(["--config-dir", str(self.folder), "--video-config-file", "x", "--check-config"]), 2)

    def test_directory_and_file_pair_select_the_same_identity(self):
        for args in [["--config-dir", str(self.folder)],
                     ["--video-config-file", str(self.folder / "video.yaml"), "--device-config-file", str(self.folder / "device.yaml")]]:
            with self.subTest(args=args), patch("epgeneral_video_srt.application.check_ros") as ros, patch("os.execve") as execute:
                self.assertEqual(self.invoke(args + ["--check-config"]), 0)
                ros.assert_not_called()
                execute.assert_not_called()

    def test_disabled_runtime_and_capture_do_not_import_or_execute_hardware(self):
        self.write_video(dict(schema_version=2, enabled=False, input_mode="rtsp", rtsp_uri_env="UNPROVISIONED_VIDEO_SECRET"))
        with patch("epgeneral_video_srt.application.check_ros") as ros, patch("epgeneral_video_srt.application.check_runtime") as gst, patch("os.execve") as execute, patch("os.execvpe") as camera:
            for flag in [[], ["--check-runtime"], ["--check-camera"]]:
                self.assertEqual(self.invoke(["--config-dir", str(self.folder)] + flag), 0)
            self.assertEqual(self.invoke(["--config-dir", str(self.folder)], camera=True), 0)
            for dependency in (ros, gst, execute, camera):
                dependency.assert_not_called()

    def test_capture_overrides_preserve_defaults_and_reject_invalid_names(self):
        self.write_video(dict(schema_version=2, input_mode="ros_image", image_topic="/image",
                              capture=dict(enabled=True, package="camera_driver", launch="rgb.launch",
                                           args=dict(color_fps=15))))
        with patch("os.execvpe", side_effect=SystemExit(0)) as execute:
            with self.assertRaises(SystemExit):
                self.invoke(["--config-dir", str(self.folder), "--capture-arg", "serial_no:=",
                             "--capture-arg", "color_fps:=30"], camera=True)
            command = execute.call_args[0][1]
            self.assertIn("color_fps:=30", command)
            self.assertNotIn("serial_no:=", command)
        self.assertEqual(self.invoke(["--config-dir", str(self.folder), "--capture-arg=--bad:=1"], camera=True), 2)

    def test_runtime_failure_does_not_start_backend(self):
        with patch("epgeneral_video_srt.application.check_ros"), patch("epgeneral_video_srt.application.check_runtime", side_effect=ConfigError("missing srtsink")), patch("os.execve") as execute:
            self.assertEqual(self.invoke(["--config-dir", str(self.folder)]), 2)
            execute.assert_not_called()

    def test_compatibility_alias_uses_generic_config_without_ros_installed(self):
        root = ROOT / "EPGeneral_video_srt/scripts"
        for name in ["video_srt_node.py", "rtsp_srt_node.py"]:
            result = subprocess.run([sys.executable, "-B", str(root/name), "--config-dir",
                                     str(self.folder), "--check-config"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(json.loads(result.stdout)["device_id"], "ROBOT_09")

    def test_native_and_camera_exec_retain_process_ownership(self):
        # exec replaces the owned ROS child rather than detaching unmanaged subprocesses.
        with patch("epgeneral_video_srt.application.check_ros"), patch("epgeneral_video_srt.application.check_runtime"), patch("epgeneral_video_srt.application.native_command", return_value=["/backend"]), patch("os.execve", side_effect=SystemExit(0)) as execute:
            with self.assertRaises(SystemExit):
                self.invoke(["--config-dir", str(self.folder)])
            self.assertEqual(execute.call_args[0][0], "/backend")


if __name__ == "__main__":
    unittest.main()
