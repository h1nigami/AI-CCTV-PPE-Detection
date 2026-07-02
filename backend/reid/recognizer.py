import os
import time
import threading
import numpy as np
from pathlib import Path
from typing import Optional, List, Tuple
from backend.reid.gallery import FaceGallery

try:
    import insightface
    INSIGHTFACE_AVAILABLE = True
except ImportError:
    INSIGHTFACE_AVAILABLE = False


def _get_insightface_root() -> str:
    env_root = os.environ.get("INSIGHTFACE_ROOT")
    if env_root:
        return env_root
    return str(Path.home() / ".insightface")


class FaceRecognizer:
    def __init__(self, model_name: str = "buffalo_l", det_size: Tuple[int, int] = (640, 640)):
        if not INSIGHTFACE_AVAILABLE:
            raise RuntimeError("insightface не установлен (pip install insightface)")
        root = _get_insightface_root()
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        # Один экземпляр FaceRecognizer делят ВСЕ FaceRecognitionWorker (по одному
        # на камеру), поэтому self.app.get() может вызываться из нескольких потоков
        # одновременно. Сериализуем доступ к сессии — дешёво при одной камере (нет
        # конкуренции) и безопасно при нескольких.
        self._infer_lock = threading.Lock()

        model_dir = Path(root) / "models" / model_name

        def _have_model() -> bool:
            return model_dir.exists() and any(model_dir.iterdir())

        # Офлайн-старт: если модели нет локально И нет сети — не виснем на
        # download-ретраях insightface (DNS/connect-таймауты × 3), а сразу
        # деградируем (main.py поймает и отключит Re-ID). Когда модель на месте,
        # is_online() не вызывается — офлайн-загрузка с диска работает как обычно.
        if not _have_model():
            from backend.netutil import is_online
            if not is_online():
                raise RuntimeError(
                    f"InsightFace {model_name} отсутствует локально ({model_dir}), "
                    f"а сети нет — Re-ID отключён. Заранее выполните "
                    f"download_models.py при наличии интернета или задайте "
                    f"INSIGHTFACE_ROOT с готовой моделью."
                )

        last_exc = None
        for attempt in range(3):
            try:
                self.app = insightface.app.FaceAnalysis(
                    name=model_name, providers=providers, root=root
                )
                self.app.prepare(ctx_id=0, det_size=det_size)
                print(f"[ReID] InsightFace {model_name} loaded (root={root})")
                return
            except Exception as e:
                last_exc = e
                err_msg = str(e) if str(e) else repr(e)
                print(f"[ReID] Попытка {attempt + 1}/3 не удалась: {err_msg}")
                if attempt < 2:
                    # Если директория модели пуста — удаляем, чтобы insightface попробовал скачать заново
                    if model_dir.exists() and not any(model_dir.iterdir()):
                        import shutil
                        shutil.rmtree(model_dir)
                        print(f"[ReID] Пустая директория {model_dir} удалена, будет повторная загрузка")
                    # Сетевая пауза перед ретраем имеет смысл только онлайн —
                    # офлайн скачивание не поможет, не тратим время на сон.
                    from backend.netutil import is_online
                    if not is_online():
                        print("[ReID] Сети нет — повторные попытки скачивания пропущены")
                        break
                    wait = 2 ** attempt * 5
                    print(f"[ReID] Повтор через {wait}с...")
                    time.sleep(wait)

        if "SSLError" in str(last_exc) or "ssl" in str(last_exc).lower():
            print(
                f"[ReID] SSL ошибка при загрузке buffalo_l. "
                f"Скачайте модель вручную:\n"
                f"  mkdir -p {root}/models/buffalo_l\n"
                f"  cd {root}/models/buffalo_l\n"
                f"  wget https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip\n"
                f"  unzip buffalo_l.zip\n"
                f"Или установите INSIGHTFACE_ROOT на директорию с предзагруженной моделью."
            )
        raise RuntimeError(
            f"Не удалось загрузить InsightFace {model_name} после 3 попыток: {last_exc}"
        )

    def detect_faces(self, frame: np.ndarray) -> List[Tuple[np.ndarray, np.ndarray, float]]:
        with self._infer_lock:
            faces = self.app.get(frame)
        result = []
        h, w = frame.shape[:2]
        for face in faces:
            emb = face.embedding.astype(np.float32)
            emb = emb / (np.linalg.norm(emb) + 1e-8)
            bbox = face.bbox.astype(np.float32)
            det_score = getattr(face, "det_score", 0.5)
            fx1, fy1, fx2, fy2 = bbox
            face_size = min((fx2 - fx1) / w, (fy2 - fy1) / h)
            size_score = min(1.0, face_size / 0.10)
            quality = det_score * 0.7 + size_score * 0.3
            quality = min(1.0, max(0.35, quality))
            result.append((bbox, emb, quality))
        return result


class FaceRecognitionWorker:
    def __init__(self, raw_buffer, face_recognizer: FaceRecognizer, frame_skip: int = 3):
        self._buf = raw_buffer
        self._rec = face_recognizer
        self._frame_skip = frame_skip
        self._latest_faces: List[Tuple[np.ndarray, np.ndarray, float]] = []
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def get_faces(self) -> List[Tuple[np.ndarray, np.ndarray, float]]:
        with self._lock:
            return list(self._latest_faces)

    def _run(self):
        frame_idx = 0
        while self._running:
            frame = self._buf.read()
            if frame is None:
                time.sleep(0.01)
                continue
            if frame_idx % self._frame_skip == 0:
                try:
                    self._latest_faces = self._rec.detect_faces(frame)
                except Exception as e:
                    print(f"[FaceRecognitionWorker] Ошибка: {e}")
            frame_idx += 1


def match_faces_to_persons(
    person_boxes: List[np.ndarray],
    face_data: List[Tuple[np.ndarray, np.ndarray, float]]
) -> List[Tuple[Optional[np.ndarray], float]]:
    if not face_data or not person_boxes:
        return [(None, 0.0)] * len(person_boxes) if person_boxes else []
    results = []
    for pbox in person_boxes:
        px1, py1, px2, py2 = map(int, pbox)
        pcx = (px1 + px2) / 2.0
        pcy = (py1 + py2) / 2.0
        best_emb = None
        best_quality = 0.0
        best_overlap = 0.0
        best_center_dist = float('inf')
        for face_bbox, emb, quality in face_data:
            fx1, fy1, fx2, fy2 = map(int, face_bbox)
            ix1, iy1 = max(px1, fx1), max(py1, fy1)
            ix2, iy2 = min(px2, fx2), min(py2, fy2)
            face_area = (fx2 - fx1) * (fy2 - fy1)
            if face_area > 0:
                overlap = 0.0
                if ix2 > ix1 and iy2 > iy1:
                    inter = (ix2 - ix1) * (iy2 - iy1)
                    overlap = inter / face_area
                # Лицо ВНЕ bbox человека не рассматривается: иначе человеку без
                # видимого лица (спиной) доставалось бы ближайшее ЧУЖОЕ лицо из
                # кадра — а с ним чужая личность и её активный пропуск.
                if overlap <= 0.0:
                    continue
                fcx = (fx1 + fx2) / 2.0
                fcy = (fy1 + fy2) / 2.0
                center_dist = ((fcx - pcx) ** 2 + (fcy - pcy) ** 2) ** 0.5
                if overlap > best_overlap or (overlap == best_overlap and center_dist < best_center_dist):
                    best_overlap = overlap
                    best_center_dist = center_dist
                    best_emb = emb
                    best_quality = quality
        results.append((best_emb, best_quality))
    return results
