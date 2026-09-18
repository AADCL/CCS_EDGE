#!/usr/bin/env python3
"""ROS entry point for Wheeltec control-authority coordination."""
from __future__ import absolute_import

import rospy

from epgeneral_task_control.config import load_config
from epgeneral_task_control.wheeltec_control import WheeltecControlAuthority


def main():
    rospy.init_node("wheeltec_control")
    task_config = rospy.get_param("~task_config_file", "")
    device_config = rospy.get_param("~device_config_file", "")
    if not task_config or not device_config:
        raise rospy.ROSInitException("task and device config paths are required")
    config = load_config(task_config, device_config)
    authority = config.get("adapter", {}).get("control_authority")
    if not authority:
        raise rospy.ROSInitException("adapter.control_authority is required")
    node = WheeltecControlAuthority(rospy, authority)
    node.start()
    rospy.loginfo("Wheeltec control authority coordinator started in manual mode")
    rospy.spin()


if __name__ == "__main__":
    main()
