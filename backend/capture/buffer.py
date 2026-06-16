import threading
import numpy as np


class FrameBuffer:
    def __init__(self):
        self._frame = None
        self._lock = threading.Lock()
        self._event = threading.Event()

    def write(self, frame):
        with self._lock:
            self._frame = frame.copy()
        self._event.set()

    def read(self):
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def wait(self, timeout=1.0):
        self._event.wait(timeout)
        self._event.clear()

    def clear(self):
        with self._lock:
            self._frame = None
