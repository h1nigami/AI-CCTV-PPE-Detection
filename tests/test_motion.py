"""Тесты детекции движения (MOG2)."""
import numpy as np
import pytest

from backend.detection.motion import MotionDetector, MotionResult


def _blank(h=240, w=320):
    return np.zeros((h, w, 3), dtype=np.uint8)


def test_empty_frame_no_motion():
    det = MotionDetector()
    res = det.detect(None)
    assert isinstance(res, MotionResult)
    assert not res.motion
    res2 = det.detect(np.zeros((0, 0, 3), dtype=np.uint8))
    assert not res2.motion


def test_static_scene_has_no_motion():
    det = MotionDetector(min_area=500, cooldown_frames=0)
    frame = _blank()
    # Прогреваем модель фона несколькими одинаковыми кадрами.
    for _ in range(10):
        det.detect(frame)
    assert not det.detect(frame).motion


def test_moving_object_triggers_motion():
    det = MotionDetector(threshold=30, min_area=300, cooldown_frames=0)
    frame = _blank()
    for _ in range(10):
        det.detect(frame)
    moved = _blank()
    # Крупный яркий прямоугольник — резкое изменение сцены.
    moved[50:180, 60:220] = 255
    res = det.detect(moved)
    assert res.motion
    assert res.area_ratio > 0
    assert len(res.boxes) >= 1


def test_cooldown_holds_motion_after_object_stops():
    det = MotionDetector(threshold=30, min_area=300, cooldown_frames=3)
    frame = _blank()
    for _ in range(10):
        det.detect(frame)
    moved = _blank()
    moved[50:180, 60:220] = 255
    assert det.detect(moved).motion
    # После исчезновения движения cooldown ещё удерживает True.
    held = [det.detect(moved).motion for _ in range(3)]
    assert all(held)


def test_bool_protocol():
    res = MotionResult(True, 0.1, [(0, 0, 10, 10)])
    assert bool(res) is True
    assert not bool(MotionResult(False, 0.0, []))


def test_reset_clears_state():
    det = MotionDetector(cooldown_frames=5)
    det._cooldown = 5
    det.reset()
    assert det._cooldown == 0
