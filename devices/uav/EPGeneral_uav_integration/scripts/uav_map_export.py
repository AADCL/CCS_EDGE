#!/usr/bin/env python3
import json,sys,time
from pathlib import Path
import rospy,tf2_ros
from fast_lio_sam.srv import save_map
from epgeneral_uav_integration.core import transform_matrix
from epgeneral_uav_integration.maps import export

def main():
    root=Path(sys.argv[1]).resolve()
    raw=root/('native-'+str(time.time_ns()))
    if raw.exists():raise ValueError('native map destination already exists')
    rospy.init_node('uav_map_export',anonymous=True)
    buffer=tf2_ros.Buffer();listener=tf2_ros.TransformListener(buffer)
    t=buffer.lookup_transform('odom','camera_init',rospy.Time(0),rospy.Duration(10)).transform
    matrix=transform_matrix([t.translation.x,t.translation.y,t.translation.z],[t.rotation.x,t.rotation.y,t.rotation.z,t.rotation.w])
    rospy.wait_for_service('/ducted/mapping/save_map',timeout=10)
    started=time.time()
    result=rospy.ServiceProxy('/ducted/mapping/save_map',save_map)(0.,str(raw))
    pcd=raw/'GlobalMap.pcd'
    if not result.success or not pcd.is_file() or pcd.stat().st_mtime<started-1:raise RuntimeError('no fresh native map')
    count=export(pcd,root,matrix)
    print(json.dumps(dict(success=True,points=count,source=str(pcd),frame_id='odom')))
if __name__=='__main__':main()
