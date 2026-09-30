"""Unified payment ledger. Kiosk and mobile write the same tables.

A browser success screen is not paid. SUCCEEDED is only written here after
a verified provider callback or a logged-in kiosk/manual confirmation.
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import PaymentIntent, PaymentTransaction, ParkingSession, utcnow

SUCCEEDED = "SUCCEEDED"
CREATED = "CREATED"
PENDING = "PENDING"
FAILED = "FAILED"
EXPIRED = "EXPIRED"
REFUNDED = "REFUNDED"
PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"

PAYMENT_STATUSES = (CREATED, PENDING, SUCCEEDED, FAILED, EXPIRED, REFUNDED, PARTIALLY_REFUNDED)
DEFAULT_EXIT_GRACE_SECONDS = 15 * 60


def transaction_dict(row: PaymentTransaction) -> dict:
    return {
        "id": row.id,
        "intent_id": row.intent_id,
        "session_id": row.session_id,
        "provider_id": row.provider_id,
        "method": row.method,
        "amount": float(row.amount or 0),
        "currency": row.currency,
        "status": row.status,
        "provider_transaction_id": row.provider_transaction_id,
        "idempotency_key": row.idempotency_key,
        "operator_id": row.operator_id,
        "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def paid_total(db: Session, session_id: int) -> float:
    total = db.scalar(
        select(func.coalesce(func.sum(PaymentTransaction.amount), 0)).where(
            PaymentTransaction.session_id == session_id,
            PaymentTransaction.status == SUCCEEDED,
        )
    )
    return float(total or 0)


def apply_session_payment_state(
    db: Session,
    row: ParkingSession,
    *,
    grace_seconds: int | None = None,
) -> ParkingSession:
    paid = paid_total(db, row.id)
    row.amount_paid = paid
    due = float(row.amount_due or 0)
    if paid + 0.0001 >= due and due >= 0:
        row.status = "PAID"
        row.payment_status = SUCCEEDED
        row.paid_at = row.paid_at or utcnow()
        seconds = int(grace_seconds if grace_seconds is not None else DEFAULT_EXIT_GRACE_SECONDS)
        if seconds > 0 and row.payment_exit_grace_until is None:
            row.payment_exit_grace_until = row.paid_at + timedelta(seconds=seconds)
    elif paid > 0 and paid < due:
        row.payment_status = PENDING
    db.flush()
    return row


def record_succeeded_payment(
    db: Session,
    row: ParkingSession,
    *,
    amount: float,
    method: str = "KIOSK_CASH",
    provider_id: str = "kiosk_manual",
    operator_id: int | None = None,
    idempotency_key: str | None = None,
    intent: PaymentIntent | None = None,
    provider_transaction_id: str | None = None,
    extra: dict | None = None,
) -> dict:
    """Write an immutable SUCCEEDED transaction and recompute session paid state.

    Call this only after a kiosk operator confirms cash/local payment, or after
    a verified provider webhook. Do not call from a public browser POST.

    ``intent`` links the ledger row to an existing PENDING intent (external
    providers) instead of minting a synthetic one. ``provider_transaction_id``
    is the provider's own id; the unique constraint on that column makes a
    replayed provider transaction a duplicate even under a different key.
    """
    amount = float(amount or 0)
    if amount < 0:
        raise ValueError("Payment amount cannot be negative")
    key = (idempotency_key or "").strip() or f"session:{row.id}:{method}:{secrets.token_hex(8)}"
    existing = db.scalar(select(PaymentTransaction).where(PaymentTransaction.idempotency_key == key))
    if existing is None and provider_transaction_id:
        existing = db.scalar(
            select(PaymentTransaction).where(PaymentTransaction.provider_transaction_id == provider_transaction_id)
        )
    if existing is not None:
        if intent is not None and intent.status != SUCCEEDED:
            intent.status = SUCCEEDED
        apply_session_payment_state(db, row)
        db.commit()
        db.refresh(row)
        return {"session": row, "transaction": existing, "intent": db.get(PaymentIntent, existing.intent_id), "duplicate": True}

    now = utcnow()
    if intent is None:
        intent = PaymentIntent(
            session_id=row.id,
            provider_id=provider_id,
            method=method,
            amount=amount,
            currency=row.currency or "TZS",
            status=SUCCEEDED,
            idempotency_key=f"intent:{key}",
            operator_id=operator_id,
            extra={"source": "ledger"},
        )
        db.add(intent)
    else:
        intent.status = SUCCEEDED
    db.flush()
    txn = PaymentTransaction(
        intent_id=intent.id,
        session_id=row.id,
        provider_id=provider_id,
        method=method,
        amount=amount,
        currency=row.currency or "TZS",
        status=SUCCEEDED,
        provider_transaction_id=provider_transaction_id or f"{provider_id}:{secrets.token_hex(10)}",
        idempotency_key=key,
        operator_id=operator_id,
        confirmed_at=now,
        extra={"source": "ledger", **(extra or {})},
    )
    db.add(txn)
    db.flush()
    apply_session_payment_state(db, row)
    db.commit()
    db.refresh(row)
    db.refresh(txn)
    return {"session": row, "transaction": txn, "intent": intent, "duplicate": False}


def list_transactions(db: Session, *, limit: int = 100) -> list[PaymentTransaction]:
    return list(
        db.scalars(
            select(PaymentTransaction).order_by(PaymentTransaction.id.desc()).limit(limit)
        ).all()
    )
