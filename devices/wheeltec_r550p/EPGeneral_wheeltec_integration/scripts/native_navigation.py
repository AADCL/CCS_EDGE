#!/usr/bin/env python3
"""Own native terrain navigation only while the matching localization is alive."""
import fcntl
import json
import os
import subprocess
import time
from pathlib import Path
import rospy
from epgeneral_wheeltec_integration.native_maps import ensure_native_map, stop_process, contained
from epgeneral_wheeltec_integration.readiness import Readiness


def main():
    rospy.init_node('ccs_wheeltec_navigation')
    workspace = Path(os.environ.get('CCS_EDGE_WORKSPACE', '/home/nrc19/ccs_edge_ws')).resolve()
    map_id = rospy.get_param('~map_name')
    map_dir = contained(rospy.get_param('~map_dir'), workspace)
    state_path = workspace / 'run/state/relocalization.json'
    ready_path = workspace / 'run/state/native_navigation.json'
    lock_file = workspace / 'run/algorithm.lock'
    child = None

    def localized():
        try:
            state = json.loads(state_path.read_text())
            if state.get('status') != 'localized' or state.get('map_id') != map_id:
                return False
            with lock_file.open('r+') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    owner = json.load(lock)
                    return owner.get("kind") == "localization" and owner.get("map_id") == map_id
                return False
        except (OSError, ValueError):
            return False

    def record(ready, reason):
        ready_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = ready_path.with_suffix('.tmp')
        tmp.write_text(json.dumps({'map_id': map_id, 'ready': ready, 'reason': reason,
                                   'monotonic': time.monotonic(), 'pid': os.getpid()}))
        os.replace(tmp, ready_path)

    try:
        if not localized():
            raise RuntimeError('matching live localization is required')
        record(False, 'preparing native terrain products')
        ensure_native_map(map_dir, workspace, cancelled=lambda: rospy.is_shutdown() or not localized())
        if rospy.is_shutdown() or not localized():
            return
        child = subprocess.Popen(['roslaunch', 'epgeneral_wheeltec_integration', 'native_navigation_components.launch',
            'map_name:=' + map_id, 'map_dir:=' + str(map_dir), 'odom_topic:=' + rospy.get_param('~odom_topic', '/odom'),
            'cmd_vel_topic:=' + rospy.get_param('~cmd_vel_topic', '/wheeltec_driver/cmd_vel')], start_new_session=True)
        readiness = Readiness('navigation', cmd_vel_topic=rospy.get_param('~cmd_vel_topic', '/wheeltec_driver/cmd_vel'))
        initial_deadline = time.monotonic() + 45
        last_ready = None
        while not rospy.is_shutdown():
            if child.poll() is not None:
                raise RuntimeError('native navigation process exited')
            if not localized():
                raise RuntimeError('localization session lost or map changed')
            ready, reason = readiness.check()
            record(ready, reason)
            if ready:
                last_ready = time.monotonic()
            elif (last_ready is not None and time.monotonic() - last_ready > 3) or (last_ready is None and time.monotonic() > initial_deadline):
                raise RuntimeError(reason)
            time.sleep(0.5)
    finally:
        record(False, 'navigation stopped')
        if child is not None:
            stop_process(child)


if __name__ == '__main__':
    main()
