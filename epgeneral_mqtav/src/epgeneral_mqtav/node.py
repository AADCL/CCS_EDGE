"""Explicit profile selection and lifecycle management for the generic bridge."""
import argparse
import json
import sys
from pathlib import Path

from .config import ConfigError, load_config
from .durable_logging import build_logger
from .mqtt_client import MqttPublisher
from .ros_bridge import RosBridge
from .state import HealthState
from .version import get_version


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Publish configurable ROS health telemetry to MQTT")
    parser.add_argument("--config-dir", default="", help="directory containing device.yaml and epgeneral_mqtav.yaml")
    parser.add_argument("--config-file", default="", help="legacy explicit epgeneral_mqtav.yaml path (requires --device-config-file)")
    parser.add_argument("--device-config-file", default="", help="legacy explicit device.yaml path")
    parser.add_argument("--log-dir", default="", help="defaults to ~/.ros/log/epgeneral_mqtav/<device_id>")
    parser.add_argument("--check-config", action="store_true", help="validate and print resolved deployment; no ROS or MQTT required")
    parser.add_argument("--check-ros", action="store_true", help="also validate installed ROS message types and field paths, then exit")
    raw_args = list(sys.argv[1:] if argv is None else argv)
    # Private roslaunch remappings remain available to rospy through sys.argv.
    return parser.parse_args([arg for arg in raw_args if not (arg.startswith("__") and ":=" in arg)])


def config_paths(args):
    if args.config_dir:
        if args.config_file or args.device_config_file:
            raise ConfigError("use --config-dir OR both explicit config files, not both")
        directory = Path(args.config_dir).expanduser().resolve()
        return directory / "epgeneral_mqtav.yaml", directory / "device.yaml"
    if not args.config_file or not args.device_config_file:
        raise ConfigError("select --config-dir, or supply both --config-file and --device-config-file; sample identity is never selected automatically")
    return Path(args.config_file).expanduser().resolve(), Path(args.device_config_file).expanduser().resolve()


def describe(config):
    ros = config.ros
    sources = {}
    for label in ("state", "battery", "mission", "connection"):
        spec = getattr(ros, label)
        sources[label] = {"topic": spec.topic, "message_type": spec.message_type} if spec is not None and spec.enabled else None
    return {"config_schema_version": config.schema_version,
            "device_id": config.device.device_id, "device_ip": config.device.ip_address,
            "client_id": config.client_id, "topics": dict(config.mqtt.topics),
            "broker": {"ip": config.mqtt.ground_station_ip, "port": config.mqtt.port},
            "connection_mode": ros.connection_mode, "percentage_unit": ros.battery.percentage_unit,
            "sources": sources}


def run(argv=None, rospy_module=None):
    args = parse_args(argv)
    try:
        config_file, device_file = config_paths(args)
        config = load_config(config_file, device_file)
    except ConfigError as exc:
        print("epgeneral_mqtav configuration error: {0}".format(exc), file=sys.stderr)
        return 2
    if args.check_config or args.check_ros:
        if args.check_ros:
            try:
                RosBridge(config, None, None, None).validate_sources()
            except Exception as exc:
                print("epgeneral_mqtav ROS validation error: {0}".format(exc), file=sys.stderr)
                return 2
        print(json.dumps(describe(config), ensure_ascii=False, indent=2, allow_nan=False))
        return 0

    log_dir = args.log_dir or str(Path.home() / ".ros/log/epgeneral_mqtav" / config.device.device_id)
    logger = build_logger(log_dir)
    logger.info("configuration_loaded path=%s device_config=%s mode=%s schema=%s",
                config_file, device_file, config.ros.connection_mode, config.schema_version)
    if config.schema_version == 1:
        logger.warning("legacy_configuration migrate_to_schema_version=2 for explicit connection mode and battery units")
    publisher, bridge = None, None
    timers = []
    stopped = [False]

    def shutdown():
        if stopped[0]:
            return
        stopped[0] = True
        actions = [timer.shutdown for timer in timers]
        if bridge is not None:
            actions.append(bridge.stop)
        if publisher is not None:
            actions.append(publisher.stop)
        for action in actions:
            try:
                action()
            except Exception:
                logger.exception("shutdown_resource_error")

    try:
        health = HealthState(config.device)
        bridge = RosBridge(config, health, logger, rospy_module)
        bridge.validate_sources()
        if rospy_module is None:
            import rospy as rospy_module
        bridge._rospy = rospy_module
        rospy_module.init_node(config.ros.node_name, anonymous=False)
        rospy_module.on_shutdown(shutdown)
        logger.info("epgeneral_mqtav_starting version=%s device_id=%s client_id=%s",
                    get_version(), config.device.device_id, config.client_id)
        bridge.start()
        publisher = MqttPublisher(config, health, logger)
        publisher.start()
        timers.append(rospy_module.Timer(rospy_module.Duration(1.0 / config.mqtt.heartbeat_hz), lambda _event: publisher.publish_heartbeat()))
        timers.append(rospy_module.Timer(rospy_module.Duration(1.0 / config.mqtt.telemetry_hz), lambda _event: publisher.publish_status()))
        rospy_module.spin()
        return 0
    except Exception:
        logger.exception("epgeneral_mqtav_fatal_error")
        return 1
    finally:
        shutdown()
