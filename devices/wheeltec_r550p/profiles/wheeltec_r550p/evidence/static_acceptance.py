#!/usr/bin/env python3
"""UGV_003 stationary acceptance. Requires standby and an existing CCS map.
No motion goal or velocity command is published. Control tests are zero-only.
"""
import json, logging, os, subprocess, time, threading
from pathlib import Path
import rospy
from geometry_msgs.msg import Twist
from std_msgs.msg import Bool
from std_srvs.srv import Trigger, SetBool
from epgeneral_relocalization.config import load_config
from epgeneral_relocalization.ros_bridge import StackManager, RosBridge
from epgeneral_wheeltec_integration.native_maps import stop_process
w=Path('/home/nrc19/ccs_edge_ws')
map_id='static_acceptance'
state=w/'run/state/relocalization.json'
report={'map_id':map_id,'motion_goals_sent':0,'nonzero_commands':0}
logging.basicConfig(level=logging.INFO)
rospy.init_node('ccs_static_acceptance',anonymous=True)
cfg=load_config(str(w/'config/wheeltec_r550p/relocalization.yaml'),str(w/'config/wheeltec_r550p/device.yaml'))
stack=StackManager(cfg,logging.getLogger('static_acceptance'));nav=None

def velocity(msg):
 if any(abs(v)>1e-9 for v in [msg.linear.x,msg.linear.y,msg.linear.z,msg.angular.x,msg.angular.y,msg.angular.z]):
  report['nonzero_commands']+=1
rospy.Subscriber('/wheeltec_driver/cmd_vel',Twist,velocity,queue_size=100)
try:
 stack.start(map_id,str(w/'maps/download'/map_id))
 bridge=RosBridge(cfg,rospy,logging.getLogger('tf'))
 deadline=time.monotonic()+15
 while bridge.publisher.get_num_connections()<1 and time.monotonic()<deadline: time.sleep(.2)
 completed=threading.Event(); result=[]
 def done(*args): result.extend(args);completed.set()
 bridge.publish_and_monitor(0.0,0.0,0.0,{},done)
 assert completed.wait(40), 'TF callback timeout'
 assert result[0], str(result)
 report['localization_transform']=result[1]
 state.write_text(json.dumps({'schema_version':2,'map_id':map_id,'status':'localized'}))
 f=(w/'log/acceptance-navigation.log').open('w')
 nav=subprocess.Popen(['roslaunch','epgeneral_wheeltec_integration','navigation.launch','map_name:='+map_id,'map_dir:='+str(w/'maps/download'/map_id)],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
 deadline=time.monotonic()+100
 while time.monotonic()<deadline:
  assert nav.poll() is None, 'navigation exited; see acceptance-navigation.log'
  try:
   ready=json.loads((w/'run/state/native_navigation.json').read_text())
   if ready.get('ready') and ready.get('map_id')==map_id and time.monotonic()-ready['monotonic']<2: break
  except (OSError,ValueError): pass
  time.sleep(.5)
 else: raise RuntimeError('navigation readiness timeout')
 report['navigation_ready']=ready
 report['velocity_subscribers']=subprocess.check_output(['rostopic','info','/wheeltec_driver/cmd_vel'],text=True)
 for name in ['/wheeltec_control/enable','/wheeltec_control/stop','/wheeltec_control/reset']: rospy.wait_for_service(name,10)
 enable=rospy.ServiceProxy('/wheeltec_control/enable',SetBool)
 stop=rospy.ServiceProxy('/wheeltec_control/stop',Trigger)
 reset=rospy.ServiceProxy('/wheeltec_control/reset',Trigger)
 assert reset().success
 assert enable(True).success
 time.sleep(3)
 report['gate_eligible_after_idle']=rospy.wait_for_message('/wheeltec_control/enabled',Bool,timeout=3).data
 assert report['gate_eligible_after_idle']
 assert stop().success
 time.sleep(.4)
 assert not rospy.wait_for_message('/wheeltec_control/enabled',Bool,timeout=3).data
 report['emergency_stop']=True
 assert reset().success
 assert enable(False).success
 report['reset_to_manual']=True
 assert report['nonzero_commands']==0
 report['success']=True
finally:
 if nav is not None: stop_process(nav)
 stack.stop()
 state.write_text(json.dumps({'schema_version':2,'map_id':'','status':'idle'}))
 (w/'log/acceptance-result.json').write_text(json.dumps(report,indent=2))
 print(json.dumps(report,indent=2))
