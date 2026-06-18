"""Tests for backend/capture/buffer.py (FrameBuffer)"""
from __future__ import annotations
import threading
import numpy as np
import pytest


@pytest.fixture
def buf():
    from backend.capture.buffer import FrameBuffer
    return FrameBuffer()


class TestFrameBuffer:
    def test_read_before_write_returns_none(self, buf):
        assert buf.read() is None

    def test_write_then_read_returns_frame(self, buf):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        buf.write(frame)
        result = buf.read()
        assert result is not None
        np.testing.assert_array_equal(result, frame)

    def test_read_returns_copy_not_reference(self, buf):
        frame = np.zeros((10, 10, 3), dtype=np.uint8)
        buf.write(frame)
        result = buf.read()
        result[:] = 255
        second_read = buf.read()
        assert second_read[0, 0, 0] == 0   # internal copy not mutated

    def test_write_overwrites_previous_frame(self, buf):
        buf.write(np.zeros((5, 5, 3), dtype=np.uint8))
        new_frame = np.full((5, 5, 3), 128, dtype=np.uint8)
        buf.write(new_frame)
        result = buf.read()
        assert result[0, 0, 0] == 128

    def test_clear_makes_read_return_none(self, buf):
        buf.write(np.zeros((5, 5, 3), dtype=np.uint8))
        buf.clear()
        assert buf.read() is None

    def test_age_huge_before_write(self, buf):
        # Кадров ещё не было → возраст «бесконечный».
        assert buf.age() > 1e6

    def test_age_small_after_write(self, buf):
        buf.write(np.zeros((5, 5, 3), dtype=np.uint8))
        assert buf.age() < 1.0

    def test_clear_resets_age(self, buf):
        buf.write(np.zeros((5, 5, 3), dtype=np.uint8))
        buf.clear()
        assert buf.age() > 1e6

    def test_wait_is_unblocked_by_write(self, buf):
        frame = np.zeros((5, 5, 3), dtype=np.uint8)
        result_holder = []

        def writer():
            import time
            time.sleep(0.05)
            buf.write(frame)

        t = threading.Thread(target=writer)
        t.start()
        buf.wait(timeout=1.0)
        result_holder.append(buf.read())
        t.join()

        assert result_holder[0] is not None

    def test_wait_timeout_when_no_write(self, buf):
        import time
        start = time.monotonic()
        buf.wait(timeout=0.1)
        elapsed = time.monotonic() - start
        assert elapsed < 0.5   # returns reasonably quickly

    def test_concurrent_write_read_no_errors(self, buf):
        errors = []
        frame = np.zeros((10, 10, 3), dtype=np.uint8)

        def writer():
            for _ in range(20):
                try:
                    buf.write(frame)
                except Exception as e:
                    errors.append(e)

        def reader():
            for _ in range(20):
                try:
                    buf.read()
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(3)]
        threads += [threading.Thread(target=reader) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
