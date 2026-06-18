"""Пользовательские полигональные зоны (редактор зон).

В отличие от опасной зоны, что строится автоматически по конусам
(`detection/engine.py::get_danger_zone`), здесь зоны задаёт оператор вручную —
рисует многоугольники на кадре в UI. Хранятся в конфиге камеры
(`data/cameras_config.json`, ключ `zones`).

Координаты вершин — НОРМАЛИЗОВАННЫЕ [0..1] относительно кадра, чтобы зоны не
зависели от разрешения (кадр в редакторе и в детекции могут отличаться).
Проверка вхождения — тем же ray-casting, что и для зоны по конусам
(`_point_in_polygon`), без тяжёлых геозависимостей (shapely не нужен).

Типы зон:
  • danger     — вход = тревога/«опасная зона» (как текущая зона по конусам);
  • restricted — ограниченный доступ (трактуется как danger для детекции входа);
  • mask       — область исключается из детекции (объекты внутри игнорируются).
"""
from __future__ import annotations
import uuid
from typing import List, Optional

from backend.detection.engine import _point_in_polygon
from backend.config import get_camera_config, set_camera_config

ZONE_TYPES = ("danger", "restricted", "mask")
PPE_ITEMS = ("helmet", "mask", "vest")
_DANGER_TYPES = ("danger", "restricted")


# ── Валидация / CRUD в конфиге камеры ───────────────────────────────────────
def validate_zone(raw: dict) -> dict:
    """Проверить и нормализовать зону. Бросает ValueError при некорректных данных."""
    if not isinstance(raw, dict):
        raise ValueError("зона должна быть объектом")
    ztype = raw.get("type", "danger")
    if ztype not in ZONE_TYPES:
        raise ValueError(f"неизвестный тип зоны: {ztype}")
    points = []
    for p in (raw.get("points") or []):
        if len(p) != 2:
            raise ValueError("точка должна быть парой [x, y]")
        x = min(1.0, max(0.0, float(p[0])))
        y = min(1.0, max(0.0, float(p[1])))
        points.append([x, y])
    if len(points) < 3:
        raise ValueError("полигон требует не менее 3 точек")
    require_ppe = [i for i in (raw.get("require_ppe") or []) if i in PPE_ITEMS]
    return {
        "id": str(raw.get("id") or uuid.uuid4().hex[:12]),
        "name": str(raw.get("name") or ztype),
        "type": ztype,
        "points": points,
        "require_ppe": require_ppe,
    }


def get_zones(cam_id: str) -> List[dict]:
    return list(get_camera_config(cam_id).get("zones", []))


def set_zones(cam_id: str, zones: list) -> List[dict]:
    validated = [validate_zone(z) for z in zones]
    set_camera_config(cam_id, zones=validated)
    return validated


def add_zone(cam_id: str, zone: dict) -> dict:
    z = validate_zone(zone)
    zones = get_zones(cam_id)
    zones.append(z)
    set_camera_config(cam_id, zones=zones)
    return z


def update_zone(cam_id: str, zone_id: str, patch: dict) -> Optional[dict]:
    zones = get_zones(cam_id)
    for i, z in enumerate(zones):
        if z.get("id") == zone_id:
            zones[i] = validate_zone({**z, **patch, "id": zone_id})
            set_camera_config(cam_id, zones=zones)
            return zones[i]
    return None


def delete_zone(cam_id: str, zone_id: str) -> bool:
    zones = get_zones(cam_id)
    remaining = [z for z in zones if z.get("id") != zone_id]
    if len(remaining) == len(zones):
        return False
    set_camera_config(cam_id, zones=remaining)
    return True


# ── Геометрия (нормализованные координаты) ──────────────────────────────────
def _foot_norm(person_box, w: int, h: int):
    px1, _py1, px2, py2 = person_box
    return ((px1 + px2) / 2.0) / w, py2 / h


def _center_norm(box, w: int, h: int):
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2.0) / w, ((y1 + y2) / 2.0) / h


def person_in_zone(person_box, zone: dict, w: int, h: int) -> bool:
    """Человек в зоне по точке ног (центр низа bbox), как для зоны по конусам."""
    if w <= 0 or h <= 0:
        return False
    fx, fy = _foot_norm(person_box, w, h)
    return _point_in_polygon(fx, fy, zone["points"])


def in_any_danger_zone(person_box, zones: list, w: int, h: int) -> bool:
    return any(person_in_zone(person_box, z, w, h)
               for z in zones if z.get("type") in _DANGER_TYPES)


def has_danger_zones(zones: list) -> bool:
    return any(z.get("type") in _DANGER_TYPES for z in zones)


def box_in_mask(box, zones: list, w: int, h: int) -> bool:
    """Центр bbox попадает в зону-маску → объект исключается из детекции."""
    if w <= 0 or h <= 0:
        return False
    cx, cy = _center_norm(box, w, h)
    return any(_point_in_polygon(cx, cy, z["points"])
               for z in zones if z.get("type") == "mask")


def to_pixels(zone: dict, w: int, h: int):
    """Вершины зоны в пиксельных координатах кадра (для отрисовки)."""
    return [(int(x * w), int(y * h)) for x, y in zone["points"]]


def apply_masks(detected: dict, zones: list, w: int, h: int) -> dict:
    """Удалить из результата детекции объекты, чьи центры в зонах-масках.
    persons и person_track_ids фильтруются согласованно (parallel lists)."""
    mask_zones = [z for z in zones if z.get("type") == "mask"]
    if not mask_zones:
        return detected

    def keep(box) -> bool:
        return not box_in_mask(box, mask_zones, w, h)

    persons = detected.get("persons", [])
    tids = detected.get("person_track_ids", [])
    kept_p, kept_t = [], []
    for i, b in enumerate(persons):
        if keep(b):
            kept_p.append(b)
            kept_t.append(tids[i] if i < len(tids) else -1)
    detected["persons"] = kept_p
    detected["person_track_ids"] = kept_t
    for key in ("helmets", "masks", "vests", "cones"):
        if key in detected:
            detected[key] = [b for b in detected[key] if keep(b)]
    return detected
