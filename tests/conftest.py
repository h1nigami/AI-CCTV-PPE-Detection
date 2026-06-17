import pytest
import numpy as np
from pathlib import Path


@pytest.fixture
def normalized_embedding():
    emb = np.random.randn(512).astype(np.float32)
    return emb / (np.linalg.norm(emb) + 1e-8)


@pytest.fixture
def different_embedding():
    emb = np.random.randn(512).astype(np.float32)
    emb = emb / (np.linalg.norm(emb) + 1e-8)
    return emb


@pytest.fixture
def gallery_path(tmp_path):
    return tmp_path / "test_gallery.pkl"


@pytest.fixture
def gallery(gallery_path):
    from backend.reid.gallery import FaceGallery
    gal = FaceGallery(
        gallery_path=gallery_path,
        sim_threshold=0.55,
        max_embeddings_per_id=5,
    )
    yield gal
    if gallery_path.exists():
        gallery_path.unlink()


@pytest.fixture
def state(gallery_path):
    from backend.core.state import DetectionState
    s = DetectionState()
    s.init_gallery(gallery_path)
    yield s
