from datetime import datetime
from ultralytics import YOLO

from config import MODEL_PATH, POSE_MODEL_PATH, CLASS_NAMES
from camera import FrameBuffer, CameraCapture
from detection import run_detection, get_danger_zone, has_item_on_person, is_in_danger_zone
from gestures import detect_ok_gesture
from visualization import draw_danger_zone, draw_person, draw_hint, draw_legend, draw_stats_panel
from state import DetectionState, LogEntry
import threading
import cv2

# ─── Инициализация ────────────────────────────
model      = YOLO(MODEL_PATH)
model.model.names = CLASS_NAMES
model.save("models/best.pt")

pose_model = YOLO(POSE_MODEL_PATH)

state        = DetectionState()
frame_buffer = FrameBuffer()
camera       = CameraCapture(buffer=frame_buffer)


# ─── Detection worker ─────────────────────────

def detection_worker():
    while state.live_active:
        frame_buffer.wait(timeout=1.0)
        frame = frame_buffer.read()
        if frame is None:
            continue

        try:
            detected    = run_detection(frame, model)
            danger_zone = get_danger_zone(detected["cones"])

            message           = f"{datetime.now().strftime('%H:%M:%S')} - "
            has_any_violation = False

            if detected["persons"]:
                message += f"Людей: {len(detected['persons'])} | "

                for idx, pbox in enumerate(detected["persons"]):
                    has_helmet = any(has_item_on_person(pbox, h) for h in detected["helmets"])
                    has_mask   = any(has_item_on_person(pbox, m) for m in detected["masks"])
                    has_vest   = any(has_item_on_person(pbox, v) for v in detected["vests"])
                    in_danger  = is_in_danger_zone(pbox, danger_zone)
                    approved   = state.is_approved(pbox)

                    fully_equipped = has_helmet and has_mask and has_vest
                    missing = [
                        name for flag, name in [
                            (has_helmet, "каска"),
                            (has_mask,   "маска"),
                            (has_vest,   "жилет"),
                        ] if not flag
                    ]

                    if fully_equipped and not approved:
                        if detect_ok_gesture(frame, pbox, pose_model):
                            state.approve(pbox)
                            approved = True

                    message += f"Чел.{idx + 1}: "
                    if approved:
                        message += "ПРОПУСК | Все СИЗ + ОК"
                    elif in_danger:
                        message += "ОПАСНАЯ ЗОНА | "
                        message += "Все СИЗ — покажи ОК" if fully_equipped \
                               else f"Нет СИЗ: {', '.join(missing)}"
                        if not fully_equipped:
                            has_any_violation = True
                    else:
                        message += "Вне зоны | "
                        message += "Все СИЗ на месте" if fully_equipped \
                               else f"Нет СИЗ: {', '.join(missing)}"
                        if not fully_equipped:
                            has_any_violation = True

                    if idx < len(detected["persons"]) - 1:
                        message += " | "
            else:
                message += "Людей не обнаружено"

            if danger_zone:
                message += f" | Зона активна ({len(detected['cones'])} конуса)"

            category = (
                "нарушение" if has_any_violation else
                "внимание"  if danger_zone and detected["persons"] else
                "норма"
            )

            state.add_log(LogEntry(
                id        = str(datetime.now().timestamp()),
                timestamp = datetime.now().strftime('%H:%M:%S'),
                message   = message,
                category  = category,
            ))
            print(message)

        except Exception as e:
            print(f"Ошибка детекции: {e}")


# ─── Live feed ────────────────────────────────

def generate_live_feed():
    while state.live_active:
        frame_buffer.wait(timeout=1.0)
        frame = frame_buffer.read()
        if frame is None:
            continue

        try:
            detected    = run_detection(frame, model)
            danger_zone = get_danger_zone(detected["cones"])

            frame = draw_danger_zone(frame, danger_zone)

            # Счётчики для панели
            persons_count   = len(detected["persons"])
            approved_count  = 0
            violation_count = 0
            gesture_now     = False  # жест был распознан на этом кадре

            for idx, pbox in enumerate(detected["persons"]):
                has_helmet = any(has_item_on_person(pbox, h) for h in detected["helmets"])
                has_mask   = any(has_item_on_person(pbox, m) for m in detected["masks"])
                has_vest   = any(has_item_on_person(pbox, v) for v in detected["vests"])
                in_danger  = is_in_danger_zone(pbox, danger_zone)
                approved   = state.is_approved(pbox)

                fully_equipped = has_helmet and has_mask and has_vest

                # Проверяем жест если в СИЗ и не одобрен
                if fully_equipped and not approved:
                    if detect_ok_gesture(frame, pbox, pose_model):
                        state.approve(pbox)
                        approved   = True
                        gesture_now = True  # показываем реакцию на кадре

                if approved:
                    approved_count += 1
                elif not fully_equipped:
                    violation_count += 1

                ppe = (
                    f"{'К' if has_helmet else '!К'} "
                    f"{'М' if has_mask   else '!М'} "
                    f"{'Ж' if has_vest   else '!Ж'}"
                )

                if approved:    label = f"Чел.{idx+1} ПРОПУСК | {ppe}"
                elif in_danger: label = f"Чел.{idx+1} ОПАСНАЯ ЗОНА | {ppe}"
                else:           label = f"Чел.{idx+1} Вне зоны | {ppe}"

                frame = draw_person(frame, pbox, label,
                                    in_danger, not fully_equipped, approved)

                if fully_equipped and not approved and in_danger:
                    frame = draw_hint(frame, pbox)

            # Рисуем панель статистики
            frame = draw_stats_panel(
                frame,
                persons_count   = persons_count,
                approved_count  = approved_count,
                violation_count = violation_count,
                gesture_detected = gesture_now,
            )

            frame = draw_legend(frame)

            ret, buffer = cv2.imencode('.jpg', frame)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

        except Exception as e:
            print(f"Ошибка кадра: {e}")
            break


# ─── Управление ───────────────────────────────

def start_live():
    if not state.live_active:
        state.live_active = True
        state.clear_log()
        camera.start()
        t = threading.Thread(target=detection_worker, daemon=True)
        t.start()
        print("Детекция запущена")


def stop_live():
    state.live_active = False
    camera.stop()
    print("Детекция остановлена")