"""Тесты эндпоинтов наблюдаемости (/health, /metrics, /api/stats)."""
import pytest
from flask import Flask

from backend.api.monitoring import monitoring_bp
from backend.core.metrics import get_metrics


@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(monitoring_bp)
    app.config["TESTING"] = True
    return app.test_client()


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert "uptime_seconds" in data


def test_metrics_prometheus(client):
    get_metrics().record_frame("camX", 10.0)
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert resp.mimetype == "text/plain"
    assert b"frigate_uptime_seconds" in resp.data


def test_api_stats_json(client):
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "uptime_seconds" in data
    assert "cameras" in data
    assert "events" in data
