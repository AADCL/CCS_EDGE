"""ROS-independent UAV validation, transforms and direct-flight state machine."""
import math
import os
import json
import tempfile
import numpy as np

def atomic_json(path,value):
    os.makedirs(os.path.dirname(path),exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=os.path.dirname(path),prefix='.state-')
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(value,f,allow_nan=False);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def transform_matrix(translation,quaternion):
    q=np.asarray(quaternion,dtype=float)
    if not np.isfinite(q).all() or abs(np.linalg.norm(q)-1)>.01: raise ValueError('invalid quaternion')
    x,y,z,w=q/np.linalg.norm(q); t=np.eye(4)
    t[:3,:3]=[[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
               [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
               [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]]
    t[:3,3]=translation
    if not np.isfinite(t).all(): raise ValueError('nonfinite transform')
    return t

def mission(payload,identity,odom_from_map,current_position):
    for key in ('task_id','subtask_id','device_id','revision','map_id','frame_id'):
        if payload.get(key)!=identity[key]: raise ValueError('trajectory identity mismatch: '+key)
    if payload['frame_id']!='map' or payload.get('task_type','unspecified') not in ('unspecified','air','air_nav'):
        raise ValueError('UAV requires map-frame air task')
    speed=float(payload['cruise_speed_mps']);delay=float(payload['start_delay_seconds'])
    if not math.isfinite(speed) or not 0<speed<=.3: raise ValueError('UAV cruise speed must be (0,0.3] m/s')
    if not math.isfinite(delay) or delay<0: raise ValueError('invalid delay')
    points=payload['waypoints']
    if not 2<=len(points)<=500: raise ValueError('invalid waypoint count')
    out=[];previous=np.asarray(current_position,dtype=float)
    for i,p in enumerate(points):
        if p['index']!=i: raise ValueError('waypoint order mismatch')
        xyz=np.array([p[k] for k in ('x','y','z')],dtype=float)
        if not np.isfinite(xyz).all(): raise ValueError('nonfinite waypoint')
        xyz=(odom_from_map@np.r_[xyz,1])[:3];dx,dy=xyz[:2]-previous[:2]
        yaw=math.degrees(math.atan2(dy,dx)) if abs(dx)+abs(dy)>1e-6 else (out[-1]['yaw_deg'] if out else 0.)
        out.append(dict(x=float(xyz[0]),y=float(xyz[1]),z=float(xyz[2]),yaw_deg=yaw));previous=xyz
    return dict(frame_id='odom',waypoints=out),speed,delay

class FlightWorkflow:
    """Emit commands once; advance only from fresh native feedback."""
    def __init__(self,count,start_at):
        self.count=count;self.start_at=start_at;self.phase='scheduled'
        self.started=None;self.generation=None;self.seen_guiding=False
    def tick(self,now,s,healthy):
        if self.phase in ('completed','stopped','failed','emergency_stopped'): return []
        if not healthy: self.phase='failed';return [0]
        p=s.get('task_phase',s.get('phase'))
        if self.phase=='scheduled' and now>=self.start_at:
            if s['armed'] or s['landed_state']!=1 or p!='IDLE_GROUND':
                self.phase='failed';return [0]
            self.started=now;self.generation=s['task_generation'];self.phase='taking_off';return [1]
        if self.phase=='taking_off':
            if now-self.started>40 or p in ('ERROR','PAUSED'):
                self.phase='failed';return [0]
            if s['armed'] and p=='HOLDING' and s['fcu_mode']=='OFFBOARD' and s['task_generation']>self.generation:
                self.generation=s['task_generation'];self.phase='running';return [2]
        elif self.phase=='running':
            if s['task_generation']!=self.generation or p in ('ERROR','PAUSED') or not s['armed'] or s['fcu_mode']!='OFFBOARD':
                self.phase='failed';return [0]
            self.seen_guiding |= p=='GUIDING'
            if self.seen_guiding and p=='HOLDING' and s['waypoint_count']==self.count and s['current_waypoint']>=self.count-1 and s.get('reason')=='mission complete; waiting for state=3':
                self.phase='completed'
        return []


def validate_pose_agreement(position_a,quaternion_a,position_b,quaternion_b):
    a=np.asarray(position_a,dtype=float);b=np.asarray(position_b,dtype=float)
    qa=np.asarray(quaternion_a,dtype=float);qb=np.asarray(quaternion_b,dtype=float)
    if not all(np.isfinite(v).all() for v in (a,b,qa,qb)):
        raise ValueError('nonfinite MAVROS/native pose')
    if np.linalg.norm(a-b)>.15:raise ValueError('MAVROS/native odom position mismatch')
    if abs(np.linalg.norm(qa)-1)>.01 or abs(np.linalg.norm(qb)-1)>.01:
        raise ValueError('invalid pose quaternion')
    qa=qa/np.linalg.norm(qa);qb=qb/np.linalg.norm(qb)
    if 2*math.acos(min(1.,abs(float(np.dot(qa,qb)))))>math.radians(10):
        raise ValueError('MAVROS/native odom attitude mismatch')
