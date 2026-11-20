"""SQLAlchemy models: linked-vehicle authorization groups, visitor passes, exit confirmations.

See app/domain/vehicle_groups.py for the rules. The one-vehicle-at-a-time
guarantee is a database invariant: ``uq_vehicle_group_occupancy_live_slot``
lets at most one *unreleased* occupancy own each (group, slot). A PRIVATE
group has one slot, so two linked cars can never both hold it, whatever the
number of lanes, processes or servers racing.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, false, text, true
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base
from app.domain.site import DEFAULT_SITE_ID

from .base import AwareDateTime, utcnow


class VehicleGroup(Base):
    """Vehicles sharing one parking entitlement (private owner) or a company fleet."""

    __tablename__ = "vehicle_groups"
    __table_args__ = (
        UniqueConstraint("site_id", "name", name="uq_vehicle_groups_site_name"),
        CheckConstraint("kind <> 'PRIVATE' OR max_active_sessions = 1", name="ck_vehicle_groups_private_single"),
        CheckConstraint("max_active_sessions >= 0", name="ck_vehicle_groups_limit_nonnegative"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id"), nullable=False, default=DEFAULT_SITE_ID, server_default=str(DEFAULT_SITE_ID), index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="PRIVATE", server_default="PRIVATE", index=True)
    company_name: Mapped[str] = mapped_column(String(160), default="", server_default="")
    owner_name: Mapped[str] = mapped_column(String(160), default="", server_default="")
    contact_phone: Mapped[str] = mapped_column(String(40), default="", server_default="")
    # PRIVATE is always 1. FLEET: 0 = no limit, N = at most N members inside.
    max_active_sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    exit_release: Mapped[str] = mapped_column(String(24), nullable=False, default="EXIT_LANE", server_default="EXIT_LANE")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)


class VehicleGroupOccupancy(Base):
    """One group slot held by one visit, from entry until confirmed exit."""

    __tablename__ = "vehicle_group_occupancies"
    __table_args__ = (
        Index(
            "uq_vehicle_group_occupancy_live_slot",
            "group_id",
            "slot",
            unique=True,
            sqlite_where=text("released_at IS NULL"),
            postgresql_where=text("released_at IS NULL"),
        ),
        Index(
            "uq_vehicle_group_occupancy_session",
            "session_id",
            unique=True,
            sqlite_where=text("session_id IS NOT NULL"),
            postgresql_where=text("session_id IS NOT NULL"),
        ),
        Index("ix_vehicle_group_occupancies_group_state", "group_id", "state"),
        CheckConstraint("slot >= 1", name="ck_vehicle_group_occupancy_slot"),
        CheckConstraint("(state = 'RELEASED') = (released_at IS NOT NULL)", name="ck_vehicle_group_occupancy_released_state"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(Integer, nullable=False, default=DEFAULT_SITE_ID, server_default=str(DEFAULT_SITE_ID), index=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("vehicle_groups.id"), nullable=False, index=True)
    slot: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE", server_default="ACTIVE", index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("parking_sessions.id"), nullable=True)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("registered_vehicles.id", ondelete="SET NULL"), nullable=True, index=True)
    plate: Mapped[str] = mapped_column(String(32), default="", server_default="", index=True)
    claimed_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)
    exit_reported_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    release_evidence: Mapped[str] = mapped_column(String(40), default="", server_default="")
    release_reason: Mapped[str] = mapped_column(String(240), default="", server_default="")
    released_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)


class VisitorPass(Base):
    """Temporary authorization for a plate that is not a registered vehicle."""

    __tablename__ = "visitor_passes"
    __table_args__ = (
        Index("ix_visitor_passes_site_plate", "site_id", "plate"),
        CheckConstraint("max_entries = 0 OR entries_used <= max_entries", name="ck_visitor_passes_entries"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id"), nullable=False, default=DEFAULT_SITE_ID, server_default=str(DEFAULT_SITE_ID), index=True
    )
    plate: Mapped[str] = mapped_column(String(32), nullable=False)
    visitor_name: Mapped[str] = mapped_column(String(160), default="", server_default="")
    host_group_id: Mapped[int | None] = mapped_column(ForeignKey("vehicle_groups.id", ondelete="SET NULL"), nullable=True, index=True)
    host_name: Mapped[str] = mapped_column(String(160), default="", server_default="")
    purpose: Mapped[str] = mapped_column(String(240), default="", server_default="")
    valid_from: Mapped[datetime] = mapped_column(AwareDateTime(), nullable=False, default=utcnow)
    valid_until: Mapped[datetime] = mapped_column(AwareDateTime(), nullable=False)
    max_entries: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")  # 0 = any number
    entries_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    revoked_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)


class ExitConfirmation(Base):
    """Append-only audit of every exit confirmation, uncertainty and reconciliation."""

    __tablename__ = "exit_confirmations"
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(Integer, nullable=False, default=DEFAULT_SITE_ID, server_default=str(DEFAULT_SITE_ID), index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("parking_sessions.id"), nullable=True, index=True)
    occupancy_id: Mapped[int | None] = mapped_column(ForeignKey("vehicle_group_occupancies.id"), nullable=True, index=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("vehicle_groups.id", ondelete="SET NULL"), nullable=True, index=True)
    plate: Mapped[str] = mapped_column(String(32), default="", server_default="", index=True)
    # MANUAL_EXIT_CONFIRMED | MANUAL_EXIT_UNCERTAIN | SUPERVISOR_RELEASED |
    # SUPERVISOR_KEPT_INSIDE | SUPERVISOR_KEPT_LOCKED | AUTO_RELEASED | EXIT_UNCONFIRMED
    action: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    evidence: Mapped[str] = mapped_column(String(40), default="", server_default="")
    identified_by: Mapped[str] = mapped_column(String(20), default="", server_default="")  # SESSION | PLATE | QR | SYSTEM
    previous_state: Mapped[str] = mapped_column(String(20), default="", server_default="")
    new_state: Mapped[str] = mapped_column(String(20), default="", server_default="")
    session_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    operator_name: Mapped[str] = mapped_column(String(120), default="", server_default="")
    reason: Mapped[str] = mapped_column(String(240), default="", server_default="")
    entry_image_ref: Mapped[str] = mapped_column(String(300), default="", server_default="")
    amount_owed: Mapped[float] = mapped_column(Numeric(14, 2), default=0, server_default="0")
    currency: Mapped[str] = mapped_column(String(8), default="", server_default="")
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow, index=True)
