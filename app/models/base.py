"""SQLAlchemy models: base (was app/models/00_context.py, 00_base.py)."""

from __future__ import annotations


from datetime import datetime, timezone

from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text

from sqlalchemy.orm import Mapped, mapped_column, relationship

from sqlalchemy.types import JSON, TypeDecorator

from app.db import Base

from app.domain.site import DEFAULT_SITE_ID


def utcnow():
    return datetime.now(timezone.utc)

def as_utc(dt: datetime | None) -> datetime | None:
    """SQLite often returns naive datetimes; compare only in UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

class AwareDateTime(TypeDecorator):
    """Always return UTC-aware datetimes from SQLite."""

    impl = DateTime
    cache_ok = True

    def __init__(self) -> None:
        super().__init__(timezone=True)

    def process_bind_param(self, value, dialect):
        return as_utc(value) if value is not None else None

    def process_result_value(self, value, dialect):
        return as_utc(value)

class UserStatus(str, Enum):
    ACTIVE = "ACTIVE"
    LOCKED = "LOCKED"
    DISABLED = "DISABLED"

class CameraStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    DISCOVERED = "DISCOVERED"
    SDK_CONNECTING = "SDK_CONNECTING"
    SDK_CONNECTED = "SDK_CONNECTED"
    SDK_FAILED = "SDK_FAILED"
    VIDEO_CONNECTED = "VIDEO_CONNECTED"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"

class GateMode(str, Enum):
    COMMISSIONING = "COMMISSIONING"
    SHADOW = "SHADOW"
    PRODUCTION = "PRODUCTION"
    MAINTENANCE = "MAINTENANCE"
