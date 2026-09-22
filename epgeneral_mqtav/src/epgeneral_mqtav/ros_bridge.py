"""Python 3.6 compatible ROS subscription boundary for configurable health telemetry."""

import time
from threading import Lock

from .config import RosTopicConfig
from .fields import extract, read_field


def default_message_resolver(message_type):
    try:
        from roslib.message import get_message_class
    except ImportError as exc:
        raise RuntimeError("ROS roslib is required") from exc
    message_class = get_message_class(message_type)
    if message_class is None:
        raise RuntimeError("ROS message type is unavailable: {0}".format(message_type))
    return message_class


class RosBridge(object):
    def __init__(self, config, health, logger, rospy_module, message_resolver=default_message_resolver):
        self._config = config
        self._health = health
        self._logger = logger
        self._rospy = rospy_module
        self._message_resolver = message_resolver
        self._subscriptions = []
        self._last_state_message = None
        self._last_connection_message = None
        self._connection_lock = Lock()
        self._state_lock = Lock()
        self._message_classes = {}
        self._freshness_timer = None

    def _subscribe(self, spec, callback, label):
        message_class = self._message_classes[spec.message_type]
        self._subscriptions.append(self._rospy.Subscriber(spec.topic, message_class, callback, queue_size=10))
        self._logger.info("ros_subscribed stream=%s topic=%s type=%s", label, spec.topic, spec.message_type)

    def validate_sources(self):
        """Resolve every enabled source before opening any subscription or MQTT connection."""
        ros = self._config.ros
        specs = [ros.state, ros.battery, ros.mission]
        if ros.connection is not None:
            specs.append(ros.connection)
        classes = {}
        for spec in specs:
            if not spec.enabled:
                continue
            cls = self._message_resolver(spec.message_type)
            if cls is None:
                raise RuntimeError("ROS message type is unavailable: " + spec.message_type)
            classes[spec.message_type] = cls
            # Generated ROS message classes expose __slots__; test doubles need not.
            if hasattr(cls, "__slots__"):
                sample = cls()
                mappings = [value for key, value in getattr(spec, "mapping", {}).items()
                            if not (spec is ros.state and key == "connected" and ros.connection_mode != "field")]
                if getattr(spec, "field_path", None):
                    mappings.append(spec.field_path)
                for mapping in mappings:
                    if mapping is None:
                        continue
                    path = mapping["field"] if isinstance(mapping, dict) else mapping
                    try:
                        read_field(sample, path)
                    except (AttributeError, KeyError, TypeError, ValueError) as exc:
                        raise RuntimeError("{0} field {1} is unavailable".format(spec.message_type, path)) from exc

        self._message_classes = classes

    def stop(self):
        if self._freshness_timer is not None:
            self._freshness_timer.shutdown()
            self._freshness_timer = None
        subscriptions, self._subscriptions = self._subscriptions, []
        for subscription in subscriptions:
            subscription.unregister()

    def start(self):
        if not self._message_classes:
            self.validate_sources()
        connection = self._config.ros.connection
        if connection is not None:
            self._health.update_connected(False)
            self._subscribe(connection, self._on_connection, "connection")
        if self._config.ros.state.enabled:
            self._subscribe(self._config.ros.state, self._on_state, "state")
        if self._config.ros.battery.enabled:
            self._subscribe(self._config.ros.battery, self._on_battery, "battery")
        else:
            self._logger.info("ros_subscription_disabled stream=battery")
        state = self._config.ros.state
        if connection is not None:
            self._freshness_timer = self._rospy.Timer(
                self._rospy.Duration(min(1.0, connection.timeout_seconds / 2.0)),
                self._check_connection_freshness,
            )
        elif state.connected_on_message and state.timeout_seconds is not None:
            self._freshness_timer = self._rospy.Timer(
                self._rospy.Duration(min(1.0, state.timeout_seconds / 2.0)),
                self._check_state_freshness,
            )
        mission = self._config.ros.mission
        if mission.enabled:
            self._subscribe(RosTopicConfig(mission.topic or "", mission.message_type or ""), self._on_mission, "mission")

    def _on_state(self, message):
        with self._state_lock:
            mapping = self._config.ros.state.mapping
            self._last_state_message = time.monotonic()

            def mapped(name):
                field_path = mapping.get(name)
                if field_path is None:
                    return None
                try:
                    return extract(message, field_path)
                except (AttributeError, KeyError, TypeError, ValueError) as exc:
                    self._logger.warning("state_field_unavailable field=%s error=%s", name, exc)
                    return None

            independent_connection = self._config.ros.connection_mode in ("heartbeat", "disabled")
            connected = None
            if not independent_connection:
                connected = True if self._config.ros.state.connected_on_message else mapped("connected")
            self._health.update_state(
                connected,
                mapped("armed"),
                mapped("system_status"),
                mapped("mode"),
                preserve_connected=independent_connection,
            )

    def _on_connection(self, _message):
        with self._connection_lock:
            self._last_connection_message = time.monotonic()
            self._health.update_connected(True)

    def _check_connection_freshness(self, _event):
        with self._connection_lock:
            timeout = self._config.ros.connection.timeout_seconds
            if self._last_connection_message is None or time.monotonic() - self._last_connection_message > timeout:
                self._health.update_connected(False)

    def _on_battery(self, message):
        mapping = self._config.ros.battery.mapping

        def mapped(name):
            field_path = mapping.get(name)
            if field_path is None:
                return None
            try:
                return extract(message, field_path)
            except (AttributeError, KeyError, TypeError, ValueError) as exc:
                self._logger.warning("battery_field_unavailable field=%s error=%s", name, exc)
                return None

        self._health.update_battery(
            mapped("percentage"),
            mapped("voltage"),
            mapped("current"),
            percentage_unit=self._config.ros.battery.percentage_unit,
        )

    def _check_state_freshness(self, _event):
        with self._state_lock:
            timeout = self._config.ros.state.timeout_seconds
            if timeout is None:
                return
            if self._last_state_message is None or time.monotonic() - self._last_state_message > timeout:
                self._health.update_connected(False)

    def _on_mission(self, message):
        try:
            self._health.update_mission(read_field(message, self._config.ros.mission.field_path or ""))
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            self._health.update_mission(None)
            self._logger.warning("mission_status_unavailable error=%s", exc)
