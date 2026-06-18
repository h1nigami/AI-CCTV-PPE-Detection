"""Tests for backend/db/models.py and backend/db/engine.py"""
from __future__ import annotations
import pytest
from datetime import datetime
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def session(in_memory_engine):
    Session = sessionmaker(bind=in_memory_engine)
    s = Session()
    yield s
    s.close()


# ── Model: User ───────────────────────────────────────────────────────────────

class TestUserModel:
    def test_create_and_query_user(self, session):
        from backend.db.models import User, UserRole
        from werkzeug.security import generate_password_hash

        user = User(
            username="alice",
            email="alice@example.com",
            password_hash=generate_password_hash("secret"),
            role=UserRole.VIEWER,
            is_active=True,
        )
        session.add(user)
        session.commit()

        fetched = session.query(User).filter_by(username="alice").first()
        assert fetched is not None
        assert fetched.email == "alice@example.com"
        assert fetched.role == UserRole.VIEWER
        assert fetched.is_active is True

    def test_user_role_enum_values(self):
        from backend.db.models import UserRole
        assert UserRole.ADMIN.value == "admin"
        assert UserRole.OPERATOR.value == "operator"
        assert UserRole.VIEWER.value == "viewer"
        assert UserRole.API.value == "api"

    def test_user_unique_username_constraint(self, session):
        from backend.db.models import User, UserRole
        from werkzeug.security import generate_password_hash

        session.add(User(username="dupe", password_hash=generate_password_hash("x"),
                         role=UserRole.VIEWER))
        session.commit()
        session.add(User(username="dupe", password_hash=generate_password_hash("y"),
                         role=UserRole.VIEWER))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_user_created_at_auto_set(self, session):
        from backend.db.models import User, UserRole
        user = User(username="bob", password_hash="x", role=UserRole.VIEWER)
        session.add(user)
        session.commit()
        assert user.created_at is not None

    def test_user_last_login_nullable(self, session):
        from backend.db.models import User, UserRole
        user = User(username="carol", password_hash="x", role=UserRole.VIEWER)
        session.add(user)
        session.commit()
        assert user.last_login is None


# ── Model: ApiKey ─────────────────────────────────────────────────────────────

class TestApiKeyModel:
    def test_api_key_unique_key_constraint(self, session):
        from backend.db.models import ApiKey, UserRole

        session.add(ApiKey(key="ppe_abc", name="Key1", role=UserRole.API))
        session.commit()
        session.add(ApiKey(key="ppe_abc", name="Key2", role=UserRole.API))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_api_key_expires_at_nullable(self, session):
        from backend.db.models import ApiKey, UserRole
        key = ApiKey(key="ppe_xyz", name="NoExpiry", role=UserRole.API)
        session.add(key)
        session.commit()
        assert key.expires_at is None


# ── Model: Event / Camera (cascade) ──────────────────────────────────────────

class TestEventModel:
    def test_create_event(self, session):
        import uuid
        from backend.db.models import Camera, Event, EventLabel

        cam = Camera(id="cam01", name="Main", source="rtsp://test")
        session.add(cam)
        session.commit()

        event = Event(
            id=str(uuid.uuid4()),
            camera_id="cam01",
            label=EventLabel.VIOLATION,
            timestamp=1000.0,
            start_time=990.0,
        )
        session.add(event)
        session.commit()

        fetched = session.query(Event).filter_by(camera_id="cam01").first()
        assert fetched is not None
        assert fetched.label == EventLabel.VIOLATION

    def test_camera_delete_cascades_to_events(self, session):
        import uuid
        from backend.db.models import Camera, Event, EventLabel

        cam = Camera(id="cam02", name="Secondary", source="rtsp://test2")
        session.add(cam)
        session.commit()

        event = Event(
            id=str(uuid.uuid4()),
            camera_id="cam02",
            label=EventLabel.APPROVED,
            timestamp=2000.0,
            start_time=1990.0,
        )
        session.add(event)
        session.commit()
        event_id = event.id

        session.delete(cam)
        session.commit()

        assert session.query(Event).filter_by(id=event_id).first() is None


# ── Enum coverage ─────────────────────────────────────────────────────────────

class TestEnumCoverage:
    def test_event_label_enum_values(self):
        from backend.db.models import EventLabel
        assert EventLabel.VIOLATION.value == "violation"
        assert EventLabel.APPROVED.value == "approved"
        assert EventLabel.DANGER_ZONE.value == "danger_zone"

    def test_sub_label_enum_has_ten_values(self):
        from backend.db.models import SubLabel
        assert len(SubLabel) == 10

    def test_sub_label_critical_values(self):
        from backend.db.models import SubLabel
        assert SubLabel.NO_HELMET.value == "no_helmet"
        assert SubLabel.DANGER_ZONE.value == "danger_zone"
        assert SubLabel.OK_GESTURE.value == "ok_gesture"


# ── Indexes ───────────────────────────────────────────────────────────────────

class TestIndexes:
    def test_event_indexes_defined(self, in_memory_engine):
        insp = inspect(in_memory_engine)
        indexes = {idx["name"] for idx in insp.get_indexes("events")}
        assert "ix_events_camera_time" in indexes
        assert "ix_events_label_time" in indexes


# ── engine.py functions ───────────────────────────────────────────────────────

class TestDbEngine:
    def test_init_db_creates_all_tables(self, monkeypatch):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        test_engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}
        )
        import backend.db.engine as db_engine
        monkeypatch.setattr(db_engine, "engine", test_engine)

        from backend.db.engine import init_db
        init_db()

        insp = inspect(test_engine)
        tables = insp.get_table_names()
        assert "users" in tables
        assert "events" in tables
        assert "cameras" in tables
        assert "api_keys" in tables

    def test_get_session_returns_usable_session(self):
        from backend.db.engine import get_session
        session = get_session()
        assert session is not None
        session.close()
