import numpy as np
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
from backend.config import (BASE_DIR, MIN_CONES, ZONE_EXPAND_PX, TOP_RATIO, CONF_THRESH)

CLASS_PERSON = 5


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


TRACKER_CFG = str(BASE_DIR / "backend" / "detection" / "bytetrack_custom.yaml")


def run_detection(frame, model) -> Dict[str, Any]:
    results = model.track(frame, conf=CONF_THRESH, verbose=False,
                          persist=True, tracker=TRACKER_CFG)[0]
    names = model.names
    boxes = results.boxes.xyxy.cpu().numpy()
    classes = results.boxes.cls.cpu().numpy().astype(int)
    all_track_ids = None
    if results.boxes.id is not None:
        all_track_ids = results.boxes.id.cpu().numpy().astype(int)
    persons = []
    person_track_ids = []
    for i, c in enumerate(classes):
        if names[c] == "Человек":
            persons.append(boxes[i])
            tid = int(all_track_ids[i]) if all_track_ids is not None else -1
            person_track_ids.append(tid)
    return {
        "persons": persons,
        "person_track_ids": person_track_ids,
        "helmets": get_boxes_by_class(boxes, classes, names, "Каска"),
        "masks": get_boxes_by_class(boxes, classes, names, "Маска"),
        "vests": get_boxes_by_class(boxes, classes, names, "Защитный жилет"),
        "cones": get_boxes_by_class(boxes, classes, names, "Конус безопасности"),
    }
