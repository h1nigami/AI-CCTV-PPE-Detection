import cv2
import numpy as np
from PIL import ImageFont, ImageDraw, Image
from typing import Optional, Tuple
from backend.config import (
    FONT_PATHS, FONT_SIZE_SMALL, FONT_SIZE_NORMAL, FONT_SIZE_LARGE,
    COLOR_GREEN, COLOR_ORANGE, COLOR_RED, COLOR_YELLOW, COLOR_GOLD, COLOR_WHITE
)


def _load_font(size: int):
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(str(path), size)
        except:
            continue
    return ImageFont.load_default()


FONT = _load_font(FONT_SIZE_NORMAL)
FONT_SMALL = _load_font(FONT_SIZE_SMALL)
FONT_LARGE = _load_font(FONT_SIZE_LARGE)
FONT_NORMAL = _load_font(FONT_SIZE_NORMAL)


def put_text(frame, text: str, pos: Tuple, color=COLOR_WHITE, font=None):
    if font is None:
        font = FONT
    img_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    color_rgb = (color[2], color[1], color[0])
    draw.text(pos, text, font=font, fill=color_rgb)
    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)


def draw_danger_zone(frame, danger_zone):
    """Рисует опасную зону как МНОГОУГОЛЬНИК по вершинам (массив (N,2))."""
    if danger_zone is None:
        return frame
    pts = np.asarray(danger_zone, dtype=np.int32).reshape(-1, 1, 2)
    overlay = frame.copy()
    cv2.fillPoly(overlay, [pts], COLOR_RED)
    cv2.addWeighted(overlay, 0.25, frame, 0.75, 0, frame)
    cv2.polylines(frame, [pts], isClosed=True, color=COLOR_RED, thickness=2)
    # Подпись у самой верхней вершины
    top = min(danger_zone, key=lambda p: p[1])
    return put_text(frame, "ОПАСНАЯ ЗОНА", (int(top[0]), max(0, int(top[1]) - 25)),
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


def draw_trajectory(frame, points, color=COLOR_YELLOW, thickness=2):
    """След траектории движения (полилиния по точкам ног). points — [(x, y), ...]."""
    if points is None or len(points) < 2:
        return frame
    pts = np.asarray(points, dtype=np.int32).reshape(-1, 1, 2)
    cv2.polylines(frame, [pts], isClosed=False, color=color,
                  thickness=thickness, lineType=cv2.LINE_AA)
    return frame


def draw_seat_marker(frame, anchor, color=COLOR_GREEN):
    """Отметка «место человека» (якорь), у которого считается время сидения."""
    if anchor is None:
        return frame
    x, y = int(anchor[0]), int(anchor[1])
    cv2.drawMarker(frame, (x, y), color, markerType=cv2.MARKER_TILTED_CROSS,
                   markerSize=14, thickness=2)
    cv2.circle(frame, (x, y), 6, color, 1, lineType=cv2.LINE_AA)
    return frame


def draw_movement_badge(frame, person_box, text, color):
    """Бейдж статуса перемещения под рамкой человека («Сидит MM:SS» / «Идёт»)."""
    x1, _, _, y2 = map(int, person_box)
    y = min(frame.shape[0] - 18, y2 + 2)
    return put_text(frame, text, (x1, y), color=color, font=FONT_SMALL)
