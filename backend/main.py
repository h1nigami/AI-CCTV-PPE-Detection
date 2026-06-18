from __future__ import annotations
import io
import os
import subprocess
import cv2
import threading
import time
import traceback
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional
from ultralytics import YOLO
import torch

cv2.INTER_NEAREST_EXACT = getattr(cv2, 'INTER_NEAREST_EXACT', cv2.INTER_NEAREST)

from backend.config import (
    MODEL_PATH, POSE_MODEL_PATH, CLASS_NAMES, CAMERAS, CONF_THRESH,
    REID_GALLERY_PATH, REID_DET_SIZE, REID_FRAME_SKIP, REID_MAX_AGE_DAYS,
    EVENT_PRE_FRAMES, EVENT_POST_FRAMES, EVENT_MAX_FRAMES, EVENT_CLIP_FPS,
    VIOLATION_LOGS_DIR, get_camera_config, VOICE_ALERT_COOLDOWN,
    MOTION_DETECTION_ENABLED, MOTION_THRESHOLD, MOTION_MIN_AREA,
    MOTION_COOLDOWN_FRAMES, MQTT_HEARTBEAT_INTERVAL,
    RECORD_ENABLED, RECORD_MODE, PPE_REQUIRED_DEFAULT,
)
from backend.core.metrics import get_metrics
from backend.detection.motion import MotionDetector
from backend.mqtt.publisher import get_publisher
from backend.recorder import get_recording_manager
from backend.zones import get_zones, apply_masks, in_any_danger_zone, required_ppe, to_pixels
from backend.capture.buffer import FrameBuffer
from backend.capture.camera import CameraCapture
from backend.detection.engine import run_detection, get_danger_zone, has_item_on_person, is_in_danger_zone
from backend.gestures.detector import detect_ok_gesture
from backend.visualization.renderer import (
    draw_danger_zone, draw_person, draw_hint,
    draw_legend, put_text
)
from backend.core.state import DetectionState, LogEntry
from backend.api.events import create_event_record, update_event_clip, update_event_snapshot
from backend.db.models import EventLabel
from backend.storage.minio_client import get_storage

DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'
print(f"Используется устройство: {DEVICE}")


def _resolve_model(path):
    engine = path.with_suffix('.engine')
    return engine if engine.exists() else path


model_path = _resolve_model(MODEL_PATH)
pose_path = _resolve_model(POSE_MODEL_PATH)

model = YOLO(str(model_path))
model.to(DEVICE)
if model_path.suffix == '.pt':
    model.model.names = CLASS_NAMES
pose_model = YOLO(str(pose_path))
pose_model.to(DEVICE)

is_tensorrt = model_path.suffix == '.engine'
if is_tensorrt:
    print("[TensorRT] FP16 engine loaded")

face_recognizer = None
try:
    from backend.reid.recognizer import FaceRecognizer, FaceRecognitionWorker, match_faces_to_persons
    face_recognizer = FaceRecognizer(model_name='buffalo_l', det_size=REID_DET_SIZE)
except Exception as e:
    print(f"[ReID] InsightFace не загружен: {e}. Re-ID отключён.")

# Body Re-ID (опознание «со спины» по одежде) — лёгкий цветовой дескриптор, без
# тяжёлых зависимостей. Включается флагом REID_BODY_ENABLED.
body_recognizer = None
try:
    from backend.config import REID_BODY_ENABLED
    if REID_BODY_ENABLED:
        from backend.reid.body import BodyRecognizer
        body_recognizer = BodyRecognizer()
        print("[ReID] Body Re-ID активен (дескриптор одежды)")
except Exception as e:
    print(f"[ReID] Body Re-ID не загружен: {e}")

state = DetectionState()
state.init_gallery(REID_GALLERY_PATH)
if state.gallery is not None:
    state.gallery.cleanup_old(REID_MAX_AGE_DAYS)

frame_buffers: dict[str, FrameBuffer] = {}
annotated_buffers: dict[str, FrameBuffer] = {}
camera_captures: dict[str, CameraCapture] = {}


def _init_camera_resources(cam_id: str, source: str | int):
    if cam_id not in frame_buffers:
        frame_buffers[cam_id] = FrameBuffer()
    if cam_id not in annotated_buffers:
        annotated_buffers[cam_id] = FrameBuffer()
    if cam_id not in camera_captures:
        camera_captures[cam_id] = CameraCapture(buffer=frame_buffers[cam_id], source=source)


for cam_id, source in CAMERAS.items():
    _init_camera_resources(cam_id, source)


def start_face_workers():
    if face_recognizer is None:
        return
    from backend.config import DETECT_MODES
    if not DETECT_MODES.get("faces", True):
        return
    for cam_id in list(CAMERAS.keys()):
        if cam_id not in face_workers and cam_id in frame_buffers:
            from backend.reid.recognizer import FaceRecognitionWorker
            fw = FaceRecognitionWorker(frame_buffers[cam_id], face_recognizer, REID_FRAME_SKIP)
            fw.start()
            face_workers[cam_id] = fw
    if face_workers:
        print(f"[ReID] Face workers запущены для {len(face_workers)} камер")


def stop_face_workers():
    for fw in list(face_workers.values()):
        fw.stop()
    face_workers.clear()
    print("[ReID] Face workers остановлены")


def _build_voice_text(statuses: dict, person_name: str) -> str:
    """Сформировать текст голосового предупреждения по статусам СИЗ.
    Статус-строка: 'КМЖз' — позиции 0=каска, 1=маска, 2=жилет, 3=зона;
    заглавная = есть, строчная = нет.

    Озвучиваем ТОЛЬКО реальное нарушение В опасной зоне (человек внутри зоны
    без СИЗ). Если нарушение СИЗ есть, но человек ВНЕ зоны — возвращаем ''
    (пустую строку), чтобы не проигрывать ложное «в опасной зоне» (категория
    «нарушение» в пайплайне срабатывает и на отсутствие СИЗ вне зоны)."""
    missing = []
    zone_violation = False
    for status in statuses.values():
        if len(status) >= 4 and status[3] == 'З':  # человек в зоне
            person_missing = []
            if status[0] == 'к':
                person_missing.append('каска')
            if status[1] == 'м':
                person_missing.append('маска')
            if status[2] == 'ж':
                person_missing.append('жилет')
            if person_missing:
                zone_violation = True
                for item in person_missing:
                    if item not in missing:
                        missing.append(item)
    if not zone_violation:
        return ""
    who = person_name if person_name else "Человек"
    if missing:
        return f"Внимание! {who} в опасной зоне. Нет СИЗ: {', '.join(missing)}"
    return f"Внимание! {who} вошёл в опасную зону без необходимых средств защиты"


def _db_upsert_camera(cam_id: str, source):
    """Продублировать камеру в таблицу Camera (БД). Не роняет операцию при сбое."""
    try:
        from backend.db.engine import get_session
        from backend.db.models import Camera
        s = get_session()
        try:
            row = s.query(Camera).filter(Camera.id == cam_id).first()
            if row is None:
                s.add(Camera(id=cam_id, name=cam_id, source=str(source)))
            else:
                row.source = str(source)
                row.name = cam_id
            s.commit()
        finally:
            s.close()
    except Exception as exc:
        print(f"[DB] Не удалось записать камеру {cam_id}: {exc}")


def _db_delete_camera(cam_id: str):
    try:
        from backend.db.engine import get_session
        from backend.db.models import Camera
        s = get_session()
        try:
            row = s.query(Camera).filter(Camera.id == cam_id).first()
            if row is not None:
                s.delete(row)
                s.commit()
        finally:
            s.close()
    except Exception as exc:
        print(f"[DB] Не удалось удалить камеру {cam_id}: {exc}")


def add_camera(cam_id: str, source: str | int):
    from backend.config import save_cameras, DETECT_MODES
    CAMERAS[cam_id] = source
    save_cameras()
    _db_upsert_camera(cam_id, source)
    _init_camera_resources(cam_id, source)
    if state.live_active:
        camera_captures[cam_id].start()
        if face_recognizer is not None and DETECT_MODES.get("faces", True):
            from backend.reid.recognizer import FaceRecognitionWorker
            fw = FaceRecognitionWorker(frame_buffers[cam_id], face_recognizer, REID_FRAME_SKIP)
            fw.start()
            face_workers[cam_id] = fw
        # Поднимаем поток детекции для новой камеры на лету.
        if cam_id not in detection_threads or not detection_threads[cam_id].is_alive():
            t = threading.Thread(target=_camera_detection_worker, args=(cam_id,), daemon=True)
            detection_threads[cam_id] = t
            t.start()
        if RECORD_ENABLED:
            get_recording_manager().add_camera(cam_id, source)
    print(f"[Камера] Добавлена: {cam_id} -> {source}")


def remove_camera(cam_id: str):
    from backend.config import save_cameras
    if cam_id in camera_captures:
        camera_captures[cam_id].stop()
        camera_captures.pop(cam_id)
    if cam_id in face_workers:
        face_workers[cam_id].stop()
        face_workers.pop(cam_id)
    if cam_id in frame_buffers:
        frame_buffers.pop(cam_id)
    if cam_id in annotated_buffers:
        annotated_buffers.pop(cam_id)
    CAMERAS.pop(cam_id, None)
    # Поток детекции сам завершится (условие `cam_id in CAMERAS`); снимаем ссылки.
    detection_threads.pop(cam_id, None)
    with _cam_models_lock:
        _cam_models.pop(cam_id, None)
    _motion_detectors.pop(cam_id, None)
    if RECORD_ENABLED:
        get_recording_manager().remove_camera(cam_id)
    save_cameras()
    _db_delete_camera(cam_id)
    print(f"[Камера] Удалена: {cam_id}")


def rename_camera(old_id: str, new_id: str) -> bool:
    if old_id not in CAMERAS:
        return False
    if not new_id or new_id == old_id:
        return False
    if new_id in CAMERAS:
        return False
    source = CAMERAS.pop(old_id)
    CAMERAS[new_id] = source
    for dct in (frame_buffers, annotated_buffers, camera_captures, face_workers,
                _motion_detectors):
        if old_id in dct:
            dct[new_id] = dct.pop(old_id)
    with _cam_models_lock:
        if old_id in _cam_models:
            _cam_models[new_id] = _cam_models.pop(old_id)
    # Старый поток детекции завершится (нет old_id в CAMERAS); поднимаем новый.
    detection_threads.pop(old_id, None)
    if state.live_active:
        t = threading.Thread(target=_camera_detection_worker, args=(new_id,), daemon=True)
        detection_threads[new_id] = t
        t.start()
        if RECORD_ENABLED:
            mgr = get_recording_manager()
            mgr.remove_camera(old_id)
            mgr.add_camera(new_id, source)
    from backend.config import save_cameras
    save_cameras()
    _db_delete_camera(old_id)
    _db_upsert_camera(new_id, source)
    print(f"[Камера] Переименована: {old_id} -> {new_id}")
    return True


def _unique_cam_name(base: str) -> str:
    if base not in CAMERAS:
        return base
    i = 2
    while f"{base}_{i}" in CAMERAS:
        i += 1
    return f"{base}_{i}"


def discover_cameras(add: bool = False) -> dict:
    """Найти открытые RTSP-потоки в локальной сети (ONVIF + скан подсети).
    При add=True добавляет новые (не дублируя уже существующие источники)."""
    from backend.config import (DISCOVERY_USE_ONVIF, DISCOVERY_USE_SCAN,
                                 DISCOVERY_ONVIF_TIMEOUT)
    from backend.discovery import discover_streams
    found = discover_streams(use_onvif=DISCOVERY_USE_ONVIF,
                             use_scan=DISCOVERY_USE_SCAN,
                             onvif_timeout=DISCOVERY_ONVIF_TIMEOUT)
    existing = {str(v) for v in CAMERAS.values()}
    added = []
    for f in found:
        if f["rtsp_url"] in existing:
            f["status"] = "exists"
            continue
        f["status"] = "new"
        if add:
            name = _unique_cam_name(f["name"])
            add_camera(name, f["rtsp_url"])
            f["added_as"] = name
            f["status"] = "added"
            added.append(name)
    return {"found": found, "added": added}


def autodiscover_and_add():
    """Фоновый автозапуск обнаружения при старте (CAMERA_AUTODISCOVER)."""
    try:
        result = discover_cameras(add=True)
        print(f"[Discovery] Автообнаружение: добавлено {len(result['added'])} камер")
    except Exception as exc:
        print(f"[Discovery] Ошибка автообнаружения: {exc}")


detection_threads: dict[str, threading.Thread] = {}
face_workers: dict[str, 'FaceRecognitionWorker'] = {}

# ── Event recording ──
_event_recordings: dict[str, Optional[dict]] = {}
_frame_prebuf: dict[str, deque] = {}

# ── Motion detection (MOG2) — по экземпляру на камеру ──
_motion_detectors: dict[str, MotionDetector] = {}

# ── Модели YOLO по экземпляру на камеру ──────────────────────
# Каждой камере — свой экземпляр YOLO: ByteTrack хранит состояние трекера ВНУТРИ
# модели (model.track(persist=True)), поэтому общий объект на потоки нескольких
# камер перемешал бы track_id. Веса крошечные (~6 МБ), N экземпляров недороги.
# Глобальные `model`/`pose_model` остаются для /upload (одиночные предсказания).
_cam_models: dict[str, tuple] = {}
_cam_models_lock = threading.Lock()


def _get_cam_models(cam_id: str) -> tuple:
    """Вернуть (yolo, pose) для камеры, создав при первом обращении."""
    with _cam_models_lock:
        pair = _cam_models.get(cam_id)
        if pair is None:
            ym = YOLO(str(model_path))
            ym.to(DEVICE)
            if model_path.suffix == '.pt':
                ym.model.names = CLASS_NAMES
            pm = YOLO(str(pose_path))
            pm.to(DEVICE)
            pair = (ym, pm)
            _cam_models[cam_id] = pair
        return pair


def _get_motion_detector(cam_id: str) -> MotionDetector:
    det = _motion_detectors.get(cam_id)
    if det is None:
        det = MotionDetector(threshold=MOTION_THRESHOLD, min_area=MOTION_MIN_AREA,
                             cooldown_frames=MOTION_COOLDOWN_FRAMES)
        _motion_detectors[cam_id] = det
    return det


_ZONE_COLORS = {  # BGR
    "danger": (0, 0, 255),
    "restricted": (0, 165, 255),
    "mask": (128, 128, 128),
}


def _draw_user_zones(frame, zones: list, w: int, h: int):
    """Отрисовать пользовательские полигональные зоны (контур + лёгкая заливка)."""
    import numpy as _np
    for z in zones:
        pts = to_pixels(z, w, h)
        if len(pts) < 3:
            continue
        color = _ZONE_COLORS.get(z.get("type"), (0, 0, 255))
        arr = _np.array(pts, dtype=_np.int32).reshape((-1, 1, 2))
        overlay = frame.copy()
        cv2.fillPoly(overlay, [arr], color)
        cv2.addWeighted(overlay, 0.18, frame, 0.82, 0, frame)
        cv2.polylines(frame, [arr], isClosed=True, color=color, thickness=2)
        label = z.get("name") or z.get("type", "зона")
        frame[:] = put_text(frame, label, (pts[0][0], max(0, pts[0][1] - 18)), color=color)


def process_frame(frame, cam_id: str, face_worker=None, det_model=None, det_pose=None):
    from backend.config import DETECT_MODES
    # Модели на камеру (для параллельных потоков детекции); по умолчанию —
    # глобальные (обратная совместимость с /upload и тестами).
    det_model = det_model if det_model is not None else model
    det_pose = det_pose if det_pose is not None else pose_model
    if not any(DETECT_MODES.values()):
        frame = draw_legend(frame)
        return frame, f"{datetime.now().strftime('%H:%M:%S')} [{cam_id}] Детекция отключена", "норма", [], {}
    state.cleanup_stale_tracks()
    detected = run_detection(frame, det_model)
    # Пользовательские зоны (нарисованы в редакторе): сперва маски — исключаем
    # объекты в замаскированных областях ДО любой логики/отрисовки.
    fh, fw = frame.shape[:2]
    ppe_on = DETECT_MODES.get("ppe", True)
    cam_zones = get_zones(cam_id)
    if cam_zones:
        detected = apply_masks(detected, cam_zones, fw, fh)
    # Опасные/ограниченные пользовательские зоны учитываются вместе с зоной по
    # конусам (только когда включена детекция СИЗ — как и зона по конусам).
    danger_user = [z for z in cam_zones if z.get("type") in ("danger", "restricted")] if ppe_on else []
    # Чистый кадр ДО любой отрисовки — для body Re-ID (рамки/заливка зоны исказили
    # бы цвета одежды). Берём копию только когда body Re-ID реально нужен.
    clean_frame = frame.copy() if (body_recognizer is not None
                                   and DETECT_MODES.get("faces", True)
                                   and detected["persons"]) else None
    danger_zone = get_danger_zone(detected["cones"]) if ppe_on else None

    def _in_danger(pbox) -> bool:
        """Человек в любой опасной зоне: по конусам ИЛИ в пользовательской зоне."""
        if danger_zone is not None and is_in_danger_zone(pbox, danger_zone):
            return True
        return in_any_danger_zone(pbox, danger_user, fw, fh) if danger_user else False

    def _required_ppe(pbox) -> set:
        """Обязательные СИЗ для точки: пер-зонные (require_ppe) или дефолт."""
        if not ppe_on:
            return set()
        return required_ppe(pbox, danger_user, fw, fh, PPE_REQUIRED_DEFAULT)
    if DETECT_MODES.get("ppe", True):
        for box in detected["helmets"]:
            x1, y1, x2, y2 = map(int, box)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            frame = put_text(frame, "Каска", (x1, max(0, y1 - 20)), color=(0, 255, 0))
        for box in detected["masks"]:
            x1, y1, x2, y2 = map(int, box)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 255, 0), 2)
            frame = put_text(frame, "Маска", (x1, max(0, y1 - 20)), color=(255, 255, 0))
        for box in detected["vests"]:
            x1, y1, x2, y2 = map(int, box)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 165, 0), 2)
            frame = put_text(frame, "Жилет", (x1, max(0, y1 - 20)), color=(255, 165, 0))
        for box in detected["cones"]:
            x1, y1, x2, y2 = map(int, box)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 128, 255), 2)
            frame = put_text(frame, "Конус", (x1, max(0, y1 - 20)), color=(0, 128, 255))
    if danger_zone is not None:
        frame = draw_danger_zone(frame, danger_zone)
    _draw_user_zones(frame, cam_zones, fw, fh)
    persons_count = len(detected["persons"])
    # Извлекаем до любых веток: используется и в цикле отрисовки, и в цикле statuses.
    # Раньше присваивалось внутри `if detected["persons"] and detect_people` →
    # при выключенной детекции людей с людьми в кадре цикл statuses падал с
    # UnboundLocalError и ронял обработку кадра (стрим «зависал»).
    person_track_ids = detected.get("person_track_ids", [])
    approved_count = 0
    violation_count = 0
    has_any_violation = False
    msg_parts = [f"{datetime.now().strftime('%H:%M:%S')} [{cam_id}]"]
    global_ids = []
    detect_people = DETECT_MODES.get("people", True)
    detect_faces_mode = DETECT_MODES.get("faces", True)
    if detected["persons"] and detect_people:
        msg_parts.append(f"Людей: {persons_count}")
        face_embeddings = None
        if face_worker is not None and detect_faces_mode:
            face_data = face_worker.get_faces()
            face_embeddings = match_faces_to_persons(detected["persons"], face_data)
        for idx, pbox in enumerate(detected["persons"]):
            track_id = person_track_ids[idx] if idx < len(person_track_ids) else -1
            if track_id < 0:
                track_id = idx
            face_info = (face_embeddings or [(None, 0.0)])[idx] if face_embeddings else (None, 0.0)
            face_emb, face_quality = face_info
            # Дескриптор тела (одежды) с ЧИСТОГО кадра — для опознания «со спины».
            body_emb = (body_recognizer.extract(clean_frame, pbox)
                        if clean_frame is not None else None)
            global_id = state.get_global_id(track_id, cam_id,
                                            face_embedding=face_emb,
                                            quality=face_quality,
                                            person_box=pbox,
                                            body_embedding=body_emb)
            global_ids.append(global_id)
            has_helmet = any(has_item_on_person(pbox, h) for h in detected["helmets"]) if DETECT_MODES.get("ppe", True) else False
            has_mask = any(has_item_on_person(pbox, m) for m in detected["masks"]) if DETECT_MODES.get("ppe", True) else False
            has_vest = any(has_item_on_person(pbox, v) for v in detected["vests"]) if DETECT_MODES.get("ppe", True) else False
            in_danger = _in_danger(pbox)
            approved = state.is_approved(pbox, cam_id, global_id=global_id)
            # Обязательность СИЗ — пер-зонная (require_ppe) или дефолтная.
            required = _required_ppe(pbox)
            _present = {"helmet": has_helmet, "mask": has_mask, "vest": has_vest}
            _ru = {"helmet": "каска", "mask": "маска", "vest": "жилет"}
            missing = [_ru[i] for i in ("helmet", "mask", "vest")
                       if i in required and not _present[i]]
            fully_equipped = not missing  # все требуемые СИЗ на месте
            # В метке показываем только ТРЕБУЕМЫЕ предметы (демо без каски/жилета
            # не показывает «!К/!Ж», если они не обязательны).
            _letters = {"helmet": "К", "mask": "М", "vest": "Ж"}
            ppe = " ".join(f"{_letters[i]}" if _present[i] else f"!{_letters[i]}"
                           for i in ("helmet", "mask", "vest") if i in required)
            person_name = state.get_person_name(global_id, cam_id, face_emb is not None and detect_faces_mode) if detect_faces_mode else ""
            gesture_ok = (
                detect_ok_gesture(frame, pbox, det_pose)
                if not approved and state.can_gesture(global_id)
                else False
            )
            if gesture_ok:
                state.set_gesture_time(global_id)
                _who = person_name or "Работник"
                if fully_equipped:
                    state.approve(pbox, cam_id, global_id=global_id)
                    approved = True
                    state.set_gesture_detected()
                    # Уведомление сверху (вместо текста на кадре).
                    state.push_notification("granted", "ЖЕСТ «ОК» РАСПОЗНАН",
                                            f"{_who} — доступ разрешён")
                else:
                    # Не рисуем «ОДЕНЬТЕ СИЗ» на стриме — показываем уведомление сверху.
                    state.push_notification("missing", "НЕ ХВАТАЕТ СИЗ",
                                            f"{_who}: {', '.join(missing) if missing else 'нужны СИЗ'}")
            if approved:
                approved_count += 1
            elif not fully_equipped and DETECT_MODES.get("ppe", True):
                violation_count += 1
            name_tag = f"{person_name} " if person_name else ""
            if approved:
                label = f"{name_tag}ПРОПУСК | {ppe}" if ppe else f"{name_tag}ПРОПУСК"
            elif in_danger:
                label = f"{name_tag}ОПАСНАЯ ЗОНА | {ppe}" if ppe else f"{name_tag}ОПАСНАЯ ЗОНА"
            else:
                label = f"{name_tag}Вне зоны | {ppe}" if ppe else f"{name_tag}Вне зоны"
            frame = draw_person(frame, pbox, label, in_danger, not fully_equipped and DETECT_MODES.get("ppe", True), approved)
            if fully_equipped and not approved and in_danger:
                frame = draw_hint(frame, pbox)
            part = f"{person_name}" if person_name else "Неизвестный"
            if ppe:
                part += f" [{ppe}]"
            part += ": "
            if approved:
                part += "ПРОПУСК | Все СИЗ + ЖЕСТ-ОК"
            elif gesture_ok:
                part += "ЖЕСТ-ОК | Нет СИЗ: " + ", ".join(missing)
                has_any_violation = True
            elif in_danger:
                part += "ОПАСНАЯ ЗОНА | "
                part += "Все СИЗ — покажи ОК" if fully_equipped else f"Нет СИЗ: {', '.join(missing)}"
                if not fully_equipped:
                    has_any_violation = True
            else:
                part += "Вне зоны | "
                part += "Все СИЗ на месте" if fully_equipped else f"Нет СИЗ: {', '.join(missing)}"
                if not fully_equipped:
                    has_any_violation = True
            msg_parts.append(part)
    elif not detect_people:
        msg_parts.append("Детекция людей отключена")
    else:
        msg_parts.append("Людей не обнаружено")
    if danger_zone is not None:
        msg_parts.append(f"Зона активна ({len(detected['cones'])} конуса)")
    frame = draw_legend(frame)
    message = " | ".join(msg_parts)
    category = "нарушение" if has_any_violation else \
        "внимание" if (danger_zone is not None or danger_user) and detected["persons"] else "норма"
    statuses: dict[str, str] = {}
    for idx, pbox in enumerate(detected["persons"]):
        track_id = person_track_ids[idx] if idx < len(person_track_ids) else -1
        if track_id < 0:
            track_id = idx
        helmet = any(has_item_on_person(pbox, h) for h in detected["helmets"]) if DETECT_MODES.get("ppe", True) else False
        mask = any(has_item_on_person(pbox, m) for m in detected["masks"]) if DETECT_MODES.get("ppe", True) else False
        vest = any(has_item_on_person(pbox, v) for v in detected["vests"]) if DETECT_MODES.get("ppe", True) else False
        dz = _in_danger(pbox)
        # Необязательный СИЗ считаем «в норме» (заглавная), чтобы дедуп-лог и
        # голосовое предупреждение не сообщали об отсутствии того, что не требуется.
        req = _required_ppe(pbox)
        ok_h = helmet or "helmet" not in req
        ok_m = mask or "mask" not in req
        ok_v = vest or "vest" not in req
        key = f"{cam_id}:{track_id}"
        statuses[key] = f"{'К' if ok_h else 'к'}{'М' if ok_m else 'м'}{'Ж' if ok_v else 'ж'}{'З' if dz else 'з'}"
    return frame, message, category, global_ids, statuses


def generate_live_feed(cam_id: str = "cam1"):
    ann_buf = annotated_buffers.get(cam_id)
    if ann_buf is None:
        return
    consecutive_errors = 0
    while state.live_active:
        ann_buf.wait(timeout=2.0)
        frame = ann_buf.read()
        if frame is None:
            continue
        try:
            ret, buffer = cv2.imencode('.jpg', frame)
            if not ret:
                continue
            consecutive_errors = 0
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        except Exception as e:
            consecutive_errors += 1
            print(f"[{cam_id}] Ошибка кадра ({consecutive_errors}): {e}")
            if consecutive_errors > 30:
                print(f"[{cam_id}] Слишком много ошибок, остановка генератора")
                break
            time.sleep(0.1)


def start_live():
    if state.live_active:
        stop_live()
        time.sleep(0.5)
    state.clear_log()
    state.clear_tracks()
    state.clear_notifications()
    _motion_detectors.clear()
    for buf in annotated_buffers.values():
        buf.clear()
    state.live_active = True
    for cam_id in CAMERAS:
        _init_camera_resources(cam_id, CAMERAS[cam_id])
        camera_captures[cam_id].start()
    start_face_workers()
    # Поток детекции на КАЖДУЮ камеру — параллельная обработка вместо
    # последовательного round-robin (см. _camera_detection_worker).
    for cam_id in list(CAMERAS.keys()):
        t = threading.Thread(target=_camera_detection_worker, args=(cam_id,), daemon=True)
        detection_threads[cam_id] = t
        t.start()
    hb = threading.Thread(target=_heartbeat_loop, daemon=True)
    detection_threads["_heartbeat"] = hb
    hb.start()
    if RECORD_ENABLED:
        get_recording_manager().start_all(dict(CAMERAS))
    print(f"Детекция запущена на {len(CAMERAS)} камерах ({len(CAMERAS)} потоков)")


def stop_live():
    if not state.live_active:
        return
    state.live_active = False
    for cam_id in list(CAMERAS.keys()):
        if cam_id in camera_captures:
            camera_captures[cam_id].stop()
    for t in list(detection_threads.values()):
        t.join(timeout=2)
    detection_threads.clear()
    stop_face_workers()
    if RECORD_ENABLED:
        get_recording_manager().stop_all()
    for cam_id, rec in list(_event_recordings.items()):
        if rec.get('active'):
            rec['active'] = False
            print(f"[Events] Финализация {rec['event_id']} при остановке")
            _finalize_recording(cam_id, rec)
    for buf in annotated_buffers.values():
        buf.clear()
    print("Детекция остановлена")


def _heartbeat_loop():
    """Отдельный поток: периодический MQTT-heartbeat и отметка в метриках.
    Вынесен из петли детекции, т.к. петель теперь несколько (по камере)."""
    metrics = get_metrics()
    publisher = get_publisher()
    while state.live_active:
        metrics.heartbeat()
        if publisher is not None:
            publisher.publish_heartbeat({
                "ts": time.time(), "uptime_seconds": metrics.uptime_seconds(),
                "cameras": len(CAMERAS),
            })
        # Дробный сон, чтобы быстро реагировать на stop_live.
        slept = 0.0
        while state.live_active and slept < MQTT_HEARTBEAT_INTERVAL:
            time.sleep(0.5)
            slept += 0.5


def _camera_detection_worker(cam_id: str):
    """Поток детекции ОДНОЙ камеры. Запускается по экземпляру на камеру —
    YOLO/InsightFace/OpenCV отпускают GIL на время вычислений, поэтому камеры
    обрабатываются параллельно (на CPU — по ядрам, на GPU — с перекрытием),
    без последовательного round-robin прежней единой петли."""
    metrics = get_metrics()
    publisher = get_publisher()
    det_model, det_pose = _get_cam_models(cam_id)
    while state.live_active and cam_id in CAMERAS:
        if cam_id not in frame_buffers:
            return
        raw_buf = frame_buffers[cam_id]
        out_buf = annotated_buffers[cam_id]
        # Блокируемся до нового кадра (без busy-loop); по таймауту проверяем флаги.
        raw_buf.wait(timeout=1.0)
        frame = raw_buf.read()
        if frame is None:
            continue

        if cam_id not in _frame_prebuf:
            _frame_prebuf[cam_id] = deque(maxlen=EVENT_PRE_FRAMES)
        _frame_prebuf[cam_id].append(frame.copy())

        if not get_camera_config(cam_id).get("detect_enabled", True):
            out_buf.write(frame)
            continue

        # Движение считаем, если оно нужно либо для «Motion First» (пропуск YOLO),
        # либо для NVR-режима "motion" (пометка сегментов has_motion).
        nvr_motion = RECORD_ENABLED and RECORD_MODE == "motion"
        if MOTION_DETECTION_ENABLED or nvr_motion:
            rec = _event_recordings.get(cam_id)
            recording = rec is not None and rec.get('active')
            motion = _get_motion_detector(cam_id).detect(frame)
            if motion and nvr_motion:
                get_recording_manager().note_motion(cam_id)
            if publisher is not None:
                publisher.publish_motion(cam_id, bool(motion), motion.area_ratio)
            # Пропуск YOLO на статике — только если включён «Motion First».
            if MOTION_DETECTION_ENABLED and not motion and not recording:
                out_buf.write(frame)
                metrics.record_skipped(cam_id)
                continue

        try:
            _t0 = time.time()
            annotated, message, category, global_ids, statuses = process_frame(
                frame, cam_id, face_worker=face_workers.get(cam_id),
                det_model=det_model, det_pose=det_pose)
            metrics.record_frame(cam_id, (time.time() - _t0) * 1000.0)
            metrics.record_event(category)
            out_buf.write(annotated)

            if publisher is not None:
                people = len(statuses)
                # Строчная буква в позициях КМЖ = отсутствует СИЗ → нарушитель.
                violations = sum(1 for v in statuses.values()
                                 if len(v) >= 3 and any(c.islower() for c in v[:3]))
                publisher.publish_detection(cam_id, people, violations,
                                            max(0, people - violations), category)

            is_violation = category == "нарушение"
            rec = _event_recordings.get(cam_id)
            if is_violation:
                if rec is None or not rec.get('active'):
                    gid = global_ids[0] if global_ids else 0
                    person_name = state.get_person_name(gid, cam_id, has_face=True) if gid else ""
                    voice_text = _build_voice_text(statuses, person_name)
                    if voice_text:
                        state.push_voice_alert(cam_id, voice_text)
                    event_id = create_event_record(
                        cam_id=cam_id,
                        label=EventLabel.VIOLATION,
                        person_name=person_name or None,
                        person_id=gid or None,
                    )
                    rec = {
                        'active': True,
                        'event_id': event_id,
                        'start_time': time.time(),
                        'frames': list(_frame_prebuf[cam_id]),
                        'cam_id': cam_id,
                    }
                    _event_recordings[cam_id] = rec
                    if publisher is not None:
                        publisher.publish_violation(cam_id, person_name or "",
                                                    gid or 0)
                    print(f"[Events] Запись {event_id} начата на {cam_id}")
                if rec is not None and rec.get('active'):
                    rec['frames'].append(annotated.copy())
                    if len(rec['frames']) >= EVENT_MAX_FRAMES:
                        rec['active'] = False
                        _finalize_recording(cam_id, rec)
            else:
                if rec is not None and rec.get('active'):
                    post = rec.get('post_count', 0) + 1
                    rec['post_count'] = post
                    rec['frames'].append(annotated.copy())
                    if post >= EVENT_POST_FRAMES:
                        rec['active'] = False
                        _finalize_recording(cam_id, rec)

            any_changed = any(state.is_status_changed(cam_id, int(k.split(":")[1]), v) for k, v in statuses.items())
            if any_changed:
                gid = global_ids[0] if global_ids else 0
                state.add_log(LogEntry(
                    id=str(datetime.now().timestamp()),
                    timestamp=datetime.now().strftime('%H:%M:%S'),
                    message=message,
                    category=category,
                    cam_id=cam_id,
                    global_id=gid,
                ))
                print(message)
        except Exception as e:
            print(f"[{cam_id}] Ошибка детекции: {e}")
            traceback.print_exc()


def _finalize_recording(cam_id: str, rec: dict):
    frames = rec.get('frames', [])
    if not frames:
        return
    event_id = rec['event_id']
    h, w = frames[0].shape[:2]
    raw_path = os.path.join(VIOLATION_LOGS_DIR, f"_{event_id}_raw.mp4")
    final_path = os.path.join(VIOLATION_LOGS_DIR, f"_{event_id}.mp4")
    try:
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(raw_path, fourcc, EVENT_CLIP_FPS, (w, h))
        for f in frames:
            out.write(f)
        out.release()

        subprocess.run([
            "ffmpeg", "-y",
            "-i", raw_path,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            final_path
        ], capture_output=True, timeout=60)

        data = Path(final_path).read_bytes()

        storage = get_storage()
        storage.upload_clip(event_id, cam_id, data)

        update_event_clip(event_id, time.time())

        mid = frames[len(frames) // 2]
        ret, jpg = cv2.imencode('.jpg', mid, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if ret:
            storage.upload_snapshot(event_id, cam_id, jpg.tobytes())
            update_event_snapshot(event_id)

        print(f"[Events] Клип {event_id} сохранён ({len(frames)} кадров)")
    except Exception as e:
        print(f"[Events] Ошибка сохранения {event_id}: {e}")
    finally:
        for p in [raw_path, final_path]:
            try:
                Path(p).unlink(missing_ok=True)
            except Exception:
                pass
