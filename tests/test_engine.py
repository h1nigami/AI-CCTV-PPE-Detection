from unittest.mock import MagicMock, patch
import numpy as np
import pytest


@pytest.fixture
def mock_model():
    model = MagicMock()
    model.names = {0: "Каска", 1: "Маска", 5: "Человек", 6: "Конус безопасности", 7: "Защитный жилет"}
    return model


def make_mock_track_result(boxes_array, classes_array, track_ids_array=None,
                           confs_array=None):
    result = MagicMock()
    result.boxes.xyxy = MagicMock()
    result.boxes.xyxy.cpu.return_value.numpy.return_value = boxes_array
    result.boxes.cls = MagicMock()
    result.boxes.cls.cpu.return_value.numpy.return_value = classes_array
    # По умолчанию уверенность высокая (0.9) — все детекции проходят оба порога.
    if confs_array is None:
        confs_array = np.full((len(classes_array),), 0.9, dtype=np.float32)
    result.boxes.conf = MagicMock()
    result.boxes.conf.cpu.return_value.numpy.return_value = confs_array
    if track_ids_array is not None:
        result.boxes.id = MagicMock()
        result.boxes.id.cpu.return_value.numpy.return_value = track_ids_array
    else:
        result.boxes.id = None
    return result


class TestRunDetectionStructure:
    def test_returns_expected_keys(self, mock_model):
        boxes = np.empty((0, 4), dtype=np.float32)
        classes = np.empty((0,), dtype=np.int32)
        mock_model.track.return_value = [make_mock_track_result(boxes, classes)]

        from backend.detection.engine import run_detection
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = run_detection(frame, mock_model)

        assert 'persons' in result
        assert 'person_track_ids' in result
        assert 'helmets' in result
        assert 'masks' in result
        assert 'vests' in result
        assert 'cones' in result

    def test_no_objects_returns_empty_lists(self, mock_model):
        boxes = np.empty((0, 4), dtype=np.float32)
        classes = np.empty((0,), dtype=np.int32)
        mock_model.track.return_value = [make_mock_track_result(boxes, classes)]

        from backend.detection.engine import run_detection
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = run_detection(frame, mock_model)

        assert result['persons'] == []
        assert result['person_track_ids'] == []
        assert result['helmets'] == []
        assert result['masks'] == []
        assert result['vests'] == []
        assert result['cones'] == []


class TestPersonDetection:
    def test_single_person(self, mock_model):
        boxes = np.array([[10, 20, 100, 200]], dtype=np.float32)
        classes = np.array([5], dtype=np.int32)
        track_ids = np.array([1], dtype=np.int32)
        mock_model.track.return_value = [make_mock_track_result(boxes, classes, track_ids)]

        from backend.detection.engine import run_detection
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = run_detection(frame, mock_model)

        assert len(result['persons']) == 1
        assert result['person_track_ids'] == [1]
        np.testing.assert_array_equal(result['persons'][0], [10, 20, 100, 200])

    def test_multiple_persons(self, mock_model):
        boxes = np.array([
            [10, 20, 100, 200],
            [150, 30, 250, 220],
        ], dtype=np.float32)
        classes = np.array([5, 5], dtype=np.int32)
        track_ids = np.array([1, 2], dtype=np.int32)
        mock_model.track.return_value = [make_mock_track_result(boxes, classes, track_ids)]

        from backend.detection.engine import run_detection
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = run_detection(frame, mock_model)

        assert len(result['persons']) == 2
        assert result['person_track_ids'] == [1, 2]

    def test_filters_non_person_classes(self, mock_model):
        boxes = np.array([
            [10, 20, 50, 60],   # helmet (class 0)
            [70, 80, 120, 180],  # person (class 5)
            [200, 50, 250, 100], # cone (class 6)
        ], dtype=np.float32)
        classes = np.array([0, 5, 6], dtype=np.int32)
        track_ids = np.array([1, 2, 3], dtype=np.int32)
        mock_model.track.return_value = [make_mock_track_result(boxes, classes, track_ids)]

        from backend.detection.engine import run_detection
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = run_detection(frame, mock_model)

        assert len(result['persons']) == 1
        assert result['person_track_ids'] == [2]
        assert len(result['helmets']) == 1
        assert len(result['cones']) == 1


class TestPPEDetection:
    def test_ppe_boxes_are_extracted(self, mock_model):
        boxes = np.array([
            [10, 20, 100, 200],   # person
            [30, 40, 60, 80],     # helmet on person
            [50, 60, 90, 120],    # mask on person
            [15, 25, 95, 195],    # vest on person
        ], dtype=np.float32)
        classes = np.array([5, 0, 1, 7], dtype=np.int32)
        track_ids = np.array([1, 2, 3, 4], dtype=np.int32)
        mock_model.track.return_value = [make_mock_track_result(boxes, classes, track_ids)]

        from backend.detection.engine import run_detection
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = run_detection(frame, mock_model)

        assert len(result['persons']) == 1
        assert len(result['helmets']) == 1
        assert len(result['masks']) == 1
        assert len(result['vests']) == 1
        assert len(result['cones']) == 0

    def test_low_conf_helmet_kept_but_person_filtered(self, mock_model):
        # Каска с уверенностью 0.6 (< CONF_THRESH 0.75, но ≥ PPE 0.5) должна
        # ОСТАТЬСЯ — иначе человек в каске ложно считается без каски.
        # Человек с уверенностью 0.6 (< 0.75) — отфильтровывается (строгий порог).
        boxes = np.array([
            [10, 20, 100, 200],   # person, conf 0.6 → отфильтрован
            [30, 10, 70, 50],     # helmet, conf 0.6 → оставлен (PPE-порог мягче)
        ], dtype=np.float32)
        classes = np.array([5, 0], dtype=np.int32)
        track_ids = np.array([1, 2], dtype=np.int32)
        confs = np.array([0.6, 0.6], dtype=np.float32)
        mock_model.track.return_value = [
            make_mock_track_result(boxes, classes, track_ids, confs)]

        from backend.detection.engine import run_detection
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = run_detection(frame, mock_model)

        assert len(result['persons']) == 0   # человек 0.6 < 0.75
        assert len(result['helmets']) == 1    # каска 0.6 ≥ 0.5 — сохранена

    def test_ppe_below_ppe_threshold_dropped(self, mock_model):
        # Каска ниже даже PPE-порога (0.3 < 0.5) — отбрасывается.
        boxes = np.array([[30, 10, 70, 50]], dtype=np.float32)
        classes = np.array([0], dtype=np.int32)
        track_ids = np.array([1], dtype=np.int32)
        confs = np.array([0.3], dtype=np.float32)
        mock_model.track.return_value = [
            make_mock_track_result(boxes, classes, track_ids, confs)]

        from backend.detection.engine import run_detection
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = run_detection(frame, mock_model)

        assert len(result['helmets']) == 0


class TestTrackerConfig:
    def test_tracker_config_exists(self):
        from backend.detection.engine import TRACKER_CFG
        assert TRACKER_CFG is not None
        assert TRACKER_CFG.endswith('bytetrack_custom.yaml')


# ── Pure helper function tests ────────────────────────────────────────────────

class TestGetBoxesByClass:
    def _make_names(self, *names):
        return {i: n for i, n in enumerate(names)}

    def test_empty_inputs_returns_empty(self):
        from backend.detection.engine import get_boxes_by_class
        assert get_boxes_by_class([], [], {}, "Каска") == []

    def test_single_matching_class(self):
        from backend.detection.engine import get_boxes_by_class
        import numpy as np
        boxes = [np.array([0, 0, 10, 10])]
        names = self._make_names("Каска")
        result = get_boxes_by_class(boxes, [0], names, "Каска")
        assert len(result) == 1

    def test_no_matching_class(self):
        from backend.detection.engine import get_boxes_by_class
        import numpy as np
        boxes = [np.array([0, 0, 10, 10])]
        names = self._make_names("Каска")
        result = get_boxes_by_class(boxes, [0], names, "Маска")
        assert result == []

    def test_multiple_matching_boxes(self):
        from backend.detection.engine import get_boxes_by_class
        import numpy as np
        boxes = [np.array([0, 0, 5, 5]), np.array([10, 10, 20, 20])]
        names = self._make_names("Каска", "Каска")
        result = get_boxes_by_class(boxes, [0, 0], names, "Каска")
        assert len(result) == 2

    def test_filters_other_classes(self):
        from backend.detection.engine import get_boxes_by_class
        import numpy as np
        boxes = [np.array([0, 0, 5, 5]), np.array([10, 10, 20, 20]),
                 np.array([30, 30, 40, 40])]
        names = self._make_names("Каска", "Маска", "Каска")
        result = get_boxes_by_class(boxes, [0, 1, 0], names, "Каска")
        assert len(result) == 2


class TestHasItemOnPerson:
    def test_item_centered_on_upper_body(self):
        from backend.detection.engine import has_item_on_person
        person = [0, 0, 100, 200]   # top-left (0,0), bottom-right (100,200)
        helmet = [40, 10, 60, 50]   # center at (50, 30) — within upper 40%
        assert has_item_on_person(person, helmet) is True

    def test_item_below_upper_threshold(self):
        from backend.detection.engine import has_item_on_person
        person = [0, 0, 100, 200]
        item = [40, 150, 60, 190]   # center at (50, 170) — below 40% mark (y=80)
        assert has_item_on_person(person, item) is False

    def test_item_outside_horizontal_bounds(self):
        from backend.detection.engine import has_item_on_person
        person = [0, 0, 100, 200]
        item = [110, 10, 130, 50]   # center at (120, 30) — outside x range
        assert has_item_on_person(person, item) is False

    def test_item_at_exact_upper_boundary(self):
        from backend.detection.engine import has_item_on_person
        person = [0, 0, 100, 100]
        # upper_y = 0 + (100-0)*0.4 = 40; item center_y exactly at 40
        item = [40, 30, 60, 50]    # center_y = 40 — should be True (<=)
        assert has_item_on_person(person, item) is True

    def test_custom_top_ratio_full_body(self):
        from backend.detection.engine import has_item_on_person
        person = [0, 0, 100, 200]
        item = [40, 150, 60, 190]   # center at (50, 170)
        assert has_item_on_person(person, item, top_ratio=1.0) is True

    def test_custom_top_ratio_zero_nothing_matches(self):
        from backend.detection.engine import has_item_on_person
        person = [0, 0, 100, 200]
        item = [40, 0, 60, 2]      # center at (50, 1) — even very top
        assert has_item_on_person(person, item, top_ratio=0.0) is False

    def test_item_far_above_person_not_counted(self):
        # Каска на полке НАД человеком (центр целиком выше bbox с запасом) —
        # не считается надетой (нижняя граница по y с допуском HEAD_MARGIN_RATIO).
        from backend.detection.engine import has_item_on_person
        person = [0, 100, 100, 300]   # рост 200, допуск сверху 20px (до y=80)
        item = [40, 10, 60, 50]       # center (50, 30) — сильно выше головы
        assert has_item_on_person(person, item) is False

    def test_item_slightly_above_bbox_top_counted(self):
        # Каска чуть выступает над рамкой человека (джиттер детекции) — в
        # пределах допуска HEAD_MARGIN_RATIO засчитывается.
        from backend.detection.engine import has_item_on_person
        person = [0, 100, 100, 300]   # рост 200, допуск сверху до y=80
        item = [40, 75, 60, 105]      # center (50, 90) — чуть выше py1=100
        assert has_item_on_person(person, item) is True


class TestGetDangerZonePolygon:
    """Зона — многоугольник: N вершин = N конусов (вершина = центр конуса)."""
    def _square_cones(self):
        return [[0, 0, 20, 20], [100, 0, 120, 20],
                [100, 100, 120, 120], [0, 100, 20, 120]]

    def test_empty_cones_returns_none(self):
        from backend.detection.engine import get_danger_zone
        assert get_danger_zone([]) is None

    def test_below_min_cones_returns_none(self):
        from backend.detection.engine import get_danger_zone
        from backend.config import MIN_CONES
        cones = [[0, 0, 10, 10]] * (MIN_CONES - 1)
        assert get_danger_zone(cones) is None

    def test_vertices_count_equals_cones(self):
        from backend.detection.engine import get_danger_zone
        base = [[0, 0, 20, 20], [100, 0, 120, 20], [100, 100, 120, 120],
                [0, 100, 20, 120], [50, 150, 70, 170]]
        for n in (3, 4, 5):
            zone = get_danger_zone(base[:n])
            assert zone is not None
            assert zone.shape == (n, 2)   # N углов = N конусов

    def test_four_cones_quadrilateral(self):
        from backend.detection.engine import get_danger_zone
        zone = get_danger_zone(self._square_cones())
        assert zone.shape == (4, 2)

    def test_expansion_pushes_outward(self):
        from backend.detection.engine import get_danger_zone
        cones = self._square_cones()
        centers = np.array([[(c[0] + c[2]) / 2, (c[1] + c[3]) / 2] for c in cones])
        centroid = centers.mean(axis=0)
        zone = get_danger_zone(cones)
        zone_max = max(np.linalg.norm(np.array(v) - centroid) for v in zone)
        base_max = max(np.linalg.norm(c - centroid) for c in centers)
        assert zone_max > base_max   # вершины раздвинуты наружу на ZONE_EXPAND_PX


class TestIsInDangerZonePolygon:
    def _square_zone(self):
        from backend.detection.engine import get_danger_zone
        return get_danger_zone([[0, 0, 20, 20], [100, 0, 120, 20],
                                [100, 100, 120, 120], [0, 100, 20, 120]])

    def test_none_zone_false(self):
        from backend.detection.engine import is_in_danger_zone
        assert is_in_danger_zone([0, 0, 100, 200], None) is False

    def test_foot_inside_polygon(self):
        from backend.detection.engine import is_in_danger_zone
        zone = self._square_zone()
        person = [50, 0, 70, 60]    # foot=(60,60) — центр квадрата
        assert is_in_danger_zone(person, zone) is True

    def test_foot_outside_polygon(self):
        from backend.detection.engine import is_in_danger_zone
        zone = self._square_zone()
        person = [300, 0, 320, 400]  # foot=(310,400) — далеко за пределами
        assert is_in_danger_zone(person, zone) is False

    def test_two_cones_degenerate_no_area(self):
        # 2 конуса → полигон из 2 точек, площади нет → никто не «в зоне»
        from backend.detection.engine import get_danger_zone, is_in_danger_zone
        zone = get_danger_zone([[0, 0, 20, 20], [100, 100, 120, 120]])
        assert is_in_danger_zone([50, 0, 70, 60], zone) is False


class TestHasItemOnPersonStashed:
    def test_item_on_person(self):
        from backend.detection.engine import has_item_on_person
        person = [100, 100, 200, 300]
        helmet = [120, 120, 150, 150]
        assert has_item_on_person(person, helmet)

    def test_item_off_person_left(self):
        from backend.detection.engine import has_item_on_person
        person = [100, 100, 200, 300]
        item = [50, 120, 90, 150]   # center x = 70 < person x1
        assert not has_item_on_person(person, item)

    def test_item_off_person_right(self):
        from backend.detection.engine import has_item_on_person
        person = [100, 100, 200, 300]
        item = [210, 120, 250, 150]  # center x = 230 > person x2
        assert not has_item_on_person(person, item)

    def test_item_too_low_on_person(self):
        from backend.detection.engine import has_item_on_person
        person = [100, 100, 200, 300]
        item = [120, 250, 150, 280]
        upper_y = 100 + (300 - 100) * 0.4   # = 180
        assert 250 > upper_y   # item center y = 265 > upper_y
        assert not has_item_on_person(person, item)
