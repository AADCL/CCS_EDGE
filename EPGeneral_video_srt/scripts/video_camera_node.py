#!/usr/bin/env python3
"""Source/devel/install-space entrypoint for configured video capture."""
from pathlib import Path
import sys
source = Path(__file__).resolve().parents[1] / "src"
if (source / "epgeneral_video_srt").is_dir():
    sys.path.insert(0, str(source))
from epgeneral_video_srt.application import run

if __name__ == "__main__":
    raise SystemExit(run(camera=True))
