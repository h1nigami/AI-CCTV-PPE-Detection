from ultralytics import YOLO
import cv2
from datetime import datetime
import threading
import time
import numpy as np
from PIL import ImageFont, ImageDraw, Image

# ─────────────────────────────────────────────
#  Шрифты (загружаем один раз)
# ─────────────────────────────────────────────

def load_font(size):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",        # Linux
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "C:/Windows/Fonts/arial.ttf",                              # Windows
        "/System/Library/Fonts/Helvetica.ttc",                     # macOS
    ]
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except:
            continue
    return ImageFont.load_default()

FONT       = load_font(18)
FONT_SMALL = load_font(14)
FONT_LARGE = load_font(22)


def put_text(frame, text, pos, color=(255, 255, 255), font=None):
    """
    Рисует текст с поддержкой кириллицы через PIL.
    color — в формате BGR (как в OpenCV).
    """
    if font is None:
        font = FONT

    img_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    # BGR -> RGB для PIL
    color_rgb = (color[2], color[1], color[0])
    draw.text(pos, text, font=font, fill=color_rgb)
    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)


# ─────────────────────────────────────────────
#  Модели
# ─────────────────────────────────────────────

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
model.save("models/best.pt")

pose_model = YOLO("models/yolov8n-pose.pt")

# ─────────────────────────────────────────────
#  Global state
# ─────────────────────────────────────────────

LIVE_FEED_ACTIVE = False
camera_released  = True
DETECTION_LOG    = []
detection_thread = None
cap              = None
APPROVED_PERSONS = {}
APPROVAL_DURATION = 300  # секунд


# ─────────────────────────────────────────────
#  СИЗ / Зона
# ─────────────────────────────────────────────

def has_item_on_person(person_box, item_box, top_ratio: float = 0.4) -> bool:
    px1, py1, px2, py2 = person_box
    ix1, iy1, ix2, iy2 = item_box
    center_x = (ix1 + ix2) / 2
    center_y = (iy1 + iy2) / 2
    upper_body_y = py1 + (py2 - py1) * top_ratio
    return px1 <= center_x <= px2 and center_y <= upper_body_y


def get_cone_danger_zone(cone_boxes, min_cones: int = 2, expand_px: int = 20):
    if len(cone_boxes) < min_cones:
        return None
    x1 = int(min(b[0] for b in cone_boxes) - expand_px)
    y1 = int(min(b[1] for b in cone_boxes) - expand_px)
    x2 = int(max(b[2] for b in cone_boxes) + expand_px)
    y2 = int(max(b[3] for b in cone_boxes) + expand_px)
    return (x1, y1, x2, y2)


def is_person_in_danger_zone(person_box, danger_zone) -> bool:
    if danger_zone is None:
        return False
    px1, py1, px2, py2 = person_box
    zx1, zy1, zx2, zy2 = danger_zone
    foot_x = (px1 + px2) / 2
    foot_y = py2
    return zx1 <= foot_x <= zx2 and zy1 <= foot_y <= zy2


# ─────────────────────────────────────────────
#  Жест ОК
# ─────────────────────────────────────────────

def detect_ok_gesture(frame, person_box) -> bool:
    px1, py1, px2, py2 = map(int, person_box)
    px1 = max(0, px1 - 10)
    py1 = max(0, py1 - 10)
    px2 = min(frame.shape[1], px2 + 10)
    py2 = min(frame.shape[0], py2 + 10)

    person_crop = frame[py1:py2, px1:px2]
    if person_crop.size == 0:
        return False

    try:
        pose_results = pose_model(person_crop, verbose=False)[0]
    except Exception:
        return False

    if pose_results.keypoints is None:
        return False

    kpts = pose_results.keypoints.xy.cpu().numpy()
    if len(kpts) == 0:
        return False

    kp = kpts[0]
    if len(kp) < 11:
        return False

    def valid(pt):
        return pt[0] > 0 and pt[1] > 0

    left_wrist     = kp[9]
    right_wrist    = kp[10]
    left_elbow     = kp[7]
    right_elbow    = kp[8]
    left_shoulder  = kp[5]
    right_shoulder = kp[6]

    def is_hand_raised(wrist, elbow, shoulder):
        if not (valid(wrist) and valid(elbow) and valid(shoulder)):
            return False
        return wrist[1] < shoulder[1]

    left_raised  = is_hand_raised(left_wrist,  left_elbow,  left_shoulder)
    right_raised = is_hand_raised(right_wrist, right_elbow, right_shoulder)

    if not (left_raised or right_raised):
        return False

    wrist = right_wrist if right_raised else left_wrist
    wx, wy = int(wrist[0]), int(wrist[1])

    hand_size = int((px2 - px1) * 0.25)
    hx1 = max(0, wx - hand_size)
    hy1 = max(0, wy - hand_size)
    hx2 = min(person_crop.shape[1], wx + hand_size)
    hy2 = min(person_crop.shape[0], wy + hand_size)

    hand_crop = person_crop[hy1:hy2, hx1:hx2]
    if hand_crop.size == 0:
        return False

    return _is_ok_by_contour(hand_crop)


def _is_ok_by_contour(hand_img) -> bool:
    gray = cv2.cvtColor(hand_img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (7, 7), 0)
    thresh = cv2.adaptiveThreshold(
        blur, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 11, 2
    )
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return False

    contour = max(contours, key=cv2.contourArea)
    if cv2.contourArea(contour) < 500:
        return False

    hull = cv2.convexHull(contour, returnPoints=False)
    if hull is None or len(hull) < 3:
        return False

    try:
        defects = cv2.convexityDefects(contour, hull)
    except Exception:
        return False

    if defects is None:
        return False

    significant_defects = sum(
        1 for i in range(defects.shape[0])
        if defects[i, 0][3] / 256.0 > 15
    )
    return 1 <= significant_defects <= 3


# ─────────────────────────────────────────────
#  Пропуска
# ─────────────────────────────────────────────

def get_person_id(person_box):
    cx = int((person_box[0] + person_box[2]) / 2)
    cy = int((person_box[1] + person_box[3]) / 2)
    return (cx // 50, cy // 50)


def is_approved(person_box) -> bool:
    pid = get_person_id(person_box)
    if pid in APPROVED_PERSONS:
        if time.time() < APPROVED_PERSONS[pid]:
            return True
        del APPROVED_PERSONS[pid]
    return False


def approve_person(person_box):
    pid = get_person_id(person_box)
    APPROVED_PERSONS[pid] = time.time() + APPROVAL_DURATION
    print(f"Пропуск выдан: ID {pid} на {APPROVAL_DURATION} сек.")


# ─────────────────────────────────────────────
#  Визуализация
# ─────────────────────────────────────────────

def draw_danger_zone(frame, danger_zone):
    if danger_zone is None:
        return frame
    x1, y1, x2, y2 = danger_zone
    overlay = frame.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 255), -1)
    cv2.addWeighted(overlay, 0.25, frame, 0.75, 0, frame)
    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
    frame = put_text(frame, "ОПАСНАЯ ЗОНА", (x1, y1 - 25),
                     color=(0, 0, 255), font=FONT_LARGE)
    return frame


def draw_person_box(frame, person_box, label, in_danger, has_violation, approved):
    x1, y1, x2, y2 = map(int, person_box)

    if approved:
        color = (0, 215, 255)    # Золотой
    elif in_danger and has_violation:
        color = (0, 0, 255)      # Красный
    elif in_danger:
        color = (0, 165, 255)    # Оранжевый
    elif has_violation:
        color = (0, 255, 255)    # Жёлтый
    else:
        color = (0, 255, 0)      # Зелёный

    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    frame = put_text(frame, label, (x1, max(0, y1 - 22)), color=color)
    return frame


def draw_legend(frame):
    legend = "Зел: OK  Оранж: Зона+СИЗ  Красн: Нарушение  Золот: Пропуск"
    frame = put_text(frame, legend,
                     (10, frame.shape[0] - 25),
                     color=(255, 255, 255), font=FONT_SMALL)
    return frame


# ─────────────────────────────────────────────
#  Detection worker
# ─────────────────────────────────────────────

def detection_worker():
    global LIVE_FEED_ACTIVE, DETECTION_LOG, cap

    while LIVE_FEED_ACTIVE:
        if cap is not None and cap.isOpened():
            success, frame = cap.read()
            if success:
                try:
                    results = model(frame, conf=0.75, verbose=False)[0]

                    names   = model.names
                    boxes   = results.boxes.xyxy.cpu().numpy()
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
                        message += f"Людей: {len(person_boxes)} | "

                        for idx, pbox in enumerate(person_boxes):
                            has_helmet = any(has_item_on_person(pbox, h) for h in helmet_boxes)
                            has_mask   = any(has_item_on_person(pbox, m) for m in mask_boxes)
                            has_vest   = any(has_item_on_person(pbox, v) for v in vest_boxes)
                            in_danger  = is_person_in_danger_zone(pbox, danger_zone)
                            approved   = is_approved(pbox)

                            fully_equipped = has_helmet and has_mask and has_vest
                            missing = []
                            if not has_helmet: missing.append("каска")
                            if not has_mask:   missing.append("маска")
                            if not has_vest:   missing.append("жилет")

                            if fully_equipped and not approved:
                                if detect_ok_gesture(frame, pbox):
                                    approve_person(pbox)
                                    approved = True

                            message += f"Чел.{idx + 1}: "

                            if approved:
                                message += "ПРОПУСК АКТИВЕН | Все СИЗ + ОК жест"
                            elif in_danger:
                                message += "ОПАСНАЯ ЗОНА | "
                                if fully_equipped:
                                    message += "Все СИЗ — покажи ОК для пропуска"
                                else:
                                    message += f"Нет СИЗ: {', '.join(missing)}"
                                    has_any_violation = True
                            else:
                                message += "Вне зоны | "
                                if fully_equipped:
                                    message += "Все СИЗ на месте"
                                else:
                                    message += f"Нет СИЗ: {', '.join(missing)}"
                                    has_any_violation = True

                            if idx < len(person_boxes) - 1:
                                message += " | "
                    else:
                        message += "Людей не обнаружено"

                    if danger_zone:
                        message += f" | Зона активна ({len(cone_boxes)} конуса)"

                    category = "нарушение" if has_any_violation else \
                               "внимание"  if danger_zone and person_boxes else "норма"

                    DETECTION_LOG.append({
                        "id":        str(datetime.now().timestamp()),
                        "timestamp": datetime.now().strftime('%H:%M:%S'),
                        "message":   message,
                        "category":  category
                    })
                    if len(DETECTION_LOG) > 20:
                        DETECTION_LOG.pop(0)

                    print(message)

                except Exception as e:
                    print(f"Ошибка детекции: {e}")

        time.sleep(1)


# ─────────────────────────────────────────────
#  Live feed
# ─────────────────────────────────────────────

def generate_live_feed():
    global LIVE_FEED_ACTIVE, camera_released, cap

    cap = cv2.VideoCapture("rtsp://192.168.100.13:8554/live")
    if not cap.isOpened():
        print("Не удалось открыть камеру")
        return

    camera_released = False

    while LIVE_FEED_ACTIVE:
        success, frame = cap.read()
        if not success:
            break

        try:
            results = model(frame, verbose=False)[0]

            names   = model.names
            boxes   = results.boxes.xyxy.cpu().numpy()
            classes = results.boxes.cls.cpu().numpy().astype(int)

            person_boxes = [boxes[i] for i, c in enumerate(classes) if names[c] == "Человек"]
            helmet_boxes = [boxes[i] for i, c in enumerate(classes) if names[c] == "Каска"]
            mask_boxes   = [boxes[i] for i, c in enumerate(classes) if names[c] == "Маска"]
            vest_boxes   = [boxes[i] for i, c in enumerate(classes) if names[c] == "Защитный жилет"]
            cone_boxes   = [boxes[i] for i, c in enumerate(classes) if names[c] == "Конус безопасности"]

            danger_zone = get_cone_danger_zone(cone_boxes)
            frame = draw_danger_zone(frame, danger_zone)

            for idx, pbox in enumerate(person_boxes):
                has_helmet = any(has_item_on_person(pbox, h) for h in helmet_boxes)
                has_mask   = any(has_item_on_person(pbox, m) for m in mask_boxes)
                has_vest   = any(has_item_on_person(pbox, v) for v in vest_boxes)
                in_danger  = is_person_in_danger_zone(pbox, danger_zone)
                approved   = is_approved(pbox)

                fully_equipped = has_helmet and has_mask and has_vest
                has_violation  = not fully_equipped

                ppe = f"{'К' if has_helmet else '!К'} {'М' if has_mask else '!М'} {'Ж' if has_vest else '!Ж'}"

                if approved:
                    label = f"Чел.{idx+1} ПРОПУСК | {ppe}"
                elif in_danger:
                    label = f"Чел.{idx+1} ОПАСНАЯ ЗОНА | {ppe}"
                else:
                    label = f"Чел.{idx+1} Вне зоны | {ppe}"

                frame = draw_person_box(frame, pbox, label, in_danger, has_violation, approved)

                if fully_equipped and not approved and in_danger:
                    x1, y1 = map(int, pbox[:2])
                    frame = put_text(frame, "Покажи жест ОК",
                                     (x1, max(0, y1 - 45)),
                                     color=(0, 215, 255), font=FONT_LARGE)

            frame = draw_legend(frame)

            ret, buffer = cv2.imencode('.jpg', frame)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

        except Exception as e:
            print(f"Ошибка кадра: {e}")
            break

    cap.release()
    cv2.destroyAllWindows()
    camera_released = True
    print("Камера остановлена.")


# ─────────────────────────────────────────────
#  Управление
# ─────────────────────────────────────────────

def start_live():
    global LIVE_FEED_ACTIVE, detection_thread, DETECTION_LOG
    if not LIVE_FEED_ACTIVE:
        LIVE_FEED_ACTIVE = True
        DETECTION_LOG = []
        detection_thread = threading.Thread(target=detection_worker, daemon=True)
        detection_thread.start()
        print("Детекция запущена")


def stop_live():
    global LIVE_FEED_ACTIVE, detection_thread
    LIVE_FEED_ACTIVE = False
    if detection_thread is not None:
        detection_thread.join(timeout=2)
    print("Детекция остановлена")