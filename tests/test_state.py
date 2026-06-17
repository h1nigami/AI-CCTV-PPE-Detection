import time
import numpy as np


class TestNoFallbackWithoutFace:
    def test_no_face_returns_zero(self, state):
        gid = state.get_global_id(track_id=1, cam_id="cam01")
        assert gid == 0

    def test_no_face_name_is_empty(self, state):
        gid = state.get_global_id(track_id=1, cam_id="cam01")
        name = state.get_person_name(gid, "cam01")
        assert name == ""

    def test_track_not_stored_without_face(self, state):
        state.get_global_id(track_id=1, cam_id="cam01")
        assert ("cam01", 1) not in state._track_to_global

    def test_multiple_no_face_calls_same_result(self, state):
        assert state.get_global_id(track_id=1, cam_id="cam01") == 0
        assert state.get_global_id(track_id=1, cam_id="cam01") == 0

    def test_different_tracks_both_zero_without_face(self, state):
        assert state.get_global_id(track_id=1, cam_id="cam01") == 0
        assert state.get_global_id(track_id=2, cam_id="cam01") == 0


class TestFaceMatching:
    def test_new_track_with_face_creates_gallery_entry(self, state, normalized_embedding):
        gid = state.get_global_id(
            track_id=1, cam_id="cam01",
            face_embedding=normalized_embedding, quality=0.9,
        )
        assert state.gallery.has_id(gid)
        info = state.gallery.get_info(gid)
        assert info['name'].startswith("Гость_")

    def test_same_track_same_face_same_id(self, state, normalized_embedding):
        gid1 = state.get_global_id(
            track_id=1, cam_id="cam01",
            face_embedding=normalized_embedding, quality=0.9,
        )
        gid2 = state.get_global_id(
            track_id=1, cam_id="cam01",
            face_embedding=normalized_embedding, quality=0.9,
        )
        assert gid1 == gid2

    def test_track_no_face_then_face(self, state, normalized_embedding):
        noface_id = state.get_global_id(track_id=1, cam_id="cam01")
        assert noface_id == 0
        name = state.get_person_name(noface_id, "cam01")
        assert name == ""

        gallery_id = state.get_global_id(
            track_id=1, cam_id="cam01",
            face_embedding=normalized_embedding, quality=0.9,
        )
        assert state.gallery.has_id(gallery_id)
        info = state.gallery.get_info(gallery_id)
        assert info['embedding_count'] == 1


class TestGalleryMergeOnTrackSwitch:
    def test_singleton_gallery_merged_on_track_switch(self, state):
        emb1 = np.random.randn(512).astype(np.float32)
        emb1 = emb1 / np.linalg.norm(emb1)
        emb2 = np.random.randn(512).astype(np.float32)
        emb2 = emb2 / np.linalg.norm(emb2)

        known_id = state.gallery.match_or_register(emb1, "cam01", quality=0.9)
        state.gallery.rename(known_id, "Иван")

        guest_id = state.get_global_id(
            track_id=1, cam_id="cam01",
            face_embedding=emb2, quality=0.3,
        )
        guest_name = state.gallery.get_name(guest_id)
        assert guest_name.startswith("Гость_")

        matched_id = state.get_global_id(
            track_id=1, cam_id="cam01",
            face_embedding=emb1, quality=0.9,
        )
        assert matched_id == known_id
        assert not state.gallery.has_id(guest_id)
        info = state.gallery.get_info(known_id)
        assert info['embedding_count'] >= 2

    def test_singleton_gallery_not_merged_if_multiple_embeddings(self, state):
        emb1 = np.random.randn(512).astype(np.float32)
        emb1 = emb1 / np.linalg.norm(emb1)
        emb2 = np.random.randn(512).astype(np.float32)
        emb2 = emb2 / np.linalg.norm(emb2)
        emb3 = np.random.randn(512).astype(np.float32)
        emb3 = emb3 / np.linalg.norm(emb3)

        known_id = state.gallery.match_or_register(emb1, "cam01", quality=0.9)
        state.gallery.match_or_register(emb1, "cam01", quality=0.9)
        state.gallery.rename(known_id, "Иван")

        guest_id = state.get_global_id(
            track_id=1, cam_id="cam01",
            face_embedding=emb2, quality=0.3,
        )
        state.gallery.match_or_register(emb2, "cam01", quality=0.3)
        assert state.gallery.get_info(guest_id)['embedding_count'] == 2

        matched_id = state.get_global_id(
            track_id=1, cam_id="cam01",
            face_embedding=emb1, quality=0.9,
        )
        assert matched_id == known_id
        assert state.gallery.has_id(guest_id)

    def test_no_fallback_no_merge_needed(self, state, normalized_embedding):
        """Without fallback, face creates fresh gallery entry directly"""
        state.get_global_id(track_id=1, cam_id="cam01")

        gallery_id = state.get_global_id(
            track_id=1, cam_id="cam01",
            face_embedding=normalized_embedding, quality=0.9,
        )
        assert state.gallery.has_id(gallery_id)
        info = state.gallery.get_info(gallery_id)
        assert info['name'].startswith("Гость_")
        assert info['embedding_count'] == 1


class TestCleanup:
    def test_cleanup_stale_tracks_with_face(self, state, normalized_embedding):
        gid = state.get_global_id(
            track_id=1, cam_id="cam01",
            face_embedding=normalized_embedding, quality=0.9,
        )
        state.get_global_id(track_id=2, cam_id="cam01")

        assert ("cam01", 1) in state._track_to_global
        assert ("cam01", 2) not in state._track_to_global

        state._track_last_seen[("cam01", 1)] = 0
        state.cleanup_stale_tracks()

        assert ("cam01", 1) not in state._track_to_global

    def test_cleanup_preserves_recent_tracks(self, state, normalized_embedding):
        gid = state.get_global_id(
            track_id=1, cam_id="cam01",
            face_embedding=normalized_embedding, quality=0.9,
        )
        state.cleanup_stale_tracks()
        result = state.get_global_id(
            track_id=1, cam_id="cam01",
            face_embedding=normalized_embedding, quality=0.9,
        )
        assert result == gid


class TestPersonName:
    def test_no_face_name_empty(self, state):
        gid = state.get_global_id(track_id=1, cam_id="cam01")
        name = state.get_person_name(gid, "cam01")
        assert name == ""

    def test_gallery_name(self, state, normalized_embedding):
        gid = state.get_global_id(
            track_id=1, cam_id="cam01",
            face_embedding=normalized_embedding, quality=0.9,
        )
        state.gallery.rename(gid, "Иван")
        name = state.get_person_name(gid, "cam01")
        assert name == "Иван"

    def test_fallback_name_fallback_dict(self, state):
        gid = 999
        state._fallback_names[gid] = "Тестовый"
        name = state.get_person_name(gid, "cam01")
        assert name == "Тестовый"


class TestLog:
    def test_add_and_get_log(self, state):
        from backend.core.models import LogEntry
        entry = LogEntry(
            id="1", timestamp="2024-01-01", message="test",
            category="info", cam_id="cam01", global_id=1,
        )
        state.add_log(entry)
        log = state.get_log()
        assert len(log) == 1
        assert log[0].message == "test"

    def test_clear_log(self, state):
        from backend.core.models import LogEntry
        entry = LogEntry(
            id="1", timestamp="2024-01-01", message="test",
            category="info", cam_id="cam01", global_id=1,
        )
        state.add_log(entry)
        state.clear_log()
        assert len(state.get_log()) == 0

    def test_log_max_size(self, state):
        from backend.core.models import LogEntry
        from backend.config import MAX_LOG_SIZE
        for i in range(MAX_LOG_SIZE + 10):
            state.add_log(LogEntry(
                id=str(i), timestamp="2024-01-01", message=str(i),
                category="info", cam_id="cam01", global_id=i,
            ))
        assert len(state.get_log()) == MAX_LOG_SIZE


class TestClearTracks:
    def test_clear_tracks_removes_all(self, state):
        emb1 = np.random.randn(512).astype(np.float32)
        emb1 = emb1 / np.linalg.norm(emb1)
        emb2 = np.random.randn(512).astype(np.float32)
        emb2 = emb2 / np.linalg.norm(emb2)
        gid1 = state.get_global_id(
            track_id=1, cam_id="cam01",
            face_embedding=emb1, quality=0.9,
        )
        gid2 = state.get_global_id(
            track_id=2, cam_id="cam01",
            face_embedding=emb2, quality=0.9,
        )
        assert gid1 != gid2
        state.clear_tracks()
        gid1b = state.get_global_id(
            track_id=1, cam_id="cam01",
            face_embedding=emb1, quality=0.9,
        )
        gid2b = state.get_global_id(
            track_id=2, cam_id="cam01",
            face_embedding=emb2, quality=0.9,
        )
        assert gid1b is not None
        assert gid2b is not None
        assert gid1b != gid2b

    def test_clear_tracks_removes_fallback_names(self, state):
        state._fallback_names[42] = "Тестовый"
        assert 42 in state._fallback_names
        state.clear_tracks()
        assert 42 not in state._fallback_names
