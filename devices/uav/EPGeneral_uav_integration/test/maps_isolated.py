#!/usr/bin/env python3
"""Isolated native-save service and real relocalization TF/health bridge."""
import importlib.util,json,logging,math,os,signal,socket,subprocess,time,traceback
from pathlib import Path
import numpy as np
ROOT=Path('/home/nrc/ccs_edge_ws');OUT=ROOT/'validation'/('maps-'+time.strftime('%Y%m%d-%H%M%S'));OUT.mkdir(parents=True)
os.environ['ROS_MASTER_URI']='http://127.0.0.1:11328';os.environ['ROS_HOSTNAME']='127.0.0.1';os.environ.pop('ROS_IP',None)
os.environ['ROS_LOG_DIR']=str(OUT/'ros')
with socket.socket() as s:s.bind(('127.0.0.1',11328))
f=(OUT/'master.log').open('w');master=subprocess.Popen(['roscore','-p','11328'],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
import rospy,tf2_ros
from geometry_msgs.msg import TransformStamped,PoseWithCovarianceStamped
from std_msgs.msg import Bool
from fast_lio_sam.srv import save_map,save_mapResponse
from epgeneral_uav_integration.maps import read_pcd
from epgeneral_relocalization.config import load_config
from epgeneral_relocalization.ros_bridge import RosBridge
result={};timer=None
try:
    time.sleep(2);rospy.init_node('map_fixture')
    fixed=tf2_ros.StaticTransformBroadcaster()
    t=TransformStamped();t.header.stamp=rospy.Time.now();t.header.frame_id='odom';t.child_frame_id='camera_init'
    t.transform.translation.x=10;t.transform.translation.y=20;t.transform.translation.z=30
    t.transform.rotation.z=math.sqrt(.5);t.transform.rotation.w=math.sqrt(.5);fixed.sendTransform(t)
    mode=['good']
    def save(req):
        p=Path(req.destination);p.mkdir(parents=True)
        if mode[0]=='reject':return save_mapResponse(False)
        if mode[0]=='good':
            (p/'GlobalMap.pcd').write_text('VERSION .7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\nCOUNT 1 1 1\nWIDTH 2\nHEIGHT 1\nPOINTS 2\nDATA ascii\n1 0 2\n2 0 3\n')
        else:(p/'GlobalMap.pcd').write_text('invalid')
        return save_mapResponse(True)
    service=rospy.Service('/ducted/mapping/save_map',save_map,save)
    for case in ('good','reject','empty'):
        mode[0]=case
        completed=subprocess.run(['rosrun','epgeneral_uav_integration','uav_map_export.py',str(OUT/case)],capture_output=True,text=True,timeout=25)
        (OUT/(case+'.log')).write_text(completed.stdout+completed.stderr)
        assert (completed.returncode==0)==(case=='good'),completed.stderr
    np.testing.assert_allclose(read_pcd(OUT/'good/map.pcd'),[[10,21,32],[10,22,33]],atol=1e-5)
    result['native_save_transform_nonempty_reject_empty']=True
    cfg=load_config(str(ROOT/'src/EPGeneral_device_config/config/relocalization.yaml'),str(ROOT/'src/EPGeneral_device_config/config/device.yaml'))
    cfg.update(tf_timeout_seconds=2,tf_report_interval_seconds=.1)
    bridge=RosBridge(cfg,rospy,logging.getLogger('fixture'))
    health=rospy.Publisher(cfg['localization_health_topic'],Bool,queue_size=1)
    received=[]
    initial=rospy.Subscriber(cfg['initial_pose_topic'],PoseWithCovarianceStamped,lambda m:received.append(m))
    dynamic=tf2_ros.TransformBroadcaster();enable=[True,True]
    def publish(event):
        if enable[0]:health.publish(True)
        if enable[1]:
            tf=TransformStamped();tf.header.stamp=rospy.Time.now();tf.header.frame_id='map';tf.child_frame_id='odom';tf.transform.rotation.w=1;dynamic.sendTransform(tf)
    timer=rospy.Timer(rospy.Duration(.03),publish);time.sleep(.5)
    statuses=[];bridge.publish_and_monitor(1,2,.1,{},lambda *x:statuses.append(x));time.sleep(.7)
    assert received and any(x[0] for x in statuses)
    result['initial_pose_fresh_health_tf_success']=True
    enable[1]=False;time.sleep(.9);assert statuses[-1][0] is False,statuses
    result['stale_tf_rejected_despite_fresh_health']=True
    enable[:]=[True,True];statuses=[];bridge.publish_and_monitor(1,2,0,{},lambda *x:statuses.append(x));time.sleep(.5)
    enable[0]=False;time.sleep(.9);assert statuses[-1][0] is False
    result['stale_health_rejected']=True
    result['passed']=True
except Exception:
    result['passed']=False;result['error']=traceback.format_exc()
finally:
    if timer:timer.shutdown()
    rospy.signal_shutdown('test finished')
    os.killpg(master.pid,signal.SIGINT);master.wait(timeout=12);f.close()
    (OUT/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(dict(output=str(OUT),result=result)))
raise SystemExit(0 if result.get('passed') else 1)
