"""Concise operator output with persistent lifecycle and monitor evidence."""
import sys
import time
import traceback
from datetime import datetime


class SessionLog:
    def __init__(self):
        self.directory = None
        self.last = {}

    def attach(self, directory):
        self.directory = directory

    def record(self, message, filename="startup.log"):
        if self.directory is not None:
            with (self.directory / filename).open("a", encoding="utf-8") as stream:
                stream.write(datetime.now().astimezone().isoformat(timespec="seconds")
                             + " " + message + "\n")

    def report(self, level, message):
        self.record("[%s] %s" % (level, message))
        print("[%s] %s" % (level, message),
              file=sys.stderr if level == "ERROR" else sys.stdout, flush=True)

    def repeated(self, key, level, message, interval=30):
        now = time.monotonic()
        previous = self.last.get(key)
        if previous is None or previous[0] != message or now - previous[1] >= interval:
            self.report(level, message)
            self.last[key] = (message, now)

    def exception(self):
        self.record(traceback.format_exc(), "runtime_monitor.log")
