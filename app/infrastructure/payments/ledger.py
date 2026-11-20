"""Unified payment ledger. Kiosk and mobile write the same tables.

A browser success screen is not paid. SUCCEEDED is only written here after
a verified provider callback or a logged-in kiosk/manual confirmation.
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
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


def cash_settlement_key(session_id: int, paid_before: float, amount: float) -> str:
    """Idempotency key for one cash settlement.

    A repeated click on the same settlement (same visit, same amount already
    paid, same amount collected) is a duplicate; a later top-up after the
    payment grace ran out has a different paid-before total, so it is
    recorded instead of being silently swallowed.
    """
    return f"session:{int(session_id)}:cash:{float(paid_before):.2f}:{float(amount):.2f}"


def configured_exit_grace_seconds(db: Session) -> int:
    """The site's walk/drive-to-exit grace after payment, in seconds.

    0 is a valid setting (no grace: the exit re-quotes the stay). Only a
    missing or unreadable value falls back to the default.
    """
    try:
        from app.services.simulation import parking_settings

        raw = parking_settings(db).get("payment_exit_grace_seconds")
    except Exception:
        raw = None
    if raw is None or raw == "":
        return DEFAULT_EXIT_GRACE_SECONDS
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_EXIT_GRACE_SECONDS


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
        seconds = int(grace_seconds if grace_seconds is not None else configured_exit_grace_seconds(db))
        if seconds > 0 and row.payment_exit_grace_until is None:
            row.payment_exit_grace_until = row.paid_at + timedelta(seconds=seconds)
    elif paid > 0 and paid < due:
        row.payment_status = PENDING
    db.flush()
    return row


def _aware_utc(value):
    from datetime import timezone

    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def reopen_after_grace(db: Session, row: ParkingSession, *, at=None) -> bool:
    """A paid car still inside after its exit grace owes the rest of its stay.

    Payment freezes the price only for the walk/drive-to-exit grace. Once it
    runs out the stay is quoted again from entry; if that is more than the
    ledger holds, the visit goes back to ACTIVE with the difference due, and
    its paid_at / grace are cleared so the next payment starts a fresh grace.
    Returns True when the visit was reopened. Flushes, never commits.
    """
    from datetime import datetime, timezone

    if (row.status or "").upper() != "PAID" or row.exit_time is not None:
        return False
    if (getattr(row, "parker_kind", None) or "CASUAL").upper() not in {"", "CASUAL"}:
        return False
    grace_until = _aware_utc(row.payment_exit_grace_until)
    if grace_until is None:
        return False
    at = _aware_utc(at) or datetime.now(timezone.utc)
    if at <= grace_until:
        return False
    from app.services.simulation import quote_session

    quote_session(db, row, at=at, persist=False)
    paid = paid_total(db, row.id)
    row.amount_paid = paid
    if float(row.amount_due or 0) <= paid + 0.0001:
        db.flush()
        return False      # the stay has not reached the next tariff step yet
    row.status = "ACTIVE"
    row.payment_status = PENDING
    row.paid_at = None
    row.payment_exit_grace_until = None
    db.flush()
    return True


def reopen_expired_graces(db: Session, *, at=None, limit: int = 200) -> int:
    """Background sweep: reopen every paid visit whose exit grace ran out."""
    from datetime import datetime, timezone

    from app.models import AuditLog

    at = _aware_utc(at) or datetime.now(timezone.utc)
    rows = db.scalars(
        select(ParkingSession)
        .where(
            ParkingSession.status == "PAID",
            ParkingSession.exit_time.is_(None),
            ParkingSession.payment_exit_grace_until.is_not(None),
            ParkingSession.payment_exit_grace_until < at,
        )
        .order_by(ParkingSession.id.asc())
        .limit(int(limit))
    ).all()
    reopened = 0
    for row in rows:
        if reopen_after_grace(db, row, at=at):
            reopened += 1
            db.add(AuditLog(user_id=None, action="payments.grace_expired", target_type="parking_session",
                            target_id=str(row.id),
                            detail=f"{row.plate} still inside after the exit grace; "
                                   f"{float(row.amount_due or 0) - float(row.amount_paid or 0):.2f} {row.currency or ''} more due"))
    db.commit()
    return reopened


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
    try:
        db.flush()
    except IntegrityError:
        # Two webhook/operator retries can pass the read-before-write check at
        # the same time. The unique ledger keys are the final authority; turn
        # that race into the same idempotent result instead of a 500 response.
        db.rollback()
        existing = db.scalar(select(PaymentTransaction).where(PaymentTransaction.idempotency_key == key))
        if existing is None and provider_transaction_id:
            existing = db.scalar(
                select(PaymentTransaction).where(
                    PaymentTransaction.provider_transaction_id == provider_transaction_id
                )
            )
        if existing is None:
            raise
        fresh_row = db.get(ParkingSession, row.id)
        if fresh_row is None:
            raise RuntimeError("Payment session disappeared while resolving a duplicate transaction")
        fresh_intent = db.get(PaymentIntent, existing.intent_id) if existing.intent_id else None
        if fresh_intent is not None and fresh_intent.status != SUCCEEDED:
            fresh_intent.status = SUCCEEDED
        apply_session_payment_state(db, fresh_row)
        db.commit()
        db.refresh(fresh_row)
        return {
            "session": fresh_row,
            "transaction": existing,
            "intent": fresh_intent,
            "duplicate": True,
        }
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
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(PaymentTransaction).where(PaymentTransaction.idempotency_key == key))
        if existing is None and provider_transaction_id:
            existing = db.scalar(
                select(PaymentTransaction).where(
                    PaymentTransaction.provider_transaction_id == provider_transaction_id
                )
            )
        if existing is None:
            raise
        fresh_row = db.get(ParkingSession, row.id)
        if fresh_row is None:
            raise RuntimeError("Payment session disappeared while resolving a duplicate transaction")
        fresh_intent = db.get(PaymentIntent, existing.intent_id) if existing.intent_id else None
        if fresh_intent is not None and fresh_intent.status != SUCCEEDED:
            fresh_intent.status = SUCCEEDED
        apply_session_payment_state(db, fresh_row)
        db.commit()
        db.refresh(fresh_row)
        return {
            "session": fresh_row,
            "transaction": existing,
            "intent": fresh_intent,
            "duplicate": True,
        }
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
