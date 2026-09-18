#!/usr/bin/env python3
"""Run package unit tests in separate processes to isolate ROS stubs."""
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from edge_paths import ROOT, LAYOUT, package_path
packages = LAYOUT["common_packages"] + list(LAYOUT["special_packages"])
env = dict(os.environ, PYTHONUTF8="1")
env["PYTHONPATH"] = os.pathsep.join(str(package_path(p) / "src") for p in packages)
failed = []
for package in packages:
    tests = package_path(package) / "test"
    if tests.is_dir():
        print("\nPACKAGE:", package, flush=True)
        result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(tests), "-v"],
                                cwd=ROOT, env=env)
        if result.returncode:
            failed.append(package)
raise SystemExit(bool(failed))
