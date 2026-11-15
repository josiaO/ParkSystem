"""SQLAlchemy models: audit billing (was app/models/30_audit_and_billing.py)."""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON
from app.db import Base
from app.domain.site import DEFAULT_SITE_ID

from .base import AwareDateTime, utcnow

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    target_type: Mapped[str] = mapped_column(String(80), default="")
    target_id: Mapped[str] = mapped_column(String(80), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)

class Tariff(Base):
    """Car1 tariff snapshot. Portable JSON so PostgreSQL can take over later."""
    __tablename__ = "tariffs"
    __table_args__ = (UniqueConstraint("site_id", "name", name="uq_tariffs_site_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id"), nullable=False, default=DEFAULT_SITE_ID, server_default=str(DEFAULT_SITE_ID), index=True
    )
    name: Mapped[str] = mapped_column(String(80), index=True)
    car_type: Mapped[str] = mapped_column(String(40), default="Car1", index=True)
    currency: Mapped[str] = mapped_column(String(8), default="TZS")
    source: Mapped[str] = mapped_column(String(200), default="Car1")
    rules: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)

class Receipt(Base):
    """Issued parking slip. Printer adapter is simulated until a device is attached."""
    __tablename__ = "receipts"
    __table_args__ = (
        Index(
            "uq_receipts_print_job_id",
            "print_job_id",
            unique=True,
            sqlite_where=text("print_job_id != ''"),
            postgresql_where=text("print_job_id != ''"),
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("parking_sessions.id"), nullable=True, index=True)
    plate: Mapped[str] = mapped_column(String(32), default="", index=True)
    public_token: Mapped[str] = mapped_column(String(64), default="", index=True)
    body_text: Mapped[str] = mapped_column(Text, default="")
    qr_payload: Mapped[str] = mapped_column(Text, default="")
    qr_path: Mapped[str] = mapped_column(String(260), default="")
    printer_adapter: Mapped[str] = mapped_column(String(40), default="simulated")
    status: Mapped[str] = mapped_column(String(20), default="SIMULATED")
    print_job_id: Mapped[str] = mapped_column(String(64), default="", server_default="", index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    printer_error: Mapped[str] = mapped_column(String(240), default="", server_default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)

class PaymentIntent(Base):
    """Request to collect money. Not paid until a verified transaction succeeds."""
    __tablename__ = "payment_intents"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_payment_intent_idempotency"),
        Index("ix_payment_intents_provider_status_id", "provider_id", "status", "id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("parking_sessions.id"), nullable=True, index=True)
    provider_id: Mapped[str] = mapped_column(String(40), default="kiosk_manual")
    method: Mapped[str] = mapped_column(String(40), default="KIOSK_CASH")
    amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    currency: Mapped[str] = mapped_column(String(8), default="TZS")
    status: Mapped[str] = mapped_column(String(20), default="CREATED", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)

class PaymentTransaction(Base):
    """Immutable ledger row. Session paid amount is derived from SUCCEEDED rows."""
    __tablename__ = "payment_transactions"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_payment_txn_idempotency"),
        UniqueConstraint("provider_transaction_id", name="uq_payment_provider_txn"),
        Index("ix_payment_transactions_session_status", "session_id", "status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    intent_id: Mapped[int | None] = mapped_column(ForeignKey("payment_intents.id"), nullable=True, index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("parking_sessions.id"), nullable=True, index=True)
    provider_id: Mapped[str] = mapped_column(String(40), default="kiosk_manual")
    method: Mapped[str] = mapped_column(String(40), default="KIOSK_CASH")
    amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    currency: Mapped[str] = mapped_column(String(8), default="TZS")
    status: Mapped[str] = mapped_column(String(20), default="CREATED", index=True)
    provider_transaction_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)
