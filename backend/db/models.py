from __future__ import annotations
import enum
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text,
    Enum as SAEnum, ForeignKey, Index, JSON,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class SubLabel(str, enum.Enum):
    NO_HELMET = "no_helmet"
    NO_MASK = "no_mask"
    NO_VEST = "no_vest"
    NO_GLASSES = "no_glasses"
    DANGER_ZONE = "danger_zone"
    OK_GESTURE = "ok_gesture"
    RAISED_HAND = "raised_hand"
    PERSON_ENTER = "person_enter"
    PERSON_EXIT = "person_exit"
    GENERAL = "general"


class EventLabel(str, enum.Enum):
    VIOLATION = "violation"
    APPROVED = "approved"
    DANGER_ZONE = "danger_zone"
    MOTION = "motion"
    HEARTBEAT = "heartbeat"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"
    API = "api"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(128), unique=True, nullable=True)
    password_hash = Column(String(256), nullable=False)
    role = Column(SAEnum(UserRole), default=UserRole.VIEWER, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False)
    role = Column(SAEnum(UserRole), default=UserRole.API, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(String(64), primary_key=True)
    name = Column(String(128), unique=True, nullable=False)
    source = Column(String(512), nullable=False)
    enabled = Column(Boolean, default=True)
    detect_enabled = Column(Boolean, default=True)
    width = Column(Integer, default=1280)
    height = Column(Integer, default=720)
    fps = Column(Integer, default=15)
    conf_thresh = Column(Float, default=0.5)
    zones = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    events = relationship("Event", back_populates="camera", cascade="all, delete-orphan")


class Event(Base):
    __tablename__ = "events"

    id = Column(String(36), primary_key=True)
    camera_id = Column(String(64), ForeignKey("cameras.id"), nullable=False, index=True)
    label = Column(SAEnum(EventLabel), nullable=False, index=True)
    sub_label = Column(SAEnum(SubLabel), nullable=True, index=True)
    timestamp = Column(Float, nullable=False, index=True)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=True)
    has_clip = Column(Boolean, default=False)
    has_snapshot = Column(Boolean, default=False)
    zones = Column(JSON, default=list)
    score = Column(Float, nullable=True)
    person_id = Column(Integer, nullable=True, index=True)
    person_name = Column(String(128), nullable=True)
    ppe_helmet = Column(Boolean, default=False)
    ppe_mask = Column(Boolean, default=False)
    ppe_vest = Column(Boolean, default=False)
    ppe_glasses = Column(Boolean, default=False)
    box_x = Column(Integer, nullable=True)
    box_y = Column(Integer, nullable=True)
    box_w = Column(Integer, nullable=True)
    box_h = Column(Integer, nullable=True)

    camera = relationship("Camera", back_populates="events")


Index("ix_events_camera_time", Event.camera_id, Event.timestamp)
Index("ix_events_label_time", Event.label, Event.timestamp)
