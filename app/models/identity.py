"""SQLAlchemy models: identity (was app/models/10_identity.py)."""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base

from .base import AwareDateTime, UserStatus, utcnow

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160), default="")
    password_hash: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(30), default=UserStatus.ACTIVE.value)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)
    roles: Mapped[list["UserRole"]] = relationship(back_populates="user", cascade="all, delete-orphan")

class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    permissions_csv: Mapped[str] = mapped_column(Text, default="")
    system_role: Mapped[bool] = mapped_column(Boolean, default=False)
    users: Mapped[list["UserRole"]] = relationship(back_populates="role")

    def permissions(self) -> set[str]:
        return {p.strip() for p in self.permissions_csv.split(",") if p.strip()}

class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    user: Mapped[User] = relationship(back_populates="roles")
    role: Mapped[Role] = relationship(back_populates="users")

class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(AwareDateTime())
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)


class KioskDevice(Base):
    """A revocable credential for one kiosk PC (modelled on ``Node``).

    The device signs in with its credential instead of a person's password,
    so the kiosk does not log out mid-shift. It acts through a dedicated
    Kiosk Operator service account that can never sign in by password.
    """
    __tablename__ = "kiosk_devices"
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"), index=True)
    name: Mapped[str] = mapped_column(String(160), default="")
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", index=True)
    credential_hash: Mapped[str] = mapped_column(String(300), default="")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
