import numpy as np
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
from backend.config import (BASE_DIR, MIN_CONES, ZONE_EXPAND_PX, TOP_RATIO,
                            CONF_THRESH, PPE_CONF_THRESH)


def get_boxes_by_class(boxes, classes, names, class_name: str) -> List:
    return [boxes[i] for i, c in enumerate(classes) if names[c] == class_name]


def has_item_on_person(person_box, item_box, top_ratio: float = TOP_RATIO) -> bool:
    px1, py1, px2, py2 = person_box
    ix1, iy1, ix2, iy2 = item_box
    cx = (ix1 + ix2) / 2
    cy = (iy1 + iy2) / 2
    upper_y = py1 + (py2 - py1) * top_ratio
    return px1 <= cx <= px2 and cy <= upper_y


def get_danger_zone(cone_boxes) -> Optional[np.ndarray]:
    """Опасная зона — МНОГОУГОЛЬНИК с вершинами по конусам (N углов = N конусов),
    а не bbox. Вершина = центр конуса; вершины упорядочены по полярному углу
    вокруг центроида (чтобы многоугольник не самопересекался) и раздвинуты
    наружу от центроида на ZONE_EXPAND_PX. Возвращает массив вершин (N, 2) int
    или None, если конусов меньше MIN_CONES."""
    if len(cone_boxes) < MIN_CONES:
        return None
    pts = np.array(
        [[(b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0] for b in cone_boxes],
        dtype=np.float64,
    )
    centroid = pts.mean(axis=0)
    angles = np.arctan2(pts[:, 1] - centroid[1], pts[:, 0] - centroid[0])
    pts = pts[np.argsort(angles)]
    vecs = pts - centroid
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    pts = pts + vecs / norms * ZONE_EXPAND_PX
    return pts.astype(int)


def _point_in_polygon(x: float, y: float, poly) -> bool:
    """Точка внутри многоугольника (алгоритм ray-casting). poly — (N, 2)."""
    n = len(poly)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i][0], poly[i][1]
        xj, yj = poly[j][0], poly[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def is_in_danger_zone(person_box, danger_zone) -> bool:
    if danger_zone is None:
        return False
    px1, py1, px2, py2 = person_box
    foot_x = (px1 + px2) / 2
    foot_y = py2
    return _point_in_polygon(foot_x, foot_y, danger_zone)


TRACKER_CFG = str(BASE_DIR / "backend" / "detection" / "bytetrack_custom.yaml")


def parse_detection_results(
    results, model,
    person_conf: float = CONF_THRESH,
    ppe_conf: float = PPE_CONF_THRESH,
) -> Dict[str, Any]:
    """Извлечь detection-словарь из готового объекта ultralytics Results.

    Используется как при одиночном инференсе (run_detection), так и при
    батч-инференсе (BatchDetectionWorker), где results уже получен снаружи.
    """
    names = model.names
    boxes = results.boxes.xyxy.cpu().numpy()
    classes = results.boxes.cls.cpu().numpy().astype(int)
    conf_attr = getattr(results.boxes, "conf", None)
    confs = conf_attr.cpu().numpy() if conf_attr is not None else np.ones(len(classes), dtype=np.float32)
    all_track_ids = None
    if results.boxes.id is not None:
        all_track_ids = results.boxes.id.cpu().numpy().astype(int)

    persons: List = []
    person_track_ids: List = []
    for i, c in enumerate(classes):
        if names[c] == "Человек" and confs[i] >= person_conf:
            persons.append(boxes[i])
            tid = int(all_track_ids[i]) if all_track_ids is not None else -1
            person_track_ids.append(tid)

    def _by_class(class_name: str, thr: float) -> List:
        return [boxes[i] for i, c in enumerate(classes)
                if names[c] == class_name and confs[i] >= thr]

    return {
        "persons": persons,
        "person_track_ids": person_track_ids,
        "helmets": _by_class("Каска", ppe_conf),
        "masks": _by_class("Маска", ppe_conf),
        "vests": _by_class("Защитный жилет", ppe_conf),
        "cones": _by_class("Конус безопасности", person_conf),
    }


def run_detection(frame, model, person_conf: float = CONF_THRESH,
                  ppe_conf: float = PPE_CONF_THRESH) -> Dict[str, Any]:
    # Детекцию гоняем по НИЖНЕМУ из порогов, чтобы из модели вернулись и менее
    # уверенные предметы СИЗ; затем фильтруем покласово: люди/конусы — по
    # person_conf, предметы СИЗ — по более мягкому ppe_conf (каска/маска/жилет
    # мельче и часто детектятся слабее → при едином 0.75 ложно «нет каски»).
    base_conf = min(person_conf, ppe_conf)
    results = model.track(frame, conf=base_conf, verbose=False,
                          persist=True, tracker=TRACKER_CFG)[0]
    return parse_detection_results(results, model, person_conf, ppe_conf)
