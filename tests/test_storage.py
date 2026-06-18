"""Tests for backend/storage/minio_client.py (EventStorage)"""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def local_storage(tmp_path):
    """EventStorage with MinIO unavailable, using tmp_path for local files."""
    mock_client = MagicMock()
    mock_client.head_bucket.side_effect = Exception("MinIO not available")

    with patch("boto3.client", return_value=mock_client):
        from backend.storage.minio_client import EventStorage
        storage = EventStorage()

    # VIOLATION_LOGS_DIR is captured at import time; redirect _local_dir to tmp_path
    storage._local_dir = tmp_path

    yield storage, tmp_path


@pytest.fixture
def minio_storage(tmp_path):
    """EventStorage with mocked MinIO available."""
    mock_client = MagicMock()
    mock_client.head_bucket.return_value = {}   # no exception → available

    with patch("boto3.client", return_value=mock_client):
        from backend.storage.minio_client import EventStorage
        storage = EventStorage()

    # Redirect _local_dir so fallback writes land in tmp_path
    storage._local_dir = tmp_path

    yield storage, mock_client, tmp_path


# ── Local fallback (MinIO unavailable) ───────────────────────────────────────

class TestLocalFallback:
    def test_available_is_false_when_minio_down(self, local_storage):
        storage, _ = local_storage
        assert storage.available is False

    def test_upload_clip_writes_local_file(self, local_storage):
        storage, tmp_path = local_storage
        storage.upload_clip("evt1", "cam01", b"fake-video-data")
        local_file = tmp_path / "cam01" / "evt1.mp4"
        assert local_file.exists()
        assert local_file.read_bytes() == b"fake-video-data"

    def test_upload_snapshot_writes_local_file(self, local_storage):
        storage, tmp_path = local_storage
        storage.upload_snapshot("evt2", "cam01", b"fake-jpeg-data")
        local_file = tmp_path / "cam01" / "evt2.jpg"
        assert local_file.exists()
        assert local_file.read_bytes() == b"fake-jpeg-data"

    def test_get_clip_data_from_local_file(self, local_storage):
        storage, tmp_path = local_storage
        (tmp_path / "cam01").mkdir(parents=True, exist_ok=True)
        (tmp_path / "cam01" / "evt3.mp4").write_bytes(b"clip-bytes")
        data = storage.get_clip_data("evt3", "cam01")
        assert data == b"clip-bytes"

    def test_get_snapshot_data_from_local_file(self, local_storage):
        storage, tmp_path = local_storage
        (tmp_path / "cam01").mkdir(parents=True, exist_ok=True)
        (tmp_path / "cam01" / "evt4.jpg").write_bytes(b"snap-bytes")
        data = storage.get_snapshot_data("evt4", "cam01")
        assert data == b"snap-bytes"

    def test_get_clip_data_returns_none_when_missing(self, local_storage):
        storage, _ = local_storage
        assert storage.get_clip_data("nonexistent", "cam01") is None

    def test_get_snapshot_data_returns_none_when_missing(self, local_storage):
        storage, _ = local_storage
        assert storage.get_snapshot_data("nonexistent", "cam01") is None

    def test_get_clip_path_returns_path_when_exists(self, local_storage):
        storage, tmp_path = local_storage
        (tmp_path / "cam01").mkdir(parents=True, exist_ok=True)
        clip = tmp_path / "cam01" / "evt5.mp4"
        clip.write_bytes(b"x")
        assert storage.get_clip_path("evt5", "cam01") == clip

    def test_get_clip_path_returns_none_when_missing(self, local_storage):
        storage, _ = local_storage
        assert storage.get_clip_path("missing", "cam01") is None


# ── MinIO available path ──────────────────────────────────────────────────────

class TestMinioAvailable:
    def test_available_is_true_when_minio_ok(self, minio_storage):
        storage, _, _ = minio_storage
        assert storage.available is True

    def test_upload_clip_calls_put_object(self, minio_storage):
        storage, client, _ = minio_storage
        storage.upload_clip("evt10", "cam01", b"data")
        assert client.put_object.called

    def test_upload_snapshot_calls_put_object(self, minio_storage):
        storage, client, _ = minio_storage
        storage.upload_snapshot("evt11", "cam01", b"snap")
        assert client.put_object.called

    def test_get_clip_data_reads_from_minio(self, minio_storage):
        storage, client, _ = minio_storage
        client.get_object.return_value = {"Body": MagicMock(read=lambda: b"minio-clip")}
        data = storage.get_clip_data("evt12", "cam01")
        assert data == b"minio-clip"

    def test_upload_clip_falls_back_to_local_on_minio_error(self, minio_storage):
        storage, client, tmp_path = minio_storage
        client.put_object.side_effect = Exception("write failed")
        storage.upload_clip("evt13", "cam01", b"fallback-data")
        local_file = tmp_path / "cam01" / "evt13.mp4"
        assert local_file.exists()

    def test_get_clip_falls_back_to_local_on_minio_error(self, minio_storage):
        storage, client, tmp_path = minio_storage
        client.get_object.side_effect = Exception("read failed")
        (tmp_path / "cam01").mkdir(parents=True, exist_ok=True)
        (tmp_path / "cam01" / "evt14.mp4").write_bytes(b"local-copy")
        data = storage.get_clip_data("evt14", "cam01")
        assert data == b"local-copy"
