import unittest
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
EDGE_ROOT = ROOT
DEVICE_CONFIG = EDGE_ROOT / "EPGeneral_device_config" / "config"

PACKAGE_DIRS = (
    "EPGeneral_device_config",
    "EPGeneral_map_stream",
    "epgeneral_mqtav",
    "EPGeneral_relocalization",
    "devices/ground_air_agv/EPGeneral_ground_air_control",
    "EPGeneral_task_control",
    "EPGeneral_udp_telemetry",
    "EPGeneral_video_srt",
    "devices/go2/EPGeneral_go2_integration",
    "devices/uav/EPGeneral_uav_integration",
)
FUNCTION_DIRS = PACKAGE_DIRS[1:]
CONFIG_FILES = (
    "device.yaml",
    "epgeneral_mqtav.yaml",
    "udp_telemetry.yaml",
    "video.yaml",
    "map_stream.yaml",
    "relocalization.yaml",
    "task_control.yaml",
)


class EdgePackageLayoutTests(unittest.TestCase):
    def test_edge_root_has_nine_packages_and_two_control_side_directories(self):
        actual = {
            path.name
            for path in EDGE_ROOT.iterdir()
            if path.is_dir() and not path.name.startswith(".") and path.name != "__pycache__"
        }
        self.assertEqual(actual, {p for p in PACKAGE_DIRS if "/" not in p} | {"devices", "documents", "tests", "scripts"})

    def test_deployable_package_allowlist_has_valid_manifests(self):
        package_names = set()
        for directory in PACKAGE_DIRS:
            manifest = ElementTree.parse(
                EDGE_ROOT / directory / "package.xml").getroot()
            package_names.add(manifest.findtext("name"))
        self.assertEqual(package_names, {
            "epgeneral_device_config",
            "epgeneral_map_stream",
            "epgeneral_mqtav",
            "epgeneral_relocalization",
            "epgeneral_ground_air_control",
            "epgeneral_task_control",
            "epgeneral_udp_telemetry",
            "epgeneral_video_srt",
            "epgeneral_go2_integration",
            "epgeneral_uav_integration",
        })
        self.assertFalse((EDGE_ROOT / "deploy" / "package.xml").exists())
        self.assertFalse((EDGE_ROOT / "documents" / "package.xml").exists())

    def test_only_device_config_contains_runtime_yaml(self):
        self.assertEqual(
            {path.name for path in DEVICE_CONFIG.glob("*.yaml")},
            set(CONFIG_FILES),
        )
        for directory in FUNCTION_DIRS:
            self.assertFalse((EDGE_ROOT / directory / "config").exists())

    def test_primary_launch_defaults_use_shared_config(self):
        cases = {
            "EPGeneral_map_stream/launch/epgeneral_map_stream.launch":
                "config/map_stream.yaml",
            "EPGeneral_relocalization/launch/epgeneral_relocalization.launch":
                "config/relocalization.yaml",
            "EPGeneral_task_control/launch/epgeneral_task_control.launch":
                "config/task_control.yaml",
            "EPGeneral_video_srt/launch/epgeneral_video_srt.launch":
                "config/video.yaml",
        }
        for relative, config_path in cases.items():
            text = (EDGE_ROOT / relative).read_text(encoding="utf-8")
            self.assertIn(
                "$(find epgeneral_device_config)/" + config_path,
                text,
            )

    def test_mqtav_requires_explicit_profile_selection(self):
        launch = ElementTree.parse(EDGE_ROOT / "epgeneral_mqtav/launch/epgeneral_mqtav.launch").getroot()
        arguments = {arg.attrib["name"]: arg.attrib.get("default") for arg in launch.findall("arg")}
        self.assertEqual(arguments["config_dir"], "")
        self.assertEqual(arguments["config_file"], "")
        self.assertEqual(arguments["device_config_file"], "")

    def test_udp_requires_explicit_selection_and_no_implicit_overrides(self):
        launch = ElementTree.parse(EDGE_ROOT / "EPGeneral_udp_telemetry/launch/epgeneral_udp_telemetry.launch").getroot()
        arguments = {arg.attrib["name"]: arg.attrib.get("default") for arg in launch.findall("arg")}
        for key in ("config_dir", "telemetry_config_file", "device_config_file", "destination_host", "destination_port", "link_status_topic", "diagnostics_topic"):
            self.assertEqual(arguments[key], "")
        self.assertEqual(launch.find("node").attrib["required"], "true")

    def test_obsolete_packages_are_absent(self):
        self.assertFalse((EDGE_ROOT / "EPQRD_go2_bridge").exists())
        self.assertFalse((EDGE_ROOT / "ros_udp_telemetry").exists())


if __name__ == "__main__":
    unittest.main()
