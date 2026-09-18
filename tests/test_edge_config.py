import json
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
EDGE_CONFIG = ROOT / 'EPGeneral_device_config/config/device.yaml'
SHARED_CONFIG = EDGE_CONFIG.parent


class EdgeDeviceAlignmentTests(unittest.TestCase):
    def test_shared_config_contains_one_file_per_deployable_package(self):
        self.assertEqual(
            {path.name for path in SHARED_CONFIG.glob("*.yaml")},
            {
                "device.yaml",
                "epgeneral_mqtav.yaml",
                "udp_telemetry.yaml",
                "video.yaml",
                "map_stream.yaml",
                "relocalization.yaml",
                "task_control.yaml",
            },
        )
        for path in SHARED_CONFIG.glob("*.yaml"):
            self.assertIsInstance(
                yaml.safe_load(path.read_text(encoding="utf-8")), dict)



if __name__ == "__main__":
    unittest.main()
