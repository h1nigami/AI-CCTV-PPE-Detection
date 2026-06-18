"""Tests for backend/gestures/detector.py"""
from __future__ import annotations
import numpy as np
import pytest
from unittest.mock import MagicMock


def _make_pose_result(keypoints_xy=None):
    """Build a minimal mock that mimics a YOLO pose result."""
    result = MagicMock()
    if keypoints_xy is None:
        result.keypoints = None
    else:
        result.keypoints = MagicMock()
        result.keypoints.xy = MagicMock()
        result.keypoints.xy.cpu.return_value.numpy.return_value = keypoints_xy
    return result


def _make_model(result):
    model = MagicMock()
    model.return_value = [result]
    return model


def _blank_frame(h=200, w=200):
    return np.zeros((h, w, 3), dtype=np.uint8)


def _valid_kp(n=17, raise_right=False, raise_left=False):
    """
    Build a (1, n, 2) keypoints array with valid (non-zero) coordinates.

    Indices used by the code:
      0=nose, 5=L-shoulder, 6=R-shoulder, 7=L-elbow, 8=R-elbow,
      9=L-wrist, 10=R-wrist
    """
    kp = np.ones((1, n, 2), dtype=np.float32) * 50  # all valid
    kp[0, 0] = [100, 100]   # nose  at y=100
    kp[0, 5] = [80, 90]     # left  shoulder  at y=90
    kp[0, 6] = [120, 90]    # right shoulder  at y=90
    kp[0, 7] = [70, 80]     # left  elbow
    kp[0, 8] = [130, 80]    # right elbow
    kp[0, 9] = [60, 150]    # left  wrist     at y=150 (below nose → NOT raised)
    kp[0, 10] = [140, 150]  # right wrist     at y=150 (below nose → NOT raised)
    if raise_right:
        kp[0, 10] = [140, 50]   # right wrist above nose (y=50 < y=100)
    if raise_left:
        kp[0, 9] = [60, 50]     # left wrist above nose
    return kp


# ── detect_ok_gesture ─────────────────────────────────────────────────────────

class TestDetectOkGesture:
    def test_empty_crop_returns_false(self):
        from backend.gestures.detector import detect_ok_gesture
        frame = _blank_frame(50, 50)
        # Person box outside frame → crop is empty
        result = detect_ok_gesture(frame, [100, 100, 200, 200], MagicMock())
        assert result is False

    def test_model_exception_returns_false(self):
        from backend.gestures.detector import detect_ok_gesture
        model = MagicMock(side_effect=RuntimeError("model error"))
        frame = _blank_frame()
        result = detect_ok_gesture(frame, [0, 0, 100, 100], model)
        assert result is False

    def test_none_keypoints_returns_false(self):
        from backend.gestures.detector import detect_ok_gesture
        model = _make_model(_make_pose_result(keypoints_xy=None))
        frame = _blank_frame()
        assert detect_ok_gesture(frame, [0, 0, 100, 100], model) is False

    def test_empty_keypoints_array_returns_false(self):
        from backend.gestures.detector import detect_ok_gesture
        model = _make_model(_make_pose_result(keypoints_xy=np.zeros((0, 17, 2))))
        frame = _blank_frame()
        assert detect_ok_gesture(frame, [0, 0, 100, 100], model) is False

    def test_insufficient_keypoints_returns_false(self):
        from backend.gestures.detector import detect_ok_gesture
        kp = np.ones((1, 5, 2), dtype=np.float32)  # only 5 keypoints
        model = _make_model(_make_pose_result(keypoints_xy=kp))
        frame = _blank_frame()
        assert detect_ok_gesture(frame, [0, 0, 100, 100], model) is False

    def test_no_raised_hand_returns_false(self):
        from backend.gestures.detector import detect_ok_gesture
        kp = _valid_kp(raise_right=False, raise_left=False)
        model = _make_model(_make_pose_result(keypoints_xy=kp))
        frame = _blank_frame()
        assert detect_ok_gesture(frame, [0, 0, 100, 100], model) is False


# ── detect_raised_hand ────────────────────────────────────────────────────────

class TestDetectRaisedHand:
    def test_empty_crop_returns_false(self):
        from backend.gestures.detector import detect_raised_hand
        frame = _blank_frame(50, 50)
        assert detect_raised_hand(frame, [100, 100, 200, 200], MagicMock()) is False

    def test_model_exception_returns_false(self):
        from backend.gestures.detector import detect_raised_hand
        model = MagicMock(side_effect=RuntimeError("boom"))
        frame = _blank_frame()
        assert detect_raised_hand(frame, [0, 0, 100, 100], model) is False

    def test_none_keypoints_returns_false(self):
        from backend.gestures.detector import detect_raised_hand
        model = _make_model(_make_pose_result(keypoints_xy=None))
        frame = _blank_frame()
        assert detect_raised_hand(frame, [0, 0, 100, 100], model) is False

    def test_insufficient_keypoints_returns_false(self):
        from backend.gestures.detector import detect_raised_hand
        kp = np.ones((1, 5, 2), dtype=np.float32)
        model = _make_model(_make_pose_result(keypoints_xy=kp))
        frame = _blank_frame()
        assert detect_raised_hand(frame, [0, 0, 100, 100], model) is False

    def test_no_raised_hands_returns_false(self):
        from backend.gestures.detector import detect_raised_hand
        kp = _valid_kp(raise_right=False, raise_left=False)
        model = _make_model(_make_pose_result(keypoints_xy=kp))
        frame = _blank_frame()
        assert not detect_raised_hand(frame, [0, 0, 100, 100], model)

    def test_raised_right_hand_returns_true(self):
        from backend.gestures.detector import detect_raised_hand
        kp = _valid_kp(raise_right=True)
        model = _make_model(_make_pose_result(keypoints_xy=kp))
        frame = _blank_frame()
        assert detect_raised_hand(frame, [0, 0, 100, 100], model)

    def test_raised_left_hand_returns_true(self):
        from backend.gestures.detector import detect_raised_hand
        kp = _valid_kp(raise_left=True)
        model = _make_model(_make_pose_result(keypoints_xy=kp))
        frame = _blank_frame()
        assert detect_raised_hand(frame, [0, 0, 100, 100], model)

    def test_invalid_keypoints_zero_coords_returns_false(self):
        from backend.gestures.detector import detect_raised_hand
        kp = np.zeros((1, 17, 2), dtype=np.float32)  # all at (0,0) → invalid
        model = _make_model(_make_pose_result(keypoints_xy=kp))
        frame = _blank_frame()
        assert not detect_raised_hand(frame, [0, 0, 100, 100], model)


# ── _is_ok_by_contour ─────────────────────────────────────────────────────────

class TestIsOkByContour:
    def test_solid_color_image_returns_false(self):
        from backend.gestures.detector import _is_ok_by_contour
        img = np.ones((100, 100, 3), dtype=np.uint8) * 128
        assert _is_ok_by_contour(img) is False

    def test_too_small_contour_returns_false(self):
        from backend.gestures.detector import _is_ok_by_contour
        # Single white pixel on black background → tiny contour below MIN_HAND_AREA
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        img[50, 50] = [255, 255, 255]
        assert _is_ok_by_contour(img) is False
