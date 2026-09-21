#!/usr/bin/env python3
"""Mapping command hook and managed relocalization session."""
import argparse,json,sys,time
from pathlib import Path
import rospy
from epgeneral_uav_integration.srv import StageCommand

def main():
    p=argparse.ArgumentParser()
    p.add_argument('action',nargs='?');p.add_argument('owner',nargs='?',default='preflight')
    p.add_argument('argument',nargs='?',default='')
    args,_=p.parse_known_args()
    if args.action=='offline_check':
        import rospkg
        for name in ('ducted_bringup','ducted_offboard'):
            rospkg.RosPack().get_path(name)
        print('native packages available');return
    rospy.init_node('uav_stage_client',anonymous=True)
    action=args.action or rospy.get_param('~action')
    owner=args.owner if args.action else rospy.get_param('~owner')
    argument=args.argument if args.action else rospy.get_param('~map_file','')
    if action=='offline_check':
        for name in ('ducted_bringup','ducted_offboard'):
            import rospkg
            rospkg.RosPack().get_path(name)
        print('native packages available');return
    rospy.wait_for_service('/uav/UAV_001/stage',timeout=10)
    call=rospy.ServiceProxy('/uav/UAV_001/stage',StageCommand)
    result=call(action,owner,argument)
    if not result.success:raise RuntimeError(result.message)
    print(result.message,flush=True)
    if action=='localization_start':
        def stop():
            try:
                result=call('localization_stop',owner,'')
                if not result.success:rospy.logerr(result.message)
            except Exception as e:rospy.logerr(str(e))
        rospy.on_shutdown(stop);rospy.spin()

if __name__=='__main__':
    try:main()
    except Exception as e:print(str(e),file=sys.stderr);sys.exit(1)
