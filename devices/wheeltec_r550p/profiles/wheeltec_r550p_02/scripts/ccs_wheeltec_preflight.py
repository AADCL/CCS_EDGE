#!/usr/bin/env python3
"""Read-only checks for the UGV_004 V5.1 overlay, including on-demand launches."""
import argparse
import importlib
import json
import math
import os
from pathlib import Path
import socket
import sys
from urllib.parse import urlparse

PACKAGES = ('epgeneral_device_config', 'epgeneral_mqtav', 'epgeneral_udp_telemetry',
            'epgeneral_video_srt', 'epgeneral_map_stream', 'epgeneral_relocalization',
            'epgeneral_task_control')
CONFIG_NAMES = ('device', 'epgeneral_mqtav', 'udp_telemetry', 'video', 'map_stream',
                'relocalization', 'task_control')


def validate_profile(profile, workspace, native, device_ip, station_ip):
    import yaml
    config = {name: yaml.safe_load((profile / (name + '.yaml')).read_text(encoding='utf-8'))
              for name in CONFIG_NAMES}
    master = urlparse(os.environ.get('ROS_MASTER_URI', 'http://127.0.0.1:11311'))
    if master.scheme != 'http' or master.hostname not in ('localhost', '127.0.0.1', device_ip):
        raise ValueError('ROS master must be local to this device')
    if config['device']['device'] != {'id': 'UGV_004', 'ip': device_ip}:
        raise ValueError('UGV_004 identity does not match startup')
    for name in ('map_stream', 'relocalization', 'task_control'):
        if config[name]['network']['ground_station_ip'] != station_ip:
            raise ValueError(name + ': ground station mismatch')
    if config['epgeneral_mqtav']['mqtt']['ground_station_ip'] != station_ip:
        raise ValueError('MQTT ground station mismatch')
    if config['udp_telemetry']['network']['destination_host'] != station_ip:
        raise ValueError('UDP ground station mismatch')
    if config['video'].get('enabled') and config['video'].get('image_topic') != '/camera/color/image_raw':
        raise ValueError('Gemini RGB topic must be /camera/color/image_raw')
    if config['task_control']['timeouts']['utc_tolerance_seconds'] != 2.0:
        raise ValueError('Task UTC tolerance must remain two seconds')
    state = str(workspace / 'run/state/relocalization.json')
    maps = str(workspace / 'maps/download')
    adapter = config['task_control']['adapter']
    storage = config['relocalization']['storage']
    pgm = next(item['source'] for item in config['udp_telemetry']['descriptors']
               if item['name'] == 'pgm_mapping')
    if any(value != state for value in (adapter['active_map_state_file'],
            storage['active_map_state_file'], pgm['state_file'])):
        raise ValueError('Map state paths must agree')
    if any(value != maps for value in (adapter['navigation_map_root'], storage['map_root'], pgm['map_root'])):
        raise ValueError('Downloaded map paths must agree')
    if (adapter['navigation_launch_package'], adapter['navigation_launch_file']) != (
            'epgeneral_task_control', 'wheeltec_ccs_2d_navigation_v51.launch'):
        raise ValueError('CCS two-dimensional navigation entry is required')
    mapping = config['map_stream']
    extrinsics = native / 'src/wheeltec_tf_manager/config/extrinsics.yaml'
    if mapping['integrations']['mapping_prerequisites']['extrinsics_file'] != str(extrinsics):
        raise ValueError('Extrinsics must reference this native workspace')
    transforms = yaml.safe_load(extrinsics.read_text(encoding='utf-8'))['transforms']
    calibration = next(item for item in transforms
                       if item['parent'] == 'base_link' and item['child'] == 'body')
    # publish_inverse affects the TF broadcast direction, not the measured matrix.
    from tf.transformations import quaternion_from_euler
    q = quaternion_from_euler(*(math.radians(calibration.get(k, 0.0))
                               for k in ('roll_deg', 'pitch_deg', 'yaw_deg')))
    expected = [calibration[k] for k in ('x', 'y', 'z')] + list(q)
    actual = [mapping['ros']['body_from_sensor'][k] for k in ('x', 'y', 'z', 'qx', 'qy', 'qz', 'qw')]
    if any(abs(a-b) > 1e-6 for a, b in zip(actual, expected)):
        raise ValueError('body_from_sensor must encode base_link <- body from this device')
    yaml.safe_load((native / 'src/wheeltec_system_bringup/config/wheeltec_geometry.yaml').read_text(encoding='utf-8'))
    for name, value in config.items():
        if any(old in json.dumps(value) for old in ('UGV_003', '/home/nrc19', '192.168.50.122')):
            raise ValueError('Foreign device configuration in ' + name)
    return config


def validate_launch(arguments):
    import roslaunch
    import roslib.packages
    launch_file = roslaunch.rlutil.resolve_launch_arguments(arguments)[0]
    remappings = [arg for arg in arguments if ':=' in arg]
    launch = roslaunch.config.load_config_default([(launch_file, remappings)], None, verbose=False)
    for node in launch.nodes:
        if not roslib.packages.find_node(node.package, node.type):
            raise ValueError('Missing executable {}/{}'.format(node.package, node.type))
    print('launch {}: {} executable nodes resolved'.format(launch_file, len(launch.nodes)))
    return launch


def validate_installation(args):
    import rospkg
    import roslib.message
    import msgpack
    import paho.mqtt.client
    import shutil
    if shutil.which('bwrap') is None:
        raise ValueError('bubblewrap is required to keep native FAST-LIO runtime writes inside CCS')
    config = validate_profile(args.profile, args.workspace, args.native_workspace,
                              args.device_ip, args.station_ip)
    packages = rospkg.RosPack()
    src = (args.workspace / 'src').resolve()
    for name in PACKAGES:
        package_path = Path(packages.get_path(name))
        if package_path.is_symlink() or src not in package_path.resolve().parents:
            raise ValueError(name + ' must resolve to an entity under CCS src')
        print('package {}={}'.format(name, package_path))
    for module, filename in (('epgeneral_mqtav.config', 'epgeneral_mqtav'),
                             ('epgeneral_udp_telemetry.config', 'udp_telemetry'),
                             ('epgeneral_map_stream.config', 'map_stream'),
                             ('epgeneral_relocalization.config', 'relocalization'),
                             ('epgeneral_task_control.config', 'task_control')):
        importlib.import_module(module).load_config(str(args.profile / (filename + '.yaml')),
                                                  str(args.profile / 'device.yaml'))
    for message in ('livox_ros_driver2/CustomMsg', 'nav_msgs/Odometry', 'sensor_msgs/Imu',
                    'std_msgs/Float32', 'geometry_msgs/Twist',
                    'epgeneral_task_control/TaskExecutionCommand',
                    'epgeneral_task_control/TaskExecutionFeedback'):
        cls = roslib.message.get_message_class(message)
        if cls is None:
            raise ValueError('Missing ROS message ' + message)
        print('message {} md5={}'.format(message, cls._md5sum))
    managed = config['map_stream']['integrations']['managed']
    for prefix, extra in (('fast_lio', ['rviz:=false']), ('mapper', ['map_name:=19700101_000000']),
                          ('tf', []), ('pose', [])):
        validate_launch([managed[prefix + '_package'], managed[prefix + '_launch']] + extra)
    finalizer = Path(packages.get_path(managed['finalize_package'])) / 'scripts' / managed['finalize_executable']
    if not os.access(str(finalizer), os.X_OK):
        raise ValueError('Finalizer is not executable: ' + str(finalizer))
    values = dict(map_id='__preflight__', map_root=str(args.workspace / 'maps/download'),
                  map_dir=str(args.workspace / 'maps/download/__preflight__'),
                  map_pcd=str(args.workspace / 'maps/download/__preflight__/public_map.pcd'),
                  map_yaml=str(args.workspace / 'maps/download/__preflight__/map.yaml'))
    for stage in config['relocalization']['ros']['stages']:
        validate_launch([stage['package'], stage['launch']] +
                        [arg.format(**values) for arg in stage.get('args', [])])
    adapter = config['task_control']['adapter']
    launch = validate_launch([adapter['navigation_launch_package'], adapter['navigation_launch_file'],
                             'map_dir:=' + values['map_dir'], 'nav_map_yaml:=' + values['map_yaml']])
    if any(node.package in ('turn_on_wheeltec_robot', 'livox_ros_driver2', 'fast_lio')
           or node.type == 'terrain_map_server_node' for node in launch.nodes):
        raise ValueError('Navigation must not duplicate drivers/localization or require terrain files')
    plugins = launch.params['/move_base/global_costmap/plugins'].value
    if [item['type'] for item in plugins] != ['costmap_2d::StaticLayer', 'costmap_2d::InflationLayer']:
        raise ValueError('Navigation global costmap is not the CCS 2D contract')
    # Bind and immediately close only currently unowned endpoints. Running CCS is
    # checked by its owning root script; --check also works against an active stack.
    import rosgraph
    active = set()
    if rosgraph.is_master_online():
        master = rosgraph.Master('/ccs_wheeltec_preflight')
        active = {name for group in master.getSystemState() for unused, names in group for name in names}
    for port, kind, owner in ((14561, socket.SOCK_DGRAM, '/epgeneral_map_stream'),
                              (14563, socket.SOCK_DGRAM, '/epgeneral_task_control'),
                              (14565, socket.SOCK_DGRAM, '/epgeneral_relocalization'),
                              (14600, socket.SOCK_STREAM, '/epgeneral_map_stream')):
        if owner not in active:
            with socket.socket(socket.AF_INET, kind) as sock:
                sock.bind(('0.0.0.0', port))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path)
    parser.add_argument('--workspace', type=Path)
    parser.add_argument('--native-workspace', type=Path)
    parser.add_argument('--device-ip', default='192.168.50.123')
    parser.add_argument('--station-ip', default='192.168.50.101')
    parser.add_argument('--launch', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        if args.launch:
            validate_launch(args.launch)
        else:
            validate_installation(args)
        return 0
    except Exception as error:
        print('Wheeltec preflight failed: {}'.format(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
