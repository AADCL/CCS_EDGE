import os
from pathlib import Path
import struct
import tempfile
import time
import unittest
import zipfile
import yaml

from epgeneral_map_stream.artifacts import (
    ArtifactError, SessionPaths, build_archive, collect_occupancy, validate_ot, file_fingerprint,
)
from epgeneral_map_stream.config import load_config, build_integration_commands
import test_artifacts as helpers


def ot_bytes():
    return b"# Octomap OcTree file\nid OcTree\nsize 1\nres 0.1\ndata\n" + struct.pack("<fB", 2., 0)


class OtArtifactTests(unittest.TestCase):
    setUp = helpers.ArtifactTests.setUp

    def test_ot_only_and_negotiated_all_formats(self):
        helpers.write_outputs(self.paths)
        Path(self.paths.ot_path).write_bytes(ot_bytes())
        identity = dict(self.identity, artifact_formats=["pcd", "pgm", "yaml", "ot"])
        for roles in (("pcd", "pgm", "yaml", "ot"), ("pcd", "ot")):
            if "pgm" not in roles:
                Path(self.paths.pgm_path).unlink()
                Path(self.paths.yaml_path).unlink()
            build_archive(self.paths, self.config, identity)
            with zipfile.ZipFile(self.paths.archive_path) as archive:
                self.assertEqual(set(archive.namelist()), {"manifest.json"} | {"map." + role for role in roles})
        with self.assertRaisesRegex(ArtifactError, "not negotiated"):
            build_archive(self.paths, self.config, self.identity)

    def test_freshness_and_truncated_tree(self):
        source = Path(self.temp.name) / "native.ot"
        source.write_bytes(ot_bytes())
        os.utime(source, ns=(1, 1))
        self.config.update(source_ot_explicit=True, source_ot_template=str(source))
        baseline = {"ot": file_fingerprint(str(source))}
        started = time.time_ns()
        collect_occupancy(self.paths, self.config, baseline, started)
        self.assertFalse(Path(self.paths.ot_path).exists())
        source.write_bytes(ot_bytes())
        os.utime(source, ns=(started+1000, started+1000))
        collect_occupancy(self.paths, self.config, baseline, started)
        self.assertEqual(Path(self.paths.ot_path).read_bytes(), ot_bytes())
        source.write_bytes(ot_bytes()[:-1])
        with self.assertRaises(ArtifactError):
            validate_ot(source, self.config["max_artifact_bytes"])
        for resolution in (b"1e300", b"1e-300"):
            source.write_bytes(ot_bytes().replace(b"res 0.1", b"res " + resolution))
            with self.assertRaises(ArtifactError):
                validate_ot(source, self.config["max_artifact_bytes"])

    def test_custom_exporter_does_not_require_pgm_configuration_or_checks(self):
        with open(helpers.MAPPING, encoding="utf-8") as stream:
            mapping = yaml.safe_load(stream)
        mapping["integrations"].pop("pgm")
        mapping["integrations"]["occupancy"] = {
            "command": ["verified-export", "{pcd_path}", "{ot_path}"],
            "check_command": ["verified-export", "--check"],
        }
        for key in ("source_pgm_path", "source_yaml_path", "pgm_path", "yaml_path"):
            mapping["artifacts"].pop(key)
        path = Path(self.temp.name) / "custom.yaml"
        path.write_text(yaml.safe_dump(mapping), encoding="utf-8")
        config = load_config(str(path), helpers.DEVICE)
        paths = SessionPaths(config, self.identity)
        commands = build_integration_commands(config, paths.values)
        self.assertNotIn("generate_pgm", commands)
        self.assertNotIn(commands["check_pgm"], commands["checks"])
        self.assertEqual(commands["occupancy_export"][-1], paths.ot_path)
        self.assertEqual(os.path.dirname(paths.ot_path), os.path.dirname(paths.pcd_path))
