import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'EPGeneral_video_srt'
SHARED_CONFIG = (
    ROOT / 'EPGeneral_device_config/config')


class EdgeVideoConfigTests(unittest.TestCase):
    def test_package_identity_and_patch_version(self):
        manifest = ET.parse(PACKAGE / "package.xml").getroot()
        self.assertEqual(manifest.findtext("name"), "epgeneral_video_srt")
        self.assertEqual(manifest.findtext("version"), "0.2.0")

    def test_default_srt_listener_contract(self):
        config = yaml.safe_load(
            (SHARED_CONFIG / "video.yaml").read_text(encoding="utf-8"))
        self.assertEqual(config["srt_bind_address"], "0.0.0.0")
        self.assertEqual(config["srt_port"], 9000)
        self.assertEqual(config["srt_latency_ms"], 120)
        self.assertEqual(config["image_message_type"], "sensor_msgs/Image")
        self.assertEqual(config["rotation_degrees"], 0)

    def test_launch_uses_shared_configuration(self):
        launch = (
            PACKAGE / 'launch/epgeneral_video_srt.launch'
        ).read_text(encoding="utf-8")
        arguments = {a.attrib["name"]: a.attrib.get("default") for a in ET.fromstring(launch).findall("arg")}
        for name in ("config_dir", "device_config_file", "video_config_file"):
            self.assertEqual(arguments[name], "")
        self.assertIn("video_srt_node.py", launch)
        self.assertIn('pkg="epgeneral_video_srt"', launch)
        self.assertFalse((PACKAGE / "config").exists())

    def test_raw_and_compressed_subscriptions_remain_supported(self):
        source = (
            PACKAGE / 'src/epgeneral_video_srt_node.cpp'
        ).read_text(encoding="utf-8")
        self.assertIn("compressedImageCallback", source)
        self.assertIn("cv_bridge::toCvCopy", source)

    def test_pipeline_is_low_latency_h264_mpegts_srt_listener(self):
        source = (
            PACKAGE / 'src/epgeneral_video_srt_node.cpp'
        ).read_text(encoding="utf-8")
        for required in (
            "byte-stream=true",
            "profile=baseline",
            "bframes=0",
            "aud=true",
            "h264parse config-interval=-1",
            "mpegtsmux alignment=7",
            "srtsink",
            "mode=listener",
        ):
            self.assertIn(required, source)
        self.assertNotIn("gstreamer-rtsp-server", source.lower())

    def test_optional_rotation_is_validated_and_uses_videoflip(self):
        source = (
            PACKAGE / 'src/epgeneral_video_srt_node.cpp'
        ).read_text(encoding="utf-8")
        for required in (
            'pnh_.param("rotation_degrees", rotation_degrees_, 0)',
            "rotation_degrees must be 0 or 180",
            'gst_element_factory_find("videoflip")',
            'videoflip method=rotate-180',
        ):
            self.assertIn(required, source)

    def test_only_wheeltec_profile_rotates_video(self):
        profiles = ROOT / 'devices'
        rotated = []
        for path in profiles.glob("*/profiles/*/config/video.yaml"):
            config = yaml.safe_load(path.read_text(encoding="utf-8"))
            if config.get("rotation_degrees", 0):
                rotated.append((path.parent.parent.name, config["rotation_degrees"]))
        self.assertEqual(rotated, [("wheeltec_r550p", 180)])


if __name__ == "__main__":
    unittest.main()
