import re
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

import yaml
from markdown_it import MarkdownIt

from scripts.documentation import document_links, local_target, rewrite_links

ROOT = Path(__file__).resolve().parents[1]
EDGE = ROOT
REFERENCE = EDGE / "documents/INTERFACE_REFERENCE.md"


def leaf_keys(value, prefix=""):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from leaf_keys(child, prefix + "." + key if prefix else key)
    elif isinstance(value, list) and value and isinstance(value[0], dict):
        for child in value:
            yield from leaf_keys(child, prefix + "[]")
    else:
        yield prefix


def heading_ids(text):
    identifiers = set()
    tokens = MarkdownIt().parse(text)
    for index, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        children = tokens[index + 1].children or []
        title = "".join(child.content for child in children
                        if child.type in ("text", "code_inline"))
        base = re.sub(r"[^\w\s-]", "", title.lower()).replace(" ", "-")
        slug, suffix = base, 0
        while slug in identifiers:
            suffix += 1
            slug = base + "-" + str(suffix)
        identifiers.add(slug)
    identifiers.update(re.findall(r'id=["\']([^"\']+)["\']', text))
    return identifiers


class EdgeDocumentationTests(unittest.TestCase):
    def test_all_56_yaml_files_have_parameter_coverage(self):
        reference = REFERENCE.read_text(encoding="utf-8")
        profiles = {"go2_edu", "go2_robot2", "go2_robot3", "ground_air_agv",
                    "scout_mini", "wheeltec_r550p", "wheeltec_r550p_02", "uav_001"}
        config_names = {"device.yaml", "epgeneral_mqtav.yaml", "map_stream.yaml",
                        "relocalization.yaml", "task_control.yaml", "udp_telemetry.yaml",
                        "video.yaml"}
        defaults = list((EDGE / "EPGeneral_device_config/config").glob("*.yaml"))
        self.assertEqual({path.name for path in defaults}, config_names)
        count = 0
        for default in defaults:
            heading = re.search(r"(?m)^## \d+\. " + re.escape(default.name) + r"$", reference)
            self.assertIsNotNone(heading, default.name)
            end = reference.find("\n## ", heading.end())
            section = reference[heading.end():end if end != -1 else len(reference)]
            documented = set(re.findall(r"`([A-Za-z0-9_.\[\]]+)`", section))
            deployed = list((EDGE / "devices").glob("*/profiles/*/config/" + default.name))
            self.assertEqual({path.parent.parent.name for path in deployed}, profiles,
                             default.name)
            paths = [default] + deployed
            self.assertEqual(len(paths), 9, default.name)
            for path in paths:
                count += 1
                config = yaml.safe_load(path.read_text(encoding="utf-8"))
                self.assertFalse(set(leaf_keys(config)) - documented,
                                 f"{path}: {set(leaf_keys(config)) - documented}")
        self.assertEqual(count, 63)

    def test_all_package_readmes_and_versions_are_navigable(self):
        overview = (EDGE / "README.md").read_text(encoding="utf-8")
        manifests = list(EDGE.glob("*/package.xml")) + list(EDGE.glob("devices/*/*/package.xml"))
        self.assertEqual({manifest.parent.name for manifest in manifests}, {
            "EPGeneral_device_config", "EPGeneral_map_stream", "epgeneral_mqtav",
            "EPGeneral_relocalization", "EPGeneral_ground_air_control",
            "EPGeneral_task_control", "EPGeneral_go2_integration",
            "EPGeneral_udp_telemetry", "EPGeneral_video_srt", "EPGeneral_uav_integration",
        })
        for manifest in manifests:
            tree = ElementTree.parse(manifest).getroot()
            text = (manifest.parent / "README.md").read_text(encoding="utf-8")
            self.assertIn(tree.findtext("version"), overview)
            self.assertIn("USER_MANUAL.md", text)
            self.assertIn("INTERFACE_REFERENCE.md", text)

    def test_current_documentation_local_links_and_anchors(self):
        paths = list(EDGE.rglob("*.md"))
        for path in sorted(set(paths)):
            source = path.relative_to(ROOT).as_posix()
            text = path.read_text(encoding="utf-8")
            for link in document_links(text):
                parts = urlsplit(link)
                if parts.scheme or parts.netloc:
                    continue
                target = local_target(source, link) or source
                target_path = ROOT / target
                self.assertTrue(target_path.exists(), f"{source}: {link}")
                if parts.fragment and target_path.suffix == ".md":
                    self.assertIn(unquote(parts.fragment),
                                  heading_ids(target_path.read_text(encoding="utf-8")),
                                  f"{source}: {link}")

    def test_profile_topic_matrix_matches_configured_interfaces(self):
        text = (EDGE / "documents/INTERFACE_REFERENCE.md").read_text(encoding="utf-8")

        def interfaces(value, prefix=""):
            if isinstance(value, list):
                for index, item in enumerate(value):
                    name = item.get("name", index) if isinstance(item, dict) else index
                    yield from interfaces(item, f"{prefix}[{name}]")
            elif isinstance(value, dict):
                for key, child in value.items():
                    path = prefix + "." + key if prefix else key
                    if isinstance(child, str) and (key in ("topic", "service")
                            or key.endswith(("_topic", "_service", "_action", "_param"))):
                        yield path, child, value.get("message_type", value.get("image_message_type"))
                    else:
                        yield from interfaces(child, path)

        for config_dir in sorted((EDGE / "devices").glob("*/profiles/*/config")):
            profile = config_dir.parent.name
            match = re.search(r"(?m)^### \w+ / " + re.escape(profile) + r"$", text)
            self.assertIsNotNone(match, profile)
            end = text.find("\n### ", match.end())
            section = text[match.end():end if end != -1 else len(text)]
            for path in config_dir.glob("*.yaml"):
                config = yaml.safe_load(path.read_text(encoding="utf-8"))
                for key, value, message_type in interfaces(config):
                    expected = f"| `{path.name}: {key}` | `{value}` |"
                    row = next((line for line in section.splitlines() if line.startswith(expected)), None)
                    self.assertIsNotNone(row, f"{profile}: {expected}")
                    if message_type:
                        self.assertIn(message_type, row, f"{profile}: {key}")


    def test_script_environment_and_public_launch_arguments_are_described(self):
        text = REFERENCE.read_text(encoding="utf-8")
        for script in (EDGE / "devices").glob("*/profiles/*/start_ccs_edge_dev.sh"):
            for name in set(re.findall(r"\$\{(CCS_[A-Z0-9_]+)", script.read_text(encoding="utf-8"))):
                self.assertIn(name, text, str(script))
        for launch in EDGE.glob("*/launch/*.launch"):
            for arg in ElementTree.parse(launch).getroot().findall("arg"):
                self.assertIn(arg.attrib["name"], text, str(launch))
