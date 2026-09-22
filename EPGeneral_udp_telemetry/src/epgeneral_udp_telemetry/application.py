"""Explicit, side-effect-free deployment selection and ROS runtime orchestration."""
import argparse
import json
from pathlib import Path
import sys

from .config import ConfigError, load_config, ros_topic, validate_destination
from .sources import validate_ros_sources


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Generic ROS/file to CCS UDP telemetry")
    parser.add_argument("--config-dir", default="")
    parser.add_argument("--telemetry-config-file", default="")
    parser.add_argument("--device-config-file", default="")
    parser.add_argument("--destination-host", default="")
    parser.add_argument("--destination-port", default="")
    parser.add_argument("--link-status-topic", default="")
    parser.add_argument("--diagnostics-topic", default="")
    parser.add_argument("--check-config", action="store_true")
    parser.add_argument("--check-ros", action="store_true")
    args = sys.argv[1:] if argv is None else argv
    return parser.parse_args([arg for arg in args if not (arg.startswith("__") and ":=" in arg)])


def select_config(args):
    if args.config_dir:
        if args.telemetry_config_file or args.device_config_file:
            raise ConfigError("use config-dir OR both explicit config files, not both")
        folder = Path(args.config_dir).expanduser().resolve()
        telemetry, device = folder / "udp_telemetry.yaml", folder / "device.yaml"
    elif args.telemetry_config_file and args.device_config_file:
        telemetry, device = Path(args.telemetry_config_file).expanduser(), Path(args.device_config_file).expanduser()
    else:
        raise ConfigError("select config-dir or both explicit files; no implicit sample identity")
    config = load_config(telemetry, device)
    if args.destination_host:
        config["destination_host"] = args.destination_host
    if args.destination_port != "":
        try:
            config["destination_port"] = int(args.destination_port)
        except (TypeError, ValueError) as exc:
            raise ConfigError("destination-port must be an integer") from exc
    validate_destination(config)
    for key in ("link_status_topic", "diagnostics_topic"):
        if getattr(args, key):
            config[key] = ros_topic(getattr(args, key), config["device_id"], key)
    return config


def run(argv=None, rospy_module=None):
    args = parse_args(argv)
    try:
        config = select_config(args)
        if args.check_config or args.check_ros:
            if args.check_ros:
                validate_ros_sources(config)
            # Status maps can have mixed scalar keys; avoid sorting those keys.
            print(json.dumps(config, ensure_ascii=False, indent=2, allow_nan=False))
            return 0
        classes = validate_ros_sources(config)
    except (ConfigError, ImportError) as exc:
        print("UDP telemetry configuration error: %s" % exc, file=sys.stderr)
        return 2
    from .node import RosUdpTelemetryNode
    node = None
    try:
        if rospy_module is None:
            import rospy as rospy_module
        rospy_module.init_node("epgeneral_udp_telemetry")
        node = RosUdpTelemetryNode(rospy_module, config)
        node._classes = classes
        rospy_module.loginfo("UDP effective configuration device=%s destination=%s:%s descriptor_hash=%s schema=%s",
                             config["device_id"], config["destination_host"], config["destination_port"], config["descriptor_hash"], config["schema_version"])
        node.start()
        rospy_module.spin()
        return 0
    except Exception as exc:
        print("UDP telemetry runtime error: %s" % exc, file=sys.stderr)
        return 1
    finally:
        if node is not None:
            node.close()
