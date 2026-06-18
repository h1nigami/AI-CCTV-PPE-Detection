"""Тесты API зон (/api/cameras/<id>/zones)."""
import pytest
from flask import Flask

import backend.config as cfg
import backend.zones as zones_mod
from backend.api.cameras import configure_camera_routes

SQUARE = [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]]


class _DummyState:
    live_active = False


@pytest.fixture
def client(monkeypatch):
    # In-memory конфиг зон.
    store: dict = {}
    monkeypatch.setattr(zones_mod, "get_camera_config", lambda cam: store.setdefault(cam, {}))
    monkeypatch.setattr(zones_mod, "set_camera_config",
                        lambda cam, **kw: store.setdefault(cam, {}).update(kw))
    # Камера cam1 существует.
    monkeypatch.setitem(cfg.CAMERAS, "cam1", 0)
    app = Flask(__name__)
    configure_camera_routes(app, _DummyState(), {})
    app.config["TESTING"] = True
    return app.test_client()


def test_get_zones_empty(client):
    r = client.get("/api/cameras/cam1/zones")
    assert r.status_code == 200
    assert r.get_json()["zones"] == []


def test_unknown_camera_404(client):
    assert client.get("/api/cameras/ghost/zones").status_code == 404


def test_add_and_get_zone(client):
    r = client.post("/api/cameras/cam1/zones",
                    json={"type": "danger", "points": SQUARE, "name": "Стройка"})
    assert r.status_code == 201
    zid = r.get_json()["zone"]["id"]
    zones = client.get("/api/cameras/cam1/zones").get_json()["zones"]
    assert len(zones) == 1 and zones[0]["id"] == zid


def test_add_invalid_zone_400(client):
    r = client.post("/api/cameras/cam1/zones",
                    json={"type": "danger", "points": [[0, 0], [1, 1]]})
    assert r.status_code == 400


def test_put_replaces_all(client):
    client.post("/api/cameras/cam1/zones", json={"type": "danger", "points": SQUARE})
    r = client.put("/api/cameras/cam1/zones",
                   json={"zones": [{"type": "mask", "points": SQUARE}]})
    assert r.status_code == 200
    zones = r.get_json()["zones"]
    assert len(zones) == 1 and zones[0]["type"] == "mask"


def test_update_and_delete_zone(client):
    zid = client.post("/api/cameras/cam1/zones",
                      json={"type": "danger", "points": SQUARE}).get_json()["zone"]["id"]
    r = client.put(f"/api/cameras/cam1/zones/{zid}", json={"name": "Новая"})
    assert r.status_code == 200 and r.get_json()["zone"]["name"] == "Новая"
    assert client.put("/api/cameras/cam1/zones/nope", json={"name": "x"}).status_code == 404
    assert client.delete(f"/api/cameras/cam1/zones/{zid}").status_code == 200
    assert client.delete(f"/api/cameras/cam1/zones/{zid}").status_code == 404
