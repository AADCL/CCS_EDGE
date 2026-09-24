"""Actual-message readiness checks; ROS imports are isolated from pure tests."""
import math
import time


def driver_velocity_link(system_state, topic):
    publishers = dict(system_state[0])
    subscribers = dict(system_state[1])
    sources = set(publishers.get(topic, []))
    sinks = set(subscribers.get(topic, []))
    if '/move_base' not in sources or '/wheeltec_robot' not in sinks:
        return False, 'move_base is not connected directly to the chassis driver'
    if '/wheeltec_safety' in sources:
        return False, 'exploration safety gate still publishes to the chassis driver'
    return True, 'direct chassis velocity link is connected'


class Readiness:
    def __init__(self, mode, cmd_vel_topic='/wheeltec_driver/cmd_vel'):
        import rospy
        import rostopic
        import tf2_ros
        self.rospy = rospy
        self.received = {}
        self.errors = {}
        self.subscribers = []
        self.mode = mode
        self.cmd_vel_topic = cmd_vel_topic
        self.topics = (['/odom', '/imu', '/PowerVoltage', '/livox/lidar', '/livox/imu'] if mode == 'base' else
                       ['/odom', '/fastlio_odom', '/cloud_registered_body', '/cloud_registered_base', '/terrain/obstacle_points', '/terrain/clearing_points'])
        self.pending = set(self.topics)
        self.buffer = tf2_ros.Buffer()
        self.listener = tf2_ros.TransformListener(self.buffer)

    def callback(self, message, topic):
        if hasattr(message, 'header'):
            stamp = message.header.stamp.to_sec()
            age = self.rospy.Time.now().to_sec() - stamp
            if stamp <= 0 or not math.isfinite(age) or age < -0.2 or age > 2:
                self.errors[topic] = 'stale/invalid source timestamp'
                return
        if topic == '/PowerVoltage' and (not math.isfinite(message.data) or message.data <= 0):
            self.errors[topic] = 'invalid voltage'
            return
        self.received[topic] = time.monotonic()
        self.errors.pop(topic, None)

    def check(self):
        import rostopic
        import rosnode
        for topic in list(self.pending):
            cls, unused, unused_fn = rostopic.get_topic_class(topic, blocking=False)
            if cls is not None:
                self.subscribers.append(self.rospy.Subscriber(topic, cls, self.callback, callback_args=topic, queue_size=1))
                self.pending.remove(topic)
        now = time.monotonic()
        missing = [name for name in self.topics if now - self.received.get(name, -1000) > 2]
        if missing:
            return False, 'waiting for fresh messages: ' + ','.join(missing)
        if self.mode == 'navigation':
            try:
                transform = self.buffer.lookup_transform('map', 'base_link', self.rospy.Time(0), self.rospy.Duration(0.1))
                age = self.rospy.Time.now().to_sec() - transform.header.stamp.to_sec()
                if not -0.2 <= age <= 1:
                    return False, 'map/base_link TF is stale'
            except Exception as exc:
                return False, 'TF unavailable: ' + str(exc)
            required = {'/move_base', '/wheeltec_terrain_map_server', '/wheeltec_navigation_map_server',
                        '/wheeltec_navigation_patchworkpp', '/wheeltec_navigation_terrain_guard',
                        '/wheeltec_robot', '/wheeltec_control',
                        '/wheeltec_global_localizer', '/wheeltec_map_loader', '/wheeltec_map_server',
                        '/laserMapping', '/wheeltec_tf_manager', '/wheeltec_geometry_tf_publisher',
                        '/wheeltec_pose_adapter', '/wheeltec_cloud_adapter'}
            if not required.issubset(set(rosnode.get_node_names())):
                return False, 'native navigation nodes are incomplete'
            try:
                import rosgraph
                state = rosgraph.Master('/ccs_wheeltec_navigation').getSystemState()
                connected, reason = driver_velocity_link(state, self.cmd_vel_topic)
                if not connected:
                    return False, reason
                for name, upper in (('cmd_vel_timeout', 0.20),
                                    ('max_linear_x', 0.20), ('max_angular_z', 0.40)):
                    value = float(self.rospy.get_param('/wheeltec_robot/' + name))
                    if not math.isfinite(value) or value <= 0 or value > upper:
                        return False, 'chassis driver protection is invalid: ' + name
            except Exception as exc:
                return False, 'chassis driver protection is unavailable: ' + str(exc)
        return True, 'fresh inputs and required nodes'
