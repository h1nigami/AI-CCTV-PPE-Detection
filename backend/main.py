from __future__ import annotations
import cv2
import threading
import time
import traceback
from datetime import datetime
from ultralytics import YOLO
import torch

cv2.INTER_NEAREST_EXACT = getattr(cv2, 'INTER_NEAREST_EXACT', cv2.INTER_NEAREST)

from backend.config import (
    MODEL_PATH, POSE_MODEL_PATH, CLASS_NAMES, CAMERAS, CONF_THRESH,
    REID_GALLERY_PATH, REID_DET_SIZE, REID_FRAME_SKIP, REID_MAX_AGE_DAYS,
    get_camera_config,
)
from backend.capture.buffer import FrameBuffer
from backend.capture.camera import CameraCapture
from backend.detection.engine import run_detection, get_danger_zone, has_item_on_person, is_in_danger_zone
from backend.gestures.detector import detect_ok_gesture, detect_raised_hand
from backend.visualization.renderer import (
    draw_danger_zone, draw_person, draw_hint,
    draw_legend, draw_stats_panel, put_text, FONT_LARGE
)
from backend.core.state import DetectionState, LogEntry

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


def add_camera(cam_id: str, source: str | int):
    from backend.config import save_cameras
    CAMERAS[cam_id] = source
    save_cameras()
    _init_camera_resources(cam_id, source)
    if state.live_active:
        camera_captures[cam_id].start()
        if face_recognizer is not None:
            from backend.reid.recognizer import FaceRecognitionWorker
            fw = FaceRecognitionWorker(frame_buffers[cam_id], face_recognizer, REID_FRAME_SKIP)
            fw.start()
            face_workers[cam_id] = fw
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
    save_cameras()
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
    for dct in (frame_buffers, annotated_buffers, camera_captures, face_workers):
        if old_id in dct:
            dct[new_id] = dct.pop(old_id)
    from backend.config import save_cameras
    save_cameras()
    print(f"[Камера] Переименована: {old_id} -> {new_id}")
    return True


detection_threads: dict[str, threading.Thread] = {}
face_workers: dict[str, 'FaceRecognitionWorker'] = {}


def process_frame(frame, cam_id: str, face_worker=None):
    from backend.config import DETECT_MODES
    state.cleanup_stale_tracks()
    detected = run_detection(frame, model)
    danger_zone = get_danger_zone(detected["cones"]) if DETECT_MODES.get("ppe", True) else None
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
    persons_count = len(detected["persons"])
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
        person_track_ids = detected.get("person_track_ids", [])
        for idx, pbox in enumerate(detected["persons"]):
            track_id = person_track_ids[idx] if idx < len(person_track_ids) else -1
            if track_id < 0:
                track_id = idx
            face_info = (face_embeddings or [(None, 0.0)])[idx] if face_embeddings else (None, 0.0)
            face_emb, face_quality = face_info
            global_id = state.get_global_id(track_id, cam_id,
                                            face_embedding=face_emb,
                                            quality=face_quality,
                                            person_box=pbox)
            global_ids.append(global_id)
            has_helmet = any(has_item_on_person(pbox, h) for h in detected["helmets"]) if DETECT_MODES.get("ppe", True) else False
            has_mask = any(has_item_on_person(pbox, m) for m in detected["masks"]) if DETECT_MODES.get("ppe", True) else False
            has_vest = any(has_item_on_person(pbox, v) for v in detected["vests"]) if DETECT_MODES.get("ppe", True) else False
            in_danger = is_in_danger_zone(pbox, danger_zone) if danger_zone is not None else False
            approved = state.is_approved(pbox, cam_id, global_id=global_id)
            fully_equipped = has_helmet and has_mask and has_vest
            missing = [n for f, n in [(has_helmet, "каска"), (has_mask, "маска"), (has_vest, "жилет")] if not f] if DETECT_MODES.get("ppe", True) else []
            ppe = f"{'К' if has_helmet else '!К'} {'М' if has_mask else '!М'} {'Ж' if has_vest else '!Ж'}" if DETECT_MODES.get("ppe", True) else ""
            person_name = state.get_person_name(global_id, cam_id, face_emb is not None and detect_faces_mode)
            gesture_ok = (
                detect_ok_gesture(frame, pbox, pose_model)
                if not approved and state.can_gesture(global_id)
                else False
            )
            if gesture_ok:
                state.set_gesture_time(global_id)
                if fully_equipped:
                    state.approve(pbox, cam_id, global_id=global_id)
                    approved = True
                    state.set_gesture_detected()
                else:
                    frame = put_text(frame, "ОДЕНЬТЕ СИЗ",
                                     (frame.shape[1] // 2 - 150, frame.shape[0] // 2),
                                     color=(0, 215, 255), font=FONT_LARGE)
            if approved:
                approved_count += 1
            elif not fully_equipped and DETECT_MODES.get("ppe", True):
                violation_count += 1
            if approved:
                label = f"{person_name} ПРОПУСК | {ppe}" if ppe else f"{person_name} ПРОПУСК"
            elif in_danger:
                label = f"{person_name} ОПАСНАЯ ЗОНА | {ppe}" if ppe else f"{person_name} ОПАСНАЯ ЗОНА"
            else:
                label = f"{person_name} Вне зоны | {ppe}" if ppe else f"{person_name} Вне зоны"
            frame = draw_person(frame, pbox, label, in_danger, not fully_equipped and DETECT_MODES.get("ppe", True), approved)
            if fully_equipped and not approved and in_danger:
                frame = draw_hint(frame, pbox)
            part = f"{person_name}"
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
        "внимание" if danger_zone is not None and detected["persons"] else "норма"
    return frame, message, category, global_ids


def detection_worker(cam_id: str):
    raw_buf = frame_buffers[cam_id]
    out_buf = annotated_buffers[cam_id]
    frame_idx = 0
    min_interval = 0.05
    while state.live_active:
        t0 = time.time()
        frame = raw_buf.read()
        if frame is None:
            time.sleep(0.01)
            continue
        try:
            annotated, message, category, global_ids = process_frame(
                frame.copy(), cam_id, face_worker=face_workers.get(cam_id))
            frame_idx += 1
            out_buf.write(annotated)
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
        elapsed = time.time() - t0
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)


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
    for buf in annotated_buffers.values():
        buf.clear()
    state.live_active = True
    for cam_id in CAMERAS:
        _init_camera_resources(cam_id, CAMERAS[cam_id])
        camera_captures[cam_id].start()
        if face_recognizer is not None and cam_id not in face_workers:
            from backend.reid.recognizer import FaceRecognitionWorker
            fw = FaceRecognitionWorker(frame_buffers[cam_id], face_recognizer, REID_FRAME_SKIP)
            fw.start()
            face_workers[cam_id] = fw
    t = threading.Thread(target=detection_loop, daemon=True)
    detection_threads["main"] = t
    t.start()
    print(f"Детекция запущена на {len(CAMERAS)} камерах")


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
    for fw in list(face_workers.values()):
        fw.stop()
    face_workers.clear()
    for buf in annotated_buffers.values():
        buf.clear()
    print("Детекция остановлена")


def detection_loop():
    """Основной цикл детекции. Проходит по всем камерам,
    делает YOLO + аннотацию на каждом кадре.
    """
    while state.live_active:
        had_any = False
        for cam_id in list(CAMERAS.keys()):
            if not state.live_active:
                return
            if cam_id not in frame_buffers:
                continue
            raw_buf = frame_buffers[cam_id]
            out_buf = annotated_buffers[cam_id]
            frame = raw_buf.read()
            if frame is None:
                continue
            had_any = True

            # Если детекция выключена — просто копируем raw кадр в аннотированный буфер
            if not get_camera_config(cam_id).get("detect_enabled", True):
                out_buf.write(frame)
                continue

            try:
                annotated, message, category, global_ids = process_frame(
                    frame, cam_id, face_worker=face_workers.get(cam_id))
                out_buf.write(annotated)
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
        if not had_any:
            time.sleep(0.01)
