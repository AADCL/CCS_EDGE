import os
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'EPGeneral_relocalization/src'))
sys.path.insert(0, str(ROOT / 'EPGeneral_task_control/src'))
from epgeneral_relocalization.ros_bridge import StackManager, RosIntegrationError, RosBridge
from epgeneral_task_control.scout_adapter import ScoutNavigationAdapter


class LifecycleTests(unittest.TestCase):
    @unittest.skipIf(os.name == 'nt', 'Linux flock integration')
    def test_localization_refuses_mapping_lease_without_starting_any_process(self):
        import fcntl
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'algorithm.lock'
            with path.open('a') as owned:
                fcntl.flock(owned, fcntl.LOCK_EX | fcntl.LOCK_NB)
                factory = Mock()
                stack = StackManager({'algorithm_lock_file': str(path)}, Mock(), popen=factory)
                with self.assertRaises(RosIntegrationError):
                    stack.start('map', tmp)
                factory.assert_not_called()
                self.assertIsNone(stack.algorithm_lock)

    @unittest.skipIf(os.name == 'nt', 'Linux flock integration')
    def test_failed_start_releases_algorithm_lease(self):
        import fcntl
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'algorithm.lock'
            config = {'algorithm_lock_file': str(path), 'stages': [{'name':'loc','package':'test','launch':'test.launch'}]}
            stack = StackManager(config, Mock(), popen=Mock(side_effect=OSError('cannot start')))
            with self.assertRaises(OSError):
                stack.start('map', tmp)
            with path.open('a') as other:
                fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertIsNone(stack.algorithm_lock)

    def test_localization_requires_fresh_distinct_tf_samples(self):
        for stamp in (0.0, 1.0, 9.9):
            bridge = RosBridge.__new__(RosBridge)
            bridge.config = {'algorithm_lock_file': '/test/lock', 'tf_timeout_seconds': .05,
                'tf_sample_hz': 200, 'map_frame': 'map', 'odom_frame': 'odom',
                'tf_sample_count': 2, 'translation_tolerance_m': .1, 'yaw_tolerance_deg': 2}
            bridge._monitor_lock = threading.Lock()
            bridge._monitor_generation = 1
            bridge._localization_health_ready = lambda: True
            bridge.rospy = SimpleNamespace(is_shutdown=lambda: False, Duration=lambda x:x,
                Time=Mock(side_effect=lambda x:x))
            bridge.rospy.Time.now = lambda: SimpleNamespace(to_sec=lambda: 10.0)
            transform = SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace(to_sec=lambda:stamp)),
                transform=SimpleNamespace(translation=SimpleNamespace(x=0,y=0,z=0),
                rotation=SimpleNamespace(x=0,y=0,z=0,w=1)))
            bridge.buffer = Mock()
            bridge.buffer.lookup_transform.return_value = transform
            result = Mock()
            bridge._monitor(result, 1)
            self.assertFalse(result.call_args[0][0], 'stale/repeated TF must not localize')

    def test_native_map_gate_is_opt_in(self):
        adapter = ScoutNavigationAdapter.__new__(ScoutNavigationAdapter)
        adapter.config = {}
        self.assertTrue(adapter._native_navigation_ready({'map_id':'map'}))

    def test_native_gate_rejects_missing_or_stale_state(self):
        adapter = ScoutNavigationAdapter.__new__(ScoutNavigationAdapter)
        adapter.config = {'native_map': {'enabled': True, 'readiness_file': '/missing/ready.json'},
                          'active_map_state_file': '/missing/localization.json'}
        self.assertFalse(adapter._native_navigation_ready({'map_id':'map'}))


if __name__ == '__main__':
    unittest.main()
