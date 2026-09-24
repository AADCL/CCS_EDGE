"""Acknowledged application of optional regions; imports native messages lazily."""
import threading
import time


class NdtRegionBridge:
    def __init__(self, rospy):
        from fast_lio_localization.msg import AllowedRegions, AllowedRegion
        from geometry_msgs.msg import Point32
        self.rospy, self.message, self.region, self.point = rospy, AllowedRegions, AllowedRegion, Point32
        self.changed = threading.Condition()
        self.actual = None
        self.last_token = 0
        self.publisher = rospy.Publisher('/ndt_gate/set_regions', AllowedRegions, queue_size=1, latch=False)
        self.subscriber = rospy.Subscriber('/ndt_gate/regions', AllowedRegions, self._received, queue_size=1)

    def _received(self, message):
        with self.changed:
            self.actual = message
            self.changed.notify_all()

    def snapshot(self):
        with self.changed:
            return self.actual

    def apply(self, document):
        message = self.message()
        message.header.frame_id = 'map'
        for item in document['regions']:
            region = self.region()
            region.id = item['id']
            for x, y in item['points']:
                point = self.point(); point.x = x; point.y = y; point.z = 0.0
                region.polygon.points.append(point)
            message.regions.append(region)
        self._send(message)

    def restore(self, previous):
        if previous is None:
            previous = self.message()
            previous.header.frame_id = 'map'
        self._send(previous)

    @staticmethod
    def matches(expected, actual):
        if actual is None or actual.header.frame_id != 'map' or actual.header.stamp != expected.header.stamp:
            return False
        if len(expected.regions) != len(actual.regions):
            return False
        for left, right in zip(expected.regions, actual.regions):
            if left.id != right.id or len(left.polygon.points) != len(right.polygon.points):
                return False
            for a, b in zip(left.polygon.points, right.polygon.points):
                if abs(a.x-b.x) > 1e-4 or abs(a.y-b.y) > 1e-4:
                    return False
        return True

    def _send(self, message):
        # A timestamp survives rospy's automatic Header.seq rewrite.
        import copy
        message = copy.deepcopy(message)
        token = max(self.rospy.Time.now().to_nsec(), self.last_token + 1)
        self.last_token = token
        message.header.stamp = self.rospy.Time(token // 1000000000, token % 1000000000)
        deadline = time.monotonic() + 4.0
        with self.changed:
            while time.monotonic() < deadline and not self.rospy.is_shutdown():
                self.publisher.publish(message)
                self.changed.wait(0.25)
                if self.matches(message, self.actual):
                    return
        raise RuntimeError('NDT_REGION_APPLICATION_TIMEOUT')
