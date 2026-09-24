import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

class PackageVersionTests(unittest.TestCase):
    def test_map_stream_package_versions_match(self):
        root = Path(__file__).resolve().parents[1] / "EPGeneral_map_stream"
        package_version = ET.parse(root / "package.xml").getroot().findtext("version")
        init_text = (root / "src" / "epgeneral_map_stream" / "__init__.py").read_text(
            encoding="utf-8"
        )
        self.assertEqual(package_version, "0.14.0")
        self.assertIn('__version__ = "0.14.0"', init_text)

    def test_relocalization_package_versions_match(self):
        root = Path(__file__).resolve().parents[1] / "EPGeneral_relocalization"
        package_version = ET.parse(root / "package.xml").getroot().findtext("version")
        init_text = (root / "src" / "epgeneral_relocalization" / "__init__.py").read_text(
            encoding="utf-8"
        )
        setup_text = (root / "setup.py").read_text(encoding="utf-8")
        self.assertEqual(package_version, "0.6.0")
        self.assertIn('__version__ = "0.6.0"', init_text)
        self.assertIn('version="0.6.0"', setup_text)

    def test_task_control_version_matches_manifest_and_source(self):
        root = Path(__file__).resolve().parents[1] / "EPGeneral_task_control"
        package_version = ET.parse(root / "package.xml").getroot().findtext("version")
        init_text = (root / "src" / "epgeneral_task_control" / "__init__.py").read_text(encoding="utf-8")
        self.assertEqual(package_version, "0.6.4")
        self.assertIn('__version__ = "0.6.4"', init_text)

    def test_device_config_version(self):
        root = Path(__file__).resolve().parents[1] / "EPGeneral_device_config"
        self.assertEqual(ET.parse(root / "package.xml").getroot().findtext("version"), "0.3.0")
