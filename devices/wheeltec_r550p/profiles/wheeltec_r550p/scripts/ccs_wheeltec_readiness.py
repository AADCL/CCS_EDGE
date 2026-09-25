#!/usr/bin/env python3
"""Observe fresh WheelTech inputs; stopped mode verifies measured wheel speed."""
import argparse
import math
import threading
import time

INPUTS = {'/odom': 'nav_msgs/Odometry', '/imu': 'sensor_msgs/Imu',
          '/PowerVoltage': 'std_msgs/Float32', '/livox/lidar': 'livox_ros_driver2/CustomMsg',
          '/livox/imu': 'sensor_msgs/Imu'}


def stationary(message):
    twist = message.twist.twist
    values = [twist.linear.x, twist.linear.y, twist.linear.z,
              twist.angular.x, twist.angular.y, twist.angular.z]
    return all(math.isfinite(v) for v in values) and max(abs(v) for v in values[:3]) <= .01 \
        and max(abs(v) for v in values[3:]) <= .02


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('inputs', 'stopped'))
    parser.add_argument('--timeout', type=float, default=30)
    parser.add_argument('--max-age', type=float, default=3)
    args = parser.parse_args()
    import rospy
    import roslib.message
    rospy.init_node('ccs_wheeltec_readiness', anonymous=True, disable_signals=True)
    topics = INPUTS if args.mode == 'inputs' else {'/odom': INPUTS['/odom']}
    observations = {}
    lock = threading.Lock()
    started = time.time()

    def observe(message, topic):
        now = time.time()
        header = getattr(message, 'header', None)
        stamp = header.stamp.to_sec() if header is not None else now
        valid = started <= stamp <= now and now - stamp <= args.max_age
        if topic == '/PowerVoltage':
            valid = valid and math.isfinite(message.data) and message.data > 0
        if args.mode == 'stopped':
            valid = valid and stationary(message)
        with lock:
            count, previous, unused = observations.get(topic, (0, 0, 0))
            observations[topic] = ((count + 1) if valid and stamp > previous else 0, stamp, now)

    subscribers = [rospy.Subscriber(topic, roslib.message.get_message_class(kind),
                                   observe, callback_args=topic, queue_size=2)
                   for topic, kind in topics.items()]
    deadline = time.monotonic() + args.timeout
    try:
        while time.monotonic() < deadline and not rospy.is_shutdown():
            with lock:
                missing = [topic for topic in topics if observations.get(topic, (0, 0, 0))[0] < 2
                           or time.time() - observations[topic][2] > args.max_age]
            if not missing:
                print('Fresh {} confirmed: {}'.format(args.mode, ', '.join(topics)))
                return 0
            time.sleep(.05)
        print('Fresh {} unavailable: {}'.format(args.mode, ', '.join(missing)))
        return 1
    finally:
        for subscriber in subscribers:
            subscriber.unregister()
        rospy.signal_shutdown('readiness completed')


if __name__ == '__main__':
    raise SystemExit(main())
