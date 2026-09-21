#!/usr/bin/env python3
"""Own one ROS master/launch; refuse shutdown while an owned controller is airborne."""
import argparse,fcntl,json,os,signal,socket,subprocess,sys,time
from pathlib import Path
from preflight import check
from session_log import SessionLog
LOG=SessionLog()
ROOT=Path('/home/nrc/ccs_edge_ws')
PROFILE=Path(__file__).resolve().parents[1]
def port_free(port,kind):
    with socket.socket(socket.AF_INET,kind) as s:
        s.bind(('0.0.0.0',port))
def main():
    p=argparse.ArgumentParser()
    mode=p.add_mutually_exclusive_group()
    mode.add_argument('--check','--preflight',action='store_true');mode.add_argument('--static',action='store_true')
    mode.add_argument('--mapping',action='store_true');mode.add_argument('--flight',action='store_true')
    mode.add_argument('--stop',action='store_true')
    a=p.parse_args()
    if a.check:
        check(ROOT)
        LOG.report('OK','UAV_001 configuration and dependencies passed; no nodes or runtime logs created.')
        return
    record=ROOT/'run/supervisor.json'
    if a.stop:
        if not record.exists():
            LOG.report('OK','UAV_001 supervisor is already stopped.');return
        data=json.loads(record.read_text())
        pid=data['pid']
        try:command=Path('/proc/%s/cmdline'%pid).read_text()
        except FileNotFoundError:
            LOG.report('OK','UAV_001 supervisor is already stopped (stale PID record).');return
        if 'supervisor.py' not in command:raise RuntimeError('owner PID no longer matches; no signal sent')
        os.kill(pid,signal.SIGTERM)
        LOG.report('INFO','Stop requested; wait for the supervisor shutdown result.')
        return
    check(ROOT)
    LOG.report('OK','UAV_001 configuration and dependencies passed.')
    (ROOT/'run').mkdir(parents=True,exist_ok=True)
    with (ROOT/'run/supervisor.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('UAV_001 workflow is already running') from None
        for port,kind in ((11311,socket.SOCK_STREAM),(14562,socket.SOCK_STREAM),(9000,socket.SOCK_DGRAM),(14561,socket.SOCK_DGRAM),
                          (14563,socket.SOCK_DGRAM),(14565,socket.SOCK_DGRAM)):
            try:port_free(port,kind)
            except OSError as error:raise RuntimeError('Required port %s is unavailable: %s'%(port,error)) from error
        logs=ROOT/'logs'/('session-'+time.strftime('%Y%m%d-%H%M%S')+'-'+str(os.getpid()))
        logs.mkdir(parents=True);os.environ['ROS_LOG_DIR']=str(logs/'ros')
        LOG.attach(logs)
        latest=logs.parent/'latest'
        if latest.is_symlink() or not latest.exists():
            temporary=logs.parent/('.latest-'+str(os.getpid()))
            temporary.symlink_to(logs.name, target_is_directory=True);temporary.replace(latest)
        else:LOG.report('WARN','logs/latest is a real directory/file; leaving it unchanged.')
        runtime_mode='flight' if a.flight else ('static' if a.static else 'mapping')
        mapping_enabled=not a.static
        execution_enabled=a.flight
        LOG.report('INFO','UAV_001 mode=%s; logs: %s'%(runtime_mode,logs))
        LOG.record('Configuration and dependencies passed; supervisor pid=%s'%os.getpid())
        children=[];files=[];stopping=[False];stage=[None,0.];failure_reason=None;ready=False
        def spawn(args,name):
            f=(logs/(name+'.log')).open('w');files.append(f)
            child=subprocess.Popen(args,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
            children.append(child);return child
        def request(signum,frame):stopping[0]=True
        signal.signal(signal.SIGTERM,request);signal.signal(signal.SIGINT,request)
        try:
            master=spawn(['roscore','-p','11311'],'roscore')
            import xmlrpc.client
            until=time.monotonic()+20
            while True:
                try:
                    with socket.create_connection(('127.0.0.1',11311),timeout=.2):break
                except OSError:
                    if master.poll() is not None or time.monotonic()>until:raise RuntimeError('ROS master failed')
                    time.sleep(.1)
            LOG.report('OK','ROS master is ready.')
            import rospy
            from std_msgs.msg import String
            rospy.init_node('uav_supervisor',disable_signals=True)
            def sample(msg):
                try:stage[:]=[json.loads(msg.data),time.monotonic()]
                except ValueError:pass
            rospy.Subscriber('/uav/UAV_001/stage_status',String,sample)
            launch=spawn(['roslaunch',str(PROFILE/'launch/uav_001_bringup.launch'),
                          'mapping_enabled:='+str(mapping_enabled).lower(),
                          'execution_enabled:='+str(execution_enabled).lower(),
                          'log_dir:='+str(logs)],'bringup')
            record.write_text(json.dumps(dict(pid=os.getpid(),master_pid=master.pid,launch_pid=launch.pid,
                                             mode=runtime_mode,mapping_enabled=mapping_enabled,
                                             execution_enabled=execution_enabled,logs=str(logs))))
            LOG.report('INFO','UAV_001 bringup launched; waiting for required ROS nodes.')
            started=time.monotonic();checked=0.;missing=0
            required={'/mavros','/livox_lidar_publisher2','/epgeneral_mqtav','/epgeneral_udp_telemetry',
                      '/epgeneral_map_stream','/epgeneral_relocalization','/epgeneral_task_control',
                      '/epgeneral_video_srt','/uav_stage_manager','/uav_task_adapter'}
            while True:
                exited=[c for c in children if c.poll() is not None]
                failure=bool(exited)
                if failure:
                    failure_reason='Managed process exited: '+', '.join('pid=%s exit=%s'%(c.pid,c.returncode) for c in exited)
                    LOG.repeated('failure','ERROR',failure_reason+'; inspect roscore.log and bringup.log.')
                now=time.monotonic()
                if not failure and now-started>25 and now-checked>2:
                    checked=now
                    try:
                        socket.setdefaulttimeout(2)
                        state_reply=xmlrpc.client.ServerProxy(os.environ['ROS_MASTER_URI']).getSystemState('/uav_supervisor')
                        if state_reply[0]!=1:raise RuntimeError('master state failed')
                        nodes={n for group in state_reply[2] for _,names in group for n in names}
                        absent=required-nodes
                        if absent:
                            missing+=1
                            failure_reason='Missing runtime nodes: '+', '.join(sorted(absent))
                            LOG.record('attempt=%s/3 %s'%(missing,failure_reason),'runtime_monitor.log')
                        else:
                            if missing:LOG.report('OK','ROS node monitoring recovered.')
                            missing=0
                            if not ready:
                                LOG.report('OK','UAV_001 required ROS nodes are registered; hardware readiness is checked separately.')
                                ready=True
                    except Exception as error:
                        missing+=1;failure_reason='ROS node check failed: '+str(error)
                        LOG.record('attempt=%s/3 %s'%(missing,failure_reason),'runtime_monitor.log')
                    failure=missing>=3
                    if failure:LOG.repeated('failure','ERROR',failure_reason+' after repeated checks; inspect runtime_monitor.log.')
                if stopping[0] or failure:
                    state,at=stage
                    # Flight mode also blocks uncertain shutdown: user must restore landed telemetry.
                    safe=(not a.flight) or (state is not None and time.monotonic()-at<2 and
                                           (not state['controller'] or state['ground_safe']))
                    if safe:
                        if failure:raise RuntimeError(failure_reason)
                        break
                    if stopping[0]:
                        LOG.repeated('shutdown_guard','WARN','Shutdown refused: airborne/unknown controller; retaining flight and localization.')
                        stopping[0]=False
                time.sleep(.2)
        finally:
            LOG.record('Shutdown requested; checking controller safety.')
            # Exceptions must also retain a potentially airborne native controller.
            marker=ROOT/'run/controller_process.json'
            while a.flight and marker.exists():
                state,at=stage
                if state is not None and time.monotonic()-at<2 and state['ground_safe']:break
                try:
                    pid=json.loads(marker.read_text())['pid']
                    command=Path('/proc/%s/cmdline'%pid).read_text()
                    if 'ducted_offboard' not in command:break
                except (FileNotFoundError,ProcessLookupError):break
                LOG.repeated('retain','WARN','Retaining airborne/unknown controller after supervisor failure.')
                time.sleep(2)
            LOG.report('INFO','Stopping owned UAV_001 processes.')
            for child in reversed(children):
                if child.poll() is None:
                    os.killpg(child.pid,signal.SIGINT)
                    try:child.wait(timeout=25)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid,signal.SIGTERM);child.wait(timeout=10)
            for f in files:f.close()
            if record.exists():record.unlink()
            LOG.report('OK','Owned UAV_001 processes stopped.')

def run():
    try:main();return 0
    except Exception as error:
        LOG.exception()
        detail='; details: '+str(LOG.directory/'runtime_monitor.log') if LOG.directory else ''
        LOG.report('ERROR',str(error)+detail)
        return 1

if __name__=='__main__':sys.exit(run())
