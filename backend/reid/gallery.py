import pickle
import threading
import time
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import numpy as np

try:
    import insightface
    INSIGHTFACE_AVAILABLE = True
except ImportError:
    INSIGHTFACE_AVAILABLE = False




class FaceGallery:
    def __init__(self, gallery_path: Path, sim_threshold: float = 0.55,
                 max_embeddings_per_id: int = 5):
        if isinstance(gallery_path, str):
            gallery_path = Path(gallery_path)
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
            return 0.50
        elif quality >= 0.6:
            return 0.55
        elif quality >= 0.4:
            return 0.62
        else:
            return 0.70

    def _assign_name(self) -> str:
        return f"Гость_{self._next_id}"

    def match_or_register(self, embedding: np.ndarray, cam_id: str,
                          quality: float = 0.5) -> int:
        threshold = self._adaptive_threshold(quality)
        with self._lock:
            best_id = None
            best_sim = -1.0
            for gid, data in self._gallery.items():
                mean_emb = np.mean(data['embeddings'], axis=0)
                sim = self._cosine_sim(embedding, mean_emb)
                person_threshold = threshold
                if len(data['embeddings']) >= 2:
                    person_threshold -= 0.08
                if len(data['embeddings']) >= 5:
                    person_threshold -= 0.05
                if sim > person_threshold and sim > best_sim:
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
            q_label = {0.50: 'отл', 0.55: 'хор', 0.62: 'ср', 0.70: 'плох'}.get(threshold, '?')
            print(f"[ReID] Новый: {name} (ID={new_id}, камера {cam_id}, "
                  f"sim={best_sim:.3f}, кач={quality:.2f} [{q_label}])")
            return new_id

    def has_id(self, global_id: int) -> bool:
        with self._lock:
            return global_id in self._gallery

    def merge_entries(self, source_id: int, target_id: int) -> bool:
        with self._lock:
            if source_id not in self._gallery or target_id not in self._gallery:
                return False
            if source_id == target_id:
                return False
            source = self._gallery[source_id]
            target = self._gallery[target_id]
            target['embeddings'].extend(source['embeddings'])
            if len(target['embeddings']) > self.max_embeddings * 2:
                target['embeddings'] = target['embeddings'][-self.max_embeddings:]
            target['cameras'].update(source['cameras'])
            target['last_seen'] = max(target['last_seen'], source['last_seen'])
            del self._gallery[source_id]
            self._save()
            src_name = source.get('name', f"ID{source_id}")
            tgt_name = target.get('name', f"ID{target_id}")
            print(f"[ReID] Слит {source_id} ({src_name}) -> {target_id} ({tgt_name}), "
                  f"эмбеддингов: {len(target['embeddings'])}")
            return True

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
