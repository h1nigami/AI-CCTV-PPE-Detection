import threading
import time
import numpy as np


class FrameBuffer:
    def __init__(self):
        self._frame = None
        self._lock = threading.Lock()
        self._event = threading.Event()
        self._ts = 0.0  # время последней записи кадра (для детекта «зависания»)

    def write(self, frame):
        with self._lock:
            self._frame = frame.copy()
            self._ts = time.time()
        self._event.set()

    def read(self):
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def age(self) -> float:
        """Секунд с последней записи кадра. Большой возраст = камера «отвалилась»
        (capture не пишет новые кадры). 1e9, если кадров ещё не было."""
        with self._lock:
            return (time.time() - self._ts) if self._ts else 1e9

    def wait(self, timeout=1.0):
        self._event.wait(timeout)
        self._event.clear()

    def clear(self):
        with self._lock:
            self._frame = None
            self._ts = 0.0
