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
from typing import Any, Dict, Optional
from ultralytics import YOLO
import torch

cv2.INTER_NEAREST_EXACT = getattr(cv2, 'INTER_NEAREST_EXACT', cv2.INTER_NEAREST)

from backend.config import (
    MODEL_PATH, POSE_MODEL_PATH, CLASS_NAMES, CAMERAS, CONF_THRESH,
    REID_GALLERY_PATH, REID_DET_SIZE, REID_FRAME_SKIP, REID_MAX_AGE_DAYS,
    REID_EMB_MAX_AGE_DAYS, REID_EMB_CLEAN_INTERVAL,
    REID_BODY_MAX_AGE_DAYS, REID_FLUSH_INTERVAL,
    EVENT_PRE_FRAMES, EVENT_POST_FRAMES, EVENT_MAX_FRAMES, EVENT_CLIP_FPS,
    VIOLATION_LOGS_DIR, get_camera_config, VOICE_ALERT_COOLDOWN,
    MOTION_DETECTION_ENABLED, MOTION_THRESHOLD, MOTION_MIN_AREA,
    MOTION_COOLDOWN_FRAMES, MQTT_HEARTBEAT_INTERVAL,
    RECORD_ENABLED, RECORD_MODE, PPE_REQUIRED_DEFAULT, STREAM_STALE_SEC,
)
from backend.core.metrics import get_metrics
from backend.detection.motion import MotionDetector
from backend.mqtt.publisher import get_publisher
from backend.recorder import get_recording_manager
from backend.zones import get_zones, apply_masks, in_any_danger_zone, required_ppe, to_pixels
from backend.capture.buffer import FrameBuffer
from backend.capture.camera import CameraCapture
from backend.detection.engine import run_detection, get_danger_zone, has_item_on_person, is_in_danger_zone
from backend.detection.batch_worker import BatchDetectionWorker
from backend.gestures.detector import detect_ok_gesture
from backend.tts.alert import (build_voice_text as _build_voice_text,
                               build_approved_voice_text as _build_approved_voice_text)
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
    """Приоритет: .engine (TensorRT) > .torchscript (ARM64/TorchScript) > .pt"""
    engine = path.with_suffix('.engine')
    if engine.exists():
        return engine
    ts = path.with_suffix('.torchscript')
    if ts.exists():
        return ts
    return path


def _apply_class_names(yolo_model, resolved_path):
    """Применить CLASS_NAMES для .pt-моделей (TorchScript и .engine берут имена из весов)."""
    if resolved_path.suffix == '.pt':
        yolo_model.model.names = CLASS_NAMES


model_path = _resolve_model(MODEL_PATH)
pose_path = _resolve_model(POSE_MODEL_PATH)

model = YOLO(str(model_path))
model.to(DEVICE)
_apply_class_names(model, model_path)
pose_model = YOLO(str(pose_path))
pose_model.to(DEVICE)

is_tensorrt = model_path.suffix == '.engine'
is_torchscript = model_path.suffix == '.torchscript'
if is_tensorrt:
    print("[TensorRT] FP16 engine загружен")
elif is_torchscript:
    print("[TorchScript] .torchscript модель загружена")

# Батч-инференс: один model.track(batch) вместо N последовательных вызовов.
# Авто-включается при ≥2 камерах; BATCH_INFERENCE=0 отключает принудительно.
_BATCH_INFERENCE_ENV = os.environ.get("BATCH_INFERENCE", "").strip().lower()
BATCH_INFERENCE_ENABLED: bool = _BATCH_INFERENCE_ENV not in ("0", "false", "no", "off")
# Синглтон воркера; создаётся/уничтожается в start_live/stop_live
_batch_worker: Optional[BatchDetectionWorker] = None

face_recognizer = None
try:
    from backend.reid.recognizer import FaceRecognizer, FaceRecognitionWorker, match_faces_to_persons
    face_recognizer = FaceRecognizer(model_name='buffalo_l', det_size=REID_DET_SIZE)
except Exception as e:
    print(f"[ReID] InsightFace не загружен: {e}. Re-ID отключён.")

# Body Re-ID (опознание «со спины») — глубокий дескриптор OSNet (ONNX) с мягкой
# деградацией на цветовой fallback. Включается флагом REID_BODY_ENABLED.
body_recognizer = None
try:
    from backend.config import REID_BODY_ENABLED
    if REID_BODY_ENABLED:
        from backend.reid.body import BodyRecognizer
        body_recognizer = BodyRecognizer()
        print(f"[ReID] Body Re-ID активен (бэкенд: {body_recognizer.backend})")
except Exception as e:
    print(f"[ReID] Body Re-ID не загружен: {e}")

state = DetectionState()
state.init_gallery(REID_GALLERY_PATH)
if state.gallery is not None:
    state.gallery.cleanup_old(REID_MAX_AGE_DAYS)
    # Затухание памяти по времени: лишние постаревшие ракурсы стираются, образ
    # (якорь + last_seen) сохраняется. Периодически повторяется в _heartbeat_loop.
    state.gallery.prune_old_embeddings(REID_EMB_MAX_AGE_DAYS)
    # Дескрипторы тела (одежда) — короткий TTL: при старте чистим устаревшие.
    state.gallery.prune_old_bodies(REID_BODY_MAX_AGE_DAYS)
# Пороги body Re-ID — под фактический бэкенд (deep OSNet vs цветовой fallback).
if body_recognizer is not None:
    state.configure_body(body_recognizer.match_threshold,
                         body_recognizer.diversity_max_sim)

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
        # Регистрируем в батч-воркере, если он активен.
        if _batch_worker is not None:
            _batch_worker.register_camera(cam_id)
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
    if _batch_worker is not None:
        _batch_worker.unregister_camera(cam_id)
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
                                 DISCOVERY_ONVIF_TIMEOUT, DISCOVERY_SUBNET)
    from backend.discovery import discover_streams, ips_from_sources, paths_from_sources
    extra_subnets = [s for s in DISCOVERY_SUBNET.split(",") if s.strip()]
    known_ips = ips_from_sources(CAMERAS.values())    # подсеть уже добавленных камер
    known_paths = paths_from_sources(CAMERAS.values())  # их RTSP-пути (напр. /stream1)
    found = discover_streams(use_onvif=DISCOVERY_USE_ONVIF,
                             use_scan=DISCOVERY_USE_SCAN,
                             onvif_timeout=DISCOVERY_ONVIF_TIMEOUT,
                             extra_subnets=extra_subnets, known_ips=known_ips,
                             known_paths=known_paths)
    existing = {str(v) for v in CAMERAS.values()}
    added = []
    for f in found:
        # Хост уже добавлен (по URL открытой камеры ИЛИ по IP — покрывает и
        # запароленные, добавленные ранее с логином в URL).
        if (f.get("rtsp_url") and f["rtsp_url"] in existing) or f["ip"] in known_ips:
            f["status"] = "exists"
            continue
        if f.get("requires_auth"):
            # Запароленная: автодобавить нельзя (нужны логин/пароль) — UI спросит их.
            f["status"] = "locked"
            continue
        f["status"] = "new"
        if add:
            name = _unique_cam_name(f["name"])
            add_camera(name, f["rtsp_url"])
            f["added_as"] = name
            f["status"] = "added"
            added.append(name)
    return {"found": found, "added": added}


def add_authenticated_camera(ip: str, username: str, password: str,
                             port: int = 554, name: str | None = None) -> dict:
    """Подобрать рабочий RTSP-URL для запароленной камеры (ip + логин/пароль),
    перебрав типовые пути, и добавить её. Возвращает {ok, rtsp_url?, added_as?,
    error?}. Логин/пароль попадают в URL источника (URL-кодируются)."""
    from backend.discovery import probe_rtsp_auth, paths_from_sources, name_for_ip, merge_paths
    if not ip:
        return {"ok": False, "error": "Не указан IP камеры"}
    # Пути уже добавленных камер пробуем первыми (часто все камеры одного вендора).
    paths = merge_paths(paths_from_sources(CAMERAS.values()))
    url = probe_rtsp_auth(ip, username, password, port=port, paths=paths)
    if not url:
        return {"ok": False, "error": "Поток не открылся с этими логином и паролем"}
    if str(url) in {str(v) for v in CAMERAS.values()}:
        return {"ok": False, "error": "Камера с таким URL уже добавлена"}
    cam_name = _unique_cam_name((name or "").strip() or name_for_ip(ip))
    add_camera(cam_name, url)
    return {"ok": True, "rtsp_url": url, "added_as": cam_name}


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
# Последняя категория кадра по камере — чтобы метрика событий считала СОБЫТИЯ
# (смены категории), а не каждый кадр (иначе frigate_events_total раздувался).
_last_event_category: dict[str, str] = {}
# Состав людей с пропуском в зоне, для которых уже проговорена спокойная отметка
# (cam_id → set global_id). Чтобы не повторять «причин для внимания нет» каждый
# кулдаун — озвучиваем только при ВХОДЕ нового человека с пропуском в зону.
_voice_approved_seen: dict[str, set] = {}

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
            _apply_class_names(ym, model_path)
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


def process_frame(frame, cam_id: str, face_worker=None, det_model=None, det_pose=None,
                  precomputed_detection: Optional[Dict[str, Any]] = None):
    from backend.config import DETECT_MODES
    # Модели на камеру (для параллельных потоков детекции); по умолчанию —
    # глобальные (обратная совместимость с /upload и тестами).
    det_model = det_model if det_model is not None else model
    det_pose = det_pose if det_pose is not None else pose_model
    if not any(DETECT_MODES.values()):
        # Все режимы выключены — детекция не выполняется, но стрим продолжается:
        # отдаём сырой кадр без оверлеев. Кортеж из 7 элементов (как в основной
        # ветке) — иначе воркер падал на распаковке и переставал писать кадры в
        # annotated_buffers → /video_frame отдавал 204 → фронт «NO SIGNAL».
        return frame, f"{datetime.now().strftime('%H:%M:%S')} [{cam_id}] Детекция отключена", "норма", [], {}, [], []
    state.cleanup_stale_tracks()
    # Батч-режим: детекция уже выполнена централизованно — используем готовый результат.
    # Одиночный режим (/upload, тесты, одна камера): вызываем run_detection здесь.
    if precomputed_detection is not None:
        detected = precomputed_detection
    else:
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
    detect_people = DETECT_MODES.get("people", True)
    detect_faces_mode = DETECT_MODES.get("faces", True)
    # Режим «только люди»: СИЗ и лица выключены — жест/пропуск/тело не нужны.
    people_only = detect_people and not ppe_on and not detect_faces_mode
    # Чистый кадр ДО любой отрисовки нужен И для body Re-ID (рамки/заливка зоны
    # исказили бы цвета одежды), И для детекции жеста: контурный анализ кисти в
    # _is_ok_by_contour чувствителен к нарисованным оверлеям и полупрозрачной
    # заливке опасной зоны. Копию берём, только когда она реально используется —
    # людей детектим (жест/тело идут внутри ветки detect_people) и не режим
    # «только люди» (там жест/тело отключены).
    clean_frame = (frame.copy()
                   if (detected["persons"] and detect_people and not people_only)
                   else None)
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
    # Нарушители для голосового предупреждения: (имя, [отсутствующие СИЗ]).
    # Собираем ПОПЕРСОННО (имя и его собственный список missing привязаны к
    # одному человеку), чтобы не приписывать чужие нарушения первому в кадре.
    voice_violators: list[tuple[str, list[str]]] = []
    # Люди с активным пропуском, стоящие в зоне: (global_id, имя). Для спокойной
    # голосовой отметки «в СИЗ, причин для внимания нет» (озвучивается при входе).
    voice_approved: list[tuple[int, str]] = []
    # detect_people / detect_faces_mode / people_only вычислены выше (нужны для
    # clean_frame). Режим «только люди» (СИЗ и лица выключены): людей рисуем
    # нейтральной рамкой без статусов/пропуска, а жест «ОК» не запускаем — иначе
    # при пустом наборе требуемых СИЗ «пропуск» из-за нестабильных global_id
    # (лица выкл.) разъезжался «на всех».
    if detected["persons"] and detect_people:
        msg_parts.append(f"Людей: {persons_count}")
        face_embeddings = None
        if face_worker is not None and detect_faces_mode:
            face_data = face_worker.get_faces()
            face_embeddings = match_faces_to_persons(detected["persons"], face_data)
        # Дескрипторы тел (одежда/силуэт) с ЧИСТОГО кадра — для опознания «со спины».
        # Батчем: для OSNet это один инференс на кадр (а не на человека). clean_frame
        # теперь берётся и ради жеста, поэтому body Re-ID гейтим явно (распознаватель
        # активен и включены лица), а не по наличию clean_frame.
        body_embs = (body_recognizer.extract_batch(clean_frame, detected["persons"])
                     if (body_recognizer is not None and detect_faces_mode
                         and clean_frame is not None) else None)
        for idx, pbox in enumerate(detected["persons"]):
            track_id = person_track_ids[idx] if idx < len(person_track_ids) else -1
            if track_id < 0:
                track_id = idx
            face_info = (face_embeddings or [(None, 0.0)])[idx] if face_embeddings else (None, 0.0)
            face_emb, face_quality = face_info
            body_emb = body_embs[idx] if body_embs else None
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
            # Pose-инференс жеста дорогой — запускаем только для неодобренных,
            # вне кулдауна И не чаще GESTURE_CHECK_INTERVAL на личность (троттлинг
            # должен идти ПОСЛЕДНИМ в конъюнкции — у него побочный эффект).
            # global_id > 0: для неопознанной личности (gid=0 — общий sentinel)
            # жест не проверяем, иначе выданный пропуск и кулдаун жеста делятся
            # на ВСЕХ неопознанных. Детекция — по ЧИСТОМУ кадру (clean_frame),
            # без рамок/заливки зоны, иначе контурный анализ кисти искажается.
            gesture_ok = (
                detect_ok_gesture(clean_frame if clean_frame is not None else frame,
                                  pbox, det_pose)
                if (not people_only and global_id > 0 and not approved
                    and state.can_gesture(global_id)
                    and state.should_run_gesture(global_id))
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
            if people_only:
                # Только люди: нейтральная рамка без текста статусов/пропуска.
                frame = draw_person(frame, pbox, "", False, False, False)
            else:
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
                # Реальный нарушитель для голосовой озвучки: в опасной зоне, без
                # пропуска, не хватает именно ЕГО требуемых СИЗ. Имя и missing — одного
                # человека (иначе озвучка путала людей: «нет каски» на человеке в каске).
                if (in_danger and not approved and not fully_equipped
                        and missing and DETECT_MODES.get("ppe", True)):
                    voice_violators.append((person_name, list(missing)))
                # Человек с активным пропуском в зоне — для спокойной голосовой отметки.
                if in_danger and approved:
                    voice_approved.append((global_id, person_name))
            if people_only:
                # Только люди: в лог без статусов СИЗ/зоны/пропуска (счётчик
                # «Людей: N» уже добавлен выше).
                continue
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
    # Легенда описывает СИЗ/зоны/пропуск — в режиме «только люди» не нужна.
    if not people_only:
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
    return frame, message, category, global_ids, statuses, voice_violators, voice_approved


_NO_SIGNAL_CACHE: dict[tuple, bytes] = {}


def _no_signal_jpeg(width: int = 1280, height: int = 720) -> bytes:
    """JPEG-заставка «NO SIGNAL» (чёрный кадр с текстом). Кэшируется по размеру —
    рисуем один раз на разрешение. Текст ASCII → cv2.putText (без PIL/кириллицы)."""
    key = (width, height)
    cached = _NO_SIGNAL_CACHE.get(key)
    if cached is not None:
        return cached
    import numpy as np
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    text = "NO SIGNAL"
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = max(1.0, width / 640.0)
    thickness = max(2, int(scale * 1.5))
    (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)
    org = ((width - tw) // 2, (height + th) // 2)
    cv2.putText(frame, text, org, font, scale, (60, 60, 200), thickness, cv2.LINE_AA)
    ok, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    data = buffer.tobytes() if ok else b""
    _NO_SIGNAL_CACHE[key] = data
    return data


def generate_live_feed(cam_id: str = "cam1"):
    ann_buf = annotated_buffers.get(cam_id)
    if ann_buf is None:
        return
    raw_buf = frame_buffers.get(cam_id)
    consecutive_errors = 0
    last_dims = (1280, 720)
    while state.live_active:
        # Камера «отвалилась» (capture не пишет новых кадров) — шлём «NO SIGNAL»
        # вместо застывшего последнего кадра, как /video_frame отдаёт 204. Иначе
        # MJPEG держал бы замороженный кадр, выдавая потерю связи за «живой» поток.
        if raw_buf is not None and raw_buf.age() > STREAM_STALE_SEC:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n'
                   + _no_signal_jpeg(*last_dims) + b'\r\n')
            time.sleep(0.5)  # троттлинг заставки (не чаще 2 кадров/с)
            continue
        ann_buf.wait(timeout=2.0)
        frame = ann_buf.read()
        if frame is None:
            continue
        try:
            ret, buffer = cv2.imencode('.jpg', frame)
            if not ret:
                continue
            last_dims = (frame.shape[1], frame.shape[0])
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
    global _batch_worker
    if state.live_active:
        stop_live()
        time.sleep(0.5)
    state.clear_log()
    state.clear_tracks()
    state.clear_notifications()
    _motion_detectors.clear()
    _voice_approved_seen.clear()
    # Пер-сессионные буферы событий: иначе пред-буфер первого клипа новой сессии
    # содержал бы застывшие кадры предыдущей (другая сцена/время), а счётчик
    # событий не зафиксировал бы первую категорию.
    _frame_prebuf.clear()
    _event_recordings.clear()
    _last_event_category.clear()
    for buf in annotated_buffers.values():
        buf.clear()
    state.live_active = True
    for cam_id in CAMERAS:
        _init_camera_resources(cam_id, CAMERAS[cam_id])
        camera_captures[cam_id].start()
    start_face_workers()

    # Батч-инференс: включаем при ≥2 камерах (или при BATCH_INFERENCE=1).
    # Один model.track(batch) вместо N последовательных GPU-вызовов.
    cam_count = len(CAMERAS)
    if BATCH_INFERENCE_ENABLED and cam_count >= 2:
        _batch_worker = BatchDetectionWorker(model)
        _batch_worker.start()
        for cam_id in CAMERAS:
            _batch_worker.register_camera(cam_id)
    else:
        _batch_worker = None
        if cam_count < 2:
            print("[BatchInference] Одна камера — батчинг не нужен, используется прямой инференс")

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
    mode = "батч" if _batch_worker is not None else "прямой"
    print(f"Детекция запущена на {cam_count} камерах (режим: {mode})")


def stop_live():
    global _batch_worker
    if not state.live_active:
        return
    state.live_active = False
    # Останавливаем батч-воркер до join потоков детекции: потоки заблокированы
    # на _batch_worker.submit() — stop() разблокирует их через _result_events.
    if _batch_worker is not None:
        _batch_worker.stop()
        _batch_worker = None
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
    # Гарантированный сброс выученного за сессию на диск при остановке.
    if state.gallery is not None:
        state.gallery.flush()
    print("Детекция остановлена")


def _heartbeat_loop():
    """Отдельный поток: периодический MQTT-heartbeat и отметка в метриках.
    Вынесен из петли детекции, т.к. петель теперь несколько (по камере)."""
    metrics = get_metrics()
    publisher = get_publisher()
    last_emb_prune = time.time()
    last_flush = time.time()
    while state.live_active:
        metrics.heartbeat()
        if publisher is not None:
            publisher.publish_heartbeat({
                "ts": time.time(), "uptime_seconds": metrics.uptime_seconds(),
                "cameras": len(CAMERAS),
            })
        # Состаривание памяти по таймеру (на своём интервале, чтобы не дёргать
        # диск на каждом heartbeat — _save только при реальном удалении).
        if (state.gallery is not None and time.time() - last_emb_prune >= REID_EMB_CLEAN_INTERVAL):
            state.gallery.prune_old_embeddings(REID_EMB_MAX_AGE_DAYS)
            state.gallery.prune_old_bodies(REID_BODY_MAX_AGE_DAYS)
            last_emb_prune = time.time()
        # Сброс выученного за сессию (липкие лица + дескрипторы тела) на диск,
        # только если что-то менялось — чтобы узнавание переживало перезапуск.
        if (state.gallery is not None and time.time() - last_flush >= REID_FLUSH_INTERVAL):
            state.gallery.flush()
            last_flush = time.time()
        # Дробный сон, чтобы быстро реагировать на stop_live.
        slept = 0.0
        while state.live_active and slept < MQTT_HEARTBEAT_INTERVAL:
            time.sleep(0.5)
            slept += 0.5


def _violator_global_id(global_ids: list, statuses: dict) -> int:
    """global_id первого РЕАЛЬНОГО нарушителя, а не просто первого человека в кадре.

    statuses и global_ids идут в одном порядке людей (оба строятся циклом по
    detected["persons"]). Строчная буква в первых трёх символах компактного
    статуса (КМЖ) = отсутствует требуемый СИЗ → это нарушитель. Фоллбэк, если
    нарушитель не вычленён, — первый global_id (старое поведение)."""
    status_list = list(statuses.values())
    for i, gid in enumerate(global_ids):
        st = status_list[i] if i < len(status_list) else ""
        if len(st) >= 3 and any(c.islower() for c in st[:3]):
            return gid
    return global_ids[0] if global_ids else 0


def _camera_detection_worker(cam_id: str):
    """Поток детекции ОДНОЙ камеры.

    Два режима (выбираются при запуске по BATCH_INFERENCE_ENABLED):

    Батч-режим (≥2 камеры, GPU): кадр сдаётся в BatchDetectionWorker,
    поток блокируется до готового detection-словаря. Все камеры обрабатываются
    одним model.track(batch) — GPU занят непрерывно, throughput ×N.

    Одиночный режим (1 камера / CPU): каждый поток вызывает свою YOLO-модель
    напрямую (ByteTrack изолирован на уровне экземпляра модели).
    """
    metrics = get_metrics()
    publisher = get_publisher()
    use_batch = _batch_worker is not None
    # Per-camera модели: в батч-режиме YOLO для детекции не используется
    # (батч-воркер делает это централизованно), но pose-модель нужна всегда
    # для жестов (throttled predict на кроп, без ByteTrack).
    det_model, det_pose = _get_cam_models(cam_id)
    while state.live_active and cam_id in CAMERAS:
        raw_buf = frame_buffers.get(cam_id)
        out_buf = annotated_buffers.get(cam_id)
        if raw_buf is None or out_buf is None:
            return
        # Блокируемся до нового кадра (без busy-loop); по таймауту проверяем флаги.
        raw_buf.wait(timeout=1.0)
        frame = raw_buf.read()
        if frame is None:
            continue

        # Камера «отвалилась» (capture не пишет новые кадры) — не гоняем YOLO по
        # застывшему кадру: пропускаем, annotated_buffer устаревает, /video_frame
        # отдаст 204 → фронт покажет «NO SIGNAL» вместо замороженного кадра.
        if raw_buf.age() > STREAM_STALE_SEC:
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
            # Батч-режим: сдаём кадр в централизованный воркер и ждём detection-словарь.
            # Одиночный режим: precomputed_detection=None → process_frame вызовет run_detection.
            precomputed = _batch_worker.submit(cam_id, frame) if use_batch else None
            annotated, message, category, global_ids, statuses, voice_violators, voice_approved = process_frame(
                frame, cam_id, face_worker=face_workers.get(cam_id),
                det_model=det_model, det_pose=det_pose,
                precomputed_detection=precomputed)
            metrics.record_frame(cam_id, (time.time() - _t0) * 1000.0)
            # Считаем СОБЫТИЕ, а не кадр: инкремент только при смене категории для
            # камеры (иначе frigate_events_total рос на каждом кадре «нормы»).
            if _last_event_category.get(cam_id) != category:
                metrics.record_event(category)
                _last_event_category[cam_id] = category
            out_buf.write(annotated)

            if publisher is not None:
                people = len(statuses)
                # Строчная буква в позициях КМЖ = отсутствует СИЗ → нарушитель.
                violations = sum(1 for v in statuses.values()
                                 if len(v) >= 3 and any(c.islower() for c in v[:3]))
                publisher.publish_detection(cam_id, people, violations,
                                            max(0, people - violations), category)

            # ── Голосовое сопровождение зоны (троттлинг по камере в push_voice_alert) ──
            # Приоритет — нарушению: voice_violators несёт (имя, его СИЗ) попермонно
            # (имя и missing одного человека, без агрегации по чужим). Пушим на КАЖДОМ
            # кадре зонного нарушения — иначе вход в зону без СИЗ не озвучивался бы,
            # если запись уже стартовала на кадре «вне зоны».
            voice_text = _build_voice_text(voice_violators)
            if voice_text:
                state.push_voice_alert(cam_id, voice_text)
                _voice_approved_seen[cam_id] = set()  # сбрасываем спокойную отметку
            else:
                # Нарушителей нет. Если в зоне есть человек с активным пропуском (в
                # СИЗ) — спокойная отметка «причин для внимания нет», но ТОЛЬКО при
                # входе нового (смена состава), чтобы не повторять её каждый кулдаун.
                appr_ids = {gid for gid, _ in voice_approved}
                prev_ids = _voice_approved_seen.get(cam_id, set())
                if appr_ids - prev_ids:  # появился новый человек с пропуском в зоне
                    calm = _build_approved_voice_text([n for _, n in voice_approved])
                    if calm:
                        state.push_voice_alert(cam_id, calm)
                _voice_approved_seen[cam_id] = appr_ids

            # Запись клипа триггерим ТОЛЬКО зонным нарушением (тем же условием,
            # что наполняет voice_violators) — иначе нарушение ВНЕ зоны (голос
            # молчит) непрерывно писало бы клипы, хотя система "молчит" голосом.
            # category/логи/метрики/MQTT остаются на общей картине (has_any_violation).
            is_violation = bool(voice_violators)
            rec = _event_recordings.get(cam_id)
            if is_violation:
                gid = _violator_global_id(global_ids, statuses)
                person_name = state.get_person_name(gid, cam_id, has_face=True) if gid else ""
                if rec is None or not rec.get('active'):
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

            # rsplit по последнему ':' — track_id корректно извлекается, даже если
            # имя камеры само содержит двоеточие (ключ = f"{cam_id}:{track_id}").
            any_changed = any(state.is_status_changed(cam_id, int(k.rsplit(":", 1)[1]), v) for k, v in statuses.items())
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
