"""
Тесты BatchDetectionWorker — централизованного батч-инференса.

Модель мокается: тесты проверяют логику слотов, маршрутизации результатов,
управления жизненным циклом и граничные случаи — без реального YOLO/GPU.
"""

import threading
import time
from unittest.mock import MagicMock, patch, call
import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------

def _make_model(names=None):
    """Минимальный мок YOLO-модели."""
    model = MagicMock()
    model.names = names or {5: "Человек", 0: "Каска", 1: "Маска",
                            7: "Защитный жилет", 6: "Конус безопасности"}
    return model


def _make_result(boxes=None, classes=None, confs=None, track_ids=None):
    """Мок одного ultralytics Results объекта."""
    r = MagicMock()
    boxes_arr = boxes if boxes is not None else np.empty((0, 4), dtype=np.float32)
    cls_arr = classes if classes is not None else np.empty((0,), dtype=np.int32)
    confs_arr = confs if confs is not None else np.ones(len(cls_arr), dtype=np.float32) * 0.9

    r.boxes.xyxy.cpu.return_value.numpy.return_value = boxes_arr
    r.boxes.cls.cpu.return_value.numpy.return_value = cls_arr
    r.boxes.conf.cpu.return_value.numpy.return_value = confs_arr
    if track_ids is not None:
        r.boxes.id.cpu.return_value.numpy.return_value = np.array(track_ids, dtype=np.int32)
    else:
        r.boxes.id = None
    return r


def _empty_result():
    return _make_result()


# ---------------------------------------------------------------------------
# Жизненный цикл
# ---------------------------------------------------------------------------

class TestLifecycle:
    def test_start_stop(self):
        from backend.detection.batch_worker import BatchDetectionWorker
        worker = BatchDetectionWorker(_make_model(), batch_timeout=0.01)
        worker.start()
        assert worker._thread is not None
        assert worker._thread.is_alive()
        thread_ref = worker._thread  # сохраняем до stop(), который обнуляет _thread
        worker.stop()
        assert worker._thread is None
        assert not thread_ref.is_alive()

    def test_double_stop_safe(self):
        from backend.detection.batch_worker import BatchDetectionWorker
        worker = BatchDetectionWorker(_make_model(), batch_timeout=0.01)
        worker.start()
        worker.stop()
        worker.stop()  # повторный stop не должен падать

    def test_stop_before_start_safe(self):
        from backend.detection.batch_worker import BatchDetectionWorker
        worker = BatchDetectionWorker(_make_model(), batch_timeout=0.01)
        worker.stop()  # не должен падать


# ---------------------------------------------------------------------------
# Регистрация камер / слоты
# ---------------------------------------------------------------------------

class TestCameraRegistration:
    def test_register_assigns_slot(self):
        from backend.detection.batch_worker import BatchDetectionWorker
        worker = BatchDetectionWorker(_make_model(), batch_timeout=0.01)
        worker.register_camera("cam1")
        assert "cam1" in worker._cam_to_slot
        assert worker._cam_to_slot["cam1"] == 0

    def test_two_cameras_get_different_slots(self):
        from backend.detection.batch_worker import BatchDetectionWorker
        worker = BatchDetectionWorker(_make_model(), batch_timeout=0.01)
        worker.register_camera("cam1")
        worker.register_camera("cam2")
        assert worker._cam_to_slot["cam1"] != worker._cam_to_slot["cam2"]

    def test_register_same_camera_twice_is_idempotent(self):
        from backend.detection.batch_worker import BatchDetectionWorker
        worker = BatchDetectionWorker(_make_model(), batch_timeout=0.01)
        worker.register_camera("cam1")
        slot_first = worker._cam_to_slot["cam1"]
        worker.register_camera("cam1")  # повторно
        assert worker._cam_to_slot["cam1"] == slot_first

    def test_unregister_frees_slot(self):
        from backend.detection.batch_worker import BatchDetectionWorker
        worker = BatchDetectionWorker(_make_model(), batch_timeout=0.01)
        worker.register_camera("cam1")
        worker.register_camera("cam2")
        slot_cam2 = worker._cam_to_slot["cam2"]
        worker.unregister_camera("cam1")
        assert "cam1" not in worker._cam_to_slot
        # слот cam1 (0) освободился — новая камера должна его получить
        worker.register_camera("cam3")
        assert worker._cam_to_slot["cam3"] == 0
        # cam2 сохранила свой слот
        assert worker._cam_to_slot["cam2"] == slot_cam2

    def test_unregister_nonexistent_is_safe(self):
        from backend.detection.batch_worker import BatchDetectionWorker
        worker = BatchDetectionWorker(_make_model(), batch_timeout=0.01)
        worker.unregister_camera("nonexistent")  # не должен падать

    def test_slot_limit_raises(self):
        from backend.detection.batch_worker import BatchDetectionWorker
        worker = BatchDetectionWorker(_make_model(), max_slots=2, batch_timeout=0.01)
        worker.register_camera("cam1")
        worker.register_camera("cam2")
        with pytest.raises(RuntimeError, match="лимит слотов"):
            worker.register_camera("cam3")


# ---------------------------------------------------------------------------
# submit() без запущенного воркера
# ---------------------------------------------------------------------------

class TestSubmitWithoutWorker:
    def test_submit_unregistered_returns_none(self):
        from backend.detection.batch_worker import BatchDetectionWorker
        worker = BatchDetectionWorker(_make_model(), batch_timeout=0.01)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = worker.submit("cam_unknown", frame, timeout=0.05)
        assert result is None

    def test_unregister_unblocks_pending_submit(self):
        """Если камера удаляется пока submit() ждёт — он должен вернуть None, не зависнуть."""
        from backend.detection.batch_worker import BatchDetectionWorker
        model = _make_model()
        # Воркер не стартует — submit будет ждать timeout
        worker = BatchDetectionWorker(model, batch_timeout=0.005)
        worker.register_camera("cam1")

        results = []

        def _submit():
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            results.append(worker.submit("cam1", frame, timeout=2.0))

        t = threading.Thread(target=_submit, daemon=True)
        t.start()
        time.sleep(0.05)
        worker.unregister_camera("cam1")  # должен разбудить submit
        t.join(timeout=1.0)
        assert not t.is_alive(), "submit завис после unregister"
        assert results[0] is None


# ---------------------------------------------------------------------------
# Полный цикл: start → submit → результат → stop
# ---------------------------------------------------------------------------

class TestSubmitReceivesResult:
    def test_single_camera_gets_detection(self):
        """Один кадр → воркер запускает model.track → результат доставляется."""
        from backend.detection.batch_worker import BatchDetectionWorker

        model = _make_model()
        # Модель возвращает один пустой результат (нет объектов)
        model.track.return_value = [_empty_result()]

        worker = BatchDetectionWorker(model, batch_timeout=0.01)
        worker.start()
        worker.register_camera("cam1")

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        det = worker.submit("cam1", frame, timeout=2.0)

        worker.stop()

        assert det is not None
        assert "persons" in det
        assert "helmets" in det
        assert det["persons"] == []

    def test_two_cameras_both_get_results(self):
        from backend.detection.batch_worker import BatchDetectionWorker

        model = _make_model()
        model.track.return_value = [_empty_result(), _empty_result()]

        worker = BatchDetectionWorker(model, batch_timeout=0.02)
        worker.start()
        worker.register_camera("cam1")
        worker.register_camera("cam2")

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        results = {}

        def _submit(cam_id):
            results[cam_id] = worker.submit(cam_id, frame, timeout=2.0)

        t1 = threading.Thread(target=_submit, args=("cam1",), daemon=True)
        t2 = threading.Thread(target=_submit, args=("cam2",), daemon=True)
        t1.start(); t2.start()
        t1.join(timeout=3.0); t2.join(timeout=3.0)

        worker.stop()

        assert results.get("cam1") is not None
        assert results.get("cam2") is not None

    def test_detection_with_person_parsed_correctly(self):
        from backend.detection.batch_worker import BatchDetectionWorker

        model = _make_model()
        boxes = np.array([[10, 20, 100, 200]], dtype=np.float32)
        classes = np.array([5], dtype=np.int32)   # 5 = Человек
        track_ids = np.array([42], dtype=np.int32)
        model.track.return_value = [_make_result(boxes, classes, track_ids=track_ids)]

        worker = BatchDetectionWorker(model, batch_timeout=0.01)
        worker.start()
        worker.register_camera("cam1")

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        det = worker.submit("cam1", frame, timeout=2.0)
        worker.stop()

        assert det is not None
        assert len(det["persons"]) == 1
        assert det["person_track_ids"] == [42]


# ---------------------------------------------------------------------------
# Обработка ошибок инференса
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_model_exception_returns_none_not_hang(self):
        from backend.detection.batch_worker import BatchDetectionWorker

        model = _make_model()
        model.track.side_effect = RuntimeError("GPU OOM")

        worker = BatchDetectionWorker(model, batch_timeout=0.01)
        worker.start()
        worker.register_camera("cam1")

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        det = worker.submit("cam1", frame, timeout=2.0)
        worker.stop()

        # Ошибка должна быть поглощена, submit вернуть None, не зависнуть
        assert det is None

    def test_stop_unblocks_waiting_submit(self):
        """stop() должен разбудить submit(), заблокированный в ожидании результата.

        Сценарий: воркер запущен, submit отправил кадр и ждёт result_event.
        Вызываем stop() — submit должен вернуться немедленно, не висеть до таймаута.
        """
        from backend.detection.batch_worker import BatchDetectionWorker

        model = _make_model()
        # Модель не возвращает результаты — submit будет ждать event вечно
        # (батч_timeout=0.005, но мы остановимся до того как воркер доберётся до track)
        hold = threading.Event()

        def _blocking_track(*a, **kw):
            hold.wait(timeout=5)  # ждём сигнала из теста
            return [_empty_result()]

        model.track.side_effect = _blocking_track

        worker = BatchDetectionWorker(model, batch_timeout=0.005)
        worker.start()
        worker.register_camera("cam1")

        results = []

        def _submit():
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            results.append(worker.submit("cam1", frame, timeout=5.0))

        t = threading.Thread(target=_submit, daemon=True)
        t.start()
        time.sleep(0.05)  # дать submit() успеть заблокироваться
        # stop() должен разбудить submit() через result_events.set()
        worker.stop()
        hold.set()  # разблокируем _blocking_track чтобы join воркера прошёл
        t.join(timeout=1.0)
        assert not t.is_alive(), "submit завис после stop()"


# ---------------------------------------------------------------------------
# parse_detection_results — проверяем рефакторинг engine.py
# ---------------------------------------------------------------------------

class TestParseDetectionResults:
    def test_empty_result(self):
        from backend.detection.engine import parse_detection_results
        model = _make_model()
        result = _empty_result()
        det = parse_detection_results(result, model)
        assert det["persons"] == []
        assert det["helmets"] == []

    def test_person_with_helmet(self):
        from backend.detection.engine import parse_detection_results
        model = _make_model()
        boxes = np.array([[0, 0, 100, 200], [10, 10, 50, 60]], dtype=np.float32)
        classes = np.array([5, 0], dtype=np.int32)  # Человек, Каска
        result = _make_result(boxes, classes)
        det = parse_detection_results(result, model)
        assert len(det["persons"]) == 1
        assert len(det["helmets"]) == 1

    def test_run_detection_uses_parse_internally(self):
        """run_detection должен делегировать парсинг в parse_detection_results."""
        from backend.detection import engine
        model = _make_model()
        model.track.return_value = [_empty_result()]
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        with patch.object(engine, 'parse_detection_results', wraps=engine.parse_detection_results) as mock_parse:
            engine.run_detection(frame, model)
            assert mock_parse.called
