"""Bounded preview data and a shared rolling-window HTTP body budget."""
from collections import deque
import threading
import time

import numpy as np


def pcd_header(count):
    return (
        "# .PCD v0.7\nVERSION 0.7\nFIELDS x y z\nSIZE 4 4 4\n"
        "TYPE F F F\nCOUNT 1 1 1\nWIDTH %d\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\n"
        "POINTS %d\nDATA binary\n" % (count, count)
    ).encode("ascii")


def bounded_preview(points, voxel_size, byte_limit):
    """Keep spatially ordered voxel representatives within the actual PCD budget."""
    points = np.asarray(points, dtype=np.float32)
    points = points[np.isfinite(points).all(axis=1)]
    if not len(points):
        return points.reshape((-1, 3))
    keys = np.floor(points.astype(np.float64) / voxel_size).astype(np.int64)
    _, indices = np.unique(keys, axis=0, return_index=True)
    points = points[indices]  # np.unique orders by voxel key, not scan acquisition order.
    count = min(len(points), byte_limit // 12)
    while count and len(pcd_header(count)) + count * 12 > byte_limit:
        count -= 1
    if count < len(points):
        points = points[np.linspace(0, len(points) - 1, count, dtype=np.int64)]
    return np.ascontiguousarray(points, dtype="<f4")


class PreviewByteBudget(object):
    """Serialize small writes; charge at completion so a slow write cannot free budget early."""
    def __init__(self, maximum=500000, clock=time.monotonic):
        self.maximum = int(maximum)
        self.clock = clock
        self.lock = threading.Lock()
        self.writes = deque()
        self.used = 0
        self.closed = threading.Event()

    def write(self, stream, data):
        if len(data) > self.maximum:
            raise ValueError("preview write exceeds one-second budget")
        while not self.closed.is_set():
            with self.lock:
                now = self.clock()
                while self.writes and now - self.writes[0][0] >= 1.0:
                    _, count = self.writes.popleft()
                    self.used -= count
                if self.used + len(data) <= self.maximum:
                    # Count failed/partial writes conservatively too.
                    try:
                        stream.write(data)
                    finally:
                        self.writes.append((self.clock(), len(data)))
                        self.used += len(data)
                    return
                delay = max(0.001, 1.0 - (now - self.writes[0][0]))
            self.closed.wait(min(delay, 0.05))
        raise OSError("preview server is closing")

    def close(self):
        self.closed.set()
