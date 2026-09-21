#!/usr/bin/env python3
"""Read current hardware freshness; never publishes flight commands."""
import json,time
import rospy
from mavros_msgs.msg import State,ExtendedState
from geometry_msgs.msg import PoseStamped
from sensor_msgs.msg import Imu
from livox_ros_driver2.msg import CustomMsg
from std_msgs.msg import String
rospy.init_node('uav_readiness',anonymous=True)
results={}
for name,topic,cls,max_age in [
 ('state','/mavros/state',State,2),('extended','/mavros/extended_state',ExtendedState,2),
 ('pose','/mavros/local_position/pose',PoseStamped,.5),('imu','/mavros/imu/data',Imu,.5),
 ('lidar','/livox/lidar',CustomMsg,1),('video','/epgeneral_video_srt/status',String,2)]:
    try:
        m=rospy.wait_for_message(topic,cls,timeout=3)
        if hasattr(m,'header'):
            age=rospy.Time.now().to_sec()-m.header.stamp.to_sec()
            if not -.05<=age<=max_age:raise RuntimeError('source stale')
        if name=='state' and (not m.connected or m.armed):raise RuntimeError('not connected/disarmed')
        if name=='extended' and m.landed_state!=1:raise RuntimeError('not landed')
        if name=='video' and not json.loads(m.data).get('ready'):raise RuntimeError('video not ready')
        results[name]='passed'
    except Exception as e:results[name]=str(e)
print(json.dumps(results,indent=2))
raise SystemExit(0 if all(v=='passed' for v in results.values()) else 1)
