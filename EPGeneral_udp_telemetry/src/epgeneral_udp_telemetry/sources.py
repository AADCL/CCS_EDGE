"""Device-independent ROS extraction, preflight and confined file status sources."""
import json
import math
import os
from pathlib import Path
import re
import stat

from .config import ConfigError, UNIT_FACTORS, field_path, source_mode


def read_path(value, path):
    for part in field_path(path).split("."):
        value = value[part] if isinstance(value, dict) else getattr(value, part)
    return value


def vector(message, spec, axes="xyz"):
    if isinstance(spec, dict):
        result = [read_path(message, spec[axis]) for axis in axes]
    else:
        value = read_path(message, spec)
        result = [value[axis] if isinstance(value, dict) else getattr(value, axis) for axis in axes]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in result):
        raise ValueError("vector components must be numeric")
    if any(not math.isfinite(v) for v in result):
        raise ValueError("vector contains nonfinite values")
    return result


def extract_sample(descriptor, message):
    source = descriptor["source"]
    if source.get("expected_frame") is not None and read_path(message, "header.frame_id") != source["expected_frame"]:
        raise ValueError("source frame does not match expected_frame; no implicit frame conversion")
    kind = descriptor["type"]
    maps = source.get("mapping", {})
    if source_mode(descriptor) == "value_status":
        value = read_path(message, maps.get("value", "data"))
        values = source.get("values", {True: "available", False: "unavailable"})
        status = next((status for key, status in values.items() if type(key) is type(value) and key == value), "unknown")
        return {"status": status}
    if kind == "text_status":
        return {"value": str(read_path(message, maps.get("value", "data"))).strip()[:source.get("text_limit", 128)]}
    units = source.get("units", {})
    orientation = maps.get("orientation", "pose.orientation" if kind == "pose" else "orientation")
    result = {"quaternion": tuple(vector(message, orientation, "xyzw"))}
    if kind == "pose":
        values = vector(message, maps.get("position", "pose.position"))
        scale = UNIT_FACTORS["position"][units.get("position", "m")]
        result.update({axis: value * scale for axis, value in zip("xyz", values)})
    else:
        for name, default in (("angular_velocity", "rad/s"), ("linear_acceleration", "m/s2")):
            values = vector(message, maps.get(name, name))
            scale = UNIT_FACTORS[name][units.get(name, default)]
            result.update({name + "_" + axis: value * scale for axis, value in zip("xyz", values)})
    return result


def validate_ros_sources(config, resolver=None):
    """Resolve all enabled message classes/fields without creating ROS or socket resources."""
    if resolver is None:
        def resolver(name):
            from roslib.message import get_message_class
            return get_message_class(name)
    classes = {}
    for descriptor in config["descriptors"]:
        mode = source_mode(descriptor)
        if mode in ("disabled", "file_status", "topic_freshness"):
            continue
        source = descriptor["source"]
        cls = resolver(source["message_type"])
        if cls is None:
            raise ConfigError("ROS message type unavailable: " + source["message_type"])
        if hasattr(cls, "__slots__"):
            try:
                sample = cls()
                for key, spec in source.get("mapping", {}).items():
                    if isinstance(spec, dict):
                        for path in spec.values():
                            read_path(sample, path)
                    else:
                        value = read_path(sample, spec)
                        if key != "value":
                            for axis in ("xyzw" if key == "orientation" else "xyz"):
                                read_path(value, axis)
                if source.get("expected_frame"):
                    read_path(sample, "header.frame_id")
            except (AttributeError, KeyError, TypeError, ValueError) as exc:
                raise ConfigError("%s message fields unavailable: %s" % (descriptor["name"], exc)) from exc
        classes[source["message_type"]] = cls
    return classes


def file_snapshot(descriptor):
    source = descriptor["source"]
    map_id = None
    try:
        state_path = Path(os.path.expanduser(source["state_file"]))
        if state_path.is_symlink() or not state_path.is_file() or state_path.stat().st_size > 1048576:
            raise ValueError("state file must be a regular file no larger than 1 MiB")
        with state_path.open(encoding="utf-8") as stream:
            value = json.loads(stream.read(1048577))
        map_id = read_path(value, source.get("state_field", "map_id"))
        if not isinstance(map_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", map_id):
            raise ValueError("invalid active map id")
        root = Path(os.path.abspath(os.path.expanduser(source["map_root"])))
        relative = source.get("path_template", "{map_id}/map.pgm").format(map_id=map_id)
        # Recheck confinement at IO time, including symlink ancestors and the artifact itself.
        if any(parent.is_symlink() for parent in (root,) + tuple(root.parents)) or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("unsafe artifact root/path")
        root = root.resolve()
        target = root / relative
        cursor = root
        for part in Path(relative).parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise ValueError("symlink in artifact path")
        if os.path.commonpath([str(root), str(target.resolve())]) != str(root):
            raise ValueError("artifact escapes root")
        available = stat.S_ISREG(target.lstat().st_mode)
        return {"valid": True, "status": "available" if available else "unavailable", "sample_age_seconds": 0.0, "map_id": map_id}
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError):
        return {"valid": True, "status": "unavailable", "sample_age_seconds": 0.0,
                "map_id": map_id if isinstance(map_id, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", map_id) else None}
