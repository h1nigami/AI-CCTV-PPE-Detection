"""Tests for backend/api/reid.py (configure_reid_routes)"""
from __future__ import annotations
import pytest
from flask import Flask


@pytest.fixture
def reid_app(state):
    """Minimal Flask app with only ReID routes registered."""
    from backend.api.reid import configure_reid_routes
    app = Flask(__name__)
    app.config["TESTING"] = True
    configure_reid_routes(app, state)
    return app.test_client()


@pytest.fixture
def reid_app_no_gallery():
    """ReID app with state that has no gallery."""
    from backend.core.state import DetectionState
    from backend.api.reid import configure_reid_routes
    s = DetectionState()   # gallery is None
    app = Flask(__name__)
    app.config["TESTING"] = True
    configure_reid_routes(app, s)
    return app.test_client()


class TestReidListPersons:
    def test_no_gallery_returns_400(self, reid_app_no_gallery):
        resp = reid_app_no_gallery.get("/api/reid/persons")
        assert resp.status_code == 400

    def test_empty_gallery_returns_empty_list(self, reid_app):
        resp = reid_app.get("/api/reid/persons")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "persons" in data
        assert data["persons"] == []

    def test_with_registered_person_returns_list(self, reid_app, state,
                                                  normalized_embedding):
        gid = state.gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        state.gallery.rename(gid, "Алексей")
        resp = reid_app.get("/api/reid/persons")
        data = resp.get_json()
        assert any(p["global_id"] == gid for p in data["persons"])


class TestReidRename:
    def test_no_gallery_returns_400(self, reid_app_no_gallery):
        resp = reid_app_no_gallery.post("/api/reid/persons/1/rename",
                                        json={"name": "NewName"})
        assert resp.status_code == 400

    def test_empty_name_returns_400(self, reid_app):
        resp = reid_app.post("/api/reid/persons/1/rename", json={"name": ""})
        assert resp.status_code == 400

    def test_unknown_id_returns_404(self, reid_app):
        resp = reid_app.post("/api/reid/persons/9999/rename",
                             json={"name": "SomeName"})
        assert resp.status_code == 404

    def test_rename_success(self, reid_app, state, normalized_embedding):
        gid = state.gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        resp = reid_app.post(f"/api/reid/persons/{gid}/rename",
                             json={"name": "Иван"})
        assert resp.status_code == 200
        assert resp.get_json()["name"] == "Иван"


class TestReidDelete:
    def test_no_gallery_returns_400(self, reid_app_no_gallery):
        resp = reid_app_no_gallery.delete("/api/reid/persons/1")
        assert resp.status_code == 400

    def test_unknown_id_returns_404(self, reid_app):
        resp = reid_app.delete("/api/reid/persons/9999")
        assert resp.status_code == 404

    def test_delete_success(self, reid_app, state, normalized_embedding):
        gid = state.gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        resp = reid_app.delete(f"/api/reid/persons/{gid}")
        assert resp.status_code == 200
        assert not state.gallery.has_id(gid)


class TestReidClear:
    def test_no_gallery_returns_400(self, reid_app_no_gallery):
        resp = reid_app_no_gallery.post("/api/reid/clear")
        assert resp.status_code == 400

    def test_clear_empties_gallery(self, reid_app, state, normalized_embedding):
        state.gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        resp = reid_app.post("/api/reid/clear")
        assert resp.status_code == 200
        assert state.gallery.count == 0


class TestReidStats:
    def test_no_gallery_returns_400(self, reid_app_no_gallery):
        resp = reid_app_no_gallery.get("/api/reid/stats")
        assert resp.status_code == 400

    def test_stats_returns_counts(self, reid_app, state, normalized_embedding):
        state.gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        resp = reid_app.get("/api/reid/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "total_persons" in data
        assert data["total_persons"] == 1
