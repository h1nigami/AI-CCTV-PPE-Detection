"""Тесты реестра метрик и Prometheus-рендера."""
import time

from backend.core.metrics import MetricsRegistry, render_prometheus, get_metrics


def test_record_frame_and_latency():
    reg = MetricsRegistry()
    reg.record_frame("cam1", 50.0)
    reg.record_frame("cam1", 70.0)
    assert reg.latency_ms("cam1") == 60.0
    snap = reg.snapshot()
    assert snap["cameras"]["cam1"]["frames_processed"] == 2


def test_fps_calculation():
    reg = MetricsRegistry()
    # Два кадра с известным интервалом → fps вычислим.
    reg.record_frame("cam1", 10.0)
    time.sleep(0.05)
    reg.record_frame("cam1", 10.0)
    fps = reg.fps("cam1")
    assert fps > 0


def test_skipped_and_events():
    reg = MetricsRegistry()
    reg.record_skipped("cam1")
    reg.record_skipped("cam1")
    reg.record_event("нарушение")
    snap = reg.snapshot()
    assert snap["cameras"]["cam1"]["frames_skipped"] == 2
    assert snap["events"]["нарушение"] == 1


def test_uptime_positive():
    reg = MetricsRegistry()
    assert reg.uptime_seconds() >= 0


def test_reset():
    reg = MetricsRegistry()
    reg.record_frame("cam1", 10.0)
    reg.reset()
    assert reg.snapshot()["cameras"] == {}


def test_prometheus_render_format():
    reg = MetricsRegistry()
    reg.record_frame("cam1", 42.0)
    reg.record_event("норма")
    text = render_prometheus(reg)
    assert "# TYPE frigate_detection_fps gauge" in text
    assert 'frigate_detection_latency_ms{camera="cam1"} 42.0' in text
    assert 'frigate_events_total{type="норма"} 1' in text
    assert "frigate_uptime_seconds" in text


def test_get_metrics_singleton():
    assert get_metrics() is get_metrics()
