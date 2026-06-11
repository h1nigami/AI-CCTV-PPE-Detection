import cv2
import time
import threading
import subprocess
import numpy as np
import shutil
from config import CAMERAS


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
    """
    Захват камеры:
    - RTSP → GStreamer (если доступен, лучше для ARM64/Jetson) или ffmpeg subprocess
    - Локальные → cv2.VideoCapture
    """

    def __init__(self, buffer: FrameBuffer, source: str):
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
            self._thread.join(timeout=5)
        if self._cap:
            if isinstance(self._cap, subprocess.Popen):
                try:
                    self._cap.terminate()
                    self._cap.wait(timeout=3)
                except:
                    self._cap.kill()
            else:
                self._cap.release()
        self.buffer.clear()
        print("Захват камеры остановлен")

    def _is_rtsp(self):
        if isinstance(self.source, int):
            return False
        return self.source.startswith("rtsp://")

    def _has_nvidia_decoder(self):
        """Проверяет наличие NVIDIA аппаратного декодера (Jetson)"""
        try:
            return subprocess.run(
                ['gst-inspect-1.0', 'nvv4l2decoder'],
                capture_output=True, timeout=5
            ).returncode == 0
        except:
            return False

    def _loop(self):
        if self._is_rtsp():
            if self._has_nvidia_decoder():
                print(f"[{self.source}] NVIDIA декодер найден, пробуем GStreamer")
                if self._test_gstreamer():
                    self._loop_gstreamer()
                    return
                print(f"[{self.source}] GStreamer не сработал, ffmpeg")
            else:
                print(f"[{self.source}] используем ffmpeg subprocess")
            self._loop_ffmpeg()
        else:
            self._loop_opencv()

    # ── Проверка GStreamer ─────────────────────────────────────

    def _has_gstreamer(self):
        return shutil.which("gst-launch-1.0") is not None

    def _test_gstreamer(self):
        """Быстрый тест — может ли GStreamer открыть RTSP"""
        try:
            cmd = [
                'gst-launch-1.0', '-q',
                'rtspsrc', f'location={self.source}', 'latency=0', 'timeout=5000000', '!',
                'rtph264depay', '!', 'avdec_h264', '!',
                'videoconvert', '!', 'video/x-raw,format=BGR', '!',
                'fakesink', 'num-buffers=1'
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=10)
            if result.returncode != 0:
                # Если ошибка в плагинах — показываем stderr для отладки
                err = result.stderr.decode('utf-8', errors='replace')[-200:]
                print(f"[{self.source}] GStreamer тест: {err}")
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            print(f"[{self.source}] GStreamer тест таймаут (сеть недоступна)")
            return False
        except Exception as e:
            print(f"[{self.source}] GStreamer тест ошибка: {e}")
            return False

    # ── GStreamer pipeline ─────────────────────────────────────

    def _loop_gstreamer(self):
        """GStreamer → OpenCV через appsink"""
        # Определяем декодер в зависимости от платформы
        # На NVIDIA Jetson: nvv4l2decoder (аппаратное ускорение)
        # На x86/ARM: avdec_h264 (программный)

        decoder = self._detect_decoder()
        pipeline = (
            f'rtspsrc location={self.source} latency=0 buffer-mode=0 ! '
            f'rtph264depay ! h264parse ! {decoder} ! '
            f'videoconvert ! video/x-raw,format=BGR,width=1280,height=720 ! '
            f'appsink drop=true max-buffers=1 emit-signals=true sync=false'
        )

        self._cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        if not self._cap.isOpened():
            print(f"[{self.source}] GStreamer не открылся, пробуем ffmpeg")
            self._loop_ffmpeg()
            return

        print(f"[{self.source}] GStreamer запущен (decoder: {decoder})")
        fail_count = 0

        while self._running:
            try:
                ret, frame = self._cap.read()
                if not ret or frame is None:
                    fail_count += 1
                    if fail_count > 10:
                        print(f"[{self.source}] GStreamer потеря кадров, переподключение")
                        self._cap.release()
                        time.sleep(2)
                        self._cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
                        if not self._cap.isOpened():
                            break
                        fail_count = 0
                    time.sleep(0.5)
                    continue

                fail_count = 0
                self.buffer.write(frame)

            except Exception as e:
                print(f"[{self.source}] GStreamer ошибка: {e}")
                time.sleep(1)

    def _detect_decoder(self):
        """Определяет лучший доступный H.264 декодер"""
        # Проверяем NVIDIA Jetson
        try:
            result = subprocess.run(
                ['gst-inspect-1.0', 'nvv4l2decoder'],
                capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return 'nvv4l2decoder'
        except:
            pass

        # Проверяем VAAPI (Intel/AMD)
        try:
            result = subprocess.run(
                ['gst-inspect-1.0', 'vaapih264dec'],
                capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return 'vaapih264dec'
        except:
            pass

        # Программный декодер (работает везде)
        return 'avdec_h264'

    # ── FFmpeg subprocess ──────────────────────────────────────

    def _stop_ffmpeg(self):
        """Останавливает текущий ffmpeg процесс, если есть"""
        if self._cap is not None and isinstance(self._cap, subprocess.Popen):
            try:
                self._cap.terminate()
                self._cap.wait(timeout=3)
            except:
                try:
                    self._cap.kill()
                except:
                    pass
        self._cap = None

    def _loop_ffmpeg(self):
        """Читает raw RGB кадры из stdout ffmpeg"""
        fail_count = 0

        while self._running:
            try:
                self._stop_ffmpeg()
                proc = self._start_ffmpeg()
                if proc is None:
                    fail_count += 1
                    wait = min(30, 2 ** min(fail_count, 5))
                    print(f"[{self.source}] ffmpeg не запустился, повтор через {wait}с")
                    time.sleep(wait)
                    continue

                self._cap = proc
                fail_count = 0
                w, h = 1280, 720
                frame_size = w * h * 3

                while self._running:
                    raw = proc.stdout.read(frame_size)

                    if len(raw) < frame_size:
                        if proc.poll() is not None:
                            err = proc.stderr.read(512).decode('utf-8', errors='replace')
                            print(f"[{self.source}] ffmpeg упал (rc={proc.returncode}): {err[-200:]}")
                            break
                        time.sleep(0.05)
                        continue

                    frame = np.frombuffer(raw, dtype=np.uint8).reshape((h, w, 3))

                    if frame.mean() < 3:
                        continue

                    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                    self.buffer.write(frame_bgr)

            except Exception as e:
                print(f"[{self.source}] ошибка ffmpeg: {e}")
                fail_count += 1
                time.sleep(2)

    def _start_ffmpeg(self):
        """Запускает ffmpeg subprocess для RTSP"""
        cmd = [
            'ffmpeg',
            '-rtsp_transport', 'tcp',
            '-stimeout', '5000000',
            '-i', self.source,
            '-an',
            '-f', 'rawvideo',
            '-pix_fmt', 'rgb24',
            '-s', '1280x720',
            '-r', '15',
            '-loglevel', 'warning',
            '-'
        ]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=10**8
            )
            # Ждём немного и проверяем что процесс жив
            time.sleep(2)
            if proc.poll() is not None:
                err = proc.stderr.read(1024).decode('utf-8', errors='replace')
                print(f"[{self.source}] ffmpeg упал сразу: {err[-300:]}")
                return None
            print(f"[{self.source}] ffmpeg запущен (PID {proc.pid})")
            return proc
        except Exception as e:
            print(f"[{self.source}] ошибка запуска ffmpeg: {e}")
            return None

    # ── Локальная камера через OpenCV ─────────────────────────

    def _loop_opencv(self):
        self._cap = cv2.VideoCapture(self.source)
        if not self._cap.isOpened():
            print(f"Не удалось открыть камеру: {self.source}")
            self._running = False
            return

        fail_count = 0
        while self._running:
            try:
                success, frame = self._cap.read()
                if not success:
                    fail_count += 1
                    print(f"Камера {self.source} — не удалось прочитать кадр ({fail_count})")
                    if fail_count > 5:
                        print(f"Камера {self.source} — переподключение...")
                        self._cap.release()
                        time.sleep(2)
                        self._cap = cv2.VideoCapture(self.source)
                        fail_count = 0
                    else:
                        time.sleep(0.5)
                    continue

                fail_count = 0
                self.buffer.write(frame)

            except Exception as e:
                print(f"Камера {self.source} — ошибка: {e}")
                time.sleep(1)

        if self._cap:
            self._cap.release()

    @property
    def is_running(self):
        return self._running
