"""Validated deployment configuration; wire descriptors remain backward compatible."""
from copy import deepcopy
import hashlib
import ipaddress
import json
import math
from pathlib import Path
import re
from string import Formatter

import yaml

LEVEL_RATES = {1: 20.0, 2: 5.0, 3: 1.0}
ALLOWED_TYPES = {"pose", "imu", "pointcloud_status", "availability", "text_status"}
MODES = {"ros_fields", "topic_freshness", "value_status", "file_status", "disabled"}
UNIT_FACTORS = {"position": {"m": 1.0, "cm": 0.01, "mm": 0.001},
                "angular_velocity": {"rad/s": 1.0, "deg/s": math.pi / 180.0},
                "linear_acceleration": {"m/s2": 1.0, "g": 9.80665}}


class ConfigError(ValueError):
    pass


def mapping(value, path):
    if not isinstance(value, dict):
        raise ConfigError(path + " must be a mapping")
    return value


def text(value, path):
    if not isinstance(value, str) or not value or value != value.strip() or any(ord(c) < 32 for c in value):
        raise ConfigError(path + " must be a nonempty string without surrounding whitespace/control characters")
    return value


def integer(value, path, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ConfigError("%s must be an integer in %s..%s" % (path, low, high))
    return value


def positive(value, path, high=3600):
    if type(value) not in (int, float) or not 0 < value <= high:
        raise ConfigError("%s must be finite and in (0, %s]" % (path, high))
    return float(value)


def known(value, allowed, path):
    if set(value) - set(allowed):
        raise ConfigError(path + " contains unknown keys: " + str(set(value) - set(allowed)))


def field_path(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)*", value):
        raise ConfigError("invalid public field path: %s" % value)
    return value


def expand(value, device_id, path):
    value = text(value, path)
    try:
        for _, name, spec, conversion in Formatter().parse(value):
            if name is not None and (name != "device_id" or spec or conversion):
                raise ValueError("only {device_id} is supported")
        result = value.format(device_id=device_id)
        if "{" in result or "}" in result:
            raise ValueError("literal braces are unsupported")
        return result
    except ValueError as exc:
        raise ConfigError(path + ": " + str(exc)) from exc


def ros_topic(value, device_id, path):
    value = expand(value, device_id, path)
    if not re.fullmatch(r"/[A-Za-z][A-Za-z0-9_/]*", value) or "//" in value or value.endswith("/"):
        raise ConfigError(path + " must be an absolute ROS topic")
    return value


def validate_destination(config):
    try:
        address = ipaddress.ip_address(text(config["destination_host"], "destination_host"))
    except ValueError as exc:
        raise ConfigError("destination_host must be an IPv4 or IPv6 address") from exc
    config["destination_host"] = str(address)
    config["destination_port"] = integer(config["destination_port"], "destination_port", 1, 65535)
    return config


def _read_yaml(path):
    try:
        with Path(path).open(encoding="utf-8") as stream:
            return mapping(yaml.safe_load(stream), str(path))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ConfigError("cannot read config %s: %s" % (path, exc)) from exc


def source_mode(descriptor):
    source = descriptor["source"]
    if "mode" in source:
        return source["mode"]
    if source.get("kind") == "pgm_file":
        return "file_status"
    return "topic_freshness" if descriptor["type"] in ("availability", "pointcloud_status") else "ros_fields"


def normalize_source(item, schema, device_id):
    source = mapping(item.get("source"), "source for " + item["name"])
    if schema == 2:
        known(source, {"mode", "kind", "topic", "message_type", "mapping", "timeout_seconds", "stale_policy",
                       "max_age_seconds", "aggregation", "max_samples", "queue_size", "units", "expected_frame",
                       "values", "text_limit", "state_file", "map_root", "state_field", "path_template"}, "source")
        if "mode" not in source:
            raise ConfigError("source.mode is required in schema 2")
    mode = source_mode(item)
    if not isinstance(mode, str) or mode not in MODES:
        raise ConfigError("invalid source.mode")
    source["mode"] = mode
    if mode == "disabled":
        return
    if source.get("kind") not in (None, "pgm_file") or (source.get("kind") == "pgm_file" and mode != "file_status"):
        raise ConfigError("source.kind only supports legacy pgm_file with file_status mode")
    allowed = {"ros_fields": {"pose", "imu", "text_status"}, "topic_freshness": {"availability", "pointcloud_status"},
               "value_status": {"availability"}, "file_status": {"availability"}}
    if item["type"] not in allowed[mode]:
        raise ConfigError("source.mode does not support descriptor type")
    if mode == "file_status":
        for key in ("state_file", "map_root"):
            source[key] = expand(source.get(key), device_id, "source." + key)
            if not source[key].startswith(("/", "~/")) and not re.match(r"^[A-Za-z]:[\\/]", source[key]):
                raise ConfigError("source.%s must be absolute or start with ~/" % key)
        source["state_field"] = field_path(source.get("state_field", "map_id"))
        template = text(source.get("path_template", "{map_id}/map.pgm"), "source.path_template")
        # A fixed relative artifact path; map_id is the only runtime substitution.
        candidate = template.replace("{map_id}", "MAP_ID")
        if "{" in candidate or "}" in candidate or "\\" in candidate or ":" in candidate or candidate.startswith("/") or any(p in ("", ".", "..") for p in candidate.split("/")):
            raise ConfigError("source.path_template must be a confined relative path with optional {map_id}")
        source["path_template"] = template
        return
    source["topic"] = ros_topic(source.get("topic"), device_id, "source.topic")
    source["queue_size"] = integer(source.get("queue_size", 50), "source.queue_size", 1, 10000)
    source["max_samples"] = integer(source.get("max_samples", 1000), "source.max_samples", 1, 100000)
    if mode == "topic_freshness":
        source["timeout_seconds"] = positive(source.get("timeout_seconds", 1.0 if item["type"] == "pointcloud_status" else 3.0), "source.timeout_seconds")
        if set(source) & {"mapping", "values", "units", "expected_frame", "stale_policy", "max_age_seconds", "aggregation"}:
            raise ConfigError("topic_freshness cannot interpret fields or sampling policies; use value_status/ros_fields")
        return
    msg = text(source.get("message_type"), "source.message_type")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*/[A-Za-z][A-Za-z0-9_]*", msg):
        raise ConfigError("source.message_type must use package/Message")
    default_mapping = {"pose": {"position": "pose.position", "orientation": "pose.orientation"},
                       "imu": {"orientation": "orientation", "angular_velocity": "angular_velocity", "linear_acceleration": "linear_acceleration"}}
    defaults = default_mapping.get(item["type"], {"value": "data"})
    raw = mapping(source.get("mapping", {}), "source.mapping")
    known(raw, defaults, "source.mapping")
    source["mapping"] = dict(defaults, **raw)
    for key, value in source["mapping"].items():
        if isinstance(value, dict) and key != "value":
            axes = set("xyzw" if key == "orientation" else "xyz")
            if set(value) != axes:
                raise ConfigError("component mapping must contain " + str(axes))
            for component in value.values():
                field_path(component)
        else:
            field_path(value)
    source["stale_policy"] = source.get("stale_policy", "invalidate" if schema == 2 else "hold")
    if source["stale_policy"] not in ("invalidate", "hold"):
        raise ConfigError("source.stale_policy must be invalidate or hold")
    source["max_age_seconds"] = positive(source.get("max_age_seconds", source.get("timeout_seconds", 3.0)), "source.max_age_seconds")
    source["timeout_seconds"] = positive(source.get("timeout_seconds", source["max_age_seconds"]), "source.timeout_seconds")
    source["aggregation"] = source.get("aggregation", "mean" if item["type"] in ("pose", "imu") else "latest")
    if source["aggregation"] not in ("mean", "latest") or (item["type"] not in ("pose", "imu") and source["aggregation"] != "latest"):
        raise ConfigError("invalid source.aggregation")
    source["text_limit"] = integer(source.get("text_limit", 128), "source.text_limit", 1, 128)
    if "expected_frame" in source:
        source["expected_frame"] = text(source["expected_frame"], "source.expected_frame")
    units = mapping(source.get("units", {}), "source.units")
    allowed_units = {"position"} if item["type"] == "pose" else {"angular_velocity", "linear_acceleration"} if item["type"] == "imu" else set()
    known(units, allowed_units, "source.units")
    if schema == 2 and set(units) != allowed_units:
        raise ConfigError("schema 2 requires explicit source.units for pose/imu")
    for name, unit in units.items():
        if not isinstance(unit, str) or unit not in UNIT_FACTORS[name]:
            raise ConfigError("unsupported unit for " + name)
    source["units"] = units
    if mode == "value_status":
        values = mapping(source.get("values", {True: "available", False: "unavailable"}), "source.values")
        for key, value in values.items():
            if type(key) not in (bool, str, int, float) or (isinstance(key, float) and not math.isfinite(key)) or value not in ("available", "unavailable", "unknown"):
                raise ConfigError("source.values must map finite scalars to availability states")
        source["values"] = values


def load_config(telemetry_path, device_path):
    telemetry = deepcopy(_read_yaml(telemetry_path))
    identity = _read_yaml(device_path)
    schema = telemetry.get("schema_version")
    if type(schema) is not int or schema not in (1, 2) or type(identity.get("schema_version")) is not int or identity["schema_version"] != 1:
        raise ConfigError("telemetry schema_version must be 1 or 2; device schema_version must be 1")
    device = mapping(identity.get("device"), "device")
    device_id = device.get("id")
    if not isinstance(device_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", device_id):
        raise ConfigError("device.id must be 1..64 ASCII letters/digits/_/-, beginning with a letter or digit")
    try:
        device_ip = str(ipaddress.ip_address(text(device.get("ip"), "device.ip")))
    except ValueError as exc:
        raise ConfigError("device.ip is invalid") from exc
    if telemetry.get("protocol_id") != "ccs-udp-telemetry-v1":
        raise ConfigError("protocol_id must be ccs-udp-telemetry-v1")
    network = mapping(telemetry.get("network"), "network")
    runtime = mapping(telemetry.get("runtime", {}), "runtime")
    if schema == 2:
        known(telemetry, {"schema_version", "protocol_id", "network", "runtime", "descriptors"}, "root")
        known(network, {"destination_host", "destination_port", "max_datagram_bytes"}, "network")
        known(runtime, {"link_status_topic", "diagnostics_topic"}, "runtime")
    descriptors = telemetry.get("descriptors")
    if not isinstance(descriptors, list) or not descriptors:
        raise ConfigError("descriptors must be a nonempty list")
    names = set()
    for item in descriptors:
        mapping(item, "descriptor")
        if schema == 2:
            known(item, {"name", "display_name", "type", "level", "source"}, "descriptor")
        name = text(item.get("name"), "descriptor.name")
        text(item.get("display_name"), "descriptor.display_name")
        if name in names:
            raise ConfigError("duplicate descriptor name")
        names.add(name)
        kind = item.get("type")
        if not isinstance(kind, str) or kind not in ALLOWED_TYPES:
            raise ConfigError("invalid descriptor type")
        level = integer(item.get("level"), "descriptor.level", 1, 3)
        if (kind in ("pose", "imu") and level != 1) or (kind == "pointcloud_status" and level != 2) or (kind in ("availability", "text_status") and level != 3):
            raise ConfigError("descriptor type/level combination violates the existing protocol")
        normalize_source(item, schema, device_id)
    config = {"schema_version": schema, "device_id": device_id, "device_ip": device_ip,
              "protocol_id": telemetry["protocol_id"], "destination_host": network.get("destination_host"),
              "destination_port": network.get("destination_port"),
              "max_datagram_bytes": integer(network.get("max_datagram_bytes", 16384), "max_datagram_bytes", 512, 65507),
              "descriptors": descriptors, "descriptor_hash": descriptor_hash(descriptors)}
    for key, suffix in (("link_status_topic", "/link/udp_tx"), ("diagnostics_topic", "/diagnostics")):
        config[key] = ros_topic(runtime.get(key, "/epgeneral_udp_telemetry" + suffix), device_id, "runtime." + key)
    return validate_destination(config)


def descriptor_hash(descriptors):
    common = [{key: item[key] for key in ("display_name", "level", "name", "type")}
              for item in sorted(descriptors, key=lambda value: value["name"])]
    encoded = json.dumps(common, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
