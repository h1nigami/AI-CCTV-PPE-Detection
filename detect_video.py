from ultralytics import YOLO
import cv2
from datetime import datetime
import threading
import time
import numpy as np

model = YOLO("models/best.pt", verbose=True)
model.model.names = {
    0: "Каска",
    1: "Маска",
    2: "Без каски",
    3: "Без маски",
    4: "Без жилета",
    5: "Человек",
    6: "Конус безопасности",
    7: "Защитный жилет",
    8: "Техника",
    9: "Транспорт"
}
model.save("best.pt")
print(model.names)

# Global state
LIVE_FEED_ACTIVE = False
camera_released = True
DETECTION_LOG = []
detection_thread = None
cap = None


# ─────────────────────────────────────────────
#  Вспомогательные функции
# ─────────────────────────────────────────────

def has_item_on_person(person_box, item_box, top_ratio: float = 0.4) -> bool:
    """Проверяет, находится ли item_box в верхней части бокса человека"""
    px1, py1, px2, py2 = person_box
    ix1, iy1, ix2, iy2 = item_box

    center_x = (ix1 + ix2) / 2
    center_y = (iy1 + iy2) / 2

    upper_body_y = py1 + (py2 - py1) * top_ratio
    return px1 <= center_x <= px2 and center_y <= upper_body_y


def get_cone_danger_zone(cone_boxes, min_cones: int = 2, expand_px: int = 20):
    """
    Вычисляет опасную зону как bounding box вокруг всех конусов.
    Возвращает (x1, y1, x2, y2) или None если конусов недостаточно.
    """
    if len(cone_boxes) < min_cones:
        return None

    x1 = int(min(b[0] for b in cone_boxes) - expand_px)
    y1 = int(min(b[1] for b in cone_boxes) - expand_px)
    x2 = int(max(b[2] for b in cone_boxes) + expand_px)
    y2 = int(max(b[3] for b in cone_boxes) + expand_px)

    return (x1, y1, x2, y2)


def is_person_in_danger_zone(person_box, danger_zone) -> bool:
    """
    Проверяет, находится ли человек в опасной зоне.
    Используем центр ног (нижняя середина bbox).
    """
    if danger_zone is None:
        return False

    px1, py1, px2, py2 = person_box
    zx1, zy1, zx2, zy2 = danger_zone

    foot_x = (px1 + px2) / 2
    foot_y = py2

    return zx1 <= foot_x <= zx2 and zy1 <= foot_y <= zy2


def draw_danger_zone(frame, danger_zone):
    """Рисует опасную зону на кадре с полупрозрачной заливкой"""
    if danger_zone is None:
        return frame

    x1, y1, x2, y2 = danger_zone

    overlay = frame.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 255), -1)
    cv2.addWeighted(overlay, 0.25, frame, 0.75, 0, frame)

    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
    cv2.putText(frame, "ОПАСНАЯ ЗОНА", (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    return frame


def draw_person_box(frame, person_box, label: str, in_danger: bool, has_violation: bool):
    """Рисует bbox человека с цветом в зависимости от статуса"""
    x1, y1, x2, y2 = map(int, person_box)

    if in_danger and has_violation:
        color = (0, 0, 255)      # Красный — в зоне и нарушение СИЗ
    elif in_danger:
        color = (0, 165, 255)    # Оранжевый — в зоне, но СИЗ есть
    elif has_violation:
        color = (0, 255, 255)    # Жёлтый — вне зоны, но нет СИЗ
    else:
        color = (0, 255, 0)      # Зелёный — всё в порядке

    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    cv2.putText(frame, label, (x1, y1 - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

    return frame


# ─────────────────────────────────────────────
#  Detection worker
# ─────────────────────────────────────────────

def detection_worker():
    """Отдельный поток для обработки детекции и логирования"""
    global LIVE_FEED_ACTIVE, DETECTION_LOG, cap

    while LIVE_FEED_ACTIVE:
        if cap is not None and cap.isOpened():
            success, frame = cap.read()
            if success:
                try:
                    CONF_THRESH = 0.75
                    results = model(frame, conf=CONF_THRESH, verbose=False)[0]

                    names = model.names
                    boxes = results.boxes.xyxy.cpu().numpy()
                    classes = results.boxes.cls.cpu().numpy().astype(int)

                    person_boxes = [boxes[i] for i, c in enumerate(classes) if names[c] == "Человек"]
                    helmet_boxes = [boxes[i] for i, c in enumerate(classes) if names[c] == "Каска"]
                    mask_boxes   = [boxes[i] for i, c in enumerate(classes) if names[c] == "Маска"]
                    vest_boxes   = [boxes[i] for i, c in enumerate(classes) if names[c] == "Защитный жилет"]
                    cone_boxes   = [boxes[i] for i, c in enumerate(classes) if names[c] == "Конус безопасности"]

                    danger_zone = get_cone_danger_zone(cone_boxes)

                    message = f"{datetime.now().strftime('%H:%M:%S')} - "
                    has_any_violation = False

                    if person_boxes:
                        message += f"👷 Людей: {len(person_boxes)} | "

                        for idx, pbox in enumerate(person_boxes):
                            has_helmet = any(has_item_on_person(pbox, hbox) for hbox in helmet_boxes)
                            has_mask   = any(has_item_on_person(pbox, mbox) for mbox in mask_boxes)
                            has_vest   = any(has_item_on_person(pbox, vbox) for vbox in vest_boxes)
                            in_danger  = is_person_in_danger_zone(pbox, danger_zone)

                            fully_equipped = has_helmet and has_mask and has_vest
                            missing = []
                            if not has_helmet: missing.append("каска")
                            if not has_mask:   missing.append("маска")
                            if not has_vest:   missing.append("жилет")

                            message += f"👤Чел.{idx + 1}: "

                            if in_danger:
                                message += "🚨 ОПАСНАЯ ЗОНА | "
                                if fully_equipped:
                                    message += "✅ Все СИЗ на месте"
                                else:
                                    message += f"❌ Нет СИЗ: {', '.join(missing)}"
                                    has_any_violation = True
                            else:
                                message += "📍 Вне зоны | "
                                if fully_equipped:
                                    message += "✅ Все СИЗ на месте"
                                else:
                                    message += f"⚠️ Нет СИЗ: {', '.join(missing)}"
                                    has_any_violation = True

                            if idx < len(person_boxes) - 1:
                                message += " | "
                    else:
                        message += "❌ Людей не обнаружено"

                    if danger_zone:
                        message += f" | 🔶 Опасная зона активна ({len(cone_boxes)} конуса)"

                    # Категория
                    if has_any_violation:
                        category = "нарушение"
                    elif danger_zone and person_boxes:
                        category = "внимание"
                    else:
                        category = "норма"

                    log_entry = {
                        "id": str(datetime.now().timestamp()),
                        "timestamp": datetime.now().strftime('%H:%M:%S'),
                        "message": message,
                        "category": category
                    }

                    DETECTION_LOG.append(log_entry)
                    if len(DETECTION_LOG) > 20:
                        DETECTION_LOG.pop(0)

                    print(message)

                except Exception as e:
                    print(f"Ошибка детекции: {e}")

        time.sleep(1)


# ─────────────────────────────────────────────
#  Live feed с визуализацией
# ─────────────────────────────────────────────

def generate_live_feed():
    """Генерирует кадры для стриминга с визуализацией опасной зоны"""
    global LIVE_FEED_ACTIVE, camera_released, cap

    cap = cv2.VideoCapture("rtsp://192.168.100.13:8554/live")
    if not cap.isOpened():
        print("❌ Не удалось открыть камеру")
        return

    camera_released = False

    while LIVE_FEED_ACTIVE:
        success, frame = cap.read()
        if not success:
            break

        try:
            results = model(frame, verbose=False)[0]

            names = model.names
            boxes = results.boxes.xyxy.cpu().numpy()
            classes = results.boxes.cls.cpu().numpy().astype(int)

            person_boxes = [boxes[i] for i, c in enumerate(classes) if names[c] == "Человек"]
            helmet_boxes = [boxes[i] for i, c in enumerate(classes) if names[c] == "Каска"]
            mask_boxes   = [boxes[i] for i, c in enumerate(classes) if names[c] == "Маска"]
            vest_boxes   = [boxes[i] for i, c in enumerate(classes) if names[c] == "Защитный жилет"]
            cone_boxes   = [boxes[i] for i, c in enumerate(classes) if names[c] == "Конус безопасности"]

            danger_zone = get_cone_danger_zone(cone_boxes)

            # Рисуем опасную зону
            frame = draw_danger_zone(frame, danger_zone)

            # Рисуем боксы людей с цветовой индикацией
            for idx, pbox in enumerate(person_boxes):
                has_helmet = any(has_item_on_person(pbox, hbox) for hbox in helmet_boxes)
                has_mask   = any(has_item_on_person(pbox, mbox) for mbox in mask_boxes)
                has_vest   = any(has_item_on_person(pbox, vbox) for vbox in vest_boxes)
                in_danger  = is_person_in_danger_zone(pbox, danger_zone)

                fully_equipped = has_helmet and has_mask and has_vest
                has_violation = not fully_equipped

                # Строим короткий лейбл для кадра
                status = "🚨" if in_danger else "📍"
                ppe = f"{'К' if has_helmet else '!К'} {'М' if has_mask else '!М'} {'Ж' if has_vest else '!Ж'}"
                label = f"Чел.{idx+1} {status} {ppe}"

                frame = draw_person_box(frame, pbox, label, in_danger, has_violation)

            # Легенда цветов
            cv2.putText(frame, "🟢 OK  🟠 Зона+СИЗ  🔴 Нарушение  🟡 Нет СИЗ",
                        (10, frame.shape[0] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            ret, buffer = cv2.imencode('.jpg', frame)
            frame_bytes = buffer.tobytes()

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

        except Exception as e:
            print(f"Ошибка кадра: {e}")
            break

    cap.release()
    cv2.destroyAllWindows()
    camera_released = True
    print("🛑 Камера остановлена.")


# ─────────────────────────────────────────────
#  Управление потоком
# ─────────────────────────────────────────────

def start_live():
    global LIVE_FEED_ACTIVE, detection_thread, DETECTION_LOG
    if not LIVE_FEED_ACTIVE:
        LIVE_FEED_ACTIVE = True
        DETECTION_LOG = []

        detection_thread = threading.Thread(target=detection_worker, daemon=True)
        detection_thread.start()

        print("🚀 Детекция запущена")


def stop_live():
    global LIVE_FEED_ACTIVE, detection_thread
    LIVE_FEED_ACTIVE = False

    if detection_thread is not None:
        detection_thread.join(timeout=2)

    print("🛑 Детекция остановлена")