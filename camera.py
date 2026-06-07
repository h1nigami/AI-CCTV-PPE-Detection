import cv2
import time
import threading
from config import CAMERA_SOURCE


class FrameBuffer:
    """Потокобезопасный буфер последнего кадра"""

    def __init__(self):
        self._frame = None
        self._lock  = threading.Lock()
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


class CameraCapture:
    """Единственный поток который делает cap.read()"""

    def __init__(self, buffer: FrameBuffer, source: str = CAMERA_SOURCE):
        self.source   = source
        self.buffer   = buffer
        self._running = False
        self._thread  = None
        self._cap     = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("Захват камеры запущен")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        if self._cap:
            self._cap.release()
        self.buffer.clear()
        print("Захват камеры остановлен")

    def _loop(self):
        self._cap = cv2.VideoCapture(self.source)
        if not self._cap.isOpened():
            print(f"Не удалось открыть камеру: {self.source}")
            self._running = False
            return

        while self._running:
            success, frame = self._cap.read()
            if not success:
                print("Камера недоступна, переподключение...")
                time.sleep(2)
                self._cap.release()
                self._cap = cv2.VideoCapture(self.source)
                continue
            self.buffer.write(frame)

        self._cap.release()

    @property
    def is_running(self):
        return self._running