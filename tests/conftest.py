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


@pytest.fixture
def in_memory_engine():
    """SQLAlchemy in-memory SQLite engine with all tables created."""
    from sqlalchemy import create_engine
    from backend.db.models import Base
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def auth_db(monkeypatch, in_memory_engine):
    """Patches auth service to use in-memory DB and a fixed JWT secret."""
    from sqlalchemy.orm import sessionmaker
    import backend.auth.service as svc
    Session = sessionmaker(bind=in_memory_engine)
    monkeypatch.setattr(svc, "get_session", lambda: Session())
    monkeypatch.setattr(svc, "JWT_SECRET", "test-secret-for-tests")
    yield in_memory_engine


@pytest.fixture
def auth_client(auth_db):
    """Minimal Flask test client with only auth_bp registered."""
    from flask import Flask
    from backend.auth.routes import auth_bp
    app = Flask(__name__)
    app.register_blueprint(auth_bp)
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture
def minimal_flask_app():
    """Bare Flask app (no blueprints) for middleware tests."""
    from flask import Flask
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app
