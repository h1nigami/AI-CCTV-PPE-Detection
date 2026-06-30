"""
Батч-инференс детектора для N камер.

Проблема: при N параллельных потоках детекции каждый вызывает model.track()
отдельно — GPU получает N последовательных однокадровых вызовов вместо одного
батча. На мощных GPU (RTX 4080+, Jetson Orin) это приводит к ~4× недоиспользованию.

Решение: один BatchDetectionWorker собирает кадры со всех камер и делает
единственный model.track(batch) вызов на GPU. Каждая камера получает фиксированный
слот (индекс в батче) → ByteTrack трекер внутри модели поддерживает состояние
корректно (state[0] всегда для камеры на слоте 0, state[1] для слота 1 и т.д.).

Включается автоматически при ≥2 камерах или BATCH_INFERENCE=1.
Откат на старое поведение при BATCH_INFERENCE=0 или одной камере.

Env:
    BATCH_INFERENCE    — 1/0 (принудительно вкл/выкл; авто по умолчанию)
    BATCH_TIMEOUT_MS   — время сбора батча, мс (по умолч. 20)
    BATCH_MAX_CAMERAS  — максимум слотов (по умолч. 16)
"""

from __future__ import annotations

import os
import threading
import time
from typing import Dict, List, Optional, Any

import numpy as np

from backend.detection.engine import parse_detection_results, TRACKER_CFG
from backend.config import CONF_THRESH, PPE_CONF_THRESH

_BATCH_TIMEOUT = float(os.environ.get("BATCH_TIMEOUT_MS", "20")) / 1000.0
_MAX_SLOTS = int(os.environ.get("BATCH_MAX_CAMERAS", "16"))

_BASE_CONF = min(CONF_THRESH, PPE_CONF_THRESH)


class BatchDetectionWorker:
    """
    Централизованный батч-инференс: один model.track(batch) вместо N×model.track(frame).

    Жизненный цикл:
        worker = BatchDetectionWorker(yolo_model)
        worker.start()
        worker.register_camera("cam1")
        detection = worker.submit("cam1", frame)  # блокирует ~batch_timeout
        worker.unregister_camera("cam1")
        worker.stop()
    """

    def __init__(self, model, batch_timeout: float = _BATCH_TIMEOUT, max_slots: int = _MAX_SLOTS):
        self._model = model
        self._batch_timeout = batch_timeout
        self._max_slots = max_slots

        self._lock = threading.Lock()
        # cam_id → slot index (стабильно на всё время жизни камеры)
        self._cam_to_slot: Dict[str, int] = {}
        self._slot_to_cam: Dict[int, str] = {}
        # Последний известный кадр и флаг «новый» для каждого слота
        self._last_frames: List[Optional[np.ndarray]] = [None] * max_slots
        self._is_new: List[bool] = [False] * max_slots
        # Event + результат для каждой камеры
        self._result_events: Dict[str, threading.Event] = {}
        self._results: Dict[str, Optional[Dict[str, Any]]] = {}

        # Сигнал «хотя бы один новый кадр» для пробуждения воркера
        self._any_new = threading.Event()

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Управление жизненным циклом
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="batch-detection", daemon=True
        )
        self._thread.start()
        print(f"[BatchInference] Запущен (timeout={self._batch_timeout*1000:.0f}мс, slots={self._max_slots})")

    def stop(self) -> None:
        self._stop_event.set()
        self._any_new.set()  # разбудить заблокированный _run
        # Разбудить все потоки, ожидающие результата в submit() — иначе они
        # зависнут до своего таймаута после того как воркер уже остановлен.
        with self._lock:
            for ev in self._result_events.values():
                ev.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None
        print("[BatchInference] Остановлен")

    # ------------------------------------------------------------------
    # Регистрация камер
    # ------------------------------------------------------------------

    def register_camera(self, cam_id: str) -> None:
        with self._lock:
            if cam_id in self._cam_to_slot:
                return
            used = set(self._cam_to_slot.values())
            try:
                slot = next(i for i in range(self._max_slots) if i not in used)
            except StopIteration:
                raise RuntimeError(f"[BatchInference] Превышен лимит слотов ({self._max_slots})")
            self._cam_to_slot[cam_id] = slot
            self._slot_to_cam[slot] = cam_id
            self._result_events[cam_id] = threading.Event()
            self._results[cam_id] = None
        print(f"[BatchInference] Камера {cam_id!r} → слот {slot}")

    def unregister_camera(self, cam_id: str) -> None:
        with self._lock:
            slot = self._cam_to_slot.pop(cam_id, None)
            if slot is not None:
                self._slot_to_cam.pop(slot, None)
                self._last_frames[slot] = None
                self._is_new[slot] = False
            ev = self._result_events.pop(cam_id, None)
            self._results.pop(cam_id, None)
        if ev is not None:
            ev.set()  # разблокировать submit, если камера удалена в середине ожидания
        if slot is not None:
            print(f"[BatchInference] Камера {cam_id!r} отключена (слот {slot})")

    # ------------------------------------------------------------------
    # Основной API для потоков детекции
    # ------------------------------------------------------------------

    def submit(self, cam_id: str, frame: np.ndarray, timeout: float = 2.0) -> Optional[Dict[str, Any]]:
        """Сдать кадр, заблокироваться до получения detection-словаря."""
        with self._lock:
            slot = self._cam_to_slot.get(cam_id)
            if slot is None:
                return None
            self._last_frames[slot] = frame
            self._is_new[slot] = True
            ev = self._result_events[cam_id]
            ev.clear()
            self._results[cam_id] = None

        self._any_new.set()
        ev.wait(timeout=timeout)

        with self._lock:
            return self._results.get(cam_id)

    # ------------------------------------------------------------------
    # Внутренний цикл батч-инференса
    # ------------------------------------------------------------------

    def _run(self) -> None:
        while not self._stop_event.is_set():
            # Ждём первого нового кадра
            self._any_new.wait(timeout=0.1)
            if self._stop_event.is_set():
                break
            self._any_new.clear()

            # Даём другим камерам время подать свои кадры
            time.sleep(self._batch_timeout)

            with self._lock:
                cam_to_slot = dict(self._cam_to_slot)
                frames_snap = list(self._last_frames)
                is_new_snap = list(self._is_new)
                # Сбросим флаги до инференса, чтобы submit() следующего кадра
                # не получил «старый» result_event, уже установленный
                for slot in cam_to_slot.values():
                    self._is_new[slot] = False

            # Отбираем слоты с кадрами, сортируем для стабильного порядка
            active: List[tuple[int, str]] = sorted(
                ((slot, cam_id) for cam_id, slot in cam_to_slot.items()
                 if frames_snap[slot] is not None),
                key=lambda x: x[0],
            )
            if not active:
                continue

            batch_frames = [frames_snap[slot] for slot, _ in active]
            # Камеры с новым кадром — именно им нужно доставить result
            new_cam_ids = {cam_id for slot, cam_id in active if is_new_snap[slot]}

            if not new_cam_ids:
                continue  # нечего отдавать — все кадры старые

            # Один GPU-вызов на весь батч
            try:
                batch_results = self._model.track(
                    batch_frames,
                    conf=_BASE_CONF,
                    verbose=False,
                    persist=True,
                    tracker=TRACKER_CFG,
                )
            except Exception as exc:
                print(f"[BatchInference] Ошибка инференса: {exc}")
                self._dispatch_error(new_cam_ids)
                continue

            # Раздаём результаты ожидающим камерам
            with self._lock:
                for i, (slot, cam_id) in enumerate(active):
                    if cam_id not in self._cam_to_slot:
                        continue  # камера удалена пока шёл инференс
                    if cam_id not in new_cam_ids:
                        continue  # у этой камеры не было нового кадра — не будим поток
                    result = batch_results[i] if i < len(batch_results) else None
                    try:
                        detection = parse_detection_results(result, self._model) if result is not None else None
                    except Exception as exc:
                        print(f"[BatchInference] Ошибка парсинга [{cam_id}]: {exc}")
                        detection = None
                    self._results[cam_id] = detection
                    if cam_id in self._result_events:
                        self._result_events[cam_id].set()

    def _dispatch_error(self, cam_ids) -> None:
        with self._lock:
            for cam_id in cam_ids:
                self._results[cam_id] = None
                if cam_id in self._result_events:
                    self._result_events[cam_id].set()
