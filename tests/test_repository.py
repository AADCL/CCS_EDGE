"""Repository-layout contracts that catch partial migrations and staging errors."""
import ast
import json
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as ET
import yaml
from edge_paths import ROOT, LAYOUT, package_path, profile_path, packages_for
from scripts.prepare_profile import prepare

class RepositoryTests(unittest.TestCase):
    def test_layout_packages_profiles_and_static_files(self):
        packages = LAYOUT["common_packages"] + list(LAYOUT["special_packages"])
        manifests = [package_path(p) / "package.xml" for p in packages]
        self.assertEqual(len(manifests), 11)
        self.assertEqual(len({ET.parse(p).findtext("name") for p in manifests}), 11)
        self.assertEqual(len(LAYOUT["profiles"]), 8)
        for p in ROOT.rglob("*"):
            if ".git" in p.parts or "__pycache__" in p.parts or not p.is_file():
                continue
            if p.suffix in (".sh", ".py"):
                self.assertNotIn(b"\r", p.read_bytes(), str(p))
            if p.suffix == ".py":
                ast.parse(p.read_text(encoding="utf-8"), filename=str(p), feature_version=(3, 8))
            elif p.suffix in (".xml", ".launch"):
                ET.parse(p)
            elif p.suffix in (".yaml", ".yml"):
                yaml.safe_load(p.read_text(encoding="utf-8"))

    def test_two_device_documents_and_historical_coverage(self):
        for typ in {v["device_type"] for v in LAYOUT["profiles"].values()}:
            folder = ROOT / "documents/devices" / typ
            expected = {"DEPLOYMENT_GUIDE.md", "DEPLOYMENT_RECORD.md"}
            if typ == "wheeltec_r550p":
                expected.add("UGV004_FIX_20260924.md")
            self.assertEqual({p.name for p in folder.rglob("*.md")},
                             expected)
        for profile, definition in LAYOUT["profiles"].items():
            identity = yaml.safe_load((profile_path(profile)/"config/device.yaml").read_text())["device"]["id"]
            record = ROOT / "documents/devices" / definition["device_type"] / "DEPLOYMENT_RECORD.md"
            self.assertIn(identity, record.read_text(encoding="utf-8"))
        self.assertEqual({p.name for p in (ROOT/"documents").glob("*.md")},
                         {"USER_MANUAL.md", "INTERFACE_REFERENCE.md", "OCTOMAP.md", "UDP_TELEMETRY_GENERIC.md", "VIDEO_SRT_GENERIC.md"})

    def test_uav_profile_uses_flat_ugv_style_runtime_layout(self):
        profile = profile_path("uav_001")
        launcher = (profile / "start_ccs_edge_dev.sh").read_text(encoding="utf-8")
        self.assertIn('${WORKSPACE}/config/uav_001', launcher)
        self.assertIn('${WORKSPACE}/launch', launcher)
        self.assertIn('${WORKSPACE}/scripts', launcher)
        self.assertNotIn('deploy/uav_001', launcher)

        launch = ET.parse(profile / "launch/uav_001_bringup.launch").getroot()
        args = {item.attrib["name"]: item.attrib for item in launch.findall("arg")}
        self.assertEqual(args["profile_config_dir"]["default"],
                         "$(arg workspace)/config/uav_001")
        serialized = ET.tostring(launch, encoding="unicode")
        self.assertEqual(serialized.count('config_dir" value="$(find epgeneral_device_config)/config"'), 3)
        for name in ("device.yaml", "map_stream.yaml", "relocalization.yaml",
                     "task_control.yaml"):
            self.assertIn("$(arg profile_config_dir)/" + name, serialized)

        endpoint_doc = (profile / "DEPLOYMENT.md").read_text(encoding="utf-8")
        for command in ("cd /home/nrc/ccs_edge_ws",
                        "./start_ccs_edge_dev.sh --check",
                        "./start_ccs_edge_dev.sh", "Ctrl+C"):
            self.assertIn(command, endpoint_doc)
        self.assertFalse((ROOT / "documents/devices/uav/DEPLOYMENT_REPORT.md").exists())

    def test_every_profile_stages_only_selected_complete_packages(self):
        for profile in LAYOUT["profiles"]:
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as temp:
                dest = Path(temp)/"stage"
                selected = prepare(profile, dest)
                self.assertEqual(set(selected), set(packages_for(profile)))
                self.assertEqual({p.name for p in (dest/"src").iterdir()}, set(selected))
                for p in selected:
                    self.assertTrue((dest/"src"/p/"package.xml").is_file())
                for source in (profile_path(profile)/"config").glob("*.yaml"):
                    self.assertEqual(source.read_bytes(),
                                     (dest/"src/EPGeneral_device_config/config"/source.name).read_bytes())
                manifest = json.loads((dest/"staging-manifest.json").read_text())
                self.assertEqual(manifest["profile"], profile)
                with self.assertRaises(ValueError):
                    prepare(profile, dest)

    def test_updater_root_and_source_contracts(self):
        for path in (profile_path("ground_air_agv")).glob("deploy*.sh"):
            text = path.read_text()
            self.assertIn('/../../../..', text)
            self.assertNotIn("edge_side_pkg/", text)
            self.assertIn("documents/devices/ground_air_agv/", text)
        ugv3 = yaml.safe_load((profile_path("wheeltec_r550p")/"config/task_control.yaml").read_text())
        ugv4 = yaml.safe_load((profile_path("wheeltec_r550p_02")/"config/task_control.yaml").read_text())
        self.assertEqual(ugv3["adapter"]["navigation_launch_package"], "epgeneral_wheeltec_integration")
        self.assertEqual(ugv3["adapter"]["navigation_launch_file"], "navigation.launch")
        self.assertEqual(ugv4["adapter"]["navigation_launch_file"], "wheeltec_ccs_2d_navigation_v51.launch")
