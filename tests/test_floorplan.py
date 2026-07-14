"""Тесты гомографии кадр→карта и кросс-камерного стича (backend/tracking/floorplan.py).

Гомография решается в чистом numpy — тесты без cv2/GPU.
"""
import numpy as np
import pytest

from backend.tracking.floorplan import (
    homography_from_points, project_point, validate_mapping, CameraProjector,
)

_CORNERS = [[0, 0], [1, 0], [1, 1], [0, 1]]


class TestHomography:
    def test_identity(self):
        H = homography_from_points(_CORNERS, _CORNERS)
        assert H is not None
        for x, y in [(0.5, 0.5), (0.3, 0.7), (0.1, 0.9)]:
            u, v = project_point(H, x, y)
            assert u == pytest.approx(x, abs=1e-9)
            assert v == pytest.approx(y, abs=1e-9)

    def test_translation_scale(self):
        # image = 0.5*map + 0.25  ⇒  map = 2*image - 0.5
        img = [[0.25, 0.25], [0.75, 0.25], [0.75, 0.75], [0.25, 0.75]]
        H = homography_from_points(img, _CORNERS)
        u, v = project_point(H, 0.5, 0.5)
        assert (u, v) == pytest.approx((0.5, 0.5))
        u, v = project_point(H, 0.4, 0.6)
        assert (u, v) == pytest.approx((0.3, 0.7))

    def test_degenerate_collinear_returns_none(self):
        collinear = [[0, 0], [0.25, 0.25], [0.5, 0.5], [0.75, 0.75]]
        assert homography_from_points(collinear, _CORNERS) is None

    def test_too_few_points(self):
        assert homography_from_points([[0, 0], [1, 1]], [[0, 0], [1, 1]]) is None

    def test_project_none_homography(self):
        assert project_point(None, 0.5, 0.5) is None


class TestCrossCameraStitch:
    """Одна и та же физическая точка, снятая двумя РАЗНЫМИ камерами, должна лечь
    в ОДНУ точку карты — тогда траектория cam1→cam2 непрерывна (одна линия)."""

    def test_shared_point_projects_to_same_map_coord(self):
        # cam1 — тождественное отображение (кадр == карта).
        cam1 = CameraProjector([{"image": c, "map": c} for c in _CORNERS])
        # cam2 — сдвиг+масштаб: image = 0.5*map + 0.25.
        img2 = [[0.25, 0.25], [0.75, 0.25], [0.75, 0.75], [0.25, 0.75]]
        cam2 = CameraProjector([{"image": img2[i], "map": _CORNERS[i]} for i in range(4)])
        assert cam1.valid and cam2.valid

        # Физическая точка карты M=(0.3,0.7). В cam1 она в кадре на (0.3,0.7),
        # в cam2 — на (0.5*0.3+0.25, 0.5*0.7+0.25) = (0.4, 0.6).
        m1 = cam1.project(0.3, 0.7)
        m2 = cam2.project(0.4, 0.6)
        assert m1 == pytest.approx((0.3, 0.7))
        assert m2 == pytest.approx((0.3, 0.7))
        # Обе камеры дали одинаковую точку карты → линия сшивается.
        assert m1 == pytest.approx(m2)


class TestValidateMapping:
    def test_empty_ok(self):
        assert validate_mapping([]) == []

    def test_four_points_ok(self):
        pts = [{"image": c, "map": c} for c in _CORNERS]
        out = validate_mapping(pts)
        assert len(out) == 4
        assert out[0]["image"] == [0.0, 0.0]

    def test_three_points_raises(self):
        pts = [{"image": c, "map": c} for c in _CORNERS[:3]]
        with pytest.raises(ValueError):
            validate_mapping(pts)

    def test_clamps_to_unit(self):
        out = validate_mapping([{"image": [2.0, -1.0], "map": [0.5, 0.5]}] * 4)
        assert out[0]["image"] == [1.0, 0.0]

    def test_bad_shape_raises(self):
        with pytest.raises(ValueError):
            validate_mapping([{"image": [0.1], "map": [0.2, 0.3]}] * 4)

    def test_not_list_raises(self):
        with pytest.raises(ValueError):
            validate_mapping("nope")


class TestProjector:
    def test_invalid_without_points(self):
        p = CameraProjector([])
        assert p.valid is False
        assert p.project(0.5, 0.5) is None

    def test_invalid_with_bad_mapping(self):
        # 3 точки → validate бросит, проектор ловит и остаётся невалидным.
        p = CameraProjector([{"image": c, "map": c} for c in _CORNERS[:3]])
        assert p.valid is False

    def test_valid_projects(self):
        p = CameraProjector([{"image": c, "map": c} for c in _CORNERS])
        assert p.valid is True
        assert p.project(0.5, 0.5) == pytest.approx((0.5, 0.5))
