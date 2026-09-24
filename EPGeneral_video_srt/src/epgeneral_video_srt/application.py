"""Explicit configuration and preflight shared by both video backends."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from .config import ConfigError, capture_command, describe, load_config


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Configured ROS image/RTSP to H.264 MPEG-TS SRT")
    parser.add_argument("--config-dir", default="")
    parser.add_argument("--video-config-file", default="")
    parser.add_argument("--device-config-file", default="")
    parser.add_argument("--decoder-preload", default="", help="deprecated explicit override")
    parser.add_argument("--check-config", action="store_true")
    parser.add_argument("--check-ros", action="store_true")
    parser.add_argument("--check-runtime", action="store_true")
    parser.add_argument("--check-camera", action="store_true")
    parser.add_argument("--capture-arg", action="append", default=[])
    # Keep ROS remaps separate so they reach the selected backend unchanged.
    args, remaps = parser.parse_known_args(argv)
    if any(":=" not in a or a.startswith("--") for a in remaps):
        parser.error("unrecognized arguments: " + " ".join(remaps))
    return args, remaps


def select_config(args):
    if args.config_dir:
        if args.video_config_file or args.device_config_file:
            raise ConfigError("select config-dir OR both explicit files")
        directory = Path(args.config_dir).expanduser().resolve()
        return load_config(directory / "video.yaml", directory / "device.yaml")
    if not args.video_config_file or not args.device_config_file:
        raise ConfigError("select config-dir or both video-config-file and device-config-file; no sample identity is selected")
    return load_config(Path(args.video_config_file).expanduser(), Path(args.device_config_file).expanduser())


def runtime_environment(c, override=""):
    paths = override.split(":") if override else c["runtime"]["decoder_preload"]
    env = dict(os.environ)
    for path in paths:
        if not path.startswith("/") or any(ch.isspace() for ch in path) or not Path(path).is_file():
            raise ConfigError("decoder preload library is missing or invalid")
    if paths:
        env["LD_PRELOAD"] = ":".join(paths)
    return env


def required_plugins(c):
    result = ["videoconvert", "x264enc", "h264parse", "mpegtsmux", "srtsink", "queue"]
    if c["input_mode"] == "rtsp":
        codec = c["rtsp_codec"]
        result += ["rtspsrc", "rtp" + codec + "depay", codec + "parse", "avdec_" + codec,
                   "videoscale", "videorate", "identity"]
    else:
        result += ["appsrc"]
    if c["rotation_degrees"]:
        result += ["videoflip"]
    return sorted(set(result))


def check_ros(c):
    if c["input_mode"] != "rtsp":
        from roslib.message import get_message_class
        if get_message_class(c["image_message_type"]) is None:
            raise ConfigError("ROS image message type is unavailable")


def check_runtime(c, env):
    for plugin in required_plugins(c):
        try:
            result = subprocess.run(["gst-inspect-1.0", plugin], env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ConfigError("GStreamer inspection unavailable") from exc
        if result.returncode:
            raise ConfigError("GStreamer plugin unavailable: " + plugin)


def native_command(c, remaps, executable=None):
    if executable is None:
        from roslib.packages import find_node
        found = find_node("epgeneral_video_srt", "epgeneral_video_srt_node")
        if not found:
            raise ConfigError("ROS image backend has not been built")
        executable = found[0]
    keys = ("device_id", "device_ip", "image_topic", "image_message_type", "output_width",
            "output_height", "framerate", "bitrate_kbps", "rotation_degrees",
            "srt_bind_address", "srt_port", "srt_latency_ms", "frame_timeout_seconds")
    params = {k: c[k] for k in keys}
    params.update(status_topic=c["runtime"]["status_topic"],
                  reconnect_interval_seconds=c["runtime"]["reconnect_interval_seconds"])
    # Resolved configuration owns private parameters. ROS names/namespaces and topic
    # remaps remain available, but cannot override validated numeric/device values.
    if any(a.startswith("_") and not a.startswith("__") for a in remaps):
        raise ConfigError("private parameter overrides must be supplied in video.yaml")
    return [executable] + ["_" + k + ":=" + (v if isinstance(v, str) else json.dumps(v))
                           for k, v in sorted(params.items())] + remaps


def run(argv=None, camera=False):
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        args, remaps = parse_args(argv)
        c = select_config(args)
        if args.capture_arg:
            from .config import normalize
            # Compatibility overrides are scalar launch arguments, never shell code.
            for item in args.capture_arg:
                if ":=" not in item:
                    raise ConfigError("capture-arg must be name:=value")
                name, value = item.split(":=", 1)
                if value:
                    c["capture"].setdefault("args", {})[name] = value
            identity = {"schema_version": 1, "device": {"id": c.pop("device_id"), "ip": c.pop("device_ip")}}
            if c.get("rtsp_uri_env"):
                c.pop("rtsp_uri", None)
            c = normalize(c, identity)
        checking = args.check_config or args.check_ros or args.check_runtime or args.check_camera
        if not c["enabled"]:
            print(json.dumps({"enabled": False, "device_id": c["device_id"]}))
            return 0
        if args.check_ros or args.check_runtime:
            check_ros(c)
        if args.check_runtime:
            check_runtime(c, runtime_environment(c, args.decoder_preload))
        if args.check_camera:
            command = capture_command(c)
            if command:
                result = subprocess.run([command[0], "--files"] + command[1:],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
                if result.returncode:
                    raise ConfigError("camera launch preflight failed")
        if checking:
            print(json.dumps(describe(c), ensure_ascii=False, indent=2, allow_nan=False))
            return 0
        if camera:
            command = capture_command(c)
            if not command:
                return 0
            os.execvpe(command[0], command, dict(os.environ))
        env = runtime_environment(c, args.decoder_preload)
        check_ros(c)
        check_runtime(c, env)
        if c["input_mode"] != "rtsp":
            command = native_command(c, remaps)
            os.execve(command[0], command, env)
        else:
            # A library preload must be active before Python loads GI/decoder libraries.
            token = env.get("LD_PRELOAD", "")
            if token and os.environ.get("_CCS_VIDEO_PRELOAD_READY") != token:
                env["_CCS_VIDEO_PRELOAD_READY"] = token
                os.execve(sys.executable, [sys.executable] + sys.argv, env)
            from .rtsp_backend import run as run_rtsp
            return run_rtsp(c, remaps)
    except (ConfigError, ImportError, OSError, subprocess.TimeoutExpired) as exc:
        # Do not echo URIs/credentials from parser or plugin errors.
        print("video preflight failed: " + str(exc), file=sys.stderr)
        return 2
