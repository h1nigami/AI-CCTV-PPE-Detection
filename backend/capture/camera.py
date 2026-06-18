import cv2
import time
import threading
import subprocess
import numpy as np
import shutil
from backend.capture.buffer import FrameBuffer


class CameraCapture:

    def __init__(self, buffer: FrameBuffer, source: str):
        self.source = source
        self.buffer = buffer
        self._running = False
        self._thread = None
        self._cap = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("Захват камеры запущен")

    def stop(self):
        self._running = False
        # Поток захвата висит в блокирующем read() (subprocess.stdout / cv2)
        # и не проверяет _running, поэтому сначала рвём источник — это
        # разблокирует read, — и только потом join. Иначе join выжидает
        # весь таймаут (по 5с на камеру) и /stop тормозит.
        self._unblock_capture()
        if self._thread:
            self._thread.join(timeout=5)
        # Цикл переподключения мог создать новый процесс уже после первого
        # terminate — добиваем его.
        self._unblock_capture()
        self.buffer.clear()
        print("Захват камеры остановлен")

    def _unblock_capture(self):
        cap = self._cap
        if cap is None:
            return
        if isinstance(cap, subprocess.Popen):
            try:
                cap.terminate()
                cap.wait(timeout=3)
            except Exception:
                try:
                    cap.kill()
                except Exception:
                    pass
        else:
            try:
                cap.release()
            except Exception:
                pass

    def _is_rtsp(self):
        if isinstance(self.source, int):
            return False
        return self.source.startswith("rtsp://")

    def _has_nvidia_decoder(self):
        try:
            return subprocess.run(
                ['gst-inspect-1.0', 'nvv4l2decoder'],
                capture_output=True, timeout=5
            ).returncode == 0
        except:
            return False

    def _has_ffmpeg(self):
        return shutil.which("ffmpeg") is not None

    def _loop(self):
        if self._is_rtsp():
            if self._has_nvidia_decoder():
                print(f"[{self.source}] NVIDIA декодер найден, пробуем GStreamer")
                if self._test_gstreamer():
                    self._loop_gstreamer()
                    return
                print(f"[{self.source}] GStreamer не сработал, пробуем ffmpeg/OpenCV")
            if self._has_ffmpeg():
                print(f"[{self.source}] используем ffmpeg subprocess")
                self._loop_ffmpeg()
            else:
                print(f"[{self.source}] ffmpeg не найден, пробуем OpenCV для RTSP")
                self._loop_opencv()
        else:
            self._loop_opencv()

    def _has_gstreamer(self):
        return shutil.which("gst-launch-1.0") is not None

    def _test_gstreamer(self):
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
                err = result.stderr.decode('utf-8', errors='replace')[-200:]
                print(f"[{self.source}] GStreamer тест: {err}")
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            print(f"[{self.source}] GStreamer тест таймаут (сеть недоступна)")
            return False
        except Exception as e:
            print(f"[{self.source}] GStreamer тест ошибка: {e}")
            return False

    def _loop_gstreamer(self):
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
        try:
            result = subprocess.run(
                ['gst-inspect-1.0', 'nvv4l2decoder'],
                capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return 'nvv4l2decoder'
        except:
            pass
        try:
            result = subprocess.run(
                ['gst-inspect-1.0', 'vaapih264dec'],
                capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return 'vaapih264dec'
        except:
            pass
        return 'avdec_h264'

    def _stop_ffmpeg(self):
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
        cmd = [
            'ffmpeg',
            '-rtsp_transport', 'tcp',
            # ВАЖНО: для RTSP-источника опция -timeout трактуется ffmpeg как
            # listen-timeout (серверный режим) → "Unable to open RTSP for listening".
            # Клиентский таймаут сокета задаётся через -stimeout (микросекунды).
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
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=10 ** 8)
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

    def _open_opencv(self):
        # Для RTSP открываем через FFMPEG-бэкенд с таймаутами, чтобы
        # зависший поток не блокировал read() навсегда (иначе stop() ждёт
        # полный join-таймаут). Локальные камеры — дефолтный бэкенд.
        if self._is_rtsp():
            cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
            try:
                cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
                cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)
            except Exception:
                pass
            return cap
        return cv2.VideoCapture(self.source)

    def _loop_opencv(self):
        self._cap = self._open_opencv()
        if not self._cap.isOpened():
            print(f"Не удалось открыть камеру через OpenCV: {self.source}")
            print(f"[{self.source}] пробуем ffmpeg subprocess")
            self._loop_ffmpeg_local()
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
                        self._cap = self._open_opencv()
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

    def _loop_ffmpeg_local(self):
        fail_count = 0
        while self._running:
            try:
                self._stop_ffmpeg()
                device = f"/dev/video{self.source}" if isinstance(self.source, int) else self.source
                cmd = [
                    'ffmpeg',
                    '-f', 'v4l2',
                    '-input_format', 'mjpeg',
                    '-video_size', '1280x720',
                    '-i', device,
                    '-an',
                    '-f', 'rawvideo',
                    '-pix_fmt', 'rgb24',
                    '-s', '1280x720',
                    '-r', '15',
                    '-loglevel', 'warning',
                    '-'
                ]
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=10 ** 8)
                time.sleep(2)
                if proc.poll() is not None:
                    err = proc.stderr.read(1024).decode('utf-8', errors='replace')
                    print(f"[{self.source}] ffmpeg упал сразу: {err[-300:]}")
                    fail_count += 1
                    wait = min(30, 2 ** min(fail_count, 5))
                    time.sleep(wait)
                    continue
                print(f"[{self.source}] ffmpeg v4l2 запущен (PID {proc.pid})")
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
                print(f"[{self.source}] ошибка ffmpeg local: {e}")
                fail_count += 1
                time.sleep(2)

    @property
    def is_running(self):
        return self._running
