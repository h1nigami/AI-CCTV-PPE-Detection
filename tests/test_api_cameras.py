"""Tests for backend/api/cameras.py (configure_camera_routes)"""
from __future__ import annotations
import sys
import pytest
from unittest.mock import MagicMock, patch
from flask import Flask


@pytest.fixture
def cameras_app(monkeypatch):
    """
    Minimal Flask app with camera routes.  backend.main is stubbed via
    sys.modules so that importing it inside route functions never loads YOLO.
    """
    import backend.config as cfg

    # Stub backend.main
    main_mock = MagicMock()
    main_mock.add_camera = MagicMock()
    main_mock.remove_camera = MagicMock(return_value=True)

    def _do_rename(old, new):
        if old in cfg.CAMERAS:
            cfg.CAMERAS[new] = cfg.CAMERAS.pop(old)
            return True
        return False

    main_mock.rename_camera = MagicMock(side_effect=_do_rename)
    main_mock._init_camera_resources = MagicMock()

    # Use a fresh empty cameras dict for this test
    original_cameras = dict(cfg.CAMERAS)
    cfg.CAMERAS.clear()

    # Prevent file writes
    monkeypatch.setattr(cfg, "save_cameras", lambda: None)
    monkeypatch.setattr(cfg, "save_cameras_config", lambda: None)

    with patch.dict(sys.modules, {"backend.main": main_mock}):
        from backend.api.cameras import configure_camera_routes
        from backend.core.state import DetectionState

        state = DetectionState()
        camera_captures = {}

        app = Flask(__name__)
        app.config["TESTING"] = True
        configure_camera_routes(app, state, camera_captures)

        yield app.test_client(), cfg.CAMERAS, main_mock, state, camera_captures

    # Restore cameras
    cfg.CAMERAS.clear()
    cfg.CAMERAS.update(original_cameras)


class TestGetCameras:
    def test_empty_cameras_returns_empty_dict(self, cameras_app):
        client, cameras, _, _, _ = cameras_app
        resp = client.get("/cameras")
        assert resp.status_code == 200
        assert resp.get_json()["cameras"] == {}

    def test_configured_camera_appears_in_response(self, cameras_app):
        client, cameras, _, _, _ = cameras_app
        cameras["main"] = "rtsp://example.com/stream"
        resp = client.get("/cameras")
        data = resp.get_json()
        assert "main" in data["cameras"]
        assert data["cameras"]["main"]["source"] == "rtsp://example.com/stream"


class TestAddCamera:
    def test_missing_name_returns_400(self, cameras_app):
        client, _, _, _, _ = cameras_app
        resp = client.post("/api/cameras", json={"source": 0})
        assert resp.status_code == 400

    def test_missing_source_returns_400(self, cameras_app):
        client, _, _, _, _ = cameras_app
        resp = client.post("/api/cameras", json={"name": "newcam"})
        assert resp.status_code == 400

    def test_duplicate_name_returns_409(self, cameras_app):
        client, cameras, _, _, _ = cameras_app
        cameras["existing"] = 0
        resp = client.post("/api/cameras", json={"name": "existing", "source": 1})
        assert resp.status_code == 409

    def test_add_camera_success_returns_201(self, cameras_app):
        client, _, main_mock, _, _ = cameras_app
        resp = client.post("/api/cameras", json={"name": "newcam", "source": "0"})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["name"] == "newcam"
        assert main_mock.add_camera.called

    def test_integer_source_conversion(self, cameras_app):
        client, _, main_mock, _, _ = cameras_app
        client.post("/api/cameras", json={"name": "intcam", "source": "2"})
        _, call_source = main_mock.add_camera.call_args[0]
        assert isinstance(call_source, int)
        assert call_source == 2


class TestEditCamera:
    def test_unknown_camera_returns_404(self, cameras_app):
        client, _, _, _, _ = cameras_app
        resp = client.put("/api/cameras/unknown", json={"source": 1})
        assert resp.status_code == 404

    def test_edit_camera_updates_source(self, cameras_app):
        client, cameras, _, _, _ = cameras_app
        cameras["cam1"] = 0
        resp = client.put("/api/cameras/cam1", json={"source": "rtsp://new"})
        assert resp.status_code == 200
        assert cameras["cam1"] == "rtsp://new"

    def test_missing_source_returns_400(self, cameras_app):
        client, cameras, _, _, _ = cameras_app
        cameras["cam1"] = 0
        resp = client.put("/api/cameras/cam1", json={})
        assert resp.status_code == 400


class TestDeleteCamera:
    def test_unknown_camera_returns_404(self, cameras_app):
        client, _, _, _, _ = cameras_app
        resp = client.delete("/api/cameras/unknown")
        assert resp.status_code == 404

    def test_delete_success(self, cameras_app):
        client, cameras, main_mock, _, _ = cameras_app
        cameras["delcam"] = 0
        resp = client.delete("/api/cameras/delcam")
        assert resp.status_code == 200
        assert main_mock.remove_camera.called


class TestRenameCamera:
    def test_empty_name_returns_400(self, cameras_app):
        client, cameras, _, _, _ = cameras_app
        cameras["cam1"] = 0
        resp = client.post("/api/cameras/cam1/rename", json={"name": ""})
        assert resp.status_code == 400

    def test_conflicting_name_returns_409(self, cameras_app):
        client, cameras, _, _, _ = cameras_app
        cameras["cam1"] = 0
        cameras["cam2"] = 1
        resp = client.post("/api/cameras/cam1/rename", json={"name": "cam2"})
        assert resp.status_code == 409

    def test_rename_success(self, cameras_app):
        client, cameras, main_mock, _, _ = cameras_app
        cameras["cam1"] = 0
        resp = client.post("/api/cameras/cam1/rename", json={"name": "renamed_cam"})
        assert resp.status_code == 200
        assert main_mock.rename_camera.called


class TestToggleAnalytics:
    def test_unknown_camera_returns_404(self, cameras_app):
        client, _, _, _, _ = cameras_app
        resp = client.put("/api/cameras/unknown/analytics",
                          json={"detect_enabled": True})
        assert resp.status_code == 404

    def test_missing_detect_enabled_returns_400(self, cameras_app):
        client, cameras, _, _, _ = cameras_app
        cameras["cam1"] = 0
        resp = client.put("/api/cameras/cam1/analytics", json={})
        assert resp.status_code == 400

    def test_toggle_analytics_success(self, cameras_app):
        client, cameras, _, _, _ = cameras_app
        cameras["cam1"] = 0
        resp = client.put("/api/cameras/cam1/analytics",
                          json={"detect_enabled": False})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["detect_enabled"] is False
