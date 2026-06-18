import time
import threading
from collections import deque
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import numpy as np
from backend.core.models import LogEntry
from backend.config import (
    APPROVAL_DURATION, PERSON_ID_GRID, MAX_LOG_SIZE,
    GESTURE_DISPLAY_DURATION, GESTURE_COOLDOWN,
    REID_SIM_THRESHOLD, REID_MAX_EMBEDDINGS, REID_GALLERY_PATH, REID_MAX_AGE_DAYS,
    REID_MIN_STORE_QUALITY, REID_STORE_INTERVAL, REID_STICKY_MARGIN, REID_STICKY_MIN,
    REID_DIVERSITY_MAX_SIM, VOICE_ALERT_COOLDOWN,
    REID_BODY_ENABLED, REID_BODY_MATCH_THRESHOLD, REID_BODY_MAX_EMBEDDINGS,
    REID_BODY_DIVERSITY_MAX_SIM, REID_BODY_STORE_INTERVAL,
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
        self._last_emb_store: Dict[Tuple[str, int], float] = {}
        self._last_body_store: Dict[Tuple[str, int], float] = {}
        self._fallback_names: Dict[int, str] = {}

        # Статусы последнего залогированного события (cam_id+track_id → compact_status)
        self._last_logged_status: Dict[Tuple[str, int], str] = {}

        # Очередь голосовых предупреждений (max 50) + кулдаун по камере
        self._voice_alerts: deque = deque(maxlen=50)
        self._voice_alert_last: Dict[str, float] = {}

        # Очередь UI-уведомлений (жест ОК / нехватка СИЗ и т.п.) — фронт поллит
        # /api/notifications и показывает их сверху. Структурированные (type/title/
        # sub), не парсятся из текста лога → корректны и не зависят от дедупа логов.
        self._notifications: deque = deque(maxlen=50)

    def init_gallery(self, gallery_path: Optional[Path] = None):
        from backend.reid.gallery import FaceGallery
        path = gallery_path or REID_GALLERY_PATH
        if isinstance(path, str):
            path = Path(path)
        self._gallery = FaceGallery(
            gallery_path=path,
            sim_threshold=REID_SIM_THRESHOLD,
            max_embeddings_per_id=REID_MAX_EMBEDDINGS,
            diversity_max_sim=REID_DIVERSITY_MAX_SIM,
            max_body_embeddings=REID_BODY_MAX_EMBEDDINGS,
            body_diversity_max_sim=REID_BODY_DIVERSITY_MAX_SIM,
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

    def _gid_active_on_other_track(self, gid: int, key: Tuple[str, int], now: float,
                                   window: float = 2.0) -> bool:
        """Назначена ли личность gid ДРУГОМУ недавно виденному треку. Защита от
        слияния двух разных людей в похожей одежде в одну личность при body-Re-ID
        (вызывать под self._reid_lock)."""
        for k, g in self._track_to_global.items():
            if k == key or g != gid:
                continue
            if now - self._track_last_seen.get(k, 0.0) <= window:
                return True
        return False

    def _store_body(self, gid: int, key: Tuple[str, int],
                    body_embedding: Optional[np.ndarray], now: float):
        """Дописать дескриптор тела к личности gid с троттлингом по треку.
        Вызывать под self._reid_lock; галерея потокобезопасна своим локом."""
        if (not REID_BODY_ENABLED or body_embedding is None
                or gid <= 0 or self._gallery is None):
            return
        if now - self._last_body_store.get(key, 0.0) < REID_BODY_STORE_INTERVAL:
            return
        self._last_body_store[key] = now
        self._gallery.add_body(gid, body_embedding, diverse=True)

    def get_global_id(self, track_id: int, cam_id: str,
                      face_embedding: Optional[np.ndarray] = None,
                      quality: float = 0.0, person_box=None,
                      body_embedding: Optional[np.ndarray] = None) -> int:
        key = (cam_id, track_id)
        now = time.time()
        with self._reid_lock:
            old_id = self._track_to_global.get(key)

            if face_embedding is not None and self._gallery is not None:
                # Троттлинг хранения: добавляем эмбеддинг в галерею не чаще
                # REID_STORE_INTERVAL сек с одного трека и только при приличном
                # качестве. Иначе один и тот же кадр (кэш детектора лиц)
                # вытесняет эталонные эмбеддинги → известное лицо перестаёт
                # матчиться → создаётся новый «Гость».
                should_store = (
                    quality >= REID_MIN_STORE_QUALITY
                    and now - self._last_emb_store.get(key, 0.0) >= REID_STORE_INTERVAL
                )

                # «Липкая» личность: если у трека уже есть валидная личность и
                # новое лицо её подтверждает (мягкий порог) — не пересматчиваем,
                # чтобы один плохой кадр не сбросил имя на нового «Гостя».
                if old_id is not None and self._gallery.has_id(old_id):
                    sticky = max(REID_STICKY_MIN, self._gallery.threshold_for(quality) - REID_STICKY_MARGIN)
                    if self._gallery.similarity(old_id, face_embedding) >= sticky:
                        self._gallery.add_observation(
                            old_id, cam_id, face_embedding, quality, store=should_store)
                        if should_store:
                            self._last_emb_store[key] = now
                        self._track_to_global[key] = old_id
                        self._track_last_seen[key] = now
                        # Запоминаем, как личность выглядит «со спины», пока лицо видно.
                        self._store_body(old_id, key, body_embedding, now)
                        return old_id

                gallery_id = self._gallery.match_or_register(
                    face_embedding, cam_id, quality=quality, store=should_store)
                if should_store:
                    self._last_emb_store[key] = now
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
                        old_info = self._gallery.get_info(old_id)
                        if old_info and old_info['embedding_count'] <= 1:
                            old_name = old_info['name']
                            self._gallery.merge_entries(old_id, gallery_id)
                            print(f"[ReID] Слит gallery {old_id} ({old_name}) -> "
                                  f"{gallery_id} для трека {key}")
                        else:
                            print(f"[ReID] Track {key}: global_id {old_id} -> {gallery_id}")
                self._track_to_global[key] = gallery_id
                self._track_last_seen[key] = now
                # Привязываем внешний вид (тело/одежду) к личности с известным лицом.
                self._store_body(gallery_id, key, body_embedding, now)
                return gallery_id

            # ── Лица нет (человек спиной/боком) ──────────────────────────────
            if old_id is not None:
                # У трека уже есть личность — держим её и продолжаем запоминать тело.
                self._store_body(old_id, key, body_embedding, now)
                self._track_last_seen[key] = now
                return old_id

            # Ни лица, ни личности у трека: пробуем опознать «со спины» по телу —
            # это восстанавливает имя для нового/переинициализированного трека.
            if (REID_BODY_ENABLED and body_embedding is not None
                    and self._gallery is not None):
                gid, sim = self._gallery.match_body(body_embedding, REID_BODY_MATCH_THRESHOLD)
                # Не приписываем личность, уже активную на другом треке (два разных
                # человека в похожей одежде не должны слиться в одно имя).
                if gid is not None and not self._gid_active_on_other_track(gid, key, now):
                    self._track_to_global[key] = gid
                    self._track_last_seen[key] = now
                    self._store_body(gid, key, body_embedding, now)
                    print(f"[ReID/body] Трек {key} опознан по телу как {gid} (sim={sim:.2f})")
                    return gid
            return 0

    def cleanup_stale_tracks(self):
        now = time.time()
        with self._reid_lock:
            stale = [k for k, t in self._track_last_seen.items()
                     if now - t > TRACK_EXPIRY]
            for k in stale:
                del self._track_to_global[k]
                del self._track_last_seen[k]
                self._last_emb_store.pop(k, None)
                self._last_body_store.pop(k, None)
            if stale:
                print(f"[ReID] Очищено {len(stale)} устаревших треков")

    def clear_tracks(self):
        with self._reid_lock:
            self._track_to_global.clear()
            self._track_last_seen.clear()
            self._last_emb_store.clear()
            self._last_body_store.clear()
            self._fallback_names.clear()
            self._last_logged_status.clear()

    def get_person_name(self, global_id: int, cam_id: str, has_face: bool = False) -> str:
        if global_id <= 0:
            return ""
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

    def push_voice_alert(self, cam_id: str, text: str) -> bool:
        """Добавить голосовое предупреждение в очередь с соблюдением кулдауна.
        Возвращает True, если предупреждение добавлено."""
        now = time.time()
        with self._lock:
            if now - self._voice_alert_last.get(cam_id, 0.0) < VOICE_ALERT_COOLDOWN:
                return False
            self._voice_alert_last[cam_id] = now
            self._voice_alerts.append({
                "id": f"{cam_id}_{now}",
                "cam_id": cam_id,
                "text": text,
                "timestamp": now,
            })
            return True

    def pop_voice_alert(self) -> Optional[dict]:
        """Извлечь и вернуть старейшее ожидающее предупреждение (или None)."""
        with self._lock:
            return self._voice_alerts.popleft() if self._voice_alerts else None

    def push_notification(self, ntype: str, title: str, sub: str = ""):
        """Добавить UI-уведомление (показывается сверху на фронте)."""
        with self._lock:
            self._notifications.append({
                "id": f"{ntype}_{time.time()}",
                "type": ntype,
                "title": title,
                "sub": sub,
                "timestamp": time.time(),
            })

    def pop_notifications(self) -> List[dict]:
        """Забрать все ожидающие уведомления (очередь очищается)."""
        with self._lock:
            items = list(self._notifications)
            self._notifications.clear()
            return items
