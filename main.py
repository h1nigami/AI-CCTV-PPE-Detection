import cv2
import threading
import time
import traceback
from datetime import datetime
import torch
from ultralytics import YOLO

from config import (
    MODEL_PATH, POSE_MODEL_PATH, CLASS_NAMES, CAMERAS, CONF_THRESH,
    REID_GALLERY_PATH, REID_DET_SIZE, REID_FRAME_SKIP
)
from camera import FrameBuffer, CameraCapture
from detection import run_detection, get_danger_zone, has_item_on_person, is_in_danger_zone
from gestures import detect_ok_gesture, detect_raised_hand
from visualization import (
    draw_danger_zone, draw_person, draw_hint,
    draw_legend, draw_stats_panel, put_text, FONT_LARGE
)
from printer import print_frame
from state import DetectionState, LogEntry

# ── Модели (одни на всех, YOLO thread-safe при inference) ──
DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'
print(f"Используется устройство: {DEVICE}")

model      = YOLO(str(MODEL_PATH))
model.to(DEVICE)
model.model.names = CLASS_NAMES
pose_model = YOLO(str(POSE_MODEL_PATH))
pose_model.to(DEVICE)

# ── Re-ID (распознавание лиц) ──
face_recognizer = None
try:
    from reid import FaceRecognizer, FaceRecognitionWorker, match_faces_to_persons
    face_recognizer = FaceRecognizer(model_name='buffalo_l', det_size=REID_DET_SIZE)
except Exception as e:
    print(f"[ReID] InsightFace не загружен: {e}. Re-ID отключён.")

# ── Глобальный стейт ──
state = DetectionState()
state.init_gallery(REID_GALLERY_PATH)

# ── Буфер и захват для каждой камеры ──
frame_buffers: dict[str, FrameBuffer]     = {}
annotated_buffers: dict[str, FrameBuffer] = {}
camera_captures: dict[str, CameraCapture]  = {}

for cam_id, url in CAMERAS.items():
    buf = FrameBuffer()
    frame_buffers[cam_id]     = buf
    annotated_buffers[cam_id] = FrameBuffer()
    camera_captures[cam_id]   = CameraCapture(buffer=buf, source=url)

# ── Потоки детекции ──
detection_threads: dict[str, threading.Thread] = {}

# ── Асинхронное распознавание лиц ──
face_workers: dict[str, FaceRecognitionWorker] = {}


# ─────────────────────────────────────────────
#  Общая обработка одного кадра
# ─────────────────────────────────────────────

def process_frame(frame, cam_id: str, face_worker=None):
    """
    Детектирует СИЗ, опасную зону, жесты.
    Возвращает (annotated_frame, log_message, category, [global_ids]).
    """
    detected = run_detection(frame, model)
    danger_zone = get_danger_zone(detected["cones"])

    # ── Рисуем зону и СИЗ боксы ──
    frame = draw_danger_zone(frame, danger_zone)

    for box in detected["helmets"]:
        x1,y1,x2,y2 = map(int, box)
        cv2.rectangle(frame, (x1,y1),(x2,y2), (0,255,0), 2)
        frame = put_text(frame, "Каска", (x1, max(0,y1-20)), color=(0,255,0))

    for box in detected["masks"]:
        x1,y1,x2,y2 = map(int, box)
        cv2.rectangle(frame, (x1,y1),(x2,y2), (255,255,0), 2)
        frame = put_text(frame, "Маска", (x1, max(0,y1-20)), color=(255,255,0))

    for box in detected["vests"]:
        x1,y1,x2,y2 = map(int, box)
        cv2.rectangle(frame, (x1,y1),(x2,y2), (255,165,0), 2)
        frame = put_text(frame, "Жилет", (x1, max(0,y1-20)), color=(255,165,0))

    for box in detected["cones"]:
        x1,y1,x2,y2 = map(int, box)
        cv2.rectangle(frame, (x1,y1),(x2,y2), (0,128,255), 2)
        frame = put_text(frame, "Конус", (x1, max(0,y1-20)), color=(0,128,255))

    # ── Люди ──
    persons_count   = len(detected["persons"])
    approved_count  = 0
    violation_count = 0
    has_any_violation = False

    msg_parts = [f"{datetime.now().strftime('%H:%M:%S')} [{cam_id}]"]
    global_ids = []

    if detected["persons"]:
        msg_parts.append(f"Людей: {persons_count}")

        # Асинхронное распознавание лиц
        face_embeddings = None
        if face_worker is not None:
            face_data = face_worker.get_faces()
            face_embeddings = match_faces_to_persons(detected["persons"], face_data)

        for idx, pbox in enumerate(detected["persons"]):
            face_emb = (face_embeddings or [None])[idx] if face_embeddings else None
            global_id = state.get_global_id(idx, cam_id, face_embedding=face_emb, person_box=pbox)
            global_ids.append(global_id)

            has_helmet = any(has_item_on_person(pbox, h) for h in detected["helmets"])
            has_mask   = any(has_item_on_person(pbox, m) for m in detected["masks"])
            has_vest   = any(has_item_on_person(pbox, v) for v in detected["vests"])
            in_danger  = is_in_danger_zone(pbox, danger_zone)
            approved   = state.is_approved(pbox, cam_id, global_id=global_id)

            fully_equipped = has_helmet and has_mask and has_vest
            missing = [n for f,n in [(has_helmet,"каска"),(has_mask,"маска"),(has_vest,"жилет")] if not f]

            # Жест ОК → пропуск
            if fully_equipped and not approved:
                if detect_ok_gesture(frame, pbox, pose_model):
                    state.approve(pbox, cam_id, global_id=global_id)
                    approved = True
                    state.set_gesture_detected()

            if not fully_equipped and not approved:
                if detect_ok_gesture(frame, pbox, pose_model):
                    frame = put_text(frame, "ОДЕНЬТЕ СИЗ",
                         (frame.shape[1]//2 - 150, frame.shape[0]//2),
                         color=(0,215,255), font=FONT_LARGE)

            # Поднятая рука → печать
            #if detect_raised_hand(frame, pbox, pose_model):
            #    all_statuses = []
            #    for pb in detected["persons"]:
            #        hh = any(has_item_on_person(pb, h) for h in detected["helmets"])
            #        mm = any(has_item_on_person(pb, m) for m in detected["masks"])
            #        vv = any(has_item_on_person(pb, v) for v in detected["vests"])
            #        miss = ", ".join(n for f,n in [(hh,"каска"),(mm,"маска"),(vv,"жилет")] if not f)
            #        all_statuses.append("Все СИЗ" if not miss else f"Нет: {miss}")
            #    if print_frame(frame, all_statuses):
            #        state.set_print_triggered()

            if approved:   approved_count += 1
            elif not fully_equipped: violation_count += 1

            ppe = f"{'К' if has_helmet else '!К'} {'М' if has_mask else '!М'} {'Ж' if has_vest else '!Ж'}"

            # Имя человека (через Re-ID или псевдоним)
            person_name = state.get_person_name(global_id, cam_id, face_emb is not None)
            if approved:    label = f"{person_name} ПРОПУСК | {ppe}"
            elif in_danger: label = f"{person_name} ОПАСНАЯ ЗОНА | {ppe}"
            else:           label = f"{person_name} Вне зоны | {ppe}"

            frame = draw_person(frame, pbox, label, in_danger, not fully_equipped, approved)

            if fully_equipped and not approved and in_danger:
                frame = draw_hint(frame, pbox)

            # Строим сообщение лога (с ppe для фронта)
            part = f"{person_name} [{ppe}]: "
            if approved:
                part += "ПРОПУСК | Все СИЗ + ОК"
            elif in_danger:
                part += "ОПАСНАЯ ЗОНА | "
                part += "Все СИЗ — покажи ОК" if fully_equipped else f"Нет СИЗ: {', '.join(missing)}"
                if not fully_equipped: has_any_violation = True
            else:
                part += "Вне зоны | "
                part += "Все СИЗ на месте" if fully_equipped else f"Нет СИЗ: {', '.join(missing)}"
                if not fully_equipped: has_any_violation = True
            msg_parts.append(part)
    else:
        msg_parts.append("Людей не обнаружено")

    if danger_zone is not None:
        msg_parts.append(f"Зона активна ({len(detected['cones'])} конуса)")

    # Панель статистики
    #frame = draw_stats_panel(
        #frame,
        #persons_count    = persons_count,
        #approved_count   = approved_count,
        #violation_count  = violation_count,
        #gesture_detected = state.is_gesture_active(),
        #x=20, y=20
    #)

    if state.is_print_active():
        frame = put_text(frame, "ОТПРАВЛЕНО НА ПЕЧАТЬ",
                         (frame.shape[1]//2 - 150, frame.shape[0]//2),
                         color=(0,215,255), font=FONT_LARGE)

    frame = draw_legend(frame)

    message  = " | ".join(msg_parts)
    category = "нарушение" if has_any_violation else \
               "внимание"  if danger_zone is not None and detected["persons"] else "норма"

    return frame, message, category, global_ids


# ─────────────────────────────────────────────
#  Detection worker — один на камеру
# ─────────────────────────────────────────────

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
                id        = str(datetime.now().timestamp()),
                timestamp = datetime.now().strftime('%H:%M:%S'),
                message   = message,
                category  = category,
                cam_id    = cam_id,
                global_id = gid,
            ))
            print(message)

        except Exception as e:
            print(f"[{cam_id}] Ошибка детекции: {e}")
            traceback.print_exc()

        elapsed = time.time() - t0
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)


# ─────────────────────────────────────────────
#  Live feed — один генератор на камеру
# ─────────────────────────────────────────────

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


# ─────────────────────────────────────────────
#  Управление
# ─────────────────────────────────────────────

def start_live():
    if state.live_active:
        stop_live()
        time.sleep(0.5)

    state.clear_log()
    for buf in annotated_buffers.values():
        buf.clear()

    state.live_active = True

    for cam_id in CAMERAS:
        camera_captures[cam_id].start()
        if face_recognizer is not None:
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

    for cam_id in CAMERAS:
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
    cam_ids = list(CAMERAS.keys())
    while state.live_active:
        had_any = False
        for cam_id in cam_ids:
            if not state.live_active:
                return
            raw_buf = frame_buffers[cam_id]
            out_buf = annotated_buffers[cam_id]
            frame = raw_buf.read()
            if frame is None:
                continue
            had_any = True
            try:
                annotated, message, category, global_ids = process_frame(
                    frame.copy(), cam_id, face_worker=face_workers.get(cam_id))
                out_buf.write(annotated)
                gid = global_ids[0] if global_ids else 0
                state.add_log(LogEntry(
                    id        = str(datetime.now().timestamp()),
                    timestamp = datetime.now().strftime('%H:%M:%S'),
                    message   = message,
                    category  = category,
                    cam_id    = cam_id,
                    global_id = gid,
                ))
                print(message)
            except Exception as e:
                print(f"[{cam_id}] Ошибка детекции: {e}")
                traceback.print_exc()
        if not had_any:
            time.sleep(0.01)