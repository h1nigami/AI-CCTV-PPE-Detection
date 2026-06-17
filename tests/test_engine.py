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
