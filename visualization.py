import cv2
import numpy as np
from PIL import ImageFont, ImageDraw, Image
from typing import Optional, Tuple
from config import (
    FONT_PATHS, FONT_SIZE_SMALL, FONT_SIZE_NORMAL, FONT_SIZE_LARGE,
    COLOR_GREEN, COLOR_ORANGE, COLOR_RED, COLOR_YELLOW, COLOR_GOLD, COLOR_WHITE
)


def _load_font(size: int):
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except:
            continue
    return ImageFont.load_default()


FONT        = _load_font(FONT_SIZE_NORMAL)
FONT_SMALL  = _load_font(FONT_SIZE_SMALL)
FONT_LARGE  = _load_font(FONT_SIZE_LARGE)
FONT_NORMAL = _load_font(FONT_SIZE_NORMAL)


def put_text(frame, text: str, pos: Tuple, color=COLOR_WHITE, font=None):
    if font is None:
        font = FONT
    img_pil    = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw       = ImageDraw.Draw(img_pil)
    color_rgb  = (color[2], color[1], color[0])
    draw.text(pos, text, font=font, fill=color_rgb)
    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)


def draw_danger_zone(frame, danger_zone: Optional[Tuple]):
    if danger_zone is None:
        return frame
    x1, y1, x2, y2 = danger_zone
    overlay = frame.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), COLOR_RED, -1)
    cv2.addWeighted(overlay, 0.25, frame, 0.75, 0, frame)
    cv2.rectangle(frame, (x1, y1), (x2, y2), COLOR_RED, 2)
    return put_text(frame, "ОПАСНАЯ ЗОНА", (x1, max(0, y1 - 25)),
                    color=COLOR_RED, font=FONT_LARGE)


def draw_person(frame, person_box, label: str,
                in_danger: bool, has_violation: bool, approved: bool):
    x1, y1, x2, y2 = map(int, person_box)

    if approved:
        color = COLOR_GOLD
    elif in_danger and has_violation:
        color = COLOR_RED
    elif in_danger:
        color = COLOR_ORANGE
    elif has_violation:
        color = COLOR_YELLOW
    else:
        color = COLOR_GREEN

    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    frame = put_text(frame, label, (x1, max(0, y1 - 22)), color=color)
    return frame


def draw_hint(frame, person_box):
    x1, y1 = map(int, person_box[:2])
    return put_text(frame, "Покажи жест ОК",
                    (x1, max(0, y1 - 45)),
                    color=COLOR_GOLD, font=FONT_LARGE)


def draw_legend(frame):
    legend = "Зел: OK  Оранж: Зона+СИЗ  Красн: Нарушение  Золот: Пропуск"
    return put_text(frame, legend,
                    (10, frame.shape[0] - 25),
                    color=COLOR_WHITE, font=FONT_SMALL)

def draw_stats_panel(frame, persons_count: int, approved_count: int,
                     violation_count: int, gesture_detected: bool):
    """Панель статистики в верхнем левом углу"""
    h, w = frame.shape[:2]

    # Фон панели
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (320, 140), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

    # Статистика
    frame = put_text(frame, f"Людей в кадре:  {persons_count}",
                     (10, 10), color=COLOR_WHITE, font=FONT_NORMAL)

    frame = put_text(frame, f"Пропусков:      {approved_count}",
                     (10, 38), color=COLOR_GOLD, font=FONT_NORMAL)

    frame = put_text(frame, f"Нарушений:      {violation_count}",
                     (10, 66),
                     color=COLOR_RED if violation_count > 0 else COLOR_GREEN,
                     font=FONT_NORMAL)

    # Реакция на жест
    if gesture_detected:
        frame = put_text(frame, "ЖЕСТ ОК РАСПОЗНАН",
                         (10, 100),
                         color=COLOR_GOLD, font=FONT_LARGE)

    return frame