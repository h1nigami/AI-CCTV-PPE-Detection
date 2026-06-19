"""Тесты body Re-ID: цветовой дескриптор, глубокий бэкенд OSNet (мок onnxruntime),
хранение/матчинг в галерее (с фильтром размерности) и интеграция в
DetectionState.get_global_id (опознание «со спины»)."""
import numpy as np
import pytest

from backend.reid.body import BodyRecognizer


def _solid_frame(h, w, bgr):
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, :] = bgr
    return img


def _color_rec():
    """Распознаватель на цветовом fallback (без сети/onnxruntime)."""
    return BodyRecognizer(use_deep=False)


class TestBodyRecognizerColor:
    def test_tiny_box_returns_none(self):
        rec = _color_rec()
        frame = _solid_frame(100, 100, (10, 20, 200))
        # bbox меньше минимальной площади/размера → ненадёжно → None
        assert rec.extract(frame, [0, 0, 8, 8]) is None

    def test_none_inputs(self):
        rec = _color_rec()
        assert rec.extract(None, [0, 0, 50, 50]) is None
        assert rec.extract(_solid_frame(100, 100, (0, 0, 0)), None) is None

    def test_valid_crop_returns_normalized_vector(self):
        rec = _color_rec()
        frame = _solid_frame(200, 120, (40, 180, 60))
        emb = rec.extract(frame, [0, 0, 120, 200])
        assert emb is not None
        assert emb.shape == (rec.color_dim,)
        assert np.isclose(np.linalg.norm(emb), 1.0, atol=1e-5)

    def test_same_appearance_high_similarity(self):
        rec = _color_rec()
        f1 = _solid_frame(200, 120, (40, 180, 60))
        f2 = _solid_frame(200, 120, (40, 180, 60))
        e1 = rec.extract(f1, [0, 0, 120, 200])
        e2 = rec.extract(f2, [0, 0, 120, 200])
        assert float(np.dot(e1, e2)) > 0.95

    def test_different_appearance_low_similarity(self):
        rec = _color_rec()
        red = rec.extract(_solid_frame(200, 120, (20, 20, 220)), [0, 0, 120, 200])
        blue = rec.extract(_solid_frame(200, 120, (220, 20, 20)), [0, 0, 120, 200])
        assert float(np.dot(red, blue)) < 0.5

    def test_backend_and_thresholds(self):
        from backend.config import (REID_BODY_MATCH_THRESHOLD_COLOR,
                                     REID_BODY_DIVERSITY_MAX_SIM_COLOR)
        rec = _color_rec()
        assert rec.backend == "color"
        assert rec.match_threshold == REID_BODY_MATCH_THRESHOLD_COLOR
        assert rec.diversity_max_sim == REID_BODY_DIVERSITY_MAX_SIM_COLOR

    def test_extract_batch_matches_single(self):
        rec = _color_rec()
        frame = _solid_frame(200, 240, (40, 180, 60))
        boxes = [[0, 0, 120, 200], [2, 2, 8, 8], [120, 0, 240, 200]]
        embs = rec.extract_batch(frame, boxes)
        assert len(embs) == 3
        assert embs[1] is None  # слишком мелкий
        assert embs[0] is not None and embs[2] is not None


class _FakeSession:
    """Имитация onnxruntime.InferenceSession для OSNet: вход [B,3,H,W] → [B,512].
    Возвращает по строке детерминированный вектор, зависящий от среднего кропа."""
    def __init__(self, batch=16, dim=512):
        self.batch = batch
        self.dim = dim

    def run(self, _outputs, feed):
        x = list(feed.values())[0]
        assert x.shape[0] == self.batch, "вход должен быть дополнен до фикс. батча"
        out = np.zeros((self.batch, self.dim), dtype=np.float32)
        for i in range(self.batch):
            seed = float(np.mean(x[i])) + i * 0.0  # вектор зависит от содержимого
            out[i, 0] = 1.0 + seed
            out[i, 1] = 0.5
        return [out]


def _deep_rec():
    """Распознаватель с подменённым deep-бэкендом (без реальной модели/сети)."""
    rec = BodyRecognizer(use_deep=False)
    rec._session = _FakeSession(batch=16, dim=512)
    rec._input_name = "input"
    rec._onnx_batch = 16
    rec._in_w, rec._in_h = 128, 256
    return rec


class TestBodyRecognizerDeep:
    def test_backend_and_thresholds(self):
        from backend.config import (REID_BODY_MATCH_THRESHOLD,
                                     REID_BODY_DIVERSITY_MAX_SIM)
        rec = _deep_rec()
        assert rec.backend == "deep"
        assert rec.match_threshold == REID_BODY_MATCH_THRESHOLD
        assert rec.diversity_max_sim == REID_BODY_DIVERSITY_MAX_SIM

    def test_deep_descriptor_512_normalized(self):
        rec = _deep_rec()
        frame = _solid_frame(220, 120, (40, 180, 60))
        emb = rec.extract(frame, [0, 0, 120, 200])
        assert emb is not None
        assert emb.shape == (512,)
        assert np.isclose(np.linalg.norm(emb), 1.0, atol=1e-5)

    def test_deep_batch_padding_and_positions(self):
        # 20 человек → два чанка (16 + 4 с паддингом до 16); None для мелких bbox.
        rec = _deep_rec()
        frame = _solid_frame(220, 2200, (40, 180, 60))
        boxes = [[i * 100, 0, i * 100 + 90, 210] for i in range(20)]
        boxes[5] = [0, 0, 4, 4]  # мелкий → None
        embs = rec.extract_batch(frame, boxes)
        assert len(embs) == 20
        assert embs[5] is None
        assert sum(e is not None for e in embs) == 19
        for e in embs:
            if e is not None:
                assert e.shape == (512,)


class TestGalleryBody:
    def test_add_and_match_body(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam", quality=0.8)
        body = np.zeros(512, dtype=np.float32)
        body[0] = 1.0
        assert gallery.add_body(gid, body) is True
        matched, sim = gallery.match_body(body, threshold=0.6)
        assert matched == gid
        assert sim > 0.99

    def test_match_body_below_threshold_returns_none(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam", quality=0.8)
        a = np.zeros(512, dtype=np.float32); a[0] = 1.0
        b = np.zeros(512, dtype=np.float32); b[1] = 1.0  # ортогонален a
        gallery.add_body(gid, a)
        matched, _ = gallery.match_body(b, threshold=0.6)
        assert matched is None

    def test_body_diversity_gate(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam", quality=0.8)
        a = np.zeros(512, dtype=np.float32); a[0] = 1.0
        assert gallery.add_body(gid, a) is True
        # почти-дубль (тот же вектор) при diverse=True не добавляется
        assert gallery.add_body(gid, a.copy(), diverse=True) is False
        info = gallery.get_info(gid)
        assert info["body_count"] == 1

    def test_body_cap(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam", quality=0.8)
        for i in range(gallery.max_body_embeddings + 5):
            v = np.zeros(512, dtype=np.float32)
            v[i % 512] = 1.0
            gallery.add_body(gid, v, diverse=False)
        assert gallery.get_info(gid)["body_count"] == gallery.max_body_embeddings

    def test_merge_carries_body(self, gallery, normalized_embedding, different_embedding):
        gid1 = gallery.match_or_register(normalized_embedding, "cam", quality=0.8)
        gid2 = gallery.match_or_register(different_embedding, "cam", quality=0.8)
        assert gid1 != gid2
        v = np.zeros(512, dtype=np.float32); v[2] = 1.0
        gallery.add_body(gid1, v)
        gallery.merge_entries(gid1, gid2)
        assert gallery.get_info(gid2)["body_count"] >= 1

    def test_dimension_filter_no_cross_backend_match(self, gallery, normalized_embedding):
        """Дескрипторы разной размерности (deep 512 vs цветовой 256) не сравниваются
        между собой — иначе косинус упал бы с ошибкой/ложным матчем."""
        gid = gallery.match_or_register(normalized_embedding, "cam", quality=0.8)
        deep = np.zeros(512, dtype=np.float32); deep[0] = 1.0
        color = np.zeros(256, dtype=np.float32); color[0] = 1.0
        gallery.add_body(gid, color)   # старый цветовой
        gallery.add_body(gid, deep)    # новый глубокий
        # Запрос глубоким вектором матчится (та же размерность), без ошибки.
        matched, sim = gallery.match_body(deep, threshold=0.6)
        assert matched == gid and sim > 0.99
        # Запрос цветовым другого направления не находит (по своей размерности).
        color2 = np.zeros(256, dtype=np.float32); color2[5] = 1.0
        assert gallery.match_body(color2, threshold=0.6)[0] is None

    def test_diversity_gate_ignores_other_dimension(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam", quality=0.8)
        color = np.zeros(256, dtype=np.float32); color[0] = 1.0
        gallery.add_body(gid, color)
        deep = np.zeros(512, dtype=np.float32); deep[0] = 1.0
        # diversity сравнивает только дескрипторы той же длины → deep добавится.
        assert gallery.add_body(gid, deep, diverse=True) is True


class TestStateBodyReid:
    def test_recover_identity_by_body_no_face(self, state, normalized_embedding):
        # 1) Личность создаётся по лицу на треке 1
        gid = state.get_global_id(1, "cam", face_embedding=normalized_embedding,
                                  quality=0.8, person_box=[0, 0, 100, 200])
        assert gid > 0
        # 2) Запоминаем её тело
        body = np.zeros(512, dtype=np.float32); body[0] = 1.0
        state.gallery.add_body(gid, body)
        # Трек 1 «ушёл» (человек вышел/перекрытие) — больше не активен.
        state._track_last_seen[("cam", 1)] = 0.0
        # 3) Новый трек 2, лица нет, но тело совпадает → опознать «со спины»
        recovered = state.get_global_id(2, "cam", face_embedding=None,
                                        body_embedding=body, person_box=[5, 5, 105, 205])
        assert recovered == gid

    def test_no_body_match_returns_zero(self, state, normalized_embedding):
        gid = state.get_global_id(1, "cam", face_embedding=normalized_embedding,
                                  quality=0.8, person_box=[0, 0, 100, 200])
        a = np.zeros(512, dtype=np.float32); a[0] = 1.0
        b = np.zeros(512, dtype=np.float32); b[1] = 1.0
        state.gallery.add_body(gid, a)
        # другой трек со спины, непохожее тело → 0 (не приписываем чужую личность)
        res = state.get_global_id(3, "cam", face_embedding=None,
                                  body_embedding=b, person_box=[0, 0, 100, 200])
        assert res == 0

    def test_body_match_blocked_when_gid_active_on_other_track(self, state, normalized_embedding):
        # Личность gid активна на треке 1 (только что виден). Другой трек 2 со
        # спины с похожим телом НЕ должен забрать то же имя.
        gid = state.get_global_id(1, "cam", face_embedding=normalized_embedding,
                                  quality=0.8, person_box=[0, 0, 100, 200])
        body = np.zeros(512, dtype=np.float32); body[0] = 1.0
        state.gallery.add_body(gid, body)
        # трек 1 «жив»: подтверждаем его лицом (обновляет last_seen)
        state.get_global_id(1, "cam", face_embedding=normalized_embedding,
                            quality=0.8, person_box=[0, 0, 100, 200])
        res = state.get_global_id(2, "cam", face_embedding=None,
                                  body_embedding=body, person_box=[300, 0, 400, 200])
        assert res == 0  # не слили двух людей

    def test_configure_body_threshold(self, state):
        state.configure_body(0.6, diversity_max_sim=0.9)
        assert state._body_match_threshold == 0.6
        assert state.gallery.body_diversity_max_sim == 0.9

    def test_face_path_unaffected_without_body(self, state, normalized_embedding):
        # обратная совместимость: без body_embedding поведение прежнее
        gid = state.get_global_id(1, "cam", face_embedding=normalized_embedding,
                                  quality=0.8, person_box=[0, 0, 100, 200])
        assert gid > 0
