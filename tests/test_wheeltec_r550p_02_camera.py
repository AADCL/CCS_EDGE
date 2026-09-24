import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'devices/wheeltec_r550p/profiles/wheeltec_r550p_02/scripts/ccs_camera_supervisor.py'
spec = importlib.util.spec_from_file_location('camera_supervisor', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class CameraTests(unittest.TestCase):
    def test_direct_driver_uses_unrotated_30fps_inputs(self):
        command = module.CAMERA_COMMAND
        self.assertEqual(command[:3], ['roslaunch', 'orbbec_camera', 'gemini_330_series.launch'])
        for argument in ('color_fps:=30', 'depth_fps:=30', 'color_rotation:=0'):
            self.assertIn(argument, command)

    def test_startup_burst_waits_then_uses_capture_timestamps(self):
        window = module.FrameWindow()
        for i in range(20):
            window.add(640,480,100+i/30.,101.,i/50.)
        self.assertIsNone(window.rate(.4))
        for i in range(20,91):
            window.add(640,480,100+i/30.,100+i/30.,i/30.)
        self.assertAlmostEqual(window.rate(3.),30.)
        self.assertFalse(window.fresh(6.))
        self.assertIsNone(window.rate(6.))

    def test_stale_wrong_size_and_duplicate_frames_do_not_confirm(self):
        window = module.FrameWindow()
        for i in range(100):
            window.add(320,240,100.,100.,i/30.)
            window.add(640,480,90.,100.,i/30.)
            window.add(640,480,100.,100.,i/30.)
        self.assertIsNone(window.rate(3.))

    def test_true_60fps_is_measured_not_mistaken_for_30(self):
        window = module.FrameWindow()
        for i in range(120):
            window.add(640,480,100+i/60.,100+i/60.,i/50.)
        self.assertAlmostEqual(window.rate(2.4),60.)

if __name__ == '__main__': unittest.main()
