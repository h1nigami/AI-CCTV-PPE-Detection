"""Тесты body Re-ID: дескриптор внешнего вида, хранение/матчинг в галерее и
интеграция в DetectionState.get_global_id (опознание «со спины»)."""
import numpy as np
import pytest

from backend.reid.body import BodyRecognizer


def _solid_frame(h, w, bgr):
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, :] = bgr
    return img


class TestBodyRecognizer:
    def test_tiny_box_returns_none(self):
        rec = BodyRecognizer()
        frame = _solid_frame(100, 100, (10, 20, 200))
        # bbox меньше минимальной площади/размера → ненадёжно → None
        assert rec.extract(frame, [0, 0, 8, 8]) is None

    def test_none_inputs(self):
        rec = BodyRecognizer()
        assert rec.extract(None, [0, 0, 50, 50]) is None
        assert rec.extract(_solid_frame(100, 100, (0, 0, 0)), None) is None

    def test_valid_crop_returns_normalized_vector(self):
        rec = BodyRecognizer()
        frame = _solid_frame(200, 120, (40, 180, 60))
        emb = rec.extract(frame, [0, 0, 120, 200])
        assert emb is not None
        assert emb.shape == (rec.dim,)
        assert np.isclose(np.linalg.norm(emb), 1.0, atol=1e-5)

    def test_same_appearance_high_similarity(self):
        rec = BodyRecognizer()
        f1 = _solid_frame(200, 120, (40, 180, 60))
        f2 = _solid_frame(200, 120, (40, 180, 60))
        e1 = rec.extract(f1, [0, 0, 120, 200])
        e2 = rec.extract(f2, [0, 0, 120, 200])
        assert float(np.dot(e1, e2)) > 0.95

    def test_different_appearance_low_similarity(self):
        rec = BodyRecognizer()
        red = rec.extract(_solid_frame(200, 120, (20, 20, 220)), [0, 0, 120, 200])
        blue = rec.extract(_solid_frame(200, 120, (220, 20, 20)), [0, 0, 120, 200])
        assert float(np.dot(red, blue)) < 0.5


class TestGalleryBody:
    def test_add_and_match_body(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam", quality=0.8)
        body = np.zeros(gallery_dim(), dtype=np.float32)
        body[0] = 1.0
        assert gallery.add_body(gid, body) is True
        matched, sim = gallery.match_body(body, threshold=0.82)
        assert matched == gid
        assert sim > 0.99

    def test_match_body_below_threshold_returns_none(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam", quality=0.8)
        a = np.zeros(gallery_dim(), dtype=np.float32); a[0] = 1.0
        b = np.zeros(gallery_dim(), dtype=np.float32); b[1] = 1.0  # ортогонален a
        gallery.add_body(gid, a)
        matched, _ = gallery.match_body(b, threshold=0.82)
        assert matched is None

    def test_body_diversity_gate(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam", quality=0.8)
        a = np.zeros(gallery_dim(), dtype=np.float32); a[0] = 1.0
        assert gallery.add_body(gid, a) is True
        # почти-дубль (тот же вектор) при diverse=True не добавляется
        assert gallery.add_body(gid, a.copy(), diverse=True) is False
        info = gallery.get_info(gid)
        assert info["body_count"] == 1

    def test_body_cap(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam", quality=0.8)
        for i in range(gallery.max_body_embeddings + 5):
            v = np.zeros(gallery_dim(), dtype=np.float32)
            v[i % gallery_dim()] = 1.0
            gallery.add_body(gid, v, diverse=False)
        assert gallery.get_info(gid)["body_count"] == gallery.max_body_embeddings

    def test_merge_carries_body(self, gallery, normalized_embedding, different_embedding):
        gid1 = gallery.match_or_register(normalized_embedding, "cam", quality=0.8)
        gid2 = gallery.match_or_register(different_embedding, "cam", quality=0.8)
        assert gid1 != gid2
        v = np.zeros(gallery_dim(), dtype=np.float32); v[2] = 1.0
        gallery.add_body(gid1, v)
        gallery.merge_entries(gid1, gid2)
        assert gallery.get_info(gid2)["body_count"] >= 1


class TestStateBodyReid:
    def test_recover_identity_by_body_no_face(self, state, normalized_embedding):
        # 1) Личность создаётся по лицу на треке 1
        gid = state.get_global_id(1, "cam", face_embedding=normalized_embedding,
                                  quality=0.8, person_box=[0, 0, 100, 200])
        assert gid > 0
        # 2) Запоминаем её тело
        body = np.zeros(gallery_dim_for(state), dtype=np.float32); body[0] = 1.0
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
        a = np.zeros(gallery_dim_for(state), dtype=np.float32); a[0] = 1.0
        b = np.zeros(gallery_dim_for(state), dtype=np.float32); b[1] = 1.0
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
        body = np.zeros(gallery_dim_for(state), dtype=np.float32); body[0] = 1.0
        state.gallery.add_body(gid, body)
        # трек 1 «жив»: подтверждаем его лицом (обновляет last_seen)
        state.get_global_id(1, "cam", face_embedding=normalized_embedding,
                            quality=0.8, person_box=[0, 0, 100, 200])
        res = state.get_global_id(2, "cam", face_embedding=None,
                                  body_embedding=body, person_box=[300, 0, 400, 200])
        assert res == 0  # не слили двух людей

    def test_face_path_unaffected_without_body(self, state, normalized_embedding):
        # обратная совместимость: без body_embedding поведение прежнее
        gid = state.get_global_id(1, "cam", face_embedding=normalized_embedding,
                                  quality=0.8, person_box=[0, 0, 100, 200])
        assert gid > 0


# ── helpers ──
def gallery_dim():
    return BodyRecognizer().dim


def gallery_dim_for(state):
    return BodyRecognizer().dim
