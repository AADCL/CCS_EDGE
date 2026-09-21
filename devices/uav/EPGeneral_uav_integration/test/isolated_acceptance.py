#!/usr/bin/env python3
"""Isolated CCS adapter + production native controller + fake MAVROS, never hardware."""
import importlib.util,json,os,socket,subprocess,sys,time,uuid,traceback
from pathlib import Path
import yaml
ROOT=Path('/home/nrc/ccs_edge_ws')
OUT=ROOT/'validation'/('isolated-'+time.strftime('%Y%m%d-%H%M%S'))
OUT.mkdir(parents=True)
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,str(path));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
native=load('native_fixture',Path('/home/nrc/catkin_ws/src/ducted_offboard/test/integration/offboard_isolated.py'))
os.environ.pop('ROS_IP',None)
os.environ['ROS_MASTER_URI']='http://127.0.0.1:11327';os.environ['ROS_HOSTNAME']='127.0.0.1'
os.environ['ROS_LOG_DIR']=str(OUT/'ros')
native.ROOT=OUT;native.LOG_ROOT=OUT
with socket.socket() as probe:probe.bind(('127.0.0.1',11327))
import rospy,tf2_ros
from std_msgs.msg import Bool
from nav_msgs.msg import Odometry
from geometry_msgs.msg import TransformStamped
from epgeneral_task_control.msg import TaskExecutionCommand as C,TaskExecutionFeedback as F
from epgeneral_task_control.storage import TrajectoryStore
from epgeneral_uav_integration.srv import StageCommandRequest
manager_module=load('stage_manager',ROOT/'src/EPGeneral_uav_integration/scripts/uav_stage_node.py')
children=[];manager=None;fake=None;results={};feedback={};history=[]
def launch(cmd,name):
    p=native.launch(cmd,name);children.append(p);return p
def wait(pred,timeout=20,what='condition'):
    return native.wait_for(pred,timeout,what)
def send(action,request=None,execution='',at=0):
    c=C(action=action,request_id=request or str(uuid.uuid4()),task_id='test',subtask_id='part',
        device_id='UAV_001',revision=1,map_id='fixture',frame_id='map',execution_id=execution,
        scheduled_at=rospy.Time.from_sec(at))
    pub.publish(c);return c
def response(c,state,timeout=20):
    return wait(lambda:feedback.get(c.request_id) if feedback.get(c.request_id) and feedback[c.request_id].state==state else None,timeout,state+' '+c.request_id)
def receive(f):
    feedback[f.request_id]=f;history.append(dict(request=f.request_id,state=f.state,error=f.error_code,message=f.message))
def adapter():
    return launch(['rosrun','epgeneral_uav_integration','uav_task_adapter.py','__name:=adapter',
                   '_config_file:='+str(OUT/'task.yaml'),'_device_config_file:='+str(ROOT/'src/EPGeneral_device_config/config/device.yaml'),
                   '_execution_enabled:=true'],'adapter-'+str(len(children)))
def reset():
    fake.reset();time.sleep(.3)
    if manager.controller:manager.apply('controller_stop',manager.controller['owner'],'')
    for f in (OUT/'run/state/flight_fault.json',OUT/'run/state/emergency_stop.json'):
        if f.exists():f.unlink()
    if active[0]:native.stop(active[0])
    active[0]=adapter();wait(lambda:pub.get_num_connections()>0,10);time.sleep(.7)
def prepare():
    c=send(C.PREPARE);response(c,'ready');return c
def schedule():
    c=send(C.SCHEDULE,execution=str(uuid.uuid4()),at=time.time()+1)
    response(c,'scheduled');return c
try:
    master=launch(['roscore','-p','11327'],'master')
    wait(lambda:native.ServerProxy(os.environ['ROS_MASTER_URI']).getPid('/test')[0]==1,15)
    rospy.init_node('isolated_test')
    rospy.set_param('~workspace',str(OUT));rospy.set_param('~execution_enabled',True)
    manager=manager_module.Manager()
    fake=native.FakeMavros()
    original_publish=fake.state_pub.publish
    def healthy_fcu_state(message):
        message.system_status=3
        original_publish(message)
    fake.state_pub.publish=healthy_fcu_state
    dormant=launch(['python3','-c','import time;time.sleep(900)'],'fake-localization-owner')
    manager.stage=dict(name='localization',owner='fixture',process=dormant)
    odom=rospy.Publisher('/ducted/localization/body_odom',Odometry,queue_size=2)
    health=rospy.Publisher('/ducted/localization/map_ready',Bool,queue_size=2)
    broadcaster=tf2_ros.TransformBroadcaster()
    publishing=[True]
    def localization(event):
        if not publishing[0]:return
        o=Odometry();o.header.stamp=rospy.Time.now();o.header.frame_id='odom';o.child_frame_id='base_link'
        with fake.lock:
            o.pose.pose.position.x,o.pose.pose.position.y,o.pose.pose.position.z=fake.position
            import math
            o.pose.pose.orientation.z=math.sin(fake.yaw/2);o.pose.pose.orientation.w=math.cos(fake.yaw/2)
        odom.publish(o);health.publish(True)
        t=TransformStamped();t.header.stamp=o.header.stamp;t.header.frame_id='map';t.child_frame_id='odom';t.transform.rotation.w=1
        broadcaster.sendTransform(t)
    timer=rospy.Timer(rospy.Duration(.02),localization)
    state=OUT/'run/state';state.mkdir(parents=True,exist_ok=True)
    (state/'relocalization.json').write_text(json.dumps(dict(status='localized',map_id='fixture')))
    cfg=yaml.safe_load((ROOT/'src/EPGeneral_device_config/config/task_control.yaml').read_text())
    cfg['storage']['directory']=str(OUT/'mission');cfg['adapter']['workspace']=str(OUT)
    cfg['adapter']['active_map_state_file']=str(state/'relocalization.json')
    cfg['adapter']['emergency_stop_state_file']=str(state/'emergency_stop.json')
    (OUT/'task.yaml').write_text(yaml.safe_dump(cfg))
    store=TrajectoryStore(str(OUT/'mission'))
    payload=dict(schema_version=2,task_id='test',subtask_id='part',device_id='UAV_001',revision=1,task_name='isolated',
                 map_id='fixture',frame_id='map',task_type='air',cruise_speed_mps=.3,start_delay_seconds=0,
                 waypoints=[dict(index=0,waypoint_id='a',x=.1,y=0,z=1),dict(index=1,waypoint_id='b',x=.2,y=0,z=1)])
    store.commit(payload,123)
    pub=rospy.Publisher(cfg['ros']['command_topic'],C,queue_size=10)
    sub=rospy.Subscriber(cfg['ros']['feedback_topic'],F,receive,queue_size=100)
    active=[None];reset()
    if '--udp-only' not in sys.argv:
        c=prepare();assert not fake.arm_calls
        pub.publish(c);response(c,'ready');results['prepare_no_arm_duplicate']=True
        run=schedule();response(run,'completed',50)
        assert fake.armed and fake.mode=='OFFBOARD'
        calls=len(fake.arm_calls);pub.publish(run);time.sleep(.5);assert len(fake.arm_calls)==calls
        results['schedule_takeoff_hover_waypoints_completed_duplicate']=True
        unload=send(C.UNLOAD);response(unload,'failed');assert manager.controller
        results['airborne_unload_retains_controller']=True
        e=send(C.EMERGENCY_STOP);response(e,'emergency_stopped',25)
        assert not fake.armed and fake.landed==1 and (state/'emergency_stop.json').exists()
        results['emergency_landing_confirmed_persistent_latch']=True
        blocked=send(C.SCHEDULE,execution='blocked',at=time.time()+2);response(blocked,'failed')
        results['latch_rejects_restart']=True
        reset();prepare();run=schedule();response(run,'running',30)
        wait(lambda:fake.armed and fake.mode=='OFFBOARD' and fake.position[2]>.9,25)
        c=send(C.CANCEL,execution=run.execution_id);response(c,'stopped',8)
        assert fake.armed and fake.mode=='OFFBOARD'
        results['cancel_hover']=True
        e=send(C.EMERGENCY_STOP);response(e,'emergency_stopped',25)
        reset();prepare();run=schedule();response(run,'running',30)
        publishing[0]=False;response(run,'failed',8);assert (state/'flight_fault.json').exists()
        publishing[0]=True;time.sleep(1);assert feedback[run.request_id].state=='failed'
        results['stale_localization_no_resume']=True
        e=send(C.EMERGENCY_STOP);response(e,'emergency_stopped',25)
        reset();prepare();fake.mode_accept=False;run=schedule();response(run,'failed',50)
        assert not fake.armed
        results['service_rejection_no_success']=True
        reset();prepare();run=schedule();response(run,'running',30)
        native.stop(active[0]);active[0]=None
        wait(lambda:(state/'flight_fault.json').exists(),6)
        assert rospy.get_param('/ctrl_cmd/state')==0
        active[0]=adapter();time.sleep(2)
        assert rospy.get_param('/ctrl_cmd/state')==0
        results['adapter_restart_no_resume_lease_hold']=True
        # Fixture resets only the simulated aircraft, never a real FCU.
        fake.reset();time.sleep(.4)
    reset()
    from epgeneral_task_control.config import load_config
    from epgeneral_task_control.node import RosTaskControlNode
    import msgpack,zlib,threading
    config=load_config(str(OUT/'task.yaml'),str(ROOT/'src/EPGeneral_device_config/config/device.yaml'))
    def free_port():
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            sock.bind(('127.0.0.1',0));return sock.getsockname()[1]
    config.update(bind_host='127.0.0.1',ground_station_ip='127.0.0.1',control_port=free_port(),status_port=free_port())
    receiver=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);receiver.bind(('127.0.0.1',config['status_port']));receiver.settimeout(.2)
    packets=[];receiving=[True]
    def collect():
        while receiving[0]:
            try:packets.append(msgpack.unpackb(receiver.recv(65536),raw=False))
            except socket.timeout:pass
    collector=threading.Thread(target=collect,daemon=True);collector.start()
    coordinator=RosTaskControlNode(rospy,config,C,F,store=store);coordinator.start();time.sleep(.5)
    def wire(kind,request,payload,execution=''):
        packet=dict(schema_version=2,protocol_id='ccs-task-control-v2',task_id='test',subtask_id='part',
                    device_id='UAV_001',execution_id=execution,message_type=kind,request_id=request,
                    sequence=len(packets)+1,sent_at_ns=time.time_ns(),payload=payload)
        receiver.sendto(msgpack.packb(packet,use_bin_type=True),('127.0.0.1',config['control_port']))
    store.delete('test','part')
    raw=json.dumps(payload).encode();compressed=zlib.compress(raw);crc=zlib.crc32(compressed)&0xffffffff
    chunks=[compressed[:len(compressed)//2],compressed[len(compressed)//2:]]
    wire('task_prepare','wire-prepare',dict(revision=1,chunk_count=2,compressed_bytes=len(compressed),raw_bytes=len(raw),crc32=crc,compression='zlib',encoding='json-utf8'))
    time.sleep(.1)
    for index in (1,0):wire('task_chunk','wire-prepare',dict(revision=1,chunk_count=2,chunk_index=index,crc32=crc,data=chunks[index]))
    time.sleep(.1);wire('task_commit','wire-commit',dict(revision=1,chunk_count=2,crc32=crc))
    wait(lambda:coordinator.preparation and coordinator.preparation.state=='ready',25,'UDP task ready')
    scheduled=time.strftime('%Y-%m-%dT%H:%M:%S',time.gmtime(time.time()+4))+'+00:00'
    wire('execute_task','wire-execute',dict(revision=1,scheduled_at=scheduled),'wire-flight')
    wait(lambda:any(p['message_type']=='task_status' and p['payload'].get('state')=='completed' for p in packets),55,'UDP completion')
    result_packets=OUT/'udp_packets.json';result_packets.write_text(json.dumps(packets,indent=2,default=str))
    results['real_udp_chunks_prepare_schedule_complete']=True
    coordinator.close();receiving[0]=False;collector.join(1);receiver.close()
    fake.reset();time.sleep(.3)
    results['stage_mutex']=not manager.command(StageCommandRequest('mapping_start','other','')).success
    results['passed']=True
except Exception:
    results['passed']=False;results['error']=traceback.format_exc();print(results['error'],flush=True)
finally:
    if 'timer' in globals():timer.shutdown()
    if fake:fake.timer.shutdown()
    if fake:fake.reset();fake.publish(None);time.sleep(.3)
    if manager:
        try:manager.close()
        except Exception:pass
    for p in reversed(children):
        try:native.stop(p)
        except Exception:pass
    (OUT/'result.json').write_text(json.dumps(results,indent=2))
    if 'packets' in globals():(OUT/'udp_packets.json').write_text(json.dumps(packets,indent=2,default=str))
    (OUT/'feedback.json').write_text(json.dumps(history,indent=2))
    print(json.dumps(dict(output=str(OUT),results=results)),flush=True)
sys.exit(0 if results.get('passed') else 1)
