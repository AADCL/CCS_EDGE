#!/usr/bin/env python3
"""Optional camera/video lifecycle. Signals only subprocesses created here."""
import argparse
import collections
import os
import signal
import subprocess
import time
import threading


CAMERA_COMMAND = [
    'roslaunch', 'orbbec_camera', 'gemini_330_series.launch',
    'camera_name:=camera', 'enable_color:=true', 'enable_depth:=true',
    'color_width:=640', 'color_height:=480', 'color_fps:=30', 'color_rotation:=0',
    'depth_width:=640', 'depth_height:=480', 'depth_fps:=30', 'depth_rotation:=0',
    'depth_registration:=true', 'align_mode:=SW', 'align_target_stream:=COLOR',
    'enable_frame_sync:=true', 'enable_point_cloud:=false',
    'enable_colored_point_cloud:=false', 'enable_left_ir:=false', 'enable_right_ir:=false',
    'enable_accel:=false', 'enable_gyro:=false', 'enable_image_transport_plugins:=false',
]


class FrameWindow:
    """Use acquisition timestamps for FPS; startup callbacks may arrive in bursts."""
    def __init__(self):
        self.samples = collections.deque(maxlen=120)
        self.lock = threading.Lock()

    def add(self, width, height, stamp, ros_now, received):
        if width != 640 or height != 480 or not -0.5 <= ros_now - stamp <= 2.0:
            return
        with self.lock:
            if self.samples and stamp <= self.samples[-1][0]:
                return
            self.samples.append((stamp, received))

    def fresh(self, now):
        with self.lock:
            return bool(self.samples) and now - self.samples[-1][1] < 2.0

    def rate(self, now):
        with self.lock:
            samples = tuple(self.samples)
        if len(samples) < 30 or now - samples[-1][1] >= 2.0:
            return None
        sensor_span = samples[-1][0] - samples[0][0]
        arrival_span = samples[-1][1] - samples[0][1]
        if sensor_span < 1.5 or arrival_span < 2.0:
            return None
        return (len(samples) - 1) / sensor_span


def main():
    import rospy
    import rosgraph
    from sensor_msgs.msg import Image
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', required=True)
    parser.add_argument('--log-dir', required=True)
    parser.add_argument('--owner-pid', type=int, default=0)
    args = parser.parse_args()
    import yaml
    with open(os.path.join(args.profile, 'video.yaml')) as stream:
        if not yaml.safe_load(stream).get('enabled', False):
            return
    rospy.init_node('ccs_camera_supervisor', disable_signals=True)
    stopping = [False]
    signal.signal(signal.SIGINT, lambda *_: stopping.__setitem__(0, True))
    signal.signal(signal.SIGTERM, lambda *_: stopping.__setitem__(0, True))
    def owner_identity():
        if not args.owner_pid:
            return None
        try:
            with open('/proc/%s/stat' % args.owner_pid) as stream:
                return stream.read().rsplit(')', 1)[1].split()[19]
        except (OSError, IndexError):
            return None
    owner_start = owner_identity()
    def stop_requested():
        return stopping[0] or rospy.is_shutdown() or (args.owner_pid and
            (owner_start is None or owner_identity() != owner_start))
    frames, depth = FrameWindow(), FrameWindow()
    children = []
    streams = []
    def color(message):
        frames.add(message.width, message.height, message.header.stamp.to_sec(),
                   rospy.Time.now().to_sec(), time.monotonic())
    def depth_frame(message):
        depth.add(message.width, message.height, message.header.stamp.to_sec(),
                  rospy.Time.now().to_sec(), time.monotonic())
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
        return frames.fresh(now) and depth.fresh(now)
    def wait_images(seconds):
        deadline = time.monotonic() + seconds
        rates = (None, None)
        while not stop_requested() and time.monotonic() < deadline:
            now = time.monotonic()
            rates = (frames.rate(now), depth.rate(now))
            if all(rate is not None and 20 <= rate <= 40 for rate in rates):
                return rates
            if any(child.poll() is not None for child in children):
                raise RuntimeError('Camera process exited before fresh images; inspect camera.log')
            time.sleep(0.1)
        raise RuntimeError('RGBD did not stabilize at 640x480/30 FPS within %ss; measured=%s' % (seconds, rates))
    try:
        import rospkg
        from xml.etree import ElementTree
        video_package = rospkg.RosPack().get_path('epgeneral_video_srt')
        version = ElementTree.parse(os.path.join(video_package, 'package.xml')).findtext('version')
        if tuple(int(part) for part in version.split('.')) < (0, 1, 2):
            raise RuntimeError('epgeneral_video_srt >= 0.1.2 must be deployed and rebuilt for 180-degree rotation')
        publishers = dict(rosgraph.Master(rospy.get_name()).getSystemState()[0])
        external = bool(publishers.get('/camera/color/image_raw') or publishers.get('/camera/depth/image_raw'))
        if external:
            rospy.loginfo('Checking external RGBD instance; it remains externally owned')
        else:
            rospy.loginfo('Starting camera: %s', ' '.join(CAMERA_COMMAND))
            start('camera', CAMERA_COMMAND)
            start('camera_mount_tf', ['rosrun', 'tf2_ros', 'static_transform_publisher',
                '0.16', '0', '0.08', '0', '0', '3.141592653589793', 'base_link', 'camera_link'])
        fps, depth_fps = wait_images(30)
        rospy.loginfo('RGBD ready RGB=%.1f depth=%.1f FPS, external=%s', fps, depth_fps, external)
        if '/epgeneral_video_srt' in active_nodes():
            raise RuntimeError('External video publisher detected; refusing duplicate SRT owner')
        # Port ownership is validated by the video node; never stop its external owner.
        video = start('video', ['roslaunch', 'epgeneral_video_srt', 'epgeneral_video_srt.launch',
            'device_config_file:=' + os.path.join(args.profile, 'device.yaml'),
            'video_config_file:=' + os.path.join(args.profile, 'video.yaml')])
        video_deadline = time.monotonic() + 15
        while not stop_requested() and '/epgeneral_video_srt' not in active_nodes():
            if time.monotonic() > video_deadline or video.poll() is not None:
                raise RuntimeError('SRT node did not start; inspect video.log')
            time.sleep(0.25)
        while not stop_requested():
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
