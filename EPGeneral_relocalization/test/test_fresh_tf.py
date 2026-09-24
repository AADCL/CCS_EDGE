import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from epgeneral_relocalization.ros_bridge import RosBridge, RosIntegrationError

class FreshTfTests(unittest.TestCase):
    def test_full_chain_freshness(self):
        bridge = object.__new__(RosBridge)
        bridge.config = dict(require_fresh_tf=True, map_frame='map', base_frame='base_link',
                             localization_health_timeout_seconds=2.)
        class Time:
            def __init__(self, value): pass
            @staticmethod
            def now(): return N(to_sec=lambda: 100.)
        bridge.rospy = N(Time=Time, Duration=lambda x:x)
        transform = lambda stamp:N(header=N(stamp=N(to_sec=lambda:stamp)))
        bridge.buffer = N(lookup_transform=Mock(return_value=transform(99.9)))
        bridge._check_fresh_chain(transform(100.25))
        for stale in (0., 90., 102.):
            with self.assertRaises(RosIntegrationError): bridge._check_fresh_chain(transform(stale))
        bridge.buffer.lookup_transform.return_value = transform(90.)
        with self.assertRaises(RosIntegrationError): bridge._check_fresh_chain(transform(100.))
        bridge.buffer.lookup_transform.side_effect = RuntimeError('disconnected tree')
        with self.assertRaises(RuntimeError): bridge._check_fresh_chain(transform(100.))

if __name__ == '__main__': unittest.main()
