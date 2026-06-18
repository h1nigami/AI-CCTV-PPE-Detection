"""NVR: непрерывная сегментная запись архива (видеорегистратор).

В отличие от event-клипов (`main.py::_finalize_recording`, только нарушения),
здесь пишется НЕПРЕРЫВНЫЙ архив, чтобы можно было отмотать на любой момент.

Архитектура:
  • `SegmentRecorder` — по экземпляру на камеру: ffmpeg режет RTSP-поток на
    сегменты `RECORD_SEGMENT_SEC` секунд через `-c copy` (перепаковка без
    перекодирования → ~0% CPU). Файлы: <RECORD_DIR>/<cam>/recordings/ГГГГ/ММ/ДД/ЧЧ.ММ.СС.mp4
  • Индексатор — сканирует завершённые сегменты и пишет ряд в таблицу Recording
    (start/end/size/has_motion), чтобы timeline-API находил нужный файл.
  • `RetentionCleaner` — фоном удаляет старое по сроку (`RECORD_RETAIN_DAYS`),
    в режиме "motion" — сегменты без движения, и при переполнении диска
    (`RECORD_MAX_DISK_PERCENT`).
  • `RecordingManager` — синглтон, поднимает/останавливает рекордеры и
    чистильщик вместе с детекцией; принимает сигналы движения (`note_motion`).

Многое вынесено в чистые функции (build_ffmpeg_segment_cmd, parse_segment_start,
plan_deletions) — их легко юнит-тестить без ffmpeg/RTSP/диска.
"""
from __future__ import annotations
import os
import shutil
import subprocess
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from backend.db.engine import get_session
from backend.db.models import Recording
from backend.config import (
    RECORD_DIR, RECORD_MODE, RECORD_SEGMENT_SEC, RECORD_RETAIN_DAYS,
    RECORD_MAX_DISK_PERCENT, RECORD_CLEAN_INTERVAL_SEC, RECORD_MOTION_GRACE_SEC,
)

# Шаблон имени сегмента для ffmpeg -strftime (внутри каталога recordings камеры).
_SEGMENT_STRFTIME = "%Y/%m/%d/%H.%M.%S.mp4"


# ── Чистые помощники (без IO — легко тестировать) ───────────────────────────
def camera_recordings_dir(cam_id: str, base_dir: Path | str = None) -> Path:
    base = Path(base_dir) if base_dir is not None else RECORD_DIR
    return base / cam_id / "recordings"


def build_ffmpeg_segment_cmd(source: str, out_dir: Path | str,
                             segment_sec: int = RECORD_SEGMENT_SEC) -> list[str]:
    """Команда ffmpeg для сегментной записи RTSP через `-c copy` (без CPU).

    `-reset_timestamps 1` + `-strftime 1` → каждый сегмент с именем по времени
    старта. `-c copy` режет по ближайшему keyframe, поэтому реальная длина
    сегмента «плавает» вокруг segment_sec (зависит от GOP камеры) — это норма.
    """
    out_template = str(Path(out_dir) / _SEGMENT_STRFTIME)
    return [
        "ffmpeg", "-nostdin",
        "-rtsp_transport", "tcp",
        "-stimeout", "5000000",        # клиентский таймаут сокета (мкс), НЕ -timeout
        "-i", str(source),
        "-c", "copy", "-an",
        "-f", "segment",
        "-segment_time", str(segment_sec),
        "-segment_format", "mp4",
        "-reset_timestamps", "1",
        "-strftime", "1",
        "-loglevel", "warning",
        out_template,
    ]


def parse_segment_start(path: Path | str) -> Optional[float]:
    """Unix-время начала сегмента из имени .../ГГГГ/ММ/ДД/ЧЧ.ММ.СС.mp4.

    Время локальное (ffmpeg -strftime пишет в локальной TZ). Вернёт None, если
    путь не разбирается."""
    p = Path(path)
    parts = p.parts
    if len(parts) < 4:
        return None
    try:
        year, month, day = int(parts[-4]), int(parts[-3]), int(parts[-2])
        hh, mm, ss = p.stem.split(".")
        dt = datetime(year, month, day, int(hh), int(mm), int(ss))
        return time.mktime(dt.timetuple())
    except (ValueError, IndexError):
        return None


def plan_deletions(recordings: list, now: float, *, mode: str = RECORD_MODE,
                   retain_days: float = RECORD_RETAIN_DAYS,
                   motion_grace_sec: float = RECORD_MOTION_GRACE_SEC,
                   disk_percent: float = 0.0,
                   max_disk_percent: float = RECORD_MAX_DISK_PERCENT) -> list:
    """Чистая логика retention: какие сегменты удалить.

    `recordings` — список объектов с полями start_time/end_time/has_motion/
    size_bytes (Recording или совместимый). Возвращает подмножество на удаление.
    Правила:
      1. старше retain_days — всегда;
      2. в режиме "motion": без движения и старше motion_grace — удаляем;
      3. если диск занят выше порога — удаляем старейшие, пока не уложимся.
    """
    recs = sorted(recordings, key=lambda r: r.start_time)
    doomed = []
    doomed_ids = set()

    def mark(r):
        if id(r) not in doomed_ids:
            doomed.append(r)
            doomed_ids.add(id(r))

    # Защита от потери данных: motion-прунинг применяем только к камерам, у
    # которых ЕСТЬ хотя бы один сегмент с движением (доказательство, что
    # motion-пайплайн жив). Если камера вообще не репортит движение (детекция
    # выключена/сломана) — не удаляем её сегменты по motion-правилу, остаётся
    # только удаление по сроку.
    cams_with_motion = {r.camera_id for r in recs if getattr(r, "has_motion", False)}

    cutoff = now - retain_days * 86400.0
    for r in recs:
        if r.start_time < cutoff:
            mark(r)
        elif mode == "motion" and not getattr(r, "has_motion", False) \
                and r.camera_id in cams_with_motion \
                and (now - r.end_time) > motion_grace_sec:
            mark(r)

    # Переполнение диска: удаляем старейшие из ещё живых, пока выше порога.
    if disk_percent > max_disk_percent:
        # Грубая модель: считаем, что удаление каждого сегмента снижает занятость
        # пропорционально его размеру относительно общего объёма архива.
        total = sum(max(0, getattr(r, "size_bytes", 0)) for r in recs) or 1
        freed_ratio = 0.0
        # доля диска, занятая архивом, неизвестна; уменьшаем эвристически по
        # размеру удаляемого относительно архива, масштабируя на текущую занятость.
        for r in recs:
            if disk_percent - freed_ratio * disk_percent <= max_disk_percent:
                break
            if id(r) in doomed_ids:
                continue
            mark(r)
            freed_ratio += max(0, getattr(r, "size_bytes", 0)) / total
    return doomed


# ── Индексация сегментов в БД ───────────────────────────────────────────────
def index_segment_file(cam_id: str, path: Path | str, has_motion: bool,
                       session=None) -> Optional[str]:
    """Записать ряд Recording для завершённого файла-сегмента.

    end_time берём по mtime файла (момент последней записи ≈ конец сегмента),
    duration = end - start. Идемпотентно: если путь уже в БД — пропускаем."""
    path = Path(path)
    start = parse_segment_start(path)
    if start is None or not path.exists():
        return None
    own_session = session is None
    session = session or get_session()
    try:
        existing = session.query(Recording).filter(
            Recording.path == str(path)).first()
        if existing is not None:
            return existing.id
        end = path.stat().st_mtime
        size = path.stat().st_size
        rec_id = str(uuid.uuid4())
        session.add(Recording(
            id=rec_id, camera_id=cam_id, path=str(path),
            start_time=start, end_time=max(end, start),
            duration=max(0.0, end - start), size_bytes=int(size),
            has_motion=bool(has_motion),
        ))
        session.commit()
        return rec_id
    except Exception as exc:
        session.rollback()
        print(f"[NVR] Ошибка индексации {path}: {exc}")
        return None
    finally:
        if own_session:
            session.close()


# ── Рекордер одной камеры ───────────────────────────────────────────────────
class SegmentRecorder:
    """Управляет ffmpeg-сегментатором одной камеры (запуск/перезапуск/останов)."""

    def __init__(self, cam_id: str, source: str, base_dir: Path | str = None,
                 segment_sec: int = RECORD_SEGMENT_SEC):
        self.cam_id = cam_id
        self.source = source
        self.base_dir = Path(base_dir) if base_dir is not None else RECORD_DIR
        self.segment_sec = segment_sec
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._proc: Optional[subprocess.Popen] = None

    @property
    def out_dir(self) -> Path:
        return camera_recordings_dir(self.cam_id, self.base_dir)

    def start(self):
        if self._running:
            return
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"[NVR] Запись запущена: {self.cam_id} -> {self.out_dir}")

    def stop(self):
        self._running = False
        self._terminate_proc()  # рвём процесс ДО join (read блокирующий)
        if self._thread:
            self._thread.join(timeout=5)
        self._terminate_proc()
        print(f"[NVR] Запись остановлена: {self.cam_id}")

    def _terminate_proc(self):
        proc = self._proc
        if proc is None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def _loop(self):
        if not shutil.which("ffmpeg"):
            print(f"[NVR] ffmpeg не найден — запись {self.cam_id} невозможна")
            return
        fail = 0
        while self._running:
            try:
                cmd = build_ffmpeg_segment_cmd(self.source, self.out_dir, self.segment_sec)
                self._proc = subprocess.Popen(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                fail = 0
                # Ждём завершения процесса (он живёт, пока пишет сегменты).
                while self._running and self._proc.poll() is None:
                    time.sleep(0.5)
                if self._running and self._proc.poll() is not None:
                    err = (self._proc.stderr.read(512).decode("utf-8", "replace")
                           if self._proc.stderr else "")
                    fail += 1
                    wait = min(30, 2 ** min(fail, 5))
                    print(f"[NVR] ffmpeg {self.cam_id} упал (rc={self._proc.returncode}): "
                          f"{err[-200:]}; повтор через {wait}с")
                    time.sleep(wait)
            except Exception as exc:
                fail += 1
                print(f"[NVR] Ошибка рекордера {self.cam_id}: {exc}")
                time.sleep(min(30, 2 ** min(fail, 5)))

    @property
    def is_running(self) -> bool:
        return self._running


# ── Менеджер записи (синглтон) ──────────────────────────────────────────────
class RecordingManager:
    def __init__(self, base_dir: Path | str = None):
        self.base_dir = Path(base_dir) if base_dir is not None else RECORD_DIR
        self._recorders: dict[str, SegmentRecorder] = {}
        # Метки времени движения по камере (для пометки has_motion сегментов).
        self._motion_ts: dict[str, deque] = defaultdict(lambda: deque(maxlen=5000))
        self._lock = threading.Lock()
        self._active = False
        self._bg_thread: Optional[threading.Thread] = None

    # — сигнал движения из потока детекции —
    def note_motion(self, cam_id: str, ts: float = None):
        ts = ts if ts is not None else time.time()
        with self._lock:
            self._motion_ts[cam_id].append(ts)

    def _motion_in_range(self, cam_id: str, t0: float, t1: float) -> bool:
        with self._lock:
            return any(t0 <= t <= t1 for t in self._motion_ts.get(cam_id, ()))

    # — жизненный цикл —
    def start_all(self, cameras: dict):
        if self._active:
            return
        self._active = True
        for cam_id, source in cameras.items():
            self._start_camera(cam_id, source)
        self._bg_thread = threading.Thread(target=self._background_loop, daemon=True)
        self._bg_thread.start()
        print(f"[NVR] Менеджер записи запущен ({len(self._recorders)} камер, режим={RECORD_MODE})")

    def _start_camera(self, cam_id: str, source):
        if cam_id in self._recorders:
            return
        # Запись имеет смысл только для RTSP/файловых источников (строка).
        if not isinstance(source, str):
            print(f"[NVR] {cam_id}: источник не RTSP ({source!r}) — запись пропущена")
            return
        rec = SegmentRecorder(cam_id, source, self.base_dir)
        rec.start()
        self._recorders[cam_id] = rec

    def add_camera(self, cam_id: str, source):
        if self._active:
            self._start_camera(cam_id, source)

    def remove_camera(self, cam_id: str):
        rec = self._recorders.pop(cam_id, None)
        if rec is not None:
            rec.stop()

    def stop_all(self):
        self._active = False
        for rec in list(self._recorders.values()):
            rec.stop()
        self._recorders.clear()
        if self._bg_thread:
            self._bg_thread.join(timeout=2)
        print("[NVR] Менеджер записи остановлен")

    # — фоновый цикл: индексация новых сегментов + retention —
    def _background_loop(self):
        last_clean = 0.0
        while self._active:
            try:
                self.index_new_segments()
            except Exception as exc:
                print(f"[NVR] Ошибка индексации: {exc}")
            now = time.time()
            if now - last_clean >= RECORD_CLEAN_INTERVAL_SEC:
                try:
                    self.run_cleanup()
                except Exception as exc:
                    print(f"[NVR] Ошибка retention: {exc}")
                last_clean = now
            slept = 0.0
            while self._active and slept < 10:
                time.sleep(0.5)
                slept += 0.5

    def index_new_segments(self, now: float = None):
        """Найти завершённые .mp4-сегменты, ещё не попавшие в БД, и проиндексировать."""
        now = now if now is not None else time.time()
        for cam_id in list(self._recorders.keys()):
            rec_dir = camera_recordings_dir(cam_id, self.base_dir)
            if not rec_dir.exists():
                continue
            for path in rec_dir.rglob("*.mp4"):
                try:
                    # Файл, изменённый только что, ffmpeg ещё пишет — пропускаем.
                    if now - path.stat().st_mtime < 5:
                        continue
                except OSError:
                    continue
                start = parse_segment_start(path)
                if start is None:
                    continue
                end = path.stat().st_mtime
                has_motion = self._motion_in_range(cam_id, start, end)
                index_segment_file(cam_id, path, has_motion)

    def run_cleanup(self, now: float = None, disk_percent: float = None):
        now = now if now is not None else time.time()
        if disk_percent is None:
            disk_percent = _disk_percent(self.base_dir)
        session = get_session()
        try:
            recs = session.query(Recording).all()
            doomed = plan_deletions(recs, now, disk_percent=disk_percent)
            for r in doomed:
                try:
                    Path(r.path).unlink(missing_ok=True)
                except Exception:
                    pass
                session.delete(r)
            if doomed:
                session.commit()
                print(f"[NVR] Retention: удалено {len(doomed)} сегментов")
        except Exception as exc:
            session.rollback()
            print(f"[NVR] Ошибка очистки: {exc}")
        finally:
            session.close()


def _disk_percent(path: Path) -> float:
    try:
        path = Path(path)
        target = path if path.exists() else path.parent
        usage = shutil.disk_usage(str(target))
        return usage.used / usage.total * 100.0
    except Exception:
        return 0.0


_manager: Optional[RecordingManager] = None
_manager_lock = threading.Lock()


def get_recording_manager() -> RecordingManager:
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = RecordingManager()
    return _manager
