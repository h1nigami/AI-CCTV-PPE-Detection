import pickle
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

    def match_or_register(self, embedding: np.ndarray, cam_id: str) -> int:
        with self._lock:
            best_id = None
            best_sim = self.sim_threshold

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
            self._gallery[new_id] = {
                'embeddings': [embedding],
                'last_seen': time.time(),
                'cameras': {cam_id},
            }
            self._save()
            print(f"[ReID] Новый global_id={new_id} (камера {cam_id}, sim={best_sim:.3f})")
            return new_id

    def get_info(self, global_id: int) -> Optional[Dict]:
        with self._lock:
            data = self._gallery.get(global_id)
            if data is None:
                return None
            return {
                'global_id': global_id,
                'last_seen': data['last_seen'],
                'cameras': list(data['cameras']),
                'embedding_count': len(data['embeddings']),
            }

    def list_all(self) -> List[Dict]:
        with self._lock:
            return [
                {'global_id': gid, 'last_seen': d['last_seen'],
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

    def get_embeddings(self, frame: np.ndarray, person_boxes: List[np.ndarray]) -> List[Optional[np.ndarray]]:
        if not person_boxes:
            return []

        faces = self.app.get(frame)
        if not faces:
            return [None] * len(person_boxes)

        embeddings = []
        for pbox in person_boxes:
            px1, py1, px2, py2 = map(int, pbox)
            best_face = None
            best_overlap = 0

            for face in faces:
                fx1, fy1, fx2, fy2 = map(int, face.bbox)
                ix1, iy1 = max(px1, fx1), max(py1, fy1)
                ix2, iy2 = min(px2, fx2), min(py2, fy2)
                if ix2 > ix1 and iy2 > iy1:
                    inter = (ix2 - ix1) * (iy2 - iy1)
                    face_area = (fx2 - fx1) * (fy2 - fy1)
                    if face_area > 0:
                        overlap = inter / face_area
                        if overlap > best_overlap:
                            best_overlap = overlap
                            best_face = face

            if best_face is not None and best_face.embedding is not None:
                emb = best_face.embedding.astype(np.float32)
                emb = emb / (np.linalg.norm(emb) + 1e-8)
                embeddings.append(emb)
            else:
                embeddings.append(None)

        return embeddings
