"""Python 3.6 compatible configuration for epgeneral_mqtav."""

import ipaddress
import re
from pathlib import Path
from string import Formatter

from .fields import field_path, number, validate_mapping


class ConfigError(ValueError):
    """Raised when config.yaml cannot safely describe a node deployment."""


class DeviceConfig(object):
    def __init__(self, device_id, ip_address):
        self.device_id = device_id
        self.ip_address = ip_address


class MqttConfig(object):
    def __init__(
        self,
        ground_station_ip,
        port,
        client_id_prefix,
        qos,
        keepalive_seconds,
        heartbeat_hz,
        telemetry_hz,
        topics,
    ):
        self.ground_station_ip = ground_station_ip
        self.port = port
        self.client_id_prefix = client_id_prefix
        self.qos = qos
        self.keepalive_seconds = keepalive_seconds
        self.heartbeat_hz = heartbeat_hz
        self.telemetry_hz = telemetry_hz
        self.topics = topics


class RosTopicConfig(object):
    def __init__(
        self,
        topic,
        message_type,
        mapping=None,
        connected_on_message=False,
        timeout_seconds=None,
        enabled=True,
    ):
        self.topic = topic
        self.message_type = message_type
        self.mapping = mapping or {}
        self.connected_on_message = connected_on_message
        self.timeout_seconds = timeout_seconds
        self.enabled = enabled
        self.percentage_unit = "legacy_auto"


class MissionConfig(object):
    def __init__(self, enabled, topic=None, message_type=None, field_path=None):
        self.enabled = enabled
        self.topic = topic
        self.message_type = message_type
        self.field_path = field_path


class RosConfig(object):
    def __init__(self, node_name, state, battery, mission, connection=None):
        self.node_name = node_name
        self.state = state
        self.battery = battery
        self.mission = mission
        self.connection = connection
        self._connection_mode = None

    @property
    def connection_mode(self):
        if self._connection_mode is not None:
            return self._connection_mode
        if self.connection is not None:
            return "heartbeat"
        return "freshness" if self.state.connected_on_message else "field"


class AppConfig(object):
    def __init__(self, device, mqtt, ros):
        self.device = device
        self.mqtt = mqtt
        self.ros = ros

    def topic(self, name):
        return self.mqtt.topics[name]

    @property
    def client_id(self):
        return "{0}{1}".format(self.mqtt.client_id_prefix, self.device.device_id)


def _mapping(value, path):
    if not isinstance(value, dict):
        raise ConfigError("{0} must be a mapping".format(path))
    return value


def _string(value, path):
    if not isinstance(value, str) or not value.strip():
        raise ConfigError("{0} must be a non-empty string".format(path))
    return value.strip()


def _integer(value, path, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ConfigError("{0} must be an integer from {1} to {2}".format(path, minimum, maximum))
    return value


def _frequency(value, path):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or number(value) is None or not 0 < number(value) <= 100:
        raise ConfigError("{0} must be a number greater than 0 and no greater than 100".format(path))
    return float(value)


def _ip(value, path):
    text = _string(value, path)
    try:
        return str(ipaddress.ip_address(text))
    except ValueError as exc:
        raise ConfigError("{0} must be a valid IPv4 or IPv6 address".format(path)) from exc


def _timeout_seconds(value, path):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or number(value) is None or not 0.1 <= number(value) <= 3600:
        raise ConfigError("{0} must be between 0.1 and 3600 seconds".format(path))
    return float(value)


def _topic_config(value, path, mapping_fields=None, freshness=False):
    data = _mapping(value, path)
    topic = _string(data.get("topic"), "{0}.topic".format(path))
    message_type = _string(data.get("message_type"), "{0}.message_type".format(path))
    if not re.fullmatch(r"/[A-Za-z][A-Za-z0-9_]*(?:/[A-Za-z][A-Za-z0-9_]*)*", topic):
        raise ConfigError("{0}.topic must be an absolute ROS topic with valid name segments".format(path))
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*/[A-Za-z][A-Za-z0-9_]*", message_type):
        raise ConfigError("{0}.message_type must use package/Message syntax".format(path))
    mapping = {}
    if mapping_fields is not None:
        raw_mapping = data.get("mapping", {})
        if not isinstance(raw_mapping, dict):
            raise ConfigError("{0}.mapping must be a mapping".format(path))
        if set(raw_mapping) - set(mapping_fields):
            raise ConfigError("{0}.mapping contains unknown output fields".format(path))
        for field, default_path in mapping_fields.items():
            try:
                mapping[field] = validate_mapping(raw_mapping.get(field, default_path))
            except ValueError as exc:
                raise ConfigError("{0}.mapping.{1}: {2}".format(path, field, exc)) from exc
    connected_on_message = False
    timeout_seconds = None
    if freshness:
        connected_on_message = data.get("connected_on_message", False)
        if not isinstance(connected_on_message, bool):
            raise ConfigError("{0}.connected_on_message must be true or false".format(path))
        if connected_on_message:
            timeout_seconds = _timeout_seconds(data.get("timeout_seconds", 3.0), "{0}.timeout_seconds".format(path))
    return RosTopicConfig(topic, message_type, mapping, connected_on_message, timeout_seconds)


def _load_yaml(path):
    try:
        import yaml
    except ImportError as exc:
        raise ConfigError("PyYAML is required; install python3-yaml") from exc
    try:
        with path.open("r", encoding="utf-8") as stream:
            data = yaml.safe_load(stream)
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError("cannot read {0}: {1}".format(path, exc)) from exc
    return _mapping(data, "root")


def load_device_config(path):
    """Load the shared edge-side device identity file."""
    data = _load_yaml(Path(path))
    if type(data.get("schema_version")) is not int or data.get("schema_version") != 1:
        raise ConfigError("device config schema_version must be 1")
    device_data = _mapping(data.get("device"), "device")
    device_id = device_data.get("id")
    if not isinstance(device_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", device_id):
        raise ConfigError("device.id must be 1..64 ASCII letters/digits/_/-, starting with a letter or digit; case is preserved")
    return DeviceConfig(
        device_id,
        _ip(device_data.get("ip"), "device.ip"),
    )


def load_config(path, device_config_path):
    """Load epgeneral_mqtav and shared device configs."""
    data = _load_yaml(Path(path))
    device = load_device_config(device_config_path)
    schema = data.get("schema_version", 1)
    if type(schema) is not int or schema not in (1, 2):
        raise ConfigError("epgeneral_mqtav schema_version must be 1 or 2")

    mqtt_data = _mapping(data.get("mqtt"), "mqtt")
    topics_data = _mapping(mqtt_data.get("topics"), "mqtt.topics")
    topics = {}
    for name in ("presence", "heartbeat", "status"):
        topic = _string(topics_data.get(name), "mqtt.topics.{0}".format(name))
        if "+" in topic or "#" in topic:
            raise ConfigError("mqtt.topics.{0} must not contain MQTT wildcards".format(name))
        topics[name] = _expand(topic, device.device_id, "mqtt.topics." + name, required=schema == 2)
        if any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in topics[name]) or len(topics[name].encode("utf-8")) > 65535:
            raise ConfigError("mqtt.topics.{0} contains control characters or is too long".format(name))
    if len(set(topics.values())) != 3:
        raise ConfigError("mqtt.topics must be distinct")
    mqtt = MqttConfig(
        _ip(mqtt_data.get("ground_station_ip"), "mqtt.ground_station_ip"),
        _integer(mqtt_data.get("port"), "mqtt.port", 1, 65535),
        _string(mqtt_data.get("client_id_prefix"), "mqtt.client_id_prefix"),
        _integer(mqtt_data.get("qos"), "mqtt.qos", 0, 1),
        _integer(mqtt_data.get("keepalive_seconds"), "mqtt.keepalive_seconds", 1, 3600),
        _frequency(mqtt_data.get("heartbeat_hz"), "mqtt.heartbeat_hz"),
        _frequency(mqtt_data.get("telemetry_hz"), "mqtt.telemetry_hz"),
        topics,
    )

    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", mqtt.client_id_prefix):
        raise ConfigError("mqtt.client_id_prefix must be 1..64 ASCII letters/digits/_/-")
    ros_data = _mapping(data.get("ros"), "ros")
    for label in ("state", "battery", "mission", "connection"):
        spec = ros_data.get(label)
        if isinstance(spec, dict) and "topic" in spec:
            spec["topic"] = _expand(spec["topic"], device.device_id, "ros." + label + ".topic")
    mode = ros_data.get("connection_mode")
    if (schema == 2 or mode is not None) and mode not in ("field", "freshness", "heartbeat", "disabled"):
        raise ConfigError("ros.connection_mode must be field, freshness, heartbeat or disabled")
    if schema == 2:
        _known(data, {"schema_version", "mqtt", "ros"}, "root")
        _known(mqtt_data, {"ground_station_ip", "port", "client_id_prefix", "qos", "keepalive_seconds", "heartbeat_hz", "telemetry_hz", "topics"}, "mqtt")
        _known(topics_data, {"presence", "heartbeat", "status"}, "mqtt.topics")
        _known(ros_data, {"node_name", "connection_mode", "state", "battery", "mission", "connection"}, "ros")
        for label, keys in (
            ("state", {"enabled", "topic", "message_type", "mapping", "connected_on_message", "timeout_seconds"}),
            ("battery", {"enabled", "topic", "message_type", "mapping", "percentage_unit"}),
            ("mission", {"enabled", "topic", "message_type", "field_path"}),
            ("connection", {"topic", "message_type", "timeout_seconds"}),
        ):
            if ros_data.get(label) is not None:
                _known(_mapping(ros_data[label], "ros." + label), keys, "ros." + label)
    mission_data = _mapping(ros_data.get("mission", {"enabled": False}), "ros.mission")
    enabled = mission_data.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ConfigError("ros.mission.enabled must be true or false")
    if enabled:
        mission_topic = _topic_config(mission_data, "ros.mission")
        mission = MissionConfig(
            True,
            mission_topic.topic,
            mission_topic.message_type,
            _validated_field(mission_data.get("field_path"), "ros.mission.field_path"),
        )
    else:
        mission = MissionConfig(False)
    battery_data = _mapping(ros_data.get("battery"), "ros.battery")
    battery_enabled = battery_data.get("enabled", True)
    if not isinstance(battery_enabled, bool):
        raise ConfigError("ros.battery.enabled must be true or false")
    if battery_enabled:
        battery = _topic_config(
            battery_data,
            "ros.battery",
            {"percentage": "percentage", "voltage": "voltage", "current": "current"},
        )
    else:
        battery = RosTopicConfig(
            "",
            "",
            {"percentage": None, "voltage": None, "current": None},
            enabled=False,
        )
    unit = battery_data.get("percentage_unit", "legacy_auto")
    if unit not in ("fraction", "percent", "legacy_auto"):
        raise ConfigError("ros.battery.percentage_unit must be fraction, percent or legacy_auto")
    if schema == 2 and battery_enabled and "percentage_unit" not in battery_data:
        raise ConfigError("ros.battery.percentage_unit is required in schema 2")
    battery.percentage_unit = unit
    connection = None
    if ros_data.get("connection") is not None:
        connection_data = _mapping(ros_data["connection"], "ros.connection")
        connection = _topic_config(connection_data, "ros.connection")
        connection.connected_on_message = True
        connection.timeout_seconds = _timeout_seconds(
            connection_data.get("timeout_seconds", 3.0), "ros.connection.timeout_seconds"
        )
    state_data = _mapping(ros_data.get("state"), "ros.state")
    state_enabled = state_data.get("enabled", True)
    if not isinstance(state_enabled, bool):
        raise ConfigError("ros.state.enabled must be true or false")
    if state_enabled:
        state = _topic_config(state_data, "ros.state",
            {"connected": "connected", "armed": "armed", "system_status": "system_status", "mode": "mode"}, freshness=True)
    else:
        state = RosTopicConfig("", "", enabled=False)
    if mode is not None:
        if mode == "heartbeat" and connection is None:
            raise ConfigError("ros.connection is required for heartbeat mode")
        if mode != "heartbeat" and connection is not None:
            raise ConfigError("ros.connection is only allowed in heartbeat mode")
        if mode in ("field", "freshness") and not state_enabled:
            raise ConfigError("ros.state must be enabled for field/freshness mode")
        if mode == "field" and state.mapping.get("connected") is None:
            raise ConfigError("ros.state.mapping.connected is required for field mode")
        state.connected_on_message = mode == "freshness"
        state.timeout_seconds = _timeout_seconds(state_data.get("timeout_seconds", 3.0), "ros.state.timeout_seconds") if mode == "freshness" else None
    elif not state_enabled and connection is None:
        mode = "disabled"
    node_name = _string(ros_data.get("node_name"), "ros.node_name")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", node_name):
        raise ConfigError("ros.node_name must be a ROS base name")
    ros = RosConfig(
        node_name,
        state,
        battery,
        mission,
        connection,
    )
    ros._connection_mode = mode
    result = AppConfig(device, mqtt, ros)
    result.schema_version = schema
    return result


def _expand(value, device_id, path, required=False):
    value = _string(value, path)
    try:
        fields = list(Formatter().parse(value))
        names = []
        for _, name, spec, conversion in fields:
            if name is not None:
                if name != "device_id" or spec or conversion:
                    raise ValueError("unsupported placeholder")
                names.append(name)
        if required and "device_id" not in names:
            raise ValueError("{device_id} is required in schema 2")
        expanded = value.format(device_id=device_id)
        if "{" in expanded or "}" in expanded:
            raise ValueError("literal braces are unsupported")
        return expanded
    except ValueError as exc:
        raise ConfigError("{0} only supports {{device_id}}: {1}".format(path, exc)) from exc


def _validated_field(value, path):
    try:
        return field_path(value)
    except ValueError as exc:
        raise ConfigError("{0}: {1}".format(path, exc)) from exc


def _known(data, allowed, path):
    if set(data) - allowed:
        raise ConfigError("{0} contains unknown keys: {1}".format(path, set(data) - allowed))
