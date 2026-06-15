import pickle
import random
import threading
import time
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Set
import numpy as np

try:
    import insightface
    INSIGHTFACE_AVAILABLE = True
except ImportError:
    INSIGHTFACE_AVAILABLE = False


RUSSIAN_NAMES = [
    "Александр", "Михаил", "Иван", "Сергей", "Андрей",
    "Дмитрий", "Алексей", "Владимир", "Евгений", "Николай",
    "Никита", "Роман", "Кирилл", "Павел", "Даниил",
    "Максим", "Егор", "Илья", "Владислав", "Артём",
    "Олег", "Антон", "Глеб", "Тимофей", "Вадим",
    "Елена", "Ольга", "Наталья", "Анна", "Татьяна",
    "Светлана", "Ирина", "Мария", "Виктория", "Дарья",
    "Юлия", "Анастасия", "Екатерина", "Надежда", "Людмила",
    "Алиса", "Василиса", "Ксения", "Полина", "Вероника",
    "Варвара", "Арина", "Злата", "София", "Маргарита",
]


class FaceGallery:
    """
    Галерея известных лиц: {global_person_id: {embeddings, last_seen, cameras}}.
    Эмбеддинги усредняются для матчинга. Сохраняется на диск в pickle.
    """
    def __init__(self, gallery_path: Path, sim_threshold: float = 0.55,
                 max_embeddings_per_id: int = 5):
        self.gallery_path = gallery_path
        self.sim_threshold = sim_threshold
        self.max_embeddings = max_embeddings_per_id
        self._lock = threading.Lock()
        self._gallery: Dict[int, Dict] = {}
        self._next_id = 1
        self._load()

    def _load(self):
        if self.gallery_path.exists():
            try:
                with open(self.gallery_path, 'rb') as f:
                    data = pickle.load(f)
                self._gallery = data.get('gallery', {})
                self._next_id = data.get('next_id', 1)
                print(f"[ReID] Загружено {len(self._gallery)} личностей из {self.gallery_path}")
            except Exception as e:
                print(f"[ReID] Ошибка загрузки галереи: {e}")
                self._gallery = {}
                self._next_id = 1

    def _save(self):
        try:
            self.gallery_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.gallery_path, 'wb') as f:
                pickle.dump({'gallery': self._gallery, 'next_id': self._next_id}, f)
        except Exception as e:
            print(f"[ReID] Ошибка сохранения галереи: {e}")

    def _cosine_sim(self, a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))

    def _adaptive_threshold(self, quality: float) -> float:
        if quality >= 0.8:
            return 0.48
        elif quality >= 0.6:
            return 0.55
        elif quality >= 0.4:
            return 0.62
        else:
            return 0.72

    def _assign_name(self) -> str:
        used = {d.get('name', '') for d in self._gallery.values()}
        available = [n for n in RUSSIAN_NAMES if n not in used]
        if not available:
            return f"Гость_{self._next_id}"
        return random.choice(available)

    def match_or_register(self, embedding: np.ndarray, cam_id: str,
                          quality: float = 0.5) -> int:
        threshold = self._adaptive_threshold(quality)
        with self._lock:
            best_id = None
            best_sim = threshold

            for gid, data in self._gallery.items():
                mean_emb = np.mean(data['embeddings'], axis=0)
                sim = self._cosine_sim(embedding, mean_emb)
                if sim > best_sim:
                    best_sim = sim
                    best_id = gid

            if best_id is not None:
                data = self._gallery[best_id]
                data['embeddings'].append(embedding)
                if len(data['embeddings']) > self.max_embeddings:
                    data['embeddings'].pop(0)
                data['last_seen'] = time.time()
                data['cameras'].add(cam_id)
                return best_id

            new_id = self._next_id
            self._next_id += 1
            name = self._assign_name()
            self._gallery[new_id] = {
                'embeddings': [embedding],
                'last_seen': time.time(),
                'cameras': {cam_id},
                'name': name,
            }
            self._save()
            q_label = {0.48:'отл',0.55:'хор',0.62:'ср',0.72:'плох'}.get(threshold, '?')
            print(f"[ReID] Новый: {name} (ID={new_id}, камера {cam_id}, "
                  f"sim={best_sim:.3f}, кач={quality:.2f} [{q_label}])")
            return new_id

    def rename(self, global_id: int, new_name: str) -> bool:
        with self._lock:
            if global_id not in self._gallery:
                return False
            self._gallery[global_id]['name'] = new_name
            self._save()
            print(f"[ReID] Переименован global_id={global_id} -> {new_name}")
            return True

    def get_name(self, global_id: int) -> str:
        with self._lock:
            data = self._gallery.get(global_id)
            if data:
                return data.get('name', f"ID{global_id}")
            return f"ID{global_id}"

    def get_info(self, global_id: int) -> Optional[Dict]:
        with self._lock:
            data = self._gallery.get(global_id)
            if data is None:
                return None
            return {
                'global_id': global_id,
                'name': data.get('name', f"ID{global_id}"),
                'last_seen': data['last_seen'],
                'cameras': list(data['cameras']),
                'embedding_count': len(data['embeddings']),
            }

    def list_all(self) -> List[Dict]:
        with self._lock:
            return [
                {'global_id': gid, 'name': d.get('name', f"ID{gid}"),
                 'last_seen': d['last_seen'],
                 'cameras': list(d['cameras']),
                 'embedding_count': len(d['embeddings'])}
                for gid, d in self._gallery.items()
            ]

    def delete(self, global_id: int) -> bool:
        with self._lock:
            if global_id in self._gallery:
                del self._gallery[global_id]
                self._save()
                print(f"[ReID] Удалён global_id={global_id}")
                return True
            return False

    def clear(self):
        with self._lock:
            self._gallery.clear()
            self._next_id = 1
            self._save()
            print("[ReID] Галерея очищена")

    def cleanup_old(self, max_age_days: int = 30):
        with self._lock:
            now = time.time()
            to_del = [gid for gid, d in self._gallery.items()
                      if now - d['last_seen'] > max_age_days * 86400]
            for gid in to_del:
                del self._gallery[gid]
            if to_del:
                self._save()
                print(f"[ReID] Удалено {len(to_del)} старых личностей")

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._gallery)


class FaceRecognizer:
    """Обёртка над InsightFace для извлечения эмбеддингов лиц."""
    def __init__(self, model_name: str = 'buffalo_l', det_size: Tuple[int, int] = (640, 640)):
        if not INSIGHTFACE_AVAILABLE:
            raise RuntimeError("insightface не установлен (pip install insightface)")
        providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
        self.app = insightface.app.FaceAnalysis(
            name=model_name, providers=providers,
            root=str(Path.home() / '.insightface')
        )
        self.app.prepare(ctx_id=0, det_size=det_size)
        print(f"[ReID] InsightFace {model_name} loaded (CUDA)")

    def detect_faces(self, frame: np.ndarray) -> List[Tuple[np.ndarray, np.ndarray, float]]:
        """Возвращает список (bbox, embedding, quality) для всех лиц в кадре."""
        faces = self.app.get(frame)
        result = []
        h, w = frame.shape[:2]
        for face in faces:
            emb = face.embedding.astype(np.float32)
            emb = emb / (np.linalg.norm(emb) + 1e-8)
            bbox = face.bbox.astype(np.float32)
            # Quality = детекция (0-1) × размер лица (0-1)
            det_score = getattr(face, 'det_score', 0.5)
            fx1, fy1, fx2, fy2 = bbox
            face_size = min((fx2 - fx1) / w, (fy2 - fy1) / h)
            size_score = min(1.0, face_size / 0.15)  # 15% кадра = отлично
            quality = det_score * 0.6 + size_score * 0.4
            quality = min(1.0, max(0.1, quality))
            result.append((bbox, emb, quality))
        return result


class FaceRecognitionWorker:
    """Асинхронно распознаёт лица в отдельном потоке.

    Читает кадры из raw_buffer (FrameBuffer), прогоняет через InsightFace
    и сохраняет результаты. Основной поток детекции забирает их без блокировки.
    """
    def __init__(self, raw_buffer, face_recognizer: FaceRecognizer,
                 frame_skip: int = 3):
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
        """Последние лица: список (bbox, embedding, quality)."""
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
    """Матчит YOLO person_boxes с face_data (bbox, embedding, quality) по overlap.

    Для каждого person_box выбирает лицо с максимальным overlap'ом.
    Возвращает список (embedding, quality). Quality = 0 если лица нет.
    """
    if not face_data or not person_boxes:
        return [(None, 0.0)] * len(person_boxes) if person_boxes else []

    results = []
    for pbox in person_boxes:
        px1, py1, px2, py2 = map(int, pbox)
        best_emb = None
        best_quality = 0.0
        best_overlap = 0.0

        for face_bbox, emb, quality in face_data:
            fx1, fy1, fx2, fy2 = map(int, face_bbox)
            ix1, iy1 = max(px1, fx1), max(py1, fy1)
            ix2, iy2 = min(px2, fx2), min(py2, fy2)
            if ix2 > ix1 and iy2 > iy1:
                inter = (ix2 - ix1) * (iy2 - iy1)
                face_area = (fx2 - fx1) * (fy2 - fy1)
                if face_area > 0:
                    overlap = inter / face_area
                    if overlap > best_overlap:
                        best_overlap = overlap
                        best_emb = emb
                        best_quality = quality

        results.append((best_emb, best_quality))

    return results
