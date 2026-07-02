"""Tests for backend/reid/recognizer.py — FaceRecognitionWorker and match_faces_to_persons"""
from __future__ import annotations
import time
import threading
import numpy as np
import pytest
from unittest.mock import MagicMock


def _norm_emb(seed=None):
    rng = np.random.RandomState(seed)
    emb = rng.randn(512).astype(np.float32)
    return emb / (np.linalg.norm(emb) + 1e-8)


def _fake_face(x1, y1, x2, y2, seed=None):
    """Return (bbox, embedding, quality) tuple."""
    return (np.array([x1, y1, x2, y2], dtype=np.float32), _norm_emb(seed), 0.8)


# ── match_faces_to_persons ────────────────────────────────────────────────────

class TestMatchFacesToPersons:
    def test_empty_persons_returns_empty(self):
        from backend.reid.recognizer import match_faces_to_persons
        assert match_faces_to_persons([], [_fake_face(0, 0, 50, 50)]) == []

    def test_empty_faces_returns_nones(self):
        from backend.reid.recognizer import match_faces_to_persons
        persons = [np.array([0, 0, 100, 200]), np.array([200, 0, 300, 200])]
        results = match_faces_to_persons(persons, [])
        assert len(results) == 2
        assert all(emb is None for emb, _ in results)
        assert all(q == 0.0 for _, q in results)

    def test_overlapping_face_assigned_to_person(self):
        from backend.reid.recognizer import match_faces_to_persons
        person = np.array([0, 0, 100, 200], dtype=np.float32)
        # face completely inside person box
        face = _fake_face(10, 10, 60, 60, seed=1)
        results = match_faces_to_persons([person], [face])
        assert len(results) == 1
        emb, quality = results[0]
        assert emb is not None
        assert quality == 0.8

    def test_non_overlapping_face_not_assigned(self):
        from backend.reid.recognizer import match_faces_to_persons
        person = np.array([0, 0, 100, 200], dtype=np.float32)
        face = _fake_face(200, 200, 300, 300, seed=2)  # no overlap
        results = match_faces_to_persons([person], [face])
        # Лицо вне bbox человека НЕ присваивается: иначе человек спиной получал
        # бы ближайшее чужое лицо (а с ним чужую личность и её пропуск).
        assert len(results) == 1
        emb, quality = results[0]
        assert emb is None
        assert quality == 0.0

    def test_backturned_person_does_not_inherit_neighbors_face(self):
        # Два человека: у первого лицо видно, второй спиной (его лица нет в
        # face_data). Второй не должен получить лицо первого.
        from backend.reid.recognizer import match_faces_to_persons
        person_a = np.array([0, 0, 100, 200], dtype=np.float32)
        person_b = np.array([150, 0, 250, 200], dtype=np.float32)
        face_a = _fake_face(30, 10, 70, 50, seed=3)  # внутри person_a
        results = match_faces_to_persons([person_a, person_b], [face_a])
        assert results[0][0] is not None
        assert results[1][0] is None
        assert results[1][1] == 0.0

    def test_best_overlap_wins_when_multiple_faces(self):
        from backend.reid.recognizer import match_faces_to_persons
        person = np.array([0, 0, 100, 200], dtype=np.float32)
        face_a = _fake_face(5, 5, 30, 30, seed=10)    # inside → overlap > 0
        face_b = _fake_face(200, 200, 250, 250, seed=11)  # outside
        results = match_faces_to_persons([person], [face_a, face_b])
        _, emb_a, _ = face_a      # face_a is (bbox, emb, quality)
        emb_result, _ = results[0]
        np.testing.assert_array_equal(emb_result, emb_a)

    def test_quality_is_propagated(self):
        from backend.reid.recognizer import match_faces_to_persons
        person = np.array([0, 0, 100, 200], dtype=np.float32)
        bbox = np.array([10, 10, 60, 60], dtype=np.float32)
        emb = _norm_emb(42)
        face = (bbox, emb, 0.65)
        _, quality = match_faces_to_persons([person], [face])[0]
        assert quality == pytest.approx(0.65)


# ── FaceRecognitionWorker ─────────────────────────────────────────────────────

class TestFaceRecognitionWorker:
    def _make_worker(self, faces=None):
        from backend.reid.recognizer import FaceRecognitionWorker
        buf = MagicMock()
        buf.read.return_value = None  # returns no frame by default
        rec = MagicMock()
        rec.detect_faces.return_value = faces or []
        return FaceRecognitionWorker(buf, rec, frame_skip=1), buf, rec

    def test_get_faces_initially_empty(self):
        worker, _, _ = self._make_worker()
        assert worker.get_faces() == []

    def test_start_sets_running_flag(self):
        worker, _, _ = self._make_worker()
        worker.start()
        assert worker._running is True
        worker.stop()

    def test_stop_clears_running_flag(self):
        worker, _, _ = self._make_worker()
        worker.start()
        worker.stop()
        assert worker._running is False

    def test_start_is_idempotent(self):
        worker, _, _ = self._make_worker()
        worker.start()
        t1 = worker._thread
        worker.start()   # second call should be a no-op
        assert worker._thread is t1
        worker.stop()

    def test_worker_updates_faces_from_recognizer(self):
        from backend.reid.recognizer import FaceRecognitionWorker
        fake_face = _fake_face(0, 0, 50, 50)

        buf = MagicMock()
        buf.read.return_value = np.zeros((100, 100, 3), dtype=np.uint8)

        rec = MagicMock()
        rec.detect_faces.return_value = [fake_face]

        worker = FaceRecognitionWorker(buf, rec, frame_skip=1)
        worker.start()
        time.sleep(0.1)   # let one cycle run
        faces = worker.get_faces()
        worker.stop()

        assert len(faces) >= 1

    def test_recognizer_exception_does_not_crash_worker(self):
        from backend.reid.recognizer import FaceRecognitionWorker
        buf = MagicMock()
        buf.read.return_value = np.zeros((10, 10, 3), dtype=np.uint8)

        rec = MagicMock()
        rec.detect_faces.side_effect = RuntimeError("model crashed")

        worker = FaceRecognitionWorker(buf, rec, frame_skip=1)
        worker.start()
        time.sleep(0.1)
        assert worker._running is True  # still alive despite exceptions
        worker.stop()
