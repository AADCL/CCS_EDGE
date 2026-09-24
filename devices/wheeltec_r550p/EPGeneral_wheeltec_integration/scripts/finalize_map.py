#!/usr/bin/env python3
"""Run the native converter with explicit CCS-only input/output paths."""
import os
import re
import subprocess
import sys
from pathlib import Path

if __name__ == '__main__':
    if len(sys.argv) not in (2, 3) or not re.fullmatch(r'[0-9]{8}_[0-9]{6}', sys.argv[1]):
        raise SystemExit('expected mapping session YYYYMMDD_HHMMSS [--replace-raw]')
    if len(sys.argv) == 3 and sys.argv[2] != '--replace-raw':
        raise SystemExit('unsupported argument')
    root = Path(os.environ.get('CCS_EDGE_WORKSPACE', '/home/nrc19/ccs_edge_ws')).resolve()
    directory = root / 'maps/mapping' / sys.argv[1]
    if os.path.commonpath([str(directory.resolve()), str(root)]) != str(root):
        raise SystemExit('map directory escapes CCS workspace')
    cmd = ['rosrun', 'wheeltec_map_tools', 'finalize_map.py', sys.argv[1],
           '--source', str(directory / 'filtered_camera_init.pcd'), '--output-dir', str(directory)]
    cmd.extend(sys.argv[2:])
    raise SystemExit(subprocess.call(cmd))
