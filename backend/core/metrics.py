"""Реестр метрик системы (наблюдаемость / observability).

Лёгкий потокобезопасный сборщик метрик в памяти: FPS и латентность детекции
по камерам, счётчики кадров (обработано / пропущено по отсутствию движения),
счётчики событий по типам, аптайм. Читается эндпоинтами `/health`, `/metrics`
(Prometheus text format) и `/api/stats` (JSON) — см. `backend/api/monitoring.py`.

Намеренно без внешних зависимостей: Prometheus-формат генерируется вручную,
системные метрики (CPU/RAM/диск) берутся из psutil (уже в requirements).
"""
from __future__ import annotations
import time
import threading
from collections import defaultdict, deque
from typing import Dict, Deque


class MetricsRegistry:
    """Потокобезопасный синглтон-реестр метрик процесса детекции."""

    # Сколько последних замеров латентности держим на камеру для усреднения.
    _LATENCY_WINDOW = 30
    # Окно (сек) для расчёта мгновенного FPS по меткам времени кадров.
    _FPS_WINDOW = 5.0

    def __init__(self):
        self._lock = threading.Lock()
        self._start_time = time.time()
        # Метки времени обработанных кадров на камеру (для FPS).
        self._frame_ts: Dict[str, Deque[float]] = defaultdict(
            lambda: deque(maxlen=200))
        # Последние замеры латентности (мс) на камеру.
        self._latency_ms: Dict[str, Deque[float]] = defaultdict(
            lambda: deque(maxlen=self._LATENCY_WINDOW))
        self._frames_processed: Dict[str, int] = defaultdict(int)
        self._frames_skipped: Dict[str, int] = defaultdict(int)  # пропущено по motion
        self._events: Dict[str, int] = defaultdict(int)          # по category/label
        self._last_heartbeat: float = 0.0

    # ── Запись метрик ───────────────────────────────────────────
    def record_frame(self, cam_id: str, latency_ms: float):
        """Зафиксировать обработанный кадр и его латентность (мс)."""
        now = time.time()
        with self._lock:
            self._frame_ts[cam_id].append(now)
            self._latency_ms[cam_id].append(float(latency_ms))
            self._frames_processed[cam_id] += 1

    def record_skipped(self, cam_id: str):
        """Зафиксировать кадр, пропущенный детекцией (нет движения)."""
        with self._lock:
            self._frames_skipped[cam_id] += 1

    def record_event(self, label: str):
        """Инкремент счётчика событий по метке (например, 'нарушение')."""
        with self._lock:
            self._events[label] += 1

    def heartbeat(self):
        with self._lock:
            self._last_heartbeat = time.time()

    # ── Чтение метрик ───────────────────────────────────────────
    def fps(self, cam_id: str) -> float:
        now = time.time()
        with self._lock:
            ts = [t for t in self._frame_ts.get(cam_id, ()) if now - t <= self._FPS_WINDOW]
        if len(ts) < 2:
            return 0.0
        span = ts[-1] - ts[0]
        return round((len(ts) - 1) / span, 2) if span > 0 else 0.0

    def latency_ms(self, cam_id: str) -> float:
        with self._lock:
            vals = list(self._latency_ms.get(cam_id, ()))
        return round(sum(vals) / len(vals), 1) if vals else 0.0

    def uptime_seconds(self) -> float:
        return round(time.time() - self._start_time, 1)

    def snapshot(self) -> dict:
        """Полный срез метрик для JSON-эндпоинта."""
        with self._lock:
            cams = set(self._frame_ts) | set(self._frames_processed) | set(self._frames_skipped)
            events = dict(self._events)
            processed = dict(self._frames_processed)
            skipped = dict(self._frames_skipped)
            last_hb = self._last_heartbeat
        per_camera = {}
        for cam in cams:
            per_camera[cam] = {
                "fps": self.fps(cam),
                "latency_ms": self.latency_ms(cam),
                "frames_processed": processed.get(cam, 0),
                "frames_skipped": skipped.get(cam, 0),
            }
        return {
            "uptime_seconds": self.uptime_seconds(),
            "last_heartbeat": last_hb,
            "cameras": per_camera,
            "events": events,
            "system": _system_metrics(),
        }

    def reset(self):
        """Сброс — используется в тестах."""
        with self._lock:
            self._start_time = time.time()
            self._frame_ts.clear()
            self._latency_ms.clear()
            self._frames_processed.clear()
            self._frames_skipped.clear()
            self._events.clear()
            self._last_heartbeat = 0.0


def _system_metrics() -> dict:
    """CPU/RAM/диск через psutil; при сбое — пустой словарь."""
    try:
        import psutil
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "memory_percent": mem.percent,
            "memory_used_mb": round(mem.used / (1024 * 1024), 1),
            "disk_percent": disk.percent,
        }
    except Exception:
        return {}


_registry: MetricsRegistry | None = None
_registry_lock = threading.Lock()


def get_metrics() -> MetricsRegistry:
    """Глобальный синглтон реестра метрик."""
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = MetricsRegistry()
    return _registry


def render_prometheus(reg: MetricsRegistry | None = None) -> str:
    """Сформировать метрики в текстовом формате Prometheus."""
    reg = reg or get_metrics()
    snap = reg.snapshot()
    lines: list[str] = []

    def metric(name: str, help_text: str, mtype: str):
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {mtype}")

    metric("frigate_uptime_seconds", "Аптайм процесса в секундах", "gauge")
    lines.append(f"frigate_uptime_seconds {snap['uptime_seconds']}")

    metric("frigate_detection_fps", "Мгновенный FPS детекции по камере", "gauge")
    for cam, data in snap["cameras"].items():
        lines.append(f'frigate_detection_fps{{camera="{cam}"}} {data["fps"]}')

    metric("frigate_detection_latency_ms", "Средняя латентность детекции (мс)", "gauge")
    for cam, data in snap["cameras"].items():
        lines.append(f'frigate_detection_latency_ms{{camera="{cam}"}} {data["latency_ms"]}')

    metric("frigate_frames_processed_total", "Обработано кадров", "counter")
    for cam, data in snap["cameras"].items():
        lines.append(f'frigate_frames_processed_total{{camera="{cam}"}} {data["frames_processed"]}')

    metric("frigate_frames_skipped_total", "Пропущено кадров (нет движения)", "counter")
    for cam, data in snap["cameras"].items():
        lines.append(f'frigate_frames_skipped_total{{camera="{cam}"}} {data["frames_skipped"]}')

    metric("frigate_events_total", "Счётчик событий по типу", "counter")
    for label, count in snap["events"].items():
        lines.append(f'frigate_events_total{{type="{label}"}} {count}')

    sysm = snap.get("system", {})
    if sysm:
        metric("frigate_cpu_percent", "Загрузка CPU (%)", "gauge")
        lines.append(f"frigate_cpu_percent {sysm.get('cpu_percent', 0)}")
        metric("frigate_memory_percent", "Использование RAM (%)", "gauge")
        lines.append(f"frigate_memory_percent {sysm.get('memory_percent', 0)}")
        metric("frigate_disk_usage_percent", "Использование диска (%)", "gauge")
        lines.append(f"frigate_disk_usage_percent {sysm.get('disk_percent', 0)}")

    return "\n".join(lines) + "\n"
