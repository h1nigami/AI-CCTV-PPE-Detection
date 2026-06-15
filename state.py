import time
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import numpy as np
from config import (
    APPROVAL_DURATION, PERSON_ID_GRID,
    MAX_LOG_SIZE, GESTURE_DISPLAY_DURATION, PRINT_DISPLAY_DURATION,
    REID_SIM_THRESHOLD, REID_MAX_EMBEDDINGS, REID_GALLERY_PATH,
    REID_MAX_AGE_DAYS
)


@dataclass
class LogEntry:
    id:        str
    timestamp: str
    message:   str
    category:  str
    cam_id:    str = "cam1"
    global_id: int = 0


class DetectionState:

    def __init__(self):
        self._lock           = threading.Lock()
        self._reid_lock      = threading.Lock()
        self.live_active     = False
        self.camera_released = True
        self._log:      List[LogEntry]         = []
        self._approved: Dict[int, float]       = {}  # global_id -> expire
        self._gesture_until: float             = 0
        self._print_until: float               = 0

        # Re-ID
        self._gallery = None
        self._track_to_global: Dict[Tuple[str, int], int] = {}  # (cam_id, track_id) -> global_id

    def init_gallery(self, gallery_path: Optional[Path] = None):
        if gallery_path is None:
            gallery_path = REID_GALLERY_PATH
        from reid import FaceGallery
        self._gallery = FaceGallery(
            gallery_path=gallery_path,
            sim_threshold=REID_SIM_THRESHOLD,
            max_embeddings_per_id=REID_MAX_EMBEDDINGS,
        )

    @property
    def gallery(self):
        return self._gallery

    # ── Лог ──────────────────────────────────

    def add_log(self, entry: LogEntry):
        with self._lock:
            self._log.append(entry)
            if len(self._log) > MAX_LOG_SIZE:
                self._log.pop(0)

    def get_log(self) -> List[LogEntry]:
        with self._lock:
            return list(self._log)

    def clear_log(self):
        with self._lock:
            self._log.clear()

    # ── Re-ID: global_person_id ───────────────

    def _old_person_id(self, person_box, cam_id: str) -> Tuple:
        cx = int((person_box[0] + person_box[2]) / 2)
        cy = int((person_box[1] + person_box[3]) / 2)
        return (cam_id, cx // PERSON_ID_GRID, cy // PERSON_ID_GRID)

    def get_global_id(self, track_id: int, cam_id: str,
                      face_embedding: Optional[np.ndarray] = None,
                      person_box=None) -> int:
        """
        Возвращает global_person_id.
        Сначала ищет в track->global маппинге (на случай без лица).
        Если есть face_embedding — матчит по галерее (кросс-камерный).
        """
        key = (cam_id, track_id)
        with self._reid_lock:
            if key in self._track_to_global:
                return self._track_to_global[key]

            if face_embedding is not None and self._gallery is not None:
                global_id = self._gallery.match_or_register(face_embedding, cam_id)
            else:
                # Фоллбэк через детерминированный hash
                global_id = hash(key) & 0x7FFFFFFF

            self._track_to_global[key] = global_id
            return global_id

    def clear_tracks(self):
        with self._reid_lock:
            self._track_to_global.clear()

    # ── Пропуска (по global_id, кросс-камерные) ──

    def is_approved(self, person_box, cam_id: str, global_id: Optional[int] = None) -> bool:
        gid = global_id
        if gid is None:
            pid = self._old_person_id(person_box, cam_id)
            gid = hash(pid) & 0x7FFFFFFF
        with self._lock:
            expire = self._approved.get(gid)
            if expire is None:
                return False
            if time.time() < expire:
                return True
            del self._approved[gid]
            return False

    def approve(self, person_box, cam_id: str, global_id: Optional[int] = None):
        gid = global_id
        if gid is None:
            pid = self._old_person_id(person_box, cam_id)
            gid = hash(pid) & 0x7FFFFFFF
        with self._lock:
            self._approved[gid] = time.time() + APPROVAL_DURATION
        print(f"Пропуск выдан: global_id={gid} на {APPROVAL_DURATION} сек.")

    def clear_approved(self):
        with self._lock:
            self._approved.clear()

    # ── Жест ──────────────────────────────────

    def set_gesture_detected(self):
        with self._lock:
            self._gesture_until = time.time() + GESTURE_DISPLAY_DURATION

    def is_gesture_active(self) -> bool:
        with self._lock:
            return time.time() < self._gesture_until

    # ── Печать ────────────────────────────────

    def set_print_triggered(self):
        with self._lock:
            self._print_until = time.time() + PRINT_DISPLAY_DURATION

    def is_print_active(self) -> bool:
        with self._lock:
            return time.time() < self._print_until