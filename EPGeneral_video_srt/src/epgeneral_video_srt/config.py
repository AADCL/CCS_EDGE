"""Device-independent video configuration; importing this module needs no ROS/Gst."""
import copy
import ipaddress
import math
import os
from pathlib import Path
import re
import string
from urllib.parse import urlsplit

import yaml


class ConfigError(ValueError):
    pass


def mapping(value, label):
    if not isinstance(value, dict):
        raise ConfigError(label + " must be a mapping")
    return value


def number(value, label, low, high, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(label + " must be numeric")
    if not math.isfinite(value) or not low <= value <= high or (integer and not isinstance(value, int)):
        raise ConfigError(label + " is out of range")
    return value


def text(value, label):
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
        raise ConfigError(label + " must be non-empty text without control characters")
    return value


def topic(value, device_id, label, private=False):
    value = text(value, label)
    try:
        fields = list(string.Formatter().parse(value))
        if any(field is not None and (field != "device_id" or spec or conversion)
               for _, field, spec, conversion in fields):
            raise ValueError()
        value = value.format(device_id=device_id)
    except (KeyError, ValueError):
        raise ConfigError(label + " only supports {device_id}")
    pattern = r"(?:/|~)[A-Za-z_][A-Za-z0-9_/]*" if private else r"/[A-Za-z_][A-Za-z0-9_/]*"
    if not re.fullmatch(pattern, value):
        raise ConfigError(label + " is not a supported ROS topic")
    return value


def read_yaml(path):
    try:
        return mapping(yaml.safe_load(Path(path).read_text(encoding="utf-8")), str(path))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ConfigError("cannot read configuration: " + str(path)) from exc


def normalize(raw, identity):
    c = copy.deepcopy(mapping(raw, "video"))
    identity = mapping(identity, "device configuration")
    if identity.get("schema_version") != 1 or isinstance(identity.get("schema_version"), bool):
        raise ConfigError("device schema_version must be 1")
    device = mapping(identity.get("device"), "device")
    device_id = text(device.get("id"), "device.id")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", device_id):
        raise ConfigError("device.id must be a ROS-safe identifier")
    try:
        device_ip = str(ipaddress.ip_address(text(device.get("ip"), "device.ip")))
    except (KeyError, ValueError, TypeError):
        raise ConfigError("device.ip must be an IP literal")
    schema = c.get("schema_version", 1)
    if type(schema) is not int or schema not in (1, 2):
        raise ConfigError("video schema_version must be 1 or 2")
    allowed = {"schema_version", "enabled", "deployment", "camera_model", "input_mode",
               "image_topic", "image_message_type", "image_width", "image_height",
               "output_width", "output_height", "framerate", "bitrate_kbps",
               "rotation_degrees", "srt_bind_address", "srt_port", "srt_latency_ms",
               "frame_timeout_seconds", "rtsp_uri", "rtsp_uri_env", "rtsp_codec",
               "rtsp_transport", "rtsp_latency_ms", "runtime", "capture"}
    unknown = set(c) - allowed
    if unknown:
        raise ConfigError("unknown video fields: " + ", ".join(sorted(map(str, unknown))))
    deployment = mapping(c.get("deployment", {}), "deployment")
    enabled = c.get("enabled", deployment.get("enabled", True))
    if type(enabled) is not bool:
        raise ConfigError("enabled must be boolean")
    if "enabled" in deployment and (type(deployment["enabled"]) is not bool or deployment["enabled"] != enabled):
        raise ConfigError("enabled conflicts with deployment.enabled")
    mode = c.get("input_mode")
    if mode is None:
        if schema == 2:
            raise ConfigError("schema 2 requires input_mode")
        mode = "ros_compressed" if c.get("image_message_type") == "sensor_msgs/CompressedImage" else "ros_image"
    if mode not in ("ros_image", "ros_compressed", "rtsp"):
        raise ConfigError("input_mode must be ros_image, ros_compressed or rtsp")
    c.update(schema_version=schema, enabled=enabled, input_mode=mode,
             device_id=device_id, device_ip=device_ip)
    defaults = dict(output_width=c.get("image_width", 640), output_height=c.get("image_height", 480),
                    framerate=15 if mode == "rtsp" else 30, bitrate_kbps=2000,
                    rotation_degrees=0, srt_bind_address="0.0.0.0", srt_port=9000,
                    srt_latency_ms=120, frame_timeout_seconds=8.0 if mode == "rtsp" else 5.0)
    for k, v in defaults.items():
        c.setdefault(k, v)
    for k, low, high in (("output_width", 16, 3840), ("output_height", 16, 2160),
                         ("framerate", 1, 120), ("bitrate_kbps", 100, 20000),
                         ("srt_port", 1, 65535), ("srt_latency_ms", 20, 8000)):
        number(c[k], k, low, high, integer=True)
    if c["output_width"] % 2 or c["output_height"] % 2:
        raise ConfigError("H.264 I420 output dimensions must be even")
    if type(c["rotation_degrees"]) is not int or c["rotation_degrees"] not in (0, 180):
        raise ConfigError("rotation_degrees must be 0 or 180")
    number(c["frame_timeout_seconds"], "frame_timeout_seconds", 0.1, 3600)
    try:
        c["srt_bind_address"] = str(ipaddress.ip_address(text(c["srt_bind_address"], "srt_bind_address")))
    except (ValueError, TypeError):
        raise ConfigError("srt_bind_address must be an IP literal")
    if mode != "rtsp":
        expected = "sensor_msgs/Image" if mode == "ros_image" else "sensor_msgs/CompressedImage"
        if c.get("image_message_type", expected) != expected:
            raise ConfigError("image_message_type conflicts with input_mode")
        c["image_message_type"] = expected
        if schema == 2 and "image_topic" not in c:
            raise ConfigError("ROS input requires image_topic")
        c["image_topic"] = topic(c.get("image_topic", "/camera/image_raw"), device_id, "image_topic")
    else:
        env_key = c.get("rtsp_uri_env", "")
        if env_key:
            if "rtsp_uri" in c and c["rtsp_uri"]:
                raise ConfigError("select rtsp_uri OR rtsp_uri_env")
            if not isinstance(env_key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", env_key):
                raise ConfigError("invalid rtsp_uri_env")
            c["rtsp_uri"] = os.environ.get(env_key, "")
        # A disabled RTSP profile may be distributed before its secret is provisioned.
        uri = c.get("rtsp_uri", "")
        if enabled or uri:
            text(uri, "rtsp_uri")
            try:
                parsed = urlsplit(uri)
                if parsed.scheme != "rtsp" or not parsed.hostname or parsed.port == 0:
                    raise ValueError()
            except ValueError:
                raise ConfigError("invalid RTSP URI")
            if any(ch in uri for ch in ('"', chr(92))):
                raise ConfigError("invalid RTSP URI")
        c["rtsp_uri"] = uri
        c.setdefault("rtsp_codec", "h265")
        c.setdefault("rtsp_transport", "tcp")
        c.setdefault("rtsp_latency_ms", 100)
        if c["rtsp_codec"] not in ("h264", "h265"):
            raise ConfigError("rtsp_codec must be h264 or h265")
        if c["rtsp_transport"] not in ("tcp", "udp"):
            raise ConfigError("rtsp_transport must be tcp or udp")
        number(c["rtsp_latency_ms"], "rtsp_latency_ms", 0, 10000, integer=True)
    runtime = mapping(c.get("runtime", {}), "runtime")
    if set(runtime) - {"status_topic", "reconnect_interval_seconds", "decoder_preload"}:
        raise ConfigError("unknown runtime field")
    c["runtime"] = dict(runtime)
    c["runtime"].setdefault("status_topic", "~status")
    c["runtime"]["status_topic"] = topic(c["runtime"]["status_topic"], device_id, "status_topic", private=True)
    c["runtime"].setdefault("reconnect_interval_seconds", 3.0)
    number(c["runtime"]["reconnect_interval_seconds"], "reconnect_interval_seconds", 0.1, 300)
    preload = c["runtime"].setdefault("decoder_preload", [])
    if not isinstance(preload, list) or any(not isinstance(p, str) or not p.startswith("/") or
            any(ch.isspace() or ch == ":" for ch in p) for p in preload):
        raise ConfigError("decoder_preload must be a list of absolute library paths")
    capture = mapping(c.get("capture", {"enabled": False}), "capture")
    if set(capture) - {"enabled", "package", "launch", "args", "arg_env"}:
        raise ConfigError("unknown capture field")
    capture.setdefault("enabled", False)
    if type(capture["enabled"]) is not bool:
        raise ConfigError("capture.enabled must be boolean")
    if capture["enabled"]:
        for key in ("package", "launch"):
            value = text(capture.get(key), "capture." + key)
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", value):
                raise ConfigError("invalid capture." + key)
        args = mapping(capture.get("args", {}), "capture.args")
        envs = mapping(capture.get("arg_env", {}), "capture.arg_env")
        for key, value in args.items():
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", str(key)) or not isinstance(value, (str, bool, int, float)):
                raise ConfigError("capture arguments must have ROS argument names and scalar values")
            if isinstance(value, float) and not math.isfinite(value):
                raise ConfigError("capture argument must be finite")
            if isinstance(value, str) and any(ord(ch) < 32 for ch in value):
                raise ConfigError("invalid capture argument text")
        for key, value in envs.items():
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", str(key)) or not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
                raise ConfigError("invalid capture environment mapping")
        capture.update(args=args, arg_env=envs)
    c["capture"] = capture
    return c


def load_config(video_file, device_file):
    return normalize(read_yaml(video_file), read_yaml(device_file))


def listener_uri(c):
    host = c["srt_bind_address"]
    if ":" in host:
        host = "[" + host + "]"
    return "srt://%s:%d?mode=listener&transtype=live" % (host, c["srt_port"])


def describe(c):
    result = copy.deepcopy(c)
    if "rtsp_uri" in result:
        result["rtsp_uri"] = "<configured; redacted>" if result["rtsp_uri"] else ""
    return result


def capture_command(c):
    if not c["enabled"] or not c["capture"]["enabled"]:
        return None
    capture = c["capture"]
    args = dict(capture["args"])
    for name, env_key in capture["arg_env"].items():
        if os.environ.get(env_key):
            args[name] = os.environ[env_key]
    def scalar(value):
        return str(value).lower() if type(value) is bool else str(value)
    return ["roslaunch", capture["package"], capture["launch"]] + [
        name + ":=" + scalar(value) for name, value in sorted(args.items())]
