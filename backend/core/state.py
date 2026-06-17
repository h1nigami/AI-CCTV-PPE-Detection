import time
import threading
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import numpy as np
from backend.core.models import LogEntry
from backend.config import (
    APPROVAL_DURATION, PERSON_ID_GRID, MAX_LOG_SIZE,
    GESTURE_DISPLAY_DURATION, GESTURE_COOLDOWN,
    REID_SIM_THRESHOLD, REID_MAX_EMBEDDINGS, REID_GALLERY_PATH, REID_MAX_AGE_DAYS,
)

TRACK_EXPIRY = 60.0


class DetectionState:

    def __init__(self):
        self._lock = threading.Lock()
        self._reid_lock = threading.Lock()
        self.live_active = False
        self.camera_released = True
        self._log: List[LogEntry] = []
        self._approved: Dict[int, float] = {}
        self._gesture_until: float = 0
        self._last_gesture_time: Dict[int, float] = {}
        self._gallery = None
        self._track_to_global: Dict[Tuple[str, int], int] = {}
        self._track_last_seen: Dict[Tuple[str, int], float] = {}
        self._fallback_names: Dict[int, str] = {}

        # Статусы последнего залогированного события (cam_id+track_id → compact_status)
        self._last_logged_status: Dict[Tuple[str, int], str] = {}

    def init_gallery(self, gallery_path: Optional[Path] = None):
        from backend.reid.gallery import FaceGallery
        path = gallery_path or REID_GALLERY_PATH
        if isinstance(path, str):
            path = Path(path)
        self._gallery = FaceGallery(
            gallery_path=path,
            sim_threshold=REID_SIM_THRESHOLD,
            max_embeddings_per_id=REID_MAX_EMBEDDINGS,
        )

    @property
    def gallery(self):
        return self._gallery

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

    def _old_person_id(self, person_box, cam_id: str) -> Tuple:
        cx = int((person_box[0] + person_box[2]) / 2)
        cy = int((person_box[1] + person_box[3]) / 2)
        return (cam_id, cx // PERSON_ID_GRID, cy // PERSON_ID_GRID)

    def _assign_fallback_name(self) -> str:
        return f"Гость_{len(self._fallback_names) + 1}"

    def get_global_id(self, track_id: int, cam_id: str,
                      face_embedding: Optional[np.ndarray] = None,
                      quality: float = 0.0, person_box=None) -> int:
        key = (cam_id, track_id)
        now = time.time()
        with self._reid_lock:
            old_id = self._track_to_global.get(key)

            if face_embedding is not None and self._gallery is not None:
                gallery_id = self._gallery.match_or_register(
                    face_embedding, cam_id, quality=quality)
                if old_id is not None and old_id != gallery_id:
                    old_name = self._fallback_names.pop(old_id, None)
                    if old_name is not None:
                        info = self._gallery.get_info(gallery_id)
                        is_new = info and info['embedding_count'] <= 1
                        if is_new:
                            self._gallery.rename(gallery_id, old_name)
                            print(f"[ReID] Имя '{old_name}' перенесено с fallback {old_id} "
                                  f"на gallery {gallery_id} для трека {key}")
                        else:
                            print(f"[ReID] Track {key}: fallback {old_id} -> gallery {gallery_id}, "
                                  f"имя gallery '{info['name'] if info else '?'}' сохранено (existing)")
                    else:
                        print(f"[ReID] Track {key}: global_id {old_id} -> {gallery_id}")
                self._track_to_global[key] = gallery_id
                self._track_last_seen[key] = now
                return gallery_id

            if old_id is not None:
                self._track_last_seen[key] = now
                return old_id
            global_id = hash(key) & 0x7FFFFFFF
            if global_id not in self._fallback_names:
                name = self._assign_fallback_name()
                self._fallback_names[global_id] = name
                print(f"[ReID] Новый: {name} (ID={global_id}, камера {cam_id}, без лица)")
            self._track_to_global[key] = global_id
            self._track_last_seen[key] = now
            return global_id

    def cleanup_stale_tracks(self):
        now = time.time()
        with self._reid_lock:
            stale = [k for k, t in self._track_last_seen.items()
                     if now - t > TRACK_EXPIRY]
            for k in stale:
                del self._track_to_global[k]
                del self._track_last_seen[k]
            if stale:
                print(f"[ReID] Очищено {len(stale)} устаревших треков")

    def clear_tracks(self):
        with self._reid_lock:
            self._track_to_global.clear()
            self._track_last_seen.clear()
            self._fallback_names.clear()
            self._last_logged_status.clear()

    def get_person_name(self, global_id: int, cam_id: str, has_face: bool = False) -> str:
        name = self._fallback_names.get(global_id)
        if name:
            return name
        if self._gallery is not None:
            name = self._gallery.get_name(global_id)
            if not name.startswith("ID"):
                return name
        return f"#{global_id % 1000}"

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

    def set_gesture_detected(self):
        with self._lock:
            self._gesture_until = time.time() + GESTURE_DISPLAY_DURATION

    def is_gesture_active(self) -> bool:
        with self._lock:
            return time.time() < self._gesture_until

    def can_gesture(self, global_id: int) -> bool:
        with self._lock:
            last = self._last_gesture_time.get(global_id, 0)
            return time.time() - last >= GESTURE_COOLDOWN

    def set_gesture_time(self, global_id: int):
        with self._lock:
            self._last_gesture_time[global_id] = time.time()

    def is_status_changed(self, cam_id: str, track_id: int, compact_status: str) -> bool:
        """Проверить, изменился ли статус СИЗ для данного трека.
        Если статус совпадает с предыдущим — False, иначе True (и обновляем)."""
        key = (cam_id, track_id)
        with self._lock:
            prev = self._last_logged_status.get(key)
            if prev == compact_status:
                return False
            self._last_logged_status[key] = compact_status
            return True

    def clear_tracked_statuses(self):
        with self._lock:
            self._last_logged_status.clear()
