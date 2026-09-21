#!/usr/bin/env python3
"""CCS task bridge to the production direct C++ controller; no MAVROS setpoint publisher."""
import hashlib,json,math,queue,threading,time
from pathlib import Path
import numpy as np
import yaml
import rospy,tf2_ros
from std_msgs.msg import Bool,String
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry
from mavros_msgs.msg import State,ExtendedState
from mavros_msgs.srv import SetMode
from ducted_offboard.msg import OffboardStatus
from epgeneral_task_control.msg import TaskExecutionCommand as Command,TaskExecutionFeedback as Feedback
from epgeneral_task_control.config import load_config
from epgeneral_task_control.storage import TrajectoryStore
from epgeneral_uav_integration.srv import StageCommand
from epgeneral_uav_integration.core import atomic_json,mission,transform_matrix,FlightWorkflow,validate_pose_agreement

FIELDS=('request_id','task_id','subtask_id','device_id','execution_id','revision','map_id','frame_id')
def values(m): return {k:getattr(m,k) for k in FIELDS}
def key(m): return (m.task_id,m.subtask_id,m.device_id,m.revision,m.map_id,m.frame_id)

class Adapter:
    def __init__(self):
        self.cfg=load_config(rospy.get_param('~config_file'),rospy.get_param('~device_config_file'))
        self.execution_enabled=rospy.get_param('~execution_enabled',False)
        self.a=self.cfg['adapter'];self.root=Path(self.a['workspace'])
        self.state_file=Path(self.a['active_map_state_file'])
        self.latch=Path(self.a['emergency_stop_state_file'])
        self.fault=self.root/'run/state/flight_fault.json'
        self.store=TrajectoryStore(self.cfg['storage_directory'])
        self.cache={};self.requests={};self.inputs={};self.events=queue.Queue(maxsize=100)
        self.guard=threading.RLock();self.rpc_lock=threading.Lock()
        self.preparing=None;self.prepared=None;self.prep_thread=None;self.cancel_generation=0
        self.owner='';self.execution=None;self.workflow=None;self.emergency=None;self.stop_pending=None
        self.buffer=tf2_ros.Buffer();self.listener=tf2_ros.TransformListener(self.buffer)
        self.pub=rospy.Publisher(self.cfg['feedback_topic'],Feedback,queue_size=20)
        self.lease=rospy.Publisher('/uav/UAV_001/control_lease',String,queue_size=1)
        self.subs=[rospy.Subscriber(self.cfg['command_topic'],Command,self.receive,queue_size=20)]
        for topic,cls,name in [('/mavros/state',State,'fcu'),('/mavros/extended_state',ExtendedState,'extended'),
                              ('/mavros/local_position/pose',PoseStamped,'pose'),
                              ('/ducted/localization/body_odom',Odometry,'odom'),
                              ('/ducted/localization/map_ready',Bool,'health'),('/ctrl_cmd/status',OffboardStatus,'status')]:
            self.subs.append(rospy.Subscriber(topic,cls,lambda m,n=name:self.sample(n,m),queue_size=10))
        self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start()
    def sample(self,name,m):
        now=time.monotonic()
        if hasattr(m,'header'):
            age=rospy.Time.now().to_sec()-m.header.stamp.to_sec()
            if not -.05<=age<=2:return
        with self.guard:self.inputs[name]=(now,m)
    def fresh(self,name,age):
        item=self.inputs.get(name)
        if not item or time.monotonic()-item[0]>age:raise RuntimeError(name+' unavailable or stale')
        m=item[1]
        if hasattr(m,'header') and not -.05<=rospy.Time.now().to_sec()-m.header.stamp.to_sec()<=age:
            raise RuntimeError(name+' source timestamp stale')
        return m
    def ground(self):
        try:return self.fresh('fcu',2).connected and not self.fresh('fcu',2).armed and self.fresh('extended',2).landed_state==1
        except Exception:return False
    def healthy(self,map_id):
        fcu=self.fresh('fcu',2)
        if not fcu.connected or fcu.system_status not in (3,4):
            raise RuntimeError('FCU must report STANDBY/ACTIVE before task execution')
        if not self.fresh('health',.5).data:raise RuntimeError('localization unavailable')
        state=json.loads(self.state_file.read_text())
        if state.get('status')!='localized' or state.get('map_id')!=map_id:raise RuntimeError('active map mismatch')
        p=self.fresh('pose',.5).pose;o=self.fresh('odom',.5).pose.pose
        validate_pose_agreement(
            [getattr(p.position,k) for k in ('x','y','z')],
            [getattr(p.orientation,k) for k in ('x','y','z','w')],
            [getattr(o.position,k) for k in ('x','y','z')],
            [getattr(o.orientation,k) for k in ('x','y','z','w')])
        t=self.buffer.lookup_transform('odom','map',rospy.Time(0),rospy.Duration(.1))
        if not -.05<=rospy.Time.now().to_sec()-t.header.stamp.to_sec()<=.5:raise RuntimeError('map TF stale')
        return t
    def stage(self,action,argument='',owner=None):
        with self.rpc_lock:
            rospy.wait_for_service('/uav/UAV_001/stage',timeout=5)
            result=rospy.ServiceProxy('/uav/UAV_001/stage',StageCommand)(action,owner or self.owner,argument)
            if not result.success:raise RuntimeError(result.message)
            return result
    def feedback(self,cmd,state,error='',message=''):
        f=Feedback()
        for k in FIELDS:
            if hasattr(f,k):setattr(f,k,getattr(cmd,k))
        f.state=state;f.error_code=error;f.message=message
        try:
            s=self.fresh('status',1);f.waypoint_count=max(0,s.waypoint_count)
            f.waypoint_index=min(max(-1,s.current_waypoint),f.waypoint_count-1)
            f.progress=1. if state=='completed' else float(s.current_waypoint)/max(1,s.waypoint_count)
            f.position=self.fresh('pose',.5).pose.position
        except Exception:f.waypoint_index=-1
        self.pub.publish(f)
        self.cache[(cmd.action,cmd.request_id)]=f
        if len(self.cache)>256:self.cache.pop(next(iter(self.cache)))
    def receive(self,cmd):
        if cmd.device_id!=self.cfg['device_id']:return
        try:self.events.put_nowait(cmd)
        except queue.Full:rospy.logerr('UAV command queue full')
    def prepare(self,cmd,generation):
        try:
            if self.latch.exists() or self.fault.exists():raise RuntimeError('EMERGENCY_STOP_LATCHED')
            if not self.ground():raise RuntimeError('prepare requires landed/disarmed aircraft')
            t=self.healthy(cmd.map_id).transform
            p=self.fresh('pose',.5).pose.position
            payload=self.store.load_payload(cmd.task_id,cmd.subtask_id)
            if payload is None:raise RuntimeError('trajectory missing')
            data,speed,delay=mission(payload,values(cmd),transform_matrix(
                [t.translation.x,t.translation.y,t.translation.z],[t.rotation.x,t.rotation.y,t.rotation.z,t.rotation.w]),[p.x,p.y,p.z])
            owner=hashlib.sha256(('%s/%s/%s'%key(cmd)[:3] + '/'+str(cmd.revision)).encode()).hexdigest()[:24]
            if self.owner and self.owner!=owner:self.stage('controller_stop')
            self.owner=owner
            directory=self.root/'run/missions'/owner;directory.mkdir(parents=True,exist_ok=True)
            path=directory/'mission.yaml';path.write_text(yaml.safe_dump(data),encoding='utf-8')
            if generation!=self.cancel_generation:return
            self.stage('controller_start',json.dumps(dict(mission_file=str(path),speed=speed)))
            end=time.monotonic()+20
            while time.monotonic()<end and not rospy.is_shutdown():
                if generation!=self.cancel_generation:
                    self.stage('controller_stop');return
                try:
                    s=self.fresh('status',.5)
                    if s.mission_loaded and s.waypoint_count==len(data['waypoints']) and s.task_phase=='IDLE_GROUND':break
                except Exception:pass
                time.sleep(.05)
            else:raise RuntimeError('controller load acknowledgement timed out')
            with self.guard:
                if generation==self.cancel_generation:
                    self.prepared=dict(command=cmd,delay=delay,count=len(data['waypoints']))
                    self.feedback(cmd,'ready')
        except Exception as e:
            code='EMERGENCY_STOP_LATCHED' if 'LATCHED' in str(e) else 'UAV_PREPARATION_FAILED'
            self.feedback(cmd,'failed',code,str(e))
        finally:self.preparing=None
    def handle(self,c):
        fingerprint=tuple(getattr(c,k) for k in FIELDS)+(c.scheduled_at.to_sec(),)
        request_key=(c.action,c.request_id)
        if not c.request_id:raise RuntimeError('request_id required')
        if request_key in self.requests and self.requests[request_key]!=fingerprint:
            raise RuntimeError('request identity changed')
        self.requests[request_key]=fingerprint
        if not self.execution_enabled and c.action in (Command.PREPARE,Command.SCHEDULE):
            raise RuntimeError('static observation mode: execution disabled')
        if c.action in (Command.STOP,Command.CANCEL,Command.UNLOAD) and self.prepared and key(c)!=key(self.prepared['command']):
            raise RuntimeError('mission identity mismatch')
        cached=self.cache.get((c.action,c.request_id))
        if cached and cached.state not in ('preparing','scheduled','running','emergency_stopping','stopping'):
            self.pub.publish(cached);return
        if c.action==Command.PREPARE:
            if self.preparing or self.emergency or (self.workflow and self.workflow.phase not in ('completed','stopped','failed')):
                self.feedback(c,'failed','BUSY','active UAV operation');return
            if self.prepared and key(c)==key(self.prepared['command']):
                self.healthy(c.map_id);self.feedback(c,'ready');return
            self.cancel_generation+=1;self.preparing=c;self.feedback(c,'preparing')
            self.prep_thread=threading.Thread(target=self.prepare,args=(c,self.cancel_generation),daemon=True);self.prep_thread.start()
        elif c.action==Command.SCHEDULE:
            if not c.execution_id:raise RuntimeError('execution_id required')
            if self.latch.exists() or self.fault.exists():raise RuntimeError('EMERGENCY_STOP_LATCHED')
            if self.execution and self.workflow and self.workflow.phase not in ('completed','stopped','failed'):
                if c.execution_id==self.execution.execution_id:
                    self.feedback(c,'scheduled' if self.workflow.phase=='scheduled' else 'running');return
                raise RuntimeError('another execution active')
            if not self.prepared or key(c)!=key(self.prepared['command']):raise RuntimeError('mission not prepared')
            self.healthy(c.map_id)
            if not self.ground():raise RuntimeError('new automatic takeoff requires ground')
            at=c.scheduled_at.to_sec()+self.prepared['delay']
            if c.scheduled_at.to_sec()<=time.time():raise RuntimeError('schedule expired')
            self.execution=c;self.workflow=FlightWorkflow(self.prepared['count'],at)
            self.feedback(c,'scheduled')
        elif c.action in (Command.STOP,Command.CANCEL):
            if self.execution and c.execution_id and c.execution_id!=self.execution.execution_id:raise RuntimeError('execution mismatch')
            self.cancel_generation+=1;rospy.set_param('/ctrl_cmd/state',0)
            self.stop_pending=(c,time.monotonic())
            if self.workflow:self.workflow.phase='stopped'
        elif c.action==Command.UNLOAD:
            self.cancel_generation+=1
            if self.prep_thread and self.prep_thread.is_alive():raise RuntimeError('preparation cleanup pending')
            if not self.ground():raise RuntimeError('airborne: retain controller and localization')
            if self.owner:self.stage('controller_stop')
            self.owner='';self.prepared=None;self.execution=None;self.workflow=None
            self.feedback(c,'unloaded')
        elif c.action==Command.EMERGENCY_STOP:
            if self.emergency and self.emergency[0].request_id==c.request_id:return
            self.cancel_generation+=1
            atomic_json(str(self.latch),dict(reason='CCS emergency landing',time=time.time(),request_id=c.request_id))
            if self.ground():
                self.feedback(c,'emergency_stopped',message='landed and disarmed confirmed');return
            if not self.fresh('fcu',2).armed:raise RuntimeError('landing state unknown')
            if not self.execution_enabled:raise RuntimeError('static mode: flight services disabled')
            # Native controller owns flight output. If no controller exists, only AUTO.LAND is requested.
            if self.owner:rospy.set_param('/ctrl_cmd/state',3)
            else:
                rospy.wait_for_service('/mavros/set_mode',timeout=3)
                if not rospy.ServiceProxy('/mavros/set_mode',SetMode)(0,'AUTO.LAND').mode_sent:raise RuntimeError('AUTO.LAND rejected')
            self.emergency=(c,time.monotonic())
    def tick(self):
        if self.owner:self.lease.publish(self.owner)
        if self.preparing:self.feedback(self.preparing,'preparing')
        if self.emergency:
            c,started=self.emergency
            if self.ground():
                self.feedback(c,'emergency_stopped',message='AUTO.LAND completed; landed/disarmed confirmed')
                self.emergency=None
                if self.workflow:self.workflow.phase='emergency_stopped'
            elif time.monotonic()-started>125:
                self.feedback(c,'failed','UAV_LANDING_UNCONFIRMED','landing timeout; persistent latch retained');self.emergency=None
            elif self.execution:self.feedback(self.execution,'running',message='emergency landing in progress')
            return
        if self.stop_pending:
            c,started=self.stop_pending
            try:
                s=self.fresh('status',.5)
                stopped=self.ground() or (s.command==0 and s.task_phase in ('HOLDING','PAUSED') and s.fcu_mode=='OFFBOARD')
            except Exception:stopped=self.ground()
            if stopped:self.feedback(c,'stopped',message='hold/ground confirmed');self.stop_pending=None
            elif time.monotonic()-started>5:
                self.feedback(c,'failed','UAV_HOLD_UNCONFIRMED','hold not confirmed');self.stop_pending=None
            return
        if self.workflow and self.execution:
            healthy=True;reason=''
            try:
                self.healthy(self.execution.map_id)
                s=self.fresh('status',.5);status={k:getattr(s,k) for k in s.__slots__ if k!='header'}
            except Exception as e:healthy=False;reason=str(e);status={}
            for command in self.workflow.tick(time.time(),status,healthy):rospy.set_param('/ctrl_cmd/state',command)
            phase=self.workflow.phase
            if phase=='failed' and not self.fault.exists():
                atomic_json(str(self.fault),dict(reason=reason or 'native flight rejected',time=time.time()))
            self.feedback(self.execution,'running' if phase=='taking_off' else phase,
                          'UAV_EXECUTION_FAILED' if phase=='failed' else '',reason)
    def loop(self):
        while not rospy.is_shutdown():
            try:
                while True:
                    try:c=self.events.get_nowait()
                    except queue.Empty:break
                    try:self.handle(c)
                    except Exception as e:self.feedback(c,'failed','UAV_COMMAND_REJECTED',str(e))
                self.tick()
            except Exception as e:rospy.logerr('UAV adapter tick: %s',e)
            time.sleep(.2)

if __name__=='__main__':
    rospy.init_node('uav_task_adapter')
    Adapter()
    rospy.spin()
