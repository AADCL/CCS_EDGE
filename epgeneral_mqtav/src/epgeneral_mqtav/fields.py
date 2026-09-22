"""Safe field extraction and explicit, configuration-driven conversions."""
import math
import re


def field_path(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)*", value):
        raise ValueError("must be a dotted public field path")
    return value


def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def boolean(value):
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, str):
        value = value.lower()
        if value in ("true", "1"):
            return True
        if value in ("false", "0"):
            return False
        return None
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    return None


def validate_mapping(spec):
    if spec is None:
        return None
    if isinstance(spec, str):
        return field_path(spec)
    if not isinstance(spec, dict) or set(spec) - {"field", "scale", "offset", "invalid_values", "values"}:
        raise ValueError("must be a field path, null, or a field conversion mapping")
    field_path(spec.get("field"))
    for key in ("scale", "offset"):
        if key in spec and (not isinstance(spec[key], (int, float)) or number(spec[key]) is None):
            raise ValueError(key + " must be finite numeric")
    invalid = spec.get("invalid_values", [])
    if not isinstance(invalid, list) or any(isinstance(v, (list, dict)) for v in invalid):
        raise ValueError("invalid_values must be a list of scalar values")
    values = spec.get("values", {})
    if not isinstance(values, dict):
        raise ValueError("values must be a scalar lookup mapping")
    for key, value in values.items():
        if not isinstance(key, (str, int, float, bool)) or not (value is None or isinstance(value, (str, int, float, bool))):
            raise ValueError("values must contain scalar keys and values")
        if any(isinstance(item, float) and not math.isfinite(item) for item in (key, value)):
            raise ValueError("values must be finite")
    return dict(spec)


def read_field(message, path):
    value = message
    for field in field_path(path).split("."):
        value = value[field] if isinstance(value, dict) else getattr(value, field)
    return value


def extract(message, spec):
    if spec is None:
        return None
    if isinstance(spec, str):
        return read_field(message, spec)
    value = read_field(message, spec["field"])
    if value in spec.get("invalid_values", []):
        return None
    if "values" in spec:
        value = spec["values"].get(value)
    if "scale" in spec or "offset" in spec:
        value = number(value)
        if value is None:
            return None
        value = value * float(spec.get("scale", 1)) + float(spec.get("offset", 0))
        value = number(value)
    return value
