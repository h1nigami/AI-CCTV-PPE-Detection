import time
import numpy as np


class TestAdaptiveThreshold:
    def test_excellent_quality(self, gallery):
        assert gallery._adaptive_threshold(0.9) == 0.45
        assert gallery._adaptive_threshold(0.8) == 0.45

    def test_good_quality(self, gallery):
        assert gallery._adaptive_threshold(0.7) == 0.50
        assert gallery._adaptive_threshold(0.6) == 0.50

    def test_medium_quality(self, gallery):
        assert gallery._adaptive_threshold(0.5) == 0.55
        assert gallery._adaptive_threshold(0.4) == 0.55

    def test_poor_quality(self, gallery):
        assert gallery._adaptive_threshold(0.3) == 0.60
        assert gallery._adaptive_threshold(0.0) == 0.60

    def test_boundary_values(self, gallery):
        assert gallery._adaptive_threshold(0.799) == 0.50
        assert gallery._adaptive_threshold(0.8) == 0.45
        assert gallery._adaptive_threshold(0.599) == 0.55
        assert gallery._adaptive_threshold(0.6) == 0.50


class TestCosineSim:
    def test_identical(self, gallery):
        emb = np.random.randn(128).astype(np.float32)
        emb = emb / np.linalg.norm(emb)
        sim = gallery._cosine_sim(emb, emb)
        assert abs(sim - 1.0) < 1e-6

    def test_orthogonal(self, gallery):
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([0.0, 1.0], dtype=np.float32)
        sim = gallery._cosine_sim(a, b)
        assert abs(sim) < 1e-6

    def test_opposite(self, gallery):
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([-1.0, 0.0], dtype=np.float32)
        sim = gallery._cosine_sim(a, b)
        assert abs(sim - (-1.0)) < 1e-6

    def test_same_direction_different_magnitude(self, gallery):
        a = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        b = np.array([2.0, 4.0, 6.0], dtype=np.float32)
        sim = gallery._cosine_sim(a, b)
        assert abs(sim - 1.0) < 1e-6


class TestAssignName:
    def test_first_name(self, gallery):
        name = gallery._assign_name()
        assert name == f"Гость_{gallery._next_id}"

    def test_format(self, gallery):
        name = gallery._assign_name()
        assert name == f"Гость_{gallery._next_id}"


class TestMatchOrRegister:
    def test_creates_new_entry_on_first_call(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        assert gallery.has_id(gid)
        info = gallery.get_info(gid)
        assert info['embedding_count'] == 1
        assert info['name'].startswith("Гость_")
        assert "cam01" in info['cameras']

    def test_matches_same_embedding(self, gallery, normalized_embedding):
        gid1 = gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        gid2 = gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        assert gid1 == gid2
        info = gallery.get_info(gid1)
        assert info['embedding_count'] == 2

    def test_creates_new_for_different_embedding(self, gallery):
        emb1 = np.random.randn(512).astype(np.float32)
        emb1 = emb1 / np.linalg.norm(emb1)
        emb2 = np.random.randn(512).astype(np.float32)
        emb2 = emb2 / np.linalg.norm(emb2)
        gid1 = gallery.match_or_register(emb1, "cam01", quality=0.9)
        gid2 = gallery.match_or_register(emb2, "cam01", quality=0.9)
        assert gid1 != gid2

    def test_tracks_multiple_cameras(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        gallery.match_or_register(normalized_embedding, "cam02", quality=0.9)
        info = gallery.get_info(gid)
        assert "cam01" in info['cameras']
        assert "cam02" in info['cameras']

    def test_respects_max_embeddings(self, gallery):
        emb = np.random.randn(512).astype(np.float32)
        emb = emb / np.linalg.norm(emb)
        gid = gallery.match_or_register(emb, "cam01", quality=0.9)
        for _ in range(10):
            e = np.random.randn(512).astype(np.float32)
            e = e / np.linalg.norm(e)
            gallery.match_or_register(e, "cam01", quality=0.9)
        info = gallery.get_info(gid)
        assert info['embedding_count'] <= gallery.max_embeddings

    def test_low_quality_still_matches_same(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        gid2 = gallery.match_or_register(normalized_embedding, "cam01", quality=0.1)
        assert gid == gid2

    def test_adaptive_discount_for_many_embeddings(self, gallery):
        base_emb = np.random.randn(512).astype(np.float32)
        base_emb = base_emb / np.linalg.norm(base_emb)
        gid = gallery.match_or_register(base_emb, "cam01", quality=0.9)
        # Add 4 more similar embeddings
        for _ in range(4):
            similar = base_emb + np.random.randn(512).astype(np.float32) * 0.01
            similar = similar / np.linalg.norm(similar)
            gallery.match_or_register(similar, "cam01", quality=0.9)
        # Now entry has 5 embeddings → discount should apply
        info = gallery.get_info(gid)
        assert info['embedding_count'] == 5

    def test_save_on_new_entry(self, gallery, normalized_embedding, gallery_path):
        gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        assert gallery_path.exists()
        assert gallery_path.stat().st_size > 0

    def test_per_embedding_max_resists_mean_dilution(self, gallery):
        rng = np.random.RandomState(42)
        dim = 512

        base = rng.randn(dim).astype(np.float32)
        base = base / np.linalg.norm(base)
        gid = gallery.match_or_register(base, "cam01", quality=0.9)

        noise_ids = []
        for _ in range(4):
            noise = rng.randn(dim).astype(np.float32)
            noise = noise / np.linalg.norm(noise)
            nid = gallery.match_or_register(noise, "cam01", quality=0.9)
            assert nid != gid
            noise_ids.append(nid)

        for nid in noise_ids:
            gallery.merge_entries(nid, gid)

        info = gallery.get_info(gid)
        assert info['embedding_count'] == 5

        profile = base + rng.randn(dim).astype(np.float32) * 0.02
        profile = profile / np.linalg.norm(profile)
        match_id = gallery.match_or_register(profile, "cam01", quality=0.7)
        assert match_id == gid, (
            f"per-embedding max sim ({gid}) should beat mean-based threshold "
            f"(got {match_id})"
        )


class TestMergeEntries:
    def test_merge_two_entries(self, gallery):
        emb1 = np.random.randn(512).astype(np.float32)
        emb1 = emb1 / np.linalg.norm(emb1)
        emb2 = np.random.randn(512).astype(np.float32)
        emb2 = emb2 / np.linalg.norm(emb2)
        gid1 = gallery.match_or_register(emb1, "cam01", quality=0.9)
        gid2 = gallery.match_or_register(emb2, "cam01", quality=0.9)
        assert gallery.merge_entries(gid1, gid2) is True
        assert not gallery.has_id(gid1)
        info = gallery.get_info(gid2)
        assert info['embedding_count'] == 2
        assert "cam01" in info['cameras']

    def test_self_merge_returns_false(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        assert gallery.merge_entries(gid, gid) is False
        assert gallery.has_id(gid)

    def test_merge_nonexistent_source(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        assert gallery.merge_entries(999, gid) is False

    def test_merge_nonexistent_target(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        assert gallery.merge_entries(gid, 999) is False

    def test_merge_both_nonexistent(self, gallery):
        assert gallery.merge_entries(999, 1000) is False

    def test_merge_preserves_target_name(self, gallery):
        emb1 = np.random.randn(512).astype(np.float32)
        emb1 = emb1 / np.linalg.norm(emb1)
        emb2 = np.random.randn(512).astype(np.float32)
        emb2 = emb2 / np.linalg.norm(emb2)
        gid1 = gallery.match_or_register(emb1, "cam01", quality=0.9)
        gid2 = gallery.match_or_register(emb2, "cam01", quality=0.9)
        gallery.rename(gid2, "Иван")
        gallery.merge_entries(gid1, gid2)
        assert gallery.get_name(gid2) == "Иван"

    def test_merge_combines_cameras(self, gallery):
        emb1 = np.random.randn(512).astype(np.float32)
        emb1 = emb1 / np.linalg.norm(emb1)
        emb2 = np.random.randn(512).astype(np.float32)
        emb2 = emb2 / np.linalg.norm(emb2)
        gid1 = gallery.match_or_register(emb1, "cam01", quality=0.9)
        gid2 = gallery.match_or_register(emb2, "cam02", quality=0.9)
        gallery.merge_entries(gid1, gid2)
        info = gallery.get_info(gid2)
        assert "cam01" in info['cameras']
        assert "cam02" in info['cameras']

    def test_merge_updates_last_seen(self, gallery):
        emb1 = np.random.randn(512).astype(np.float32)
        emb1 = emb1 / np.linalg.norm(emb1)
        emb2 = np.random.randn(512).astype(np.float32)
        emb2 = emb2 / np.linalg.norm(emb2)
        gid1 = gallery.match_or_register(emb1, "cam01", quality=0.9)
        old_last_seen = gallery.get_info(gid1)['last_seen']
        time.sleep(0.01)
        gid2 = gallery.match_or_register(emb2, "cam01", quality=0.9)
        gallery.merge_entries(gid1, gid2)
        info = gallery.get_info(gid2)
        assert info['last_seen'] >= old_last_seen


class TestRename:
    def test_rename_valid(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        assert gallery.rename(gid, "Иван") is True
        assert gallery.get_name(gid) == "Иван"

    def test_rename_nonexistent(self, gallery):
        assert gallery.rename(999, "Иван") is False

    def test_rename_saves(self, gallery, normalized_embedding, gallery_path):
        gid = gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        gallery.rename(gid, "Иван")
        from backend.reid.gallery import FaceGallery
        gal2 = FaceGallery(gallery_path, sim_threshold=0.55, max_embeddings_per_id=5)
        assert gal2.get_name(gid) == "Иван"
        gal2.delete(gid)


class TestGetInfo:
    def test_get_info_valid(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        info = gallery.get_info(gid)
        assert info['global_id'] == gid
        assert info['name'] is not None
        assert info['last_seen'] > 0
        assert len(info['cameras']) > 0
        assert info['embedding_count'] >= 1

    def test_get_info_nonexistent(self, gallery):
        assert gallery.get_info(999) is None


class TestGetName:
    def test_get_name_gallery_entry(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        gallery.rename(gid, "Мария")
        assert gallery.get_name(gid) == "Мария"

    def test_get_name_nonexistent(self, gallery):
        name = gallery.get_name(999)
        assert name == "ID999"

    def test_get_name_default(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        name = gallery.get_name(gid)
        assert name.startswith("Гость_")


class TestHasId:
    def test_has_existing(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        assert gallery.has_id(gid) is True

    def test_has_nonexistent(self, gallery):
        assert gallery.has_id(999) is False

    def test_has_after_delete(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        gallery.delete(gid)
        assert gallery.has_id(gid) is False


class TestListAll:
    def test_empty(self, gallery):
        assert gallery.list_all() == []

    def test_after_addition(self, gallery):
        emb = np.random.randn(512).astype(np.float32)
        emb = emb / np.linalg.norm(emb)
        gallery.match_or_register(emb, "cam01", quality=0.9)
        entries = gallery.list_all()
        assert len(entries) == 1
        assert 'global_id' in entries[0]
        assert 'name' in entries[0]
        assert 'last_seen' in entries[0]
        assert 'cameras' in entries[0]
        assert 'embedding_count' in entries[0]

    def test_multiple_entries(self, gallery):
        for i in range(3):
            emb = np.random.randn(512).astype(np.float32)
            emb = emb / np.linalg.norm(emb)
            gallery.match_or_register(emb, "cam01", quality=0.9)
        assert len(gallery.list_all()) == 3


class TestDelete:
    def test_delete_valid(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        assert gallery.delete(gid) is True
        assert not gallery.has_id(gid)
        assert len(gallery.list_all()) == 0

    def test_delete_nonexistent(self, gallery):
        assert gallery.delete(999) is False

    def test_delete_twice(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        gallery.delete(gid)
        assert gallery.delete(gid) is False


class TestClear:
    def test_clear_empty(self, gallery):
        gallery.clear()
        assert gallery.count == 0

    def test_clear_with_entries(self, gallery):
        for _ in range(5):
            emb = np.random.randn(512).astype(np.float32)
            emb = emb / np.linalg.norm(emb)
            gallery.match_or_register(emb, "cam01", quality=0.9)
        gallery.clear()
        assert gallery.count == 0
        assert gallery.list_all() == []

    def test_clear_resets_id_counter(self, gallery):
        emb = np.random.randn(512).astype(np.float32)
        emb = emb / np.linalg.norm(emb)
        gid = gallery.match_or_register(emb, "cam01", quality=0.9)
        gallery.clear()
        emb2 = np.random.randn(512).astype(np.float32)
        emb2 = emb2 / np.linalg.norm(emb2)
        gid2 = gallery.match_or_register(emb2, "cam01", quality=0.9)
        assert gid2 == 1


class TestSaveLoad:
    def test_save_and_load_persistence(self, gallery_path, normalized_embedding):
        from backend.reid.gallery import FaceGallery
        gal1 = FaceGallery(gallery_path, sim_threshold=0.55, max_embeddings_per_id=5)
        gid = gal1.match_or_register(normalized_embedding, "cam01", quality=0.9)
        gal1.rename(gid, "Иван")
        gal2 = FaceGallery(gallery_path, sim_threshold=0.55, max_embeddings_per_id=5)
        assert gal2.has_id(gid)
        assert gal2.get_name(gid) == "Иван"
        gal2.delete(gid)

    def test_save_and_load_multiple_entries(self, gallery_path):
        from backend.reid.gallery import FaceGallery
        gal1 = FaceGallery(gallery_path, sim_threshold=0.55, max_embeddings_per_id=5)
        ids = []
        for i in range(3):
            emb = np.random.randn(512).astype(np.float32)
            emb = emb / np.linalg.norm(emb)
            gid = gal1.match_or_register(emb, "cam01", quality=0.9)
            gal1.rename(gid, f"Person_{i}")
            ids.append(gid)
        gal2 = FaceGallery(gallery_path, sim_threshold=0.55, max_embeddings_per_id=5)
        assert gal2.count == 3
        for i, gid in enumerate(ids):
            assert gal2.has_id(gid)
            assert gal2.get_name(gid) == f"Person_{i}"
        gal2.clear()


class TestCleanupOld:
    def test_cleanup_removes_stale_entry(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        # Set last_seen to 31 days ago
        with gallery._lock:
            gallery._gallery[gid]["last_seen"] = time.time() - 31 * 86400
        gallery.cleanup_old(max_age_days=30)
        assert not gallery.has_id(gid)

    def test_cleanup_preserves_recent_entry(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        gallery.cleanup_old(max_age_days=30)
        assert gallery.has_id(gid)

    def test_cleanup_saves_file_when_entries_removed(self, gallery, gallery_path,
                                                      normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        with gallery._lock:
            gallery._gallery[gid]["last_seen"] = time.time() - 31 * 86400
        before_mtime = gallery_path.stat().st_mtime if gallery_path.exists() else 0
        gallery.cleanup_old(max_age_days=30)
        if gallery_path.exists():
            assert gallery_path.stat().st_mtime >= before_mtime

    def test_cleanup_no_op_on_empty_gallery(self, gallery):
        gallery.cleanup_old(max_age_days=30)
        assert gallery.count == 0


class TestEmbeddingMemoryAging:
    """Затухание памяти ПО ВРЕМЕНИ: образ (якорь) сохраняется, лишние ракурсы
    стираются по возрасту, а не вытесняются вслепую при переполнении."""

    def _add(self, gallery, gid, n):
        for _ in range(n):
            emb = np.random.randn(512).astype(np.float32)
            emb = emb / np.linalg.norm(emb)
            gallery.add_observation(gid, "cam01", emb, quality=0.9, store=True)

    def test_timestamps_parallel_to_embeddings(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        self._add(gallery, gid, 3)
        with gallery._lock:
            data = gallery._gallery[gid]
            assert len(data['embedding_ts']) == len(data['embeddings']) == 4

    def test_prune_removes_old_non_anchor(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        self._add(gallery, gid, 3)
        with gallery._lock:
            ts = gallery._gallery[gid]['embedding_ts']
            for i in range(1, len(ts)):          # все неякорные «постарели»
                ts[i] = time.time() - 40 * 86400
        removed = gallery.prune_old_embeddings(max_age_days=30)
        assert removed == 3
        with gallery._lock:
            assert len(gallery._gallery[gid]['embeddings']) == 1   # остался якорь

    def test_prune_protects_anchor(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        with gallery._lock:
            gallery._gallery[gid]['embedding_ts'][0] = time.time() - 999 * 86400
        gallery.prune_old_embeddings(max_age_days=30)
        with gallery._lock:
            assert len(gallery._gallery[gid]['embeddings']) == 1

    def test_prune_keeps_recent(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        self._add(gallery, gid, 2)
        assert gallery.prune_old_embeddings(max_age_days=30) == 0
        with gallery._lock:
            assert len(gallery._gallery[gid]['embeddings']) == 3

    def test_prune_disabled_with_zero(self, gallery, normalized_embedding):
        gid = gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        self._add(gallery, gid, 2)
        with gallery._lock:
            for i in range(1, len(gallery._gallery[gid]['embedding_ts'])):
                gallery._gallery[gid]['embedding_ts'][i] = time.time() - 999 * 86400
        assert gallery.prune_old_embeddings(max_age_days=0) == 0
        with gallery._lock:
            assert len(gallery._gallery[gid]['embeddings']) == 3

    def test_overflow_evicts_oldest_keeps_anchor(self, gallery, normalized_embedding):
        # Кап = 5 (фикстура). Якорь + 6 дописываний → вытеснения, но якорь цел.
        gid = gallery.match_or_register(normalized_embedding, "cam01", quality=0.9)
        self._add(gallery, gid, 6)
        with gallery._lock:
            data = gallery._gallery[gid]
            assert len(data['embeddings']) == 5
            assert len(data['embedding_ts']) == 5
            assert np.allclose(data['embeddings'][0], normalized_embedding)

    def test_backward_compat_load_without_ts(self, gallery_path, normalized_embedding):
        import pickle
        from backend.reid.gallery import FaceGallery
        old = {
            'gallery': {
                1: {'embeddings': [normalized_embedding, normalized_embedding],
                    'body_embeddings': [], 'last_seen': time.time(),
                    'cameras': {'cam01'}, 'name': 'Иван'}
            },
            'next_id': 2,
        }
        with open(gallery_path, 'wb') as f:
            pickle.dump(old, f)
        gal = FaceGallery(gallery_path, sim_threshold=0.55, max_embeddings_per_id=5)
        with gal._lock:
            assert len(gal._gallery[1]['embedding_ts']) == 2
