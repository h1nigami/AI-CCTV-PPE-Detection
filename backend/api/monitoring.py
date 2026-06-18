"""Эндпоинты наблюдаемости: /health, /metrics (Prometheus), /api/stats (JSON).

Реализация Фазы 10 плана (мониторинг и observability). Читает реестр метрик
из `backend.core.metrics` (FPS, латентность, счётчики событий) и системные
метрики psutil. `/metrics` отдаёт текстовый формат Prometheus, `/health` —
быстрый healthcheck для оркестраторов/балансировщиков.
"""
from __future__ import annotations
from flask import Blueprint, jsonify, Response

from backend.core.metrics import get_metrics, render_prometheus

monitoring_bp = Blueprint("monitoring", __name__)


@monitoring_bp.route("/health")
def health():
    """Лёгкий healthcheck: 200 пока процесс жив."""
    reg = get_metrics()
    return jsonify({"status": "ok", "uptime_seconds": reg.uptime_seconds()})


@monitoring_bp.route("/metrics")
def metrics():
    """Метрики в текстовом формате Prometheus."""
    return Response(render_prometheus(), mimetype="text/plain; version=0.0.4")


@monitoring_bp.route("/api/stats")
def api_stats():
    """Полный срез метрик в JSON (для дашборда/графиков)."""
    return jsonify(get_metrics().snapshot())
