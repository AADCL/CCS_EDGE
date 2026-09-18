#!/usr/bin/env python3
"""Prepare an empty staging directory; never deploy or start devices."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from edge_paths import ROOT, LAYOUT, package_path, profile_path, packages_for

def prepare(profile, output):
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Staging directory must be empty: " + str(output))
    if output == ROOT or ROOT in output.parents:
        raise ValueError("Use staging outside the source repository")
    output.mkdir(parents=True, exist_ok=True)
    selected = packages_for(profile)
    ignore = shutil.ignore_patterns(".git", "__pycache__", "*.pyc", "build", "devel", "install", ".pytest_cache")
    for name in selected:
        shutil.copytree(package_path(name), output / "src" / name, ignore=ignore)
    source = profile_path(profile)
    shutil.copytree(source, output / "deploy" / profile, ignore=ignore)
    for config in (source / "config").glob("*.yaml"):
        shutil.copy2(config, output / "src/EPGeneral_device_config/config" / config.name)
    for path in output.rglob("*"):
        if path.is_file() and path.suffix in (".sh", ".py"):
            data = path.read_bytes().replace(b"\r\n", b"\n")
            path.write_bytes(data)
            if path.suffix == ".sh" or data.startswith(b"#!"):
                path.chmod(path.stat().st_mode | 0o111)
    manifest = {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(output.rglob("*")) if p.is_file()}
    (output / "staging-manifest.json").write_text(json.dumps({
        "profile": profile, "packages": selected, "sha256": manifest}, indent=2), encoding="utf-8")
    return selected

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=sorted(LAYOUT["profiles"]), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print("Prepared:", ", ".join(prepare(args.profile, args.output)))
