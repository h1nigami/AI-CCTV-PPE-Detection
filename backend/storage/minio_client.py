import io
import os
from pathlib import Path
from typing import Optional

from backend.config import (
    MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY,
    MINIO_BUCKET_EVENTS, MINIO_PUBLIC_URL, VIOLATION_LOGS_DIR,
)


class EventStorage:
    def __init__(self):
        self._client = None
        self._available = False
        self._bucket = MINIO_BUCKET_EVENTS
        self._local_dir = VIOLATION_LOGS_DIR
        self._local_dir.mkdir(parents=True, exist_ok=True)
        self._init_s3()

    def _init_s3(self):
        try:
            import boto3
            from botocore.config import Config
            self._client = boto3.client(
                "s3",
                endpoint_url=f"http://{MINIO_ENDPOINT}",
                aws_access_key_id=MINIO_ACCESS_KEY,
                aws_secret_access_key=MINIO_SECRET_KEY,
                config=Config(signature_version="s3v4"),
            )
            self._client.head_bucket(Bucket=self._bucket)
            self._available = True
            print(f"[Storage] MinIO подключён: {MINIO_ENDPOINT}/{self._bucket}")
        except Exception as e:
            self._client = None
            self._available = False
            print(f"[Storage] MinIO недоступен ({e}), использую локальное хранилище: {self._local_dir}")

    @property
    def available(self) -> bool:
        return self._available

    def upload_clip(self, event_id: str, cam_id: str, data: bytes) -> str:
        key = f"clips/{cam_id}/{event_id}.mp4"
        if self._available:
            try:
                self._client.put_object(Bucket=self._bucket, Key=key, Body=data)
                return f"/api/events/{event_id}/clip"
            except Exception as e:
                # MinIO упал в процессе сессии — не теряем клип, пишем локально
                print(f"[Storage] Загрузка клипа {event_id} в MinIO не удалась ({e}), пишу локально")
        local_path = self._local_dir / cam_id / f"{event_id}.mp4"
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(data)
        return f"/api/events/{event_id}/clip"

    def upload_snapshot(self, event_id: str, cam_id: str, data: bytes) -> str:
        key = f"snapshots/{cam_id}/{event_id}.jpg"
        if self._available:
            try:
                self._client.put_object(Bucket=self._bucket, Key=key, Body=data)
                return f"/api/events/{event_id}/snapshot"
            except Exception as e:
                print(f"[Storage] Загрузка снимка {event_id} в MinIO не удалась ({e}), пишу локально")
        local_path = self._local_dir / cam_id / f"{event_id}.jpg"
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(data)
        return f"/api/events/{event_id}/snapshot"

    def get_clip_path(self, event_id: str, cam_id: str) -> Optional[Path]:
        local_path = self._local_dir / cam_id / f"{event_id}.mp4"
        return local_path if local_path.exists() else None

    def get_snapshot_path(self, event_id: str, cam_id: str) -> Optional[Path]:
        local_path = self._local_dir / cam_id / f"{event_id}.jpg"
        return local_path if local_path.exists() else None

    def get_clip_data(self, event_id: str, cam_id: str) -> Optional[bytes]:
        key = f"clips/{cam_id}/{event_id}.mp4"
        if self._available:
            try:
                obj = self._client.get_object(Bucket=self._bucket, Key=key)
                return obj["Body"].read()
            except Exception:
                pass  # промах MinIO — пробуем локальную копию (могла осесть при сбое загрузки)
        local_path = self.get_clip_path(event_id, cam_id)
        return local_path.read_bytes() if local_path else None

    def get_snapshot_data(self, event_id: str, cam_id: str) -> Optional[bytes]:
        key = f"snapshots/{cam_id}/{event_id}.jpg"
        if self._available:
            try:
                obj = self._client.get_object(Bucket=self._bucket, Key=key)
                return obj["Body"].read()
            except Exception:
                pass  # промах MinIO — пробуем локальную копию
        local_path = self.get_snapshot_path(event_id, cam_id)
        return local_path.read_bytes() if local_path else None


_storage: Optional[EventStorage] = None


def get_storage() -> EventStorage:
    global _storage
    if _storage is None:
        _storage = EventStorage()
    return _storage
