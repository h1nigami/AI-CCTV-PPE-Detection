from unittest.mock import MagicMock, patch
import numpy as np
import pytest


@pytest.fixture
def mock_model():
    model = MagicMock()
    model.names = {0: "Каска", 1: "Маска", 5: "Человек", 6: "Конус безопасности", 7: "Защитный жилет"}
    return model


def make_mock_track_result(boxes_array, classes_array, track_ids_array=None):
    result = MagicMock()
    result.boxes.xyxy = MagicMock()
    result.boxes.xyxy.cpu.return_value.numpy.return_value = boxes_array
    result.boxes.cls = MagicMock()
    result.boxes.cls.cpu.return_value.numpy.return_value = classes_array
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


class TestGetDangerZone:
    def test_empty_cones_returns_none(self):
        from backend.detection.engine import get_danger_zone
        assert get_danger_zone([]) is None

    def test_single_cone_below_min_returns_none(self):
        from backend.detection.engine import get_danger_zone
        from backend.config import MIN_CONES
        if MIN_CONES > 1:
            assert get_danger_zone([[0, 0, 10, 10]]) is None

    def test_two_cones_returns_four_int_tuple(self):
        from backend.detection.engine import get_danger_zone
        cones = [[0, 0, 50, 50], [100, 100, 150, 150]]
        zone = get_danger_zone(cones)
        assert zone is not None
        assert len(zone) == 4
        assert all(isinstance(v, int) for v in zone)

    def test_expansion_applied(self):
        from backend.detection.engine import get_danger_zone
        from backend.config import ZONE_EXPAND_PX
        cones = [[10, 10, 50, 50], [60, 60, 100, 100]]
        zone = get_danger_zone(cones)
        assert zone[0] == 10 - ZONE_EXPAND_PX    # min x1 - expand
        assert zone[1] == 10 - ZONE_EXPAND_PX    # min y1 - expand
        assert zone[2] == 100 + ZONE_EXPAND_PX   # max x2 + expand
        assert zone[3] == 100 + ZONE_EXPAND_PX   # max y2 + expand

    def test_zone_uses_min_max_of_all_cones(self):
        from backend.detection.engine import get_danger_zone
        from backend.config import ZONE_EXPAND_PX
        cones = [[5, 10, 20, 30], [50, 15, 80, 90]]
        zone = get_danger_zone(cones)
        assert zone[0] == 5 - ZONE_EXPAND_PX
        assert zone[1] == 10 - ZONE_EXPAND_PX
        assert zone[2] == 80 + ZONE_EXPAND_PX
        assert zone[3] == 90 + ZONE_EXPAND_PX


class TestIsInDangerZone:
    def test_none_danger_zone_always_false(self):
        from backend.detection.engine import is_in_danger_zone
        assert is_in_danger_zone([0, 0, 100, 200], None) is False

    def test_foot_inside_zone(self):
        from backend.detection.engine import is_in_danger_zone
        person = [40, 0, 60, 100]   # foot_x=50, foot_y=100
        zone = (0, 80, 100, 150)    # zone covers x[0..100], y[80..150]
        assert is_in_danger_zone(person, zone) is True

    def test_foot_outside_zone_horizontally(self):
        from backend.detection.engine import is_in_danger_zone
        person = [200, 0, 220, 100]  # foot_x=210
        zone = (0, 80, 100, 150)
        assert is_in_danger_zone(person, zone) is False

    def test_foot_outside_zone_vertically_above(self):
        from backend.detection.engine import is_in_danger_zone
        person = [40, 0, 60, 50]    # foot_y=50
        zone = (0, 80, 100, 150)    # zone y starts at 80
        assert is_in_danger_zone(person, zone) is False

    def test_foot_at_zone_boundary(self):
        from backend.detection.engine import is_in_danger_zone
        person = [0, 0, 100, 80]    # foot_x=50, foot_y=80
        zone = (0, 80, 100, 150)    # exactly on zy1 boundary
        assert is_in_danger_zone(person, zone) is True


class TestDangerZone:
    @pytest.fixture
    def two_cones(self):
        return [np.array([100, 200, 120, 300]), np.array([300, 200, 320, 300])]

    @pytest.fixture
    def three_cones(self):
        return [
            np.array([100, 200, 120, 300]),
            np.array([300, 200, 320, 300]),
            np.array([200, 100, 220, 200]),
        ]

    def test_no_cones_returns_none(self):
        from backend.detection.engine import get_danger_zone
        assert get_danger_zone([]) is None

    def test_one_cone_returns_none(self):
        from backend.detection.engine import get_danger_zone
        assert get_danger_zone([np.array([100, 200, 120, 300])]) is None

    def test_two_cones_returns_zone(self, two_cones):
        from backend.detection.engine import get_danger_zone
        zone = get_danger_zone(two_cones)
        assert zone is not None
        x1, y1, x2, y2 = zone
        assert x1 == 80   # min(100, 300) - 20
        assert y1 == 180  # min(200, 200) - 20
        assert x2 == 340  # max(120, 320) + 20
        assert y2 == 320  # max(300, 300) + 20

    def test_three_cones_returns_zone(self, three_cones):
        from backend.detection.engine import get_danger_zone
        zone = get_danger_zone(three_cones)
        assert zone is not None
        x1, y1, x2, y2 = zone
        assert x1 == 80   # min(100, 300, 200) - 20
        assert y1 == 80   # min(200, 200, 100) - 20
        assert x2 == 340  # max(120, 320, 220) + 20
        assert y2 == 320  # max(300, 300, 200) + 20

    def test_is_in_danger_zone_person_inside(self):
        from backend.detection.engine import is_in_danger_zone
        zone = (80, 180, 340, 320)
        person = [150, 250, 200, 350]   # foot at (175, 350) — outside by y
        assert not is_in_danger_zone(person, zone)

    def test_is_in_danger_zone_person_foot_inside(self):
        from backend.detection.engine import is_in_danger_zone
        zone = (80, 180, 340, 320)
        person = [150, 200, 200, 300]   # foot at (175, 300) — inside
        assert is_in_danger_zone(person, zone)

    def test_is_in_danger_zone_person_outside_left(self):
        from backend.detection.engine import is_in_danger_zone
        zone = (80, 180, 340, 320)
        person = [10, 200, 50, 300]    # foot at (30, 300) — outside left
        assert not is_in_danger_zone(person, zone)

    def test_is_in_danger_zone_person_outside_below(self):
        from backend.detection.engine import is_in_danger_zone
        zone = (80, 180, 340, 320)
        person = [150, 400, 200, 500]  # foot at (175, 500) — outside below
        assert not is_in_danger_zone(person, zone)

    def test_is_in_danger_zone_person_on_boundary(self):
        from backend.detection.engine import is_in_danger_zone
        zone = (80, 180, 340, 320)
        person = [80, 180, 80, 180]    # foot at (80, 180) — on top-left corner
        assert is_in_danger_zone(person, zone)

    def test_is_in_danger_zone_none_zone_returns_false(self):
        from backend.detection.engine import is_in_danger_zone
        person = [150, 200, 200, 300]
        assert not is_in_danger_zone(person, None)


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
