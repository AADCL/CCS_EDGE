#!/usr/bin/env python3
"""Read-only configuration/dependency checks. No ROS node or log creation."""
import ast
import importlib
import os
import shutil
import subprocess

import rospkg
import yaml


MAPPING_PACKAGE = "epgeneral_uav_integration"
MAPPING_CLIENT = "uav_stage_client.py"
MAPPING_CHECK_TIMEOUT_SECONDS = 10


def _brief_process_error(completed):
    output = (completed.stderr or "") + "\n" + (completed.stdout or "")
    lines = [" ".join(line.split()) for line in output.splitlines() if line.strip()]
    return lines[-1][:240] if lines else "exit code %s" % completed.returncode


def _check_mapping_integration():
    rosrun = shutil.which("rosrun")
    if not rosrun:
        raise RuntimeError("mapping integration unavailable: rosrun not found in PATH")

    import roslib.packages
    clients = roslib.packages.find_node(MAPPING_PACKAGE, MAPPING_CLIENT)
    if not clients:
        raise RuntimeError(
            "mapping integration unavailable: %s could not be resolved by ROS"
            % MAPPING_CLIENT)

    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        completed = subprocess.run(
            [rosrun, MAPPING_PACKAGE, MAPPING_CLIENT, "offline_check"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=MAPPING_CHECK_TIMEOUT_SECONDS,
            env=environment,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            "mapping integration offline_check timed out after %ss"
            % MAPPING_CHECK_TIMEOUT_SECONDS) from None
    except OSError as error:
        raise RuntimeError(
            "mapping integration offline_check could not start: %s" % error) from None
    if completed.returncode:
        raise RuntimeError(
            "mapping integration offline_check failed: %s"
            % _brief_process_error(completed))


def check(root):
    import msgpack,paho.mqtt.client
    cfg=root/'src/EPGeneral_device_config/config'
    for name in ('device','epgeneral_mqtav','udp_telemetry','video','map_stream','relocalization','task_control'):
        data=yaml.safe_load((cfg/(name+'.yaml')).read_text())
        if not isinstance(data,dict):raise ValueError(name+' config invalid')
    for name,filename in [('epgeneral_task_control','task_control'),('epgeneral_map_stream','map_stream'),
                           ('epgeneral_relocalization','relocalization')]:
        module=importlib.import_module(name+'.config')
        module.load_config(str(cfg/(filename+'.yaml')),str(cfg/'device.yaml'))
    from epgeneral_mqtav.config import load_config as mqtt_config
    mqtt_config(str(cfg/'epgeneral_mqtav.yaml'),str(cfg/'device.yaml'))
    packs=rospkg.RosPack()
    for name in ('epgeneral_device_config','epgeneral_mqtav','epgeneral_udp_telemetry','epgeneral_video_srt',
                 'epgeneral_map_stream','epgeneral_relocalization','epgeneral_task_control',
                 'epgeneral_uav_integration','ducted_bringup','ducted_offboard','mavros','livox_ros_driver2'):
        packs.get_path(name)
    for p in (root/'src/EPGeneral_uav_integration').rglob('*.py'):ast.parse(p.read_text(),filename=str(p))
    for plugin in ('rtspsrc','decodebin','avdec_h265','x264enc','mpegtsmux','srtsink'):
        subprocess.run(['gst-inspect-1.0',plugin],stdout=subprocess.DEVNULL,check=True)
    _check_mapping_integration()
    return {'check':'passed','workspace':str(root),'nodes_started':0,'runtime_logs_created':0}
