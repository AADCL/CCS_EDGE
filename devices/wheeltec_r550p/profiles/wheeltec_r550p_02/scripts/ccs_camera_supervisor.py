#!/usr/bin/env python3
"""Optional camera/video lifecycle. Signals only subprocesses created here."""
import argparse
import collections
import os
import signal
import subprocess
import time


def main():
    import rospy
    import rosgraph
    from sensor_msgs.msg import Image
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', required=True)
    parser.add_argument('--log-dir', required=True)
    args = parser.parse_args()
    import yaml
    with open(os.path.join(args.profile, 'video.yaml')) as stream:
        if not yaml.safe_load(stream).get('enabled', False):
            return
    rospy.init_node('ccs_camera_supervisor', disable_signals=True)
    stopping = [False]
    signal.signal(signal.SIGINT, lambda *_: stopping.__setitem__(0, True))
    signal.signal(signal.SIGTERM, lambda *_: stopping.__setitem__(0, True))
    frames = collections.deque(maxlen=60)
    depth = collections.deque(maxlen=60)
    children = []
    streams = []
    def color(message):
        age = rospy.Time.now().to_sec() - message.header.stamp.to_sec()
        if message.width == 640 and message.height == 480 and -0.5 <= age <= 2.0:
            frames.append(time.monotonic())
    def depth_frame(message):
        age = rospy.Time.now().to_sec() - message.header.stamp.to_sec()
        if message.width == 640 and message.height == 480 and -0.5 <= age <= 2.0:
            depth.append(time.monotonic())
    rospy.Subscriber('/camera/color/image_raw', Image, color, queue_size=1)
    rospy.Subscriber('/camera/depth/image_raw', Image, depth_frame, queue_size=1)
    def start(name, command):
        stream = open(os.path.join(args.log_dir, name + '.log'), 'a', buffering=1)
        streams.append(stream)
        child = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        children.append(child)
        return child
    def active_nodes():
        return {node for group in rosgraph.Master(rospy.get_name()).getSystemState()
                for _, nodes in group for node in nodes}
    def fresh():
        now = time.monotonic()
        return len(frames) >= 15 and len(depth) >= 15 and now - frames[-1] < 2 and now - depth[-1] < 2
    def wait_images(seconds):
        deadline = time.monotonic() + seconds
        while not stopping[0] and time.monotonic() < deadline:
            if fresh(): return True
            time.sleep(0.1)
        return False
    try:
        publishers = dict(rosgraph.Master(rospy.get_name()).getSystemState()[0])
        external = bool(publishers.get('/camera/color/image_raw') or publishers.get('/camera/depth/image_raw'))
        if external:
            rospy.loginfo('Checking external RGBD instance; it remains externally owned')
        else:
            start('camera', ['roslaunch', 'wheeltec_yolo11', 'camera_rgbd.launch', 'camera_fps:=30'])
        if not wait_images(30):
            raise RuntimeError('RGBD images absent/stale or not 640x480; other CCS services remain active')
        fps = (len(frames)-1) / max(0.001, frames[-1]-frames[0])
        depth_fps = (len(depth)-1) / max(0.001, depth[-1]-depth[0])
        if not 20 <= fps <= 40 or not 20 <= depth_fps <= 40:
            raise RuntimeError('RGB/depth rate incompatible with 30 FPS: %.1f/%.1f' % (fps, depth_fps))
        rospy.loginfo('RGBD ready %.1f FPS, external=%s', fps, external)
        if '/epgeneral_video_srt' in active_nodes():
            raise RuntimeError('External video publisher detected; refusing duplicate SRT owner')
        # Port ownership is validated by the video node; never stop its external owner.
        video = start('video', ['roslaunch', 'epgeneral_video_srt', 'epgeneral_video_srt.launch',
            'device_config_file:=' + os.path.join(args.profile, 'device.yaml'),
            'video_config_file:=' + os.path.join(args.profile, 'video.yaml')])
        video_deadline = time.monotonic() + 15
        while '/epgeneral_video_srt' not in active_nodes() and not stopping[0]:
            if time.monotonic() > video_deadline or video.poll() is not None:
                raise RuntimeError('SRT node did not start; inspect video.log')
            time.sleep(0.25)
        while not stopping[0] and not rospy.is_shutdown():
            if '/epgeneral_video_srt' not in active_nodes():
                raise RuntimeError('SRT node disappeared; inspect video.log')
            if not fresh(): raise RuntimeError('RGBD frame timeout; video degraded')
            if any(child.poll() is not None for child in children):
                raise RuntimeError('Owned camera/video process exited; inspect camera.log and video.log')
            time.sleep(0.5)
    except Exception as exc:
        rospy.logerr('CAMERA_VIDEO_DEGRADED: %s', exc)
    finally:
        for child in reversed(children):
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGINT)
                try: child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGTERM)
                    child.wait(timeout=10)
        for stream in streams: stream.close()
        rospy.signal_shutdown('camera supervisor stopped')


if __name__ == '__main__':
    main()
