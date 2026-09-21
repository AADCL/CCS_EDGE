#!/usr/bin/env python3
"""Single owner of native mapping/localization/controller process groups."""
import json,os,signal,subprocess,threading,time
from pathlib import Path
import rospy
from std_msgs.msg import String
from mavros_msgs.msg import State,ExtendedState
from epgeneral_uav_integration.srv import StageCommand,StageCommandResponse
from epgeneral_uav_integration.core import atomic_json

class Manager:
    def __init__(self):
        self.root=Path(rospy.get_param('~workspace','/home/nrc/ccs_edge_ws'))
        self.native=Path(rospy.get_param('~native_workspace','/home/nrc/catkin_ws'))
        self.execution_enabled=rospy.get_param('~execution_enabled',False)
        # A mapping session may own native mapping/localization without granting flight control.
        self.mapping_enabled=rospy.get_param('~mapping_enabled',self.execution_enabled)
        self.lock=threading.RLock();self.stage=None;self.controller=None
        self.fcu=None;self.fcu_at=0;self.ext=None;self.ext_at=0
        self.lease=0;self.lease_fault=False;self.logs=[]
        self.flight_lock=self.root/'run/state/flight_fault.json'
        self.emergency_lock=self.root/'run/state/emergency_stop.json'
        self.root.joinpath('logs/stages').mkdir(parents=True,exist_ok=True)
        rospy.Subscriber('/mavros/state',State,self.state)
        rospy.Subscriber('/mavros/extended_state',ExtendedState,self.extended)
        rospy.Subscriber('/uav/UAV_001/control_lease',String,self.heartbeat)
        self.pub=rospy.Publisher('/uav/UAV_001/stage_status',String,queue_size=1,latch=True)
        self.service=rospy.Service('/uav/UAV_001/stage',StageCommand,self.command)
        self.timer=rospy.Timer(rospy.Duration(.2),self.watchdog)
    def state(self,m): self.fcu=m;self.fcu_at=time.monotonic()
    def extended(self,m): self.ext=m;self.ext_at=time.monotonic()
    def ground(self):
        return (self.fcu is not None and self.ext is not None and self.fcu.connected
                and not self.fcu.armed and self.ext.landed_state==1
                and time.monotonic()-self.fcu_at<2 and time.monotonic()-self.ext_at<2
                and -.05<=rospy.Time.now().to_sec()-self.fcu.header.stamp.to_sec()<2
                and -.05<=rospy.Time.now().to_sec()-self.ext.header.stamp.to_sec()<2)
    def heartbeat(self,m):
        if self.controller and m.data==self.controller['owner']:self.lease=time.monotonic()
    def spawn(self,name,owner,args):
        logfile=self.root/'logs/stages'/('%s-%s.log'%(name,time.time_ns()))
        f=logfile.open('w');self.logs.append(f)
        p=subprocess.Popen(args,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
        time.sleep(.4)
        if p.poll() is not None: raise RuntimeError('native process exited: '+str(logfile))
        record=dict(name=name,owner=owner,process=p,log=str(logfile),args=args)
        atomic_json(str(self.root/('run/'+name+'_process.json')),dict(pid=p.pid,args=args,owner=owner,log=str(logfile)))
        return record
    def stop(self,r):
        if r and r['process'].poll() is None:
            os.killpg(r['process'].pid,signal.SIGINT)
            try:r['process'].wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(r['process'].pid,signal.SIGTERM);r['process'].wait(timeout=5)
    def command(self,req):
        with self.lock:
            try:return StageCommandResponse(True,self.apply(req.action,req.owner,req.argument))
            except Exception as e:
                rospy.logerr('stage %s rejected: %s',req.action,e)
                return StageCommandResponse(False,str(e))
    def apply(self,action,owner,arg):
        if not owner or len(owner)>128:raise ValueError('owner required')
        if action=='check':
            if self.stage:raise RuntimeError('stage busy: '+self.stage['name'])
            if not self.ground():raise RuntimeError('fresh connected disarmed landed FCU required')
            return 'ready'
        if action in ('mapping_start','localization_start','mapping_save') and not self.mapping_enabled:
            raise RuntimeError('static observation mode: mapping/localization disabled')
        if action=='controller_start' and not self.execution_enabled:
            mode='mapping mode' if self.mapping_enabled else 'static observation mode'
            raise RuntimeError(mode+': flight control disabled')
        if action in ('mapping_start','localization_start'):
            name=action.split('_')[0]
            if self.stage:
                if self.stage['name']==name and self.stage['owner']==owner and self.stage['process'].poll() is None:return 'already started'
                raise RuntimeError('mapping/localization stage busy')
            if self.controller or not self.ground():raise RuntimeError('stage change requires landed/disarmed aircraft')
            if name=='mapping':
                args=['roslaunch','ducted_bringup','mapping.launch']
            else:
                p=Path(arg).resolve()
                if not p.is_file() or p.suffix!='.pcd':raise ValueError('map PCD missing')
                args=['roslaunch','ducted_bringup','relocalization.launch','map_file:='+str(p),'auto_initialize:=false']
            self.stage=self.spawn(name,owner,args)
            return name+' started'
        if action in ('mapping_stop','localization_stop'):
            name=action.split('_')[0]
            if self.controller or not self.ground():raise RuntimeError('cannot remove localization while flight state is unsafe')
            if self.stage:
                if self.stage['name']!=name or self.stage['owner']!=owner:raise ValueError('stage owner mismatch')
                self.stop(self.stage);self.stage=None
            return 'stopped'
        if action=='mapping_save':
            if not self.stage or self.stage['name']!='mapping' or self.stage['owner']!=owner:raise ValueError('mapping owner mismatch')
            if not self.ground():raise RuntimeError('map save requires stationary disarmed aircraft')
            destination=Path(arg).resolve()
            if self.root.resolve() not in destination.parents:raise ValueError('export must stay in CCS workspace')
            result=subprocess.run(['rosrun','epgeneral_uav_integration','uav_map_export.py',str(destination)],
                                  capture_output=True,text=True,timeout=300)
            rospy.loginfo('map export: %s %s',result.stdout,result.stderr)
            if result.returncode:raise RuntimeError(result.stderr[-2000:] or result.stdout[-2000:])
            return result.stdout[-2000:]
        if action=='controller_start':
            if self.flight_lock.exists() or self.emergency_lock.exists():raise RuntimeError('EMERGENCY_STOP_LATCHED')
            if not self.ground() or not self.stage or self.stage['name']!='localization':raise RuntimeError('localized ground stage required')
            if self.controller:
                if self.controller['owner']==owner and self.controller['process'].poll() is None:return 'already started'
                raise RuntimeError('controller busy')
            data=json.loads(arg);path=Path(data['mission_file']).resolve();speed=float(data['speed'])
            if self.root.resolve() not in path.parents or not path.is_file() or not 0<speed<=.3:raise ValueError('invalid mission/speed')
            rospy.set_param('/ctrl_cmd/state',0)
            args=['roslaunch','ducted_offboard','offboard_control.launch','execution_mode:=direct',
                  'target_source:=file','mission_file:='+str(path),'horizontal_speed:='+str(speed),
                  'log_root:='+str(self.root/'logs/offboard')]
            self.controller=self.spawn('controller',owner,args);self.lease=time.monotonic();self.lease_fault=False
            return 'controller started without arming'
        if action=='controller_stop':
            if self.controller:
                if owner!=self.controller['owner']:raise ValueError('controller owner mismatch')
                if not self.ground():raise RuntimeError('airborne or unknown: retain controller and localization')
                rospy.set_param('/ctrl_cmd/state',0)
                self.stop(self.controller);self.controller=None
                record=self.root/'run/controller_process.json'
                if record.exists():record.unlink()
            return 'stopped'
        if action=='reset':
            if self.controller or not self.ground():raise RuntimeError('reset requires idle, landed and disarmed')
            for p in (self.flight_lock,self.emergency_lock):
                if p.exists():p.unlink()
            self.lease_fault=False;return 'locks cleared without enabling control'
        raise ValueError('unknown stage action')
    def watchdog(self,event):
        # Independent of the adapter worker; never holds the service lock.
        c=self.controller
        if c and not self.lease_fault and (time.monotonic()-self.lease>2 or c['process'].poll() is not None):
            self.lease_fault=True
            atomic_json(str(self.flight_lock),dict(reason='controller/adapter lease lost',time=time.time(),owner=c['owner']))
            rospy.set_param('/ctrl_cmd/state',0)
            rospy.logerr('UAV flight lease lost; hold requested; no automatic resume')
        self.pub.publish(json.dumps(dict(stage=self.stage['name'] if self.stage else 'idle',
            owner=self.stage['owner'] if self.stage else '',controller=bool(c),ground_safe=self.ground(),
            flight_fault=self.lease_fault,time=time.time())))
    def close(self):
        with self.lock:
            if self.controller and not self.ground():
                rospy.logerr('retaining airborne controller and localization on shutdown')
                return
            self.stop(self.controller);self.controller=None
            self.stop(self.stage);self.stage=None
            for f in self.logs:f.close()

if __name__=='__main__':
    rospy.init_node('uav_stage_manager')
    manager=Manager()
    rospy.on_shutdown(manager.close)
    rospy.spin()
