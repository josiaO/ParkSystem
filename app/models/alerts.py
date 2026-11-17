"""Manual barrier openings and the alerts they raise."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base
from app.domain.site import DEFAULT_SITE_ID

from .base import AwareDateTime, utcnow

# Where a manual opening came from.
MANUAL_SOURCE_GATE = "OPERATOR_GATE"            # POST /gates/{id}/open
MANUAL_SOURCE_CAMERA = "OPERATOR_CAMERA"        # POST /cameras/{id}/barrier/open
MANUAL_SOURCE_ADMIT = "ADMIT_WITHOUT_RECEIPT"   # POST /sessions/{id}/admit-without-receipt
MANUAL_SOURCE_UNCOMMANDED = "UNCOMMANDED"       # boom-up input with no Zirp command


class ManualOpenEvent(Base):
    """One barrier opening the parking engine did not authorize by itself.

    Captures, at the moment of opening, which car was in the lane (latest
    plate read and photo), its open visit, and what it owed. The amounts are a
    snapshot for accountability; they never change the session.
    """

    __tablename__ = "manual_open_events"
    __table_args__ = (
        Index("ix_manual_open_events_ack_created", "acknowledged_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id"), nullable=False, default=DEFAULT_SITE_ID, server_default=str(DEFAULT_SITE_ID), index=True
    )
    source: Mapped[str] = mapped_column(String(40), index=True)
    gate_id: Mapped[int | None] = mapped_column(ForeignKey("gates.id"), nullable=True, index=True)
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.id"), nullable=True, index=True)
    lane_label: Mapped[str] = mapped_column(String(120), default="")
    side: Mapped[str] = mapped_column(String(10), default="")
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    operator_name: Mapped[str] = mapped_column(String(120), default="")
    reason: Mapped[str] = mapped_column(String(240), default="")

    plate: Mapped[str] = mapped_column(String(32), default="", index=True)
    plate_confidence: Mapped[float] = mapped_column(Numeric(6, 3), default=0)
    plate_seconds_before: Mapped[float | None] = mapped_column(Numeric(10, 1), nullable=True)
    capture_id: Mapped[int | None] = mapped_column(ForeignKey("vehicle_captures.id"), nullable=True)
    photo_ref: Mapped[str] = mapped_column(String(300), default="")

    session_id: Mapped[int | None] = mapped_column(ForeignKey("parking_sessions.id"), nullable=True, index=True)
    parker_kind: Mapped[str] = mapped_column(String(40), default="")
    entry_time: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount_due: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    amount_paid: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    amount_owed: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    currency: Mapped[str] = mapped_column(String(8), default="")

    command_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    command_message: Mapped[str] = mapped_column(Text, default="")
    extra: Mapped[dict] = mapped_column(JSON, default=dict)

    alert_status: Mapped[str] = mapped_column(String(20), default="NONE", index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    acknowledged_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    acknowledge_note: Mapped[str] = mapped_column(String(240), default="")
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow, index=True)


class AlertDelivery(Base):
    """Durable outbox row: one alert to one recipient on one channel."""

    __tablename__ = "alert_deliveries"
    __table_args__ = (
        UniqueConstraint("event_id", "channel", "recipient", name="uq_alert_delivery_target"),
        Index("ix_alert_deliveries_due", "status", "next_attempt_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("manual_open_events.id"), index=True)
    channel: Mapped[str] = mapped_column(String(20))
    recipient: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    sent_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)
