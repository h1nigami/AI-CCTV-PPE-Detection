import numpy as np
from typing import List, Optional, Tuple
from config import (
    MIN_CONES, ZONE_EXPAND_PX, TOP_RATIO, CONF_THRESH
)


def get_boxes_by_class(boxes, classes, names, class_name: str) -> List:
    return [boxes[i] for i, c in enumerate(classes) if names[c] == class_name]


def has_item_on_person(person_box, item_box, top_ratio: float = TOP_RATIO) -> bool:
    px1, py1, px2, py2 = person_box
    ix1, iy1, ix2, iy2 = item_box
    cx = (ix1 + ix2) / 2
    cy = (iy1 + iy2) / 2
    upper_y = py1 + (py2 - py1) * top_ratio
    return px1 <= cx <= px2 and cy <= upper_y


def get_danger_zone(cone_boxes) -> Optional[Tuple]:
    if len(cone_boxes) < MIN_CONES:
        return None
    return (
        int(min(b[0] for b in cone_boxes) - ZONE_EXPAND_PX),
        int(min(b[1] for b in cone_boxes) - ZONE_EXPAND_PX),
        int(max(b[2] for b in cone_boxes) + ZONE_EXPAND_PX),
        int(max(b[3] for b in cone_boxes) + ZONE_EXPAND_PX),
    )


def is_in_danger_zone(person_box, danger_zone) -> bool:
    if danger_zone is None:
        return False
    px1, py1, px2, py2 = person_box
    zx1, zy1, zx2, zy2 = danger_zone
    foot_x = (px1 + px2) / 2
    foot_y = py2
    return zx1 <= foot_x <= zx2 and zy1 <= foot_y <= zy2


def run_detection(frame, model):
    """Запускает модель и возвращает отфильтрованные боксы по классам"""
    results = model(frame, conf=CONF_THRESH, verbose=False)[0]
    names   = model.names
    boxes   = results.boxes.xyxy.cpu().numpy()
    classes = results.boxes.cls.cpu().numpy().astype(int)

    return {
        "persons": get_boxes_by_class(boxes, classes, names, "Человек"),
        "helmets": get_boxes_by_class(boxes, classes, names, "Каска"),
        "masks":   get_boxes_by_class(boxes, classes, names, "Маска"),
        "vests":   get_boxes_by_class(boxes, classes, names, "Защитный жилет"),
        "cones":   get_boxes_by_class(boxes, classes, names, "Конус безопасности"),
    }