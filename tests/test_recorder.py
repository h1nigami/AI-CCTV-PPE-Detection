"""Тесты NVR-рекордера: ffmpeg-команда, парсинг времени, retention, индексация."""
import time
import types
from pathlib import Path

import pytest

import backend.recorder as rec_mod
from backend.recorder import (
    build_ffmpeg_segment_cmd, parse_segment_start, camera_recordings_dir,
    plan_deletions, index_segment_file, RecordingManager,
)


# ── Чистые помощники ────────────────────────────────────────
def test_build_ffmpeg_segment_cmd():
    cmd = build_ffmpeg_segment_cmd("rtsp://x/stream", "/media/cam1/recordings", 60)
    assert cmd[0] == "ffmpeg"
    assert "-c" in cmd and cmd[cmd.index("-c") + 1] == "copy"
    assert "-f" in cmd and cmd[cmd.index("-f") + 1] == "segment"
    assert "-segment_time" in cmd and cmd[cmd.index("-segment_time") + 1] == "60"
    assert "-strftime" in cmd
    assert "-i" in cmd and cmd[cmd.index("-i") + 1] == "rtsp://x/stream"
    # клиентский таймаут именно -stimeout (не -timeout)
    assert "-stimeout" in cmd and "-timeout" not in cmd
    assert cmd[-1].endswith("%Y/%m/%d/%H.%M.%S.mp4")


def test_parse_segment_start_roundtrip():
    p = Path("/media/cam1/recordings/2026/06/18/14.30.05.mp4")
    ts = parse_segment_start(p)
    assert ts is not None
    lt = time.localtime(ts)
    assert (lt.tm_year, lt.tm_mon, lt.tm_mday) == (2026, 6, 18)
    assert (lt.tm_hour, lt.tm_min, lt.tm_sec) == (14, 30, 5)


def test_parse_segment_start_bad_path():
    assert parse_segment_start("/tmp/not_a_segment.mp4") is None
    assert parse_segment_start("/a/b/c/zzz.mp4") is None


def test_camera_recordings_dir():
    d = camera_recordings_dir("cam1", "/media")
    assert d == Path("/media/cam1/recordings")


# ── Retention (чистая логика) ───────────────────────────────
def _seg(cam, start, end, has_motion=False, size=1000):
    return types.SimpleNamespace(camera_id=cam, start_time=start, end_time=end,
                                 has_motion=has_motion, size_bytes=size)


def test_plan_deletions_age():
    now = 1_000_000.0
    old = _seg("cam1", now - 10 * 86400, now - 10 * 86400 + 60, has_motion=True)
    fresh = _seg("cam1", now - 60, now, has_motion=True)
    doomed = plan_deletions([old, fresh], now, mode="continuous", retain_days=7)
    assert old in doomed and fresh not in doomed


def test_plan_deletions_motion_prunes_motionless():
    now = 1_000_000.0
    motionful = _seg("cam1", now - 600, now - 540, has_motion=True)
    motionless = _seg("cam1", now - 500, now - 440, has_motion=False)
    doomed = plan_deletions([motionful, motionless], now, mode="motion",
                            retain_days=7, motion_grace_sec=120)
    assert motionless in doomed
    assert motionful not in doomed


def test_plan_deletions_motion_safety_net():
    # Камера без единого motion-сегмента → motionless НЕ удаляем (пайплайн мог быть выкл.).
    now = 1_000_000.0
    a = _seg("camX", now - 600, now - 540, has_motion=False)
    b = _seg("camX", now - 500, now - 440, has_motion=False)
    doomed = plan_deletions([a, b], now, mode="motion", retain_days=7, motion_grace_sec=120)
    assert doomed == []


def test_plan_deletions_grace_keeps_recent_motionless():
    now = 1_000_000.0
    motionful = _seg("cam1", now - 600, now - 540, has_motion=True)
    recent = _seg("cam1", now - 30, now, has_motion=False)  # моложе grace
    doomed = plan_deletions([motionful, recent], now, mode="motion",
                            retain_days=7, motion_grace_sec=120)
    assert recent not in doomed


def test_plan_deletions_disk_pressure():
    now = 1_000_000.0
    segs = [_seg("cam1", now - i * 60, now - i * 60 + 60, has_motion=True, size=1000)
            for i in range(5)]
    # Диск переполнен → удаляем старейшие, пока не разгрузим.
    doomed = plan_deletions(segs, now, mode="continuous", retain_days=7,
                            disk_percent=95.0, max_disk_percent=80.0)
    assert len(doomed) >= 1
    # удаляются старейшие (наименьший start_time)
    assert min(segs, key=lambda s: s.start_time) in doomed


# ── Индексация в БД ─────────────────────────────────────────
@pytest.fixture
def rec_db(monkeypatch, in_memory_engine, tmp_path):
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=in_memory_engine)
    monkeypatch.setattr(rec_mod, "get_session", lambda: Session())
    return Session


def _make_segment(tmp_path, rel="cam1/recordings/2026/06/18/10.00.00.mp4"):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\x00" * 2048)
    return p


def test_index_segment_file_creates_row(rec_db, tmp_path):
    from backend.db.models import Recording
    p = _make_segment(tmp_path)
    rec_id = index_segment_file("cam1", p, has_motion=True)
    assert rec_id is not None
    s = rec_db()
    row = s.query(Recording).filter(Recording.id == rec_id).first()
    assert row.camera_id == "cam1"
    assert row.size_bytes == 2048
    assert row.has_motion is True
    assert row.end_time >= row.start_time
    s.close()


def test_index_segment_file_idempotent(rec_db, tmp_path):
    from backend.db.models import Recording
    p = _make_segment(tmp_path)
    id1 = index_segment_file("cam1", p, has_motion=False)
    id2 = index_segment_file("cam1", p, has_motion=False)
    assert id1 == id2
    s = rec_db()
    assert s.query(Recording).count() == 1
    s.close()


def test_index_segment_file_missing_returns_none(rec_db, tmp_path):
    missing = tmp_path / "cam1/recordings/2026/06/18/11.00.00.mp4"
    assert index_segment_file("cam1", missing, has_motion=False) is None


# ── Менеджер: сигналы движения ──────────────────────────────
def test_manager_motion_in_range():
    mgr = RecordingManager(base_dir="/tmp/nvr_test")
    mgr.note_motion("cam1", 100.0)
    mgr.note_motion("cam1", 200.0)
    assert mgr._motion_in_range("cam1", 50.0, 150.0) is True
    assert mgr._motion_in_range("cam1", 300.0, 400.0) is False
    assert mgr._motion_in_range("camX", 0.0, 1000.0) is False
