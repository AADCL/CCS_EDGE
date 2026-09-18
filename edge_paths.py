"""Repository paths shared by staging and standalone checks (Python 3.8+)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LAYOUT = json.loads((ROOT / "edge-layout.json").read_text(encoding="utf-8"))

def package_path(name):
    if name in LAYOUT["common_packages"]:
        return ROOT / name
    return ROOT / LAYOUT["special_packages"][name]

def profile_path(name):
    return ROOT / LAYOUT["profiles"][name]["path"]

def packages_for(profile):
    return LAYOUT["common_packages"] + LAYOUT["profiles"][profile]["additional_packages"]
