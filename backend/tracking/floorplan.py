"""Кросс-камерный стич траекторий: проекция точки ног в общие координаты «карты».

Каждая камера видит сцену в своих пиксельных координатах. Чтобы траектория
человека, проходящего cam1→cam2, рисовалась ОДНОЙ линией, нужен общий план
помещения («карта») и проекция кадр→карта. Проекция — гомография (перспективное
преобразование), заданная 4 парами соответствия «точка в кадре ↔ точка на карте»
(оператор ставит их в UI калибровки). Координаты И кадра, И карты —
НОРМАЛИЗОВАННЫЕ [0..1], поэтому не зависят от разрешения.

Свойство «стич»: одна и та же физическая точка, снятая двумя камерами, при верной
калибровке проецируется в ОДНУ точку карты — значит, точки ног человека с разных
камер ложатся на одну непрерывную линию (ключ — глобальный `global_id`).

Гомография решается в чистом numpy (DLT, 8×8) — модуль тестируется без cv2.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np

from backend.config import get_camera_config, set_camera_config


def _clamp01(v) -> float:
    return min(1.0, max(0.0, float(v)))


def homography_from_points(src, dst) -> Optional[np.ndarray]:
    """3×3 гомография H: src→dst по 4 парам точек. None, если точки вырождены
    (коллинеарны) или пар меньше 4. src/dst — списки [x, y]."""
    if src is None or dst is None or len(src) < 4 or len(dst) < 4:
        return None
    src = np.asarray(src, dtype=np.float64)[:4]
    dst = np.asarray(dst, dtype=np.float64)[:4]
    A = np.zeros((8, 8), dtype=np.float64)
    b = np.zeros(8, dtype=np.float64)
    for i in range(4):
        x, y = src[i]
        u, v = dst[i]
        A[2 * i] = [x, y, 1, 0, 0, 0, -u * x, -u * y]
        A[2 * i + 1] = [0, 0, 0, x, y, 1, -v * x, -v * y]
        b[2 * i] = u
        b[2 * i + 1] = v
    try:
        h = np.linalg.solve(A, b)
    except np.linalg.LinAlgError:
        return None
    if not np.all(np.isfinite(h)):
        return None
    return np.array([[h[0], h[1], h[2]],
                     [h[3], h[4], h[5]],
                     [h[6], h[7], 1.0]], dtype=np.float64)


def project_point(H: Optional[np.ndarray], x: float, y: float) -> Optional[Tuple[float, float]]:
    """Применить гомографию к точке (x, y). None при H=None или вырожденном
    знаменателе (точка «за горизонтом» камеры)."""
    if H is None:
        return None
    denom = H[2, 0] * x + H[2, 1] * y + H[2, 2]
    if abs(denom) < 1e-9:
        return None
    u = (H[0, 0] * x + H[0, 1] * y + H[0, 2]) / denom
    v = (H[1, 0] * x + H[1, 1] * y + H[1, 2]) / denom
    if not (np.isfinite(u) and np.isfinite(v)):
        return None
    return (float(u), float(v))


def validate_mapping(raw) -> List[dict]:
    """Проверить/нормализовать точки калибровки. Каждая — {image:[x,y], map:[x,y]}
    в [0..1]. Пусто — допустимо (камера не на карте). 1..3 точки — ошибка (для
    гомографии нужно ≥4). Бросает ValueError при некорректных данных."""
    if not isinstance(raw, list):
        raise ValueError("map_points должен быть списком")
    out: List[dict] = []
    for p in raw:
        if not isinstance(p, dict):
            raise ValueError("точка = {image:[x,y], map:[x,y]}")
        img = p.get("image")
        mp = p.get("map")
        if not (isinstance(img, (list, tuple)) and isinstance(mp, (list, tuple))
                and len(img) == 2 and len(mp) == 2):
            raise ValueError("точка = {image:[x,y], map:[x,y]}")
        out.append({"image": [_clamp01(img[0]), _clamp01(img[1])],
                    "map": [_clamp01(mp[0]), _clamp01(mp[1])]})
    if 0 < len(out) < 4:
        raise ValueError("нужно не менее 4 точек соответствия (или ни одной)")
    return out


class CameraProjector:
    """Проектор кадр→карта одной камеры. Строит гомографию из точек калибровки;
    `valid=False`, если калибровки нет или она вырождена."""

    def __init__(self, map_points: Optional[list] = None):
        try:
            pts = validate_mapping(map_points or [])
        except ValueError:
            pts = []
        self.map_points = pts
        self._H = None
        if len(pts) >= 4:
            self._H = homography_from_points([p["image"] for p in pts],
                                             [p["map"] for p in pts])

    @property
    def valid(self) -> bool:
        return self._H is not None

    def project(self, nx: float, ny: float) -> Optional[Tuple[float, float]]:
        """Нормализованная точка кадра [0..1] → нормализованная точка карты."""
        return project_point(self._H, nx, ny)


# ── Хранение калибровки в конфиге камеры (как зоны) ─────────────────────────
def get_mapping(cam_id: str) -> List[dict]:
    return list(get_camera_config(cam_id).get("map_points", []))


def set_mapping(cam_id: str, map_points: list) -> List[dict]:
    validated = validate_mapping(map_points)
    set_camera_config(cam_id, map_points=validated)
    return validated
