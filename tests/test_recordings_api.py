"""Тесты API архива NVR (/api/recordings)."""
import uuid

import pytest
from flask import Flask

import backend.api.recordings as rec_api
from backend.api.recordings import recordings_bp


@pytest.fixture
def client(monkeypatch, in_memory_engine):
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=in_memory_engine)
    monkeypatch.setattr(rec_api, "get_session", lambda: Session())
    app = Flask(__name__)
    app.register_blueprint(recordings_bp)
    app.config["TESTING"] = True
    return app.test_client(), Session


def _add(Session, cam="cam1", start=1000.0, end=1060.0, motion=True, path="/x.mp4"):
    from backend.db.models import Recording
    s = Session()
    rid = str(uuid.uuid4())
    s.add(Recording(id=rid, camera_id=cam, path=path, start_time=start,
                    end_time=end, duration=end - start, size_bytes=10, has_motion=motion))
    s.commit()
    s.close()
    return rid


def test_list_recordings(client):
    c, Session = client
    _add(Session, start=1000, end=1060)
    _add(Session, start=1060, end=1120)
    resp = c.get("/api/recordings?cam_id=cam1")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 2
    assert len(data["recordings"]) == 2
    assert data["recordings"][0]["startTime"] <= data["recordings"][1]["startTime"]


def test_list_filters_by_time(client):
    c, Session = client
    _add(Session, start=1000, end=1060)
    _add(Session, start=5000, end=5060)
    resp = c.get("/api/recordings?cam_id=cam1&from=4000&to=6000")
    data = resp.get_json()
    assert data["total"] == 1
    assert data["recordings"][0]["startTime"] == 5000


def test_recording_at(client):
    c, Session = client
    _add(Session, start=1000, end=1060)
    resp = c.get("/api/recordings/at?cam_id=cam1&ts=1030")
    assert resp.status_code == 200
    assert resp.get_json()["recording"]["startTime"] == 1000
    # вне диапазона
    assert c.get("/api/recordings/at?cam_id=cam1&ts=9999").status_code == 404
    # без параметров
    assert c.get("/api/recordings/at").status_code == 400


def test_get_recording_404(client):
    c, _ = client
    assert c.get("/api/recordings/nope").status_code == 404


def test_play_missing_file_404(client, tmp_path):
    c, Session = client
    _add(Session, path="/nonexistent/seg.mp4")
    resp = c.get("/api/recordings?cam_id=cam1")
    rid = resp.get_json()["recordings"][0]["id"]
    assert c.get(f"/api/recordings/{rid}/play").status_code == 404


def test_play_serves_file(client, tmp_path):
    c, Session = client
    seg = tmp_path / "seg.mp4"
    seg.write_bytes(b"\x00" * 512)
    _add(Session, path=str(seg))
    rid = c.get("/api/recordings?cam_id=cam1").get_json()["recordings"][0]["id"]
    resp = c.get(f"/api/recordings/{rid}/play")
    assert resp.status_code == 200
    assert resp.mimetype == "video/mp4"
