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
                 max_embeddings_per_id: int = 5, diversity_max_sim: float = 0.92,
                 max_body_embeddings: int = 12, body_diversity_max_sim: float = 0.97):
        if isinstance(gallery_path, str):
            gallery_path = Path(gallery_path)
        self.gallery_path = gallery_path
        self.sim_threshold = sim_threshold
        self.max_embeddings = max_embeddings_per_id
        self.diversity_max_sim = diversity_max_sim
        # Body Re-ID: дескрипторы внешнего вида (одежда) для опознания «со спины».
        self.max_body_embeddings = max_body_embeddings
        self.body_diversity_max_sim = body_diversity_max_sim
        self._lock = threading.Lock()
        self._gallery: Dict[int, Dict] = {}
        self._next_id = 1
        # Грязный флаг: «обучающие» пути (липкое дописывание лиц, дескрипторы
        # тела) не пишут на диск сразу — flush() сбрасывает их по таймеру/при
        # остановке. Методы со своим _save() сбрасывают флаг сами.
        self._dirty = False
        self._load()

    def _load(self):
        if self.gallery_path.exists():
            try:
                with open(self.gallery_path, 'rb') as f:
                    data = pickle.load(f)
                self._gallery = data.get('gallery', {})
                self._next_id = data.get('next_id', 1)
                # Обратная совместимость: у старых записей нет таймстампов
                # эмбеддингов — добиваем их last_seen, чтобы длины совпали.
                for entry in self._gallery.values():
                    self._embedding_ts(entry)
                    self._body_ts(entry)
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
            self._dirty = False
        except Exception as e:
            print(f"[ReID] Ошибка сохранения галереи: {e}")

    def flush(self) -> bool:
        """Сбросить на диск накопленные за сессию изменения (тело/липкие лица),
        только если что-то менялось (грязный флаг). Возвращает True, если
        реально записали. Вызывается по таймеру из _heartbeat_loop и при
        stop_live — чтобы выученное переживало перезапуск без записи на каждый кадр."""
        with self._lock:
            if not self._dirty:
                return False
            self._save()
            return True

    def _cosine_sim(self, a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))

    def _adaptive_threshold(self, quality: float) -> float:
        if quality >= 0.8:
            return 0.45
        elif quality >= 0.6:
            return 0.50
        elif quality >= 0.4:
            return 0.55
        else:
            return 0.60

    def _assign_name(self) -> str:
        return f"Гость_{self._next_id}"

    def _embedding_ts(self, data: Dict) -> List[float]:
        """Список таймстампов (когда добавлен эмбеддинг), параллельный
        data['embeddings']. Поддерживает обратную совместимость: у старых записей
        без таймстампов добивает недостающие значения last_seen/now к НАЧАЛУ
        списка (нетаймстампленные эмбеддинги — самые старые, загруженные с диска)."""
        ts = data.setdefault('embedding_ts', [])
        n = len(data.get('embeddings', []))
        if len(ts) < n:
            fill = data.get('last_seen', time.time())
            ts[:0] = [fill] * (n - len(ts))
        elif len(ts) > n:
            del ts[:len(ts) - n]
        return ts

    def _body_ts(self, data: Dict) -> List[float]:
        """Таймстампы дескрипторов тела, параллельные data['body_embeddings'].
        Обратная совместимость как у _embedding_ts: недостающие добиваются
        last_seen к началу списка (нетаймстампленные — самые старые)."""
        ts = data.setdefault('body_ts', [])
        n = len(data.get('body_embeddings', []))
        if len(ts) < n:
            fill = data.get('last_seen', time.time())
            ts[:0] = [fill] * (n - len(ts))
        elif len(ts) > n:
            del ts[:len(ts) - n]
        return ts

    def threshold_for(self, quality: float) -> float:
        """Публичный доступ к адаптивному порогу (для «липкой» верификации в state)."""
        return self._adaptive_threshold(quality)

    def _append_embedding(self, data: Dict, embedding: np.ndarray, diverse: bool = False):
        """Добавить эмбеддинг, защищая якорный (первый/эталонный) от вытеснения.
        При переполнении выбрасываем самый старый НЕ-якорный (индекс 1), а не индекс 0.
        Если diverse=True — добавляем, только если ракурс заметно отличается от уже
        сохранённых (max косинус < diversity_max_sim); иначе это почти-дубль кадра."""
        if diverse and data['embeddings']:
            if max(self._cosine_sim(embedding, e) for e in data['embeddings']) >= self.diversity_max_sim:
                return
        ts = self._embedding_ts(data)
        data['embeddings'].append(embedding)
        ts.append(time.time())
        if len(data['embeddings']) > self.max_embeddings:
            # Якорь (индекс 0) неприкосновенен; при переполнении вытесняем самый
            # СТАРЫЙ из остальных по времени добавления, а не вслепую индекс 1.
            drop = min(range(1, len(ts)), key=ts.__getitem__)
            data['embeddings'].pop(drop)
            ts.pop(drop)

    def similarity(self, global_id: int, embedding: np.ndarray) -> float:
        """Максимальная косинусная близость эмбеддинга к записи (−1, если записи нет)."""
        with self._lock:
            data = self._gallery.get(global_id)
            if not data:
                return -1.0
            return max(self._cosine_sim(embedding, e) for e in data['embeddings'])

    def add_observation(self, global_id: int, cam_id: str, embedding: np.ndarray,
                        quality: float = 0.5, store: bool = True) -> bool:
        """Обновить запись существующей личности (last_seen/камеры) и, если store,
        добавить эмбеддинг с защитой якоря. Используется «липким» путём в state."""
        with self._lock:
            data = self._gallery.get(global_id)
            if data is None:
                return False
            if store:
                # diverse=True: «липкий» путь накапливает только новые ракурсы
                self._append_embedding(data, embedding, diverse=True)
            data['last_seen'] = time.time()
            data['cameras'].add(cam_id)
            self._dirty = True   # сбросится на диск через flush() (не на каждый кадр)
            return True

    def _body_sims(self, embedding: np.ndarray, bodies) -> List[float]:
        """Косинусы к дескрипторам тела ТОЙ ЖЕ размерности. Разные бэкенды дают
        векторы разной длины (OSNet 512 vs цветовой 256) — смешивать их нельзя,
        иначе np.dot упадёт; несовпадающие игнорируем (старый бэкенд отомрёт по капу)."""
        n = int(embedding.shape[0])
        return [self._cosine_sim(embedding, e) for e in bodies
                if getattr(e, 'shape', (None,))[0] == n]

    def add_body(self, global_id: int, embedding: np.ndarray, diverse: bool = True) -> bool:
        """Добавить дескриптор внешнего вида (тело/одежда) к личности.
        diverse=True — копим только заметно разные ракурсы (max косинус к уже
        сохранённым < body_diversity_max_sim), иначе почти-дубль кадра. Кап —
        max_body_embeddings (выбрасываем самый СТАРЫЙ по времени). На диск пишет
        не сразу: ставит грязный флаг, реальный сброс — flush() по таймеру/при
        остановке (обучение в рамках сессии, без записи на каждый кадр)."""
        if embedding is None:
            return False
        with self._lock:
            data = self._gallery.get(global_id)
            if data is None:
                return False
            bodies = data.setdefault('body_embeddings', [])
            if diverse:
                sims = self._body_sims(embedding, bodies)
                if sims and max(sims) >= self.body_diversity_max_sim:
                    return False
            ts = self._body_ts(data)
            bodies.append(embedding)
            ts.append(time.time())
            if len(bodies) > self.max_body_embeddings:
                drop = min(range(len(ts)), key=ts.__getitem__)
                bodies.pop(drop)
                ts.pop(drop)
            self._dirty = True
            return True

    def match_body(self, embedding: np.ndarray, threshold: float) -> Tuple[Optional[int], float]:
        """Найти личность по дескриптору тела: лучший global_id с max косинусом
        ≥ threshold (или (None, best_sim), если никто не прошёл порог)."""
        if embedding is None:
            return None, -1.0
        with self._lock:
            best_id: Optional[int] = None
            best_sim = -1.0
            for gid, data in self._gallery.items():
                bodies = data.get('body_embeddings')
                if not bodies:
                    continue
                sims = self._body_sims(embedding, bodies)
                if not sims:
                    continue
                sim = max(sims)
                if sim >= threshold and sim > best_sim:
                    best_sim = sim
                    best_id = gid
            return best_id, best_sim

    def body_similarity(self, global_id: int, embedding: np.ndarray) -> float:
        """Максимальная косинусная близость дескриптора тела к личности (−1, если нет)."""
        if embedding is None:
            return -1.0
        with self._lock:
            data = self._gallery.get(global_id)
            bodies = data.get('body_embeddings') if data else None
            if not bodies:
                return -1.0
            sims = self._body_sims(embedding, bodies)
            return max(sims) if sims else -1.0

    def match_or_register(self, embedding: np.ndarray, cam_id: str,
                          quality: float = 0.5, store: bool = True) -> int:
        threshold = self._adaptive_threshold(quality)
        with self._lock:
            best_id = None
            best_sim = -1.0
            for gid, data in self._gallery.items():
                sim = max(self._cosine_sim(embedding, e) for e in data['embeddings'])
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
                if store:
                    self._append_embedding(data, embedding)
                data['last_seen'] = time.time()
                data['cameras'].add(cam_id)
                self._dirty = True   # повторный матч известного лица — flush() позже
                return best_id
            new_id = self._next_id
            self._next_id += 1
            name = self._assign_name()
            self._gallery[new_id] = {
                'embeddings': [embedding],
                'embedding_ts': [time.time()],
                'body_embeddings': [],
                'last_seen': time.time(),
                'cameras': {cam_id},
                'name': name,
            }
            self._save()
            q_label = {0.45: 'отл', 0.50: 'хор', 0.55: 'ср', 0.60: 'плох'}.get(threshold, '?')
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
            t_ts = self._embedding_ts(target)
            t_ts.extend(self._embedding_ts(source))
            target['embeddings'].extend(source['embeddings'])
            if len(target['embeddings']) > self.max_embeddings * 2:
                # Срезаем эмбеддинги и таймстампы одинаково (списки параллельны).
                target['embeddings'] = target['embeddings'][-self.max_embeddings:]
                target['embedding_ts'] = t_ts[-self.max_embeddings:]
            tb_ts = self._body_ts(target)
            tb_ts.extend(self._body_ts(source))
            tgt_bodies = target.setdefault('body_embeddings', [])
            tgt_bodies.extend(source.get('body_embeddings', []))
            if len(tgt_bodies) > self.max_body_embeddings * 2:
                # Дескрипторы тела и их таймстампы режем одинаково (параллельны).
                target['body_embeddings'] = tgt_bodies[-self.max_body_embeddings:]
                target['body_ts'] = tb_ts[-self.max_body_embeddings:]
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
                'body_count': len(data.get('body_embeddings', [])),
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
        if max_age_days <= 0:
            # 0/отрицательное — личности хранятся «навсегда», авто-удаление выключено
            return
        with self._lock:
            now = time.time()
            to_del = [gid for gid, d in self._gallery.items()
                      if now - d['last_seen'] > max_age_days * 86400]
            for gid in to_del:
                del self._gallery[gid]
            if to_del:
                self._save()
                print(f"[ReID] Удалено {len(to_del)} старых личностей")

    def prune_old_embeddings(self, max_age_days: float) -> int:
        """Состарить память: удалить эмбеддинги старше max_age_days (по времени
        ДОБАВЛЕНИЯ), сохраняя якорь (индекс 0) каждой личности. Образ человека
        остаётся в памяти, а лишние «постаревшие» ракурсы со временем стираются.
        0/отрицательное — затухание выключено. Возвращает число удалённых
        эмбеддингов. Запись на диск — только при реальном удалении."""
        if max_age_days <= 0:
            return 0
        cutoff = time.time() - max_age_days * 86400
        removed = 0
        with self._lock:
            for data in self._gallery.values():
                embs = data.get('embeddings')
                if not embs:
                    continue
                ts = self._embedding_ts(data)
                keep_e = [embs[0]]   # якорь неприкосновенен
                keep_t = [ts[0]]
                for e, t in zip(embs[1:], ts[1:]):
                    if t >= cutoff:
                        keep_e.append(e)
                        keep_t.append(t)
                    else:
                        removed += 1
                data['embeddings'] = keep_e
                data['embedding_ts'] = keep_t
            if removed:
                self._save()
                print(f"[ReID] Состарено и удалено {removed} эмбеддингов "
                      f"(TTL {max_age_days} дн.)")
        return removed

    def prune_old_bodies(self, max_age_days: float) -> int:
        """Состарить дескрипторы тела: удалить все старше max_age_days (по времени
        добавления). В отличие от лиц — БЕЗ защиты якоря: внешний вид завязан на
        одежду и устаревает быстро, эталонного «вечного» ракурса тела нет. Если
        все дескрипторы устарели — личность просто перестаёт опознаваться со
        спины, пока её снова не увидят в лицо. 0/отрицательное — выключено."""
        if max_age_days <= 0:
            return 0
        cutoff = time.time() - max_age_days * 86400
        removed = 0
        with self._lock:
            for data in self._gallery.values():
                bodies = data.get('body_embeddings')
                if not bodies:
                    continue
                ts = self._body_ts(data)
                keep_e, keep_t = [], []
                for e, t in zip(bodies, ts):
                    if t >= cutoff:
                        keep_e.append(e)
                        keep_t.append(t)
                    else:
                        removed += 1
                data['body_embeddings'] = keep_e
                data['body_ts'] = keep_t
            if removed:
                self._save()
                print(f"[ReID] Состарено и удалено {removed} дескрипторов тела "
                      f"(TTL {max_age_days} дн.)")
        return removed

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._gallery)
