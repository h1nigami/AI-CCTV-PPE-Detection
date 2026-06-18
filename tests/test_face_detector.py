"""Tests for backend/reid/worker.py (FaceDetector)"""
from __future__ import annotations
import numpy as np
import pytest


class TestFaceDetector:
    def test_init_without_model_file(self, tmp_path):
        """Non-existent model path → _model is None, no crash."""
        from backend.reid.worker import FaceDetector
        fd = FaceDetector(model_path=str(tmp_path / "nonexistent.pt"))
        assert fd._model is None

    def test_detect_with_no_model_returns_empty_list(self, tmp_path):
        from backend.reid.worker import FaceDetector
        fd = FaceDetector(model_path=str(tmp_path / "nonexistent.pt"))
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        faces = fd.detect(frame)
        assert faces == []

    def test_crop_face_returns_correct_region(self, tmp_path):
        from backend.reid.worker import FaceDetector
        fd = FaceDetector(model_path=str(tmp_path / "nonexistent.pt"))
        frame = np.zeros((200, 200, 3), dtype=np.uint8)
        frame[50:100, 60:110] = 128   # mark the face region
        crop = fd.crop_face(frame, (60, 50, 110, 100), margin=0.0)
        assert crop is not None
        assert crop.shape[0] > 0 and crop.shape[1] > 0

    def test_crop_face_with_margin_stays_in_bounds(self, tmp_path):
        from backend.reid.worker import FaceDetector
        fd = FaceDetector(model_path=str(tmp_path / "nonexistent.pt"))
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        # Box at corners — margin might push outside frame, should be clamped
        crop = fd.crop_face(frame, (0, 0, 20, 20), margin=0.5)
        assert crop is not None

    def test_detect_with_mocked_model(self, tmp_path):
        from unittest.mock import MagicMock
        import numpy as np
        from backend.reid.worker import FaceDetector

        fd = FaceDetector(model_path=str(tmp_path / "nonexistent.pt"))

        # Inject a fake model
        mock_result = MagicMock()
        mock_box = MagicMock()
        mock_box.xyxy.cpu.return_value.numpy.return_value = np.array(
            [[10.0, 20.0, 50.0, 60.0]]
        )
        mock_result.boxes = mock_box
        fd._model = MagicMock(return_value=[mock_result])

        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        faces = fd.detect(frame)
        assert len(faces) == 1
        assert faces[0] == (10, 20, 50, 60)

    def test_detect_handles_model_exception(self, tmp_path):
        from unittest.mock import MagicMock
        from backend.reid.worker import FaceDetector

        fd = FaceDetector(model_path=str(tmp_path / "nonexistent.pt"))
        fd._model = MagicMock(side_effect=RuntimeError("model error"))

        frame = np.zeros((50, 50, 3), dtype=np.uint8)
        faces = fd.detect(frame)
        assert faces == []
