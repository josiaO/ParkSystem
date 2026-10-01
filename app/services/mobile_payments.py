"""External mobile-money payment orchestration (Flutterwave, ClickPesa).

Flow (never trust the browser or the webhook body for money):

  public POST /api/public/payment-intents
    -> PaymentIntent(status=PENDING, idempotency_key=tx_ref) + provider USSD push
  provider webhook (authenticated) or reconciliation job
    -> provider.query_status(...)  # server-side truth
    -> amount/currency/reference check with Decimal
    -> ledger.record_succeeded_payment(intent=..., provider_transaction_id=...)
       exactly once (idempotency_key + unique provider_transaction_id)

Barrier opening is never triggered from here; the parking core reads the
session's paid state on the next exit decision.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import time
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.infrastructure.payments import (
    EXTERNAL_PROVIDERS,
    PROVIDERS,
    is_external_provider,
    payment_provider_for,
    record_succeeded_payment,
    transaction_dict,
)
from app.infrastructure.payments.common import mask_msisdn, redact, to_decimal
from app.models import ParkingSession, PaymentIntent
from app.services.audit import write_audit

CREATED = "CREATED"
PENDING = "PENDING"
SUCCEEDED = "SUCCEEDED"
FAILED = "FAILED"
BLOCKED = "BLOCKED"
EXPIRED = "EXPIRED"
MISMATCH = "MISMATCH"
OPEN_STATES = (CREATED, PENDING)
METHOD = "MOBILE_MONEY"
REUSE_PENDING_SECONDS = 90.0
MAX_WEBHOOK_EVENTS = 10

_stats: dict[str, Any] = {
    "intents_created": 0,
    "webhooks_received": 0,
    "webhooks_rejected": 0,
    "webhooks_unknown_reference": 0,
    "credited": 0,
    "duplicates": 0,
    "mismatches": 0,
    "failed": 0,
    "expired": 0,
    "reconcile_runs": 0,
    "reconcile_last_at": None,
    "reconcile_last_checked": 0,
    "last_error": "",
}


def stats() -> dict[str, Any]:
    return dict(_stats)


def reset_stats() -> None:
    for key in list(_stats):
        _stats[key] = None if key == "reconcile_last_at" else ("" if key == "last_error" else 0)


def active_mobile_provider_id() -> str:
    pid = (settings.payments_mobile_provider or "simulated").strip().lower()
    return pid if pid in PROVIDERS else "simulated"


def external_provider_ids() -> tuple[str, ...]:
    return EXTERNAL_PROVIDERS


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _merge_extra(intent: PaymentIntent, **changes: Any) -> None:
    # JSON columns are not mutation-tracked; reassign so SQLAlchemy sees the change.
    intent.extra = {**(intent.extra or {}), **changes}


def intent_dict(intent: PaymentIntent) -> dict[str, Any]:
    """Public-safe view: masked phone, no provider secrets/raw bodies."""
    extra = intent.extra or {}
    return {
        "id": intent.id,
        "session_id": intent.session_id,
        "provider_id": intent.provider_id,
        "method": intent.method,
        "amount": float(intent.amount or 0),
        "currency": intent.currency,
        "status": intent.status,
        "reference": intent.idempotency_key,
        "phone": extra.get("phone_masked"),
        "network": extra.get("network"),
        "provider_status": extra.get("provider_status"),
        "message": extra.get("message") or extra.get("error") or "",
        "created_at": intent.created_at.isoformat() if intent.created_at else None,
        "last_checked_at": extra.get("last_checked_at"),
        "verification_error": extra.get("verification_error"),
    }


def intent_by_reference(db: Session, reference: str, *, provider_id: str | None = None) -> PaymentIntent | None:
    ref = (reference or "").strip()
    if not ref:
        return None
    stmt = select(PaymentIntent).where(PaymentIntent.idempotency_key == ref)
    if provider_id:
        stmt = stmt.where(PaymentIntent.provider_id == provider_id)
    return db.scalar(stmt)


def latest_intent_for_session(db: Session, session_id: int) -> PaymentIntent | None:
    return db.scalar(
        select(PaymentIntent)
        .where(PaymentIntent.session_id == session_id, PaymentIntent.provider_id.in_(EXTERNAL_PROVIDERS))
        .order_by(PaymentIntent.id.desc())
        .limit(1)
    )


def _remaining(db: Session, row: ParkingSession) -> Decimal:
    from app.services.simulation import quote_session

    if row.status not in ("CLOSED", "PAID"):
        quote_session(db, row)
        db.flush()
    due = to_decimal(row.amount_due or 0)
    paid = to_decimal(row.amount_paid or 0)
    remaining = due - paid
    return remaining if remaining > 0 else Decimal("0")


async def start_mobile_payment(
    db: Session,
    row: ParkingSession,
    *,
    phone: str,
    provider_id: str | None = None,
    network: str | None = None,
    amount: Any = None,
) -> dict[str, Any]:
    """Create a PENDING intent and ask the provider to push a USSD prompt.

    Returns ``ok=False`` with a reason when the provider is unavailable; local
    parking, cash and kiosk paths are unaffected.
    """
    pid = (provider_id or active_mobile_provider_id()).strip().lower()
    if not is_external_provider(pid):
        raise ValueError(f"'{pid}' is not an external mobile-money provider")
    provider = payment_provider_for(pid)
    remaining = _remaining(db, row)
    currency = (row.currency or "TZS").upper()
    if remaining <= 0:
        db.commit()
        return {"ok": True, "already_paid": True, "intent": None}
    # Public callers never own the amount. Recompute the exact outstanding
    # balance at initiation time so request tampering cannot underpay a session.
    # Keep the parameter only for backward API compatibility.
    pay_amount = remaining
    if pay_amount <= 0:
        raise ValueError("Nothing to pay")

    # Idempotent create: a fresh pending push for the same session/provider is
    # returned instead of re-prompting the customer's phone.
    latest = latest_intent_for_session(db, row.id)
    if latest is not None and latest.provider_id == pid and latest.status == PENDING and latest.created_at:
        age = (_now() - _aware(latest.created_at)).total_seconds()
        if age < REUSE_PENDING_SECONDS and to_decimal(latest.amount) == pay_amount:
            return {"ok": True, "reused": True, "intent": intent_dict(latest)}

    request = await provider.create_intent({
        "session_id": row.id,
        "amount": pay_amount,
        "currency": currency,
        "phone": phone,
        "network": network or "",
        "token": row.public_token,
    })
    intent = PaymentIntent(
        session_id=row.id,
        provider_id=pid,
        method=METHOD,
        amount=float(pay_amount),
        currency=currency,
        status=CREATED,
        idempotency_key=str(request["tx_ref"]),
        extra={
            "tx_ref": request["tx_ref"],
            "phone_masked": mask_msisdn(request.get("phone") or phone),
            "network": request.get("network") or "",
            "token": row.public_token,
            "amount_expected": str(pay_amount),
            "webhooks": [],
            "checks": 0,
        },
    )
    db.add(intent)
    db.commit()
    db.refresh(intent)
    _stats["intents_created"] += 1

    result = await provider.initiate_collection(request)
    status = str(result.get("status") or FAILED).upper()
    if status not in (PENDING, FAILED, BLOCKED):
        status = PENDING
    intent.status = status
    _merge_extra(
        intent,
        provider_transaction_id=result.get("provider_transaction_id"),
        provider_ref=result.get("provider_ref"),
        provider_status=result.get("provider_status"),
        message=result.get("message") or "",
        error=result.get("error") or "",
        initiated_at=_now().isoformat(),
    )
    if status != PENDING:
        _stats["failed"] += 1
    db.commit()
    db.refresh(intent)
    return {
        "ok": status == PENDING,
        "intent": intent_dict(intent),
        "error": result.get("error") or "",
    }


def _verification_ref(intent: PaymentIntent) -> str:
    extra = intent.extra or {}
    if intent.provider_id == "flutterwave" and extra.get("provider_transaction_id"):
        return str(extra["provider_transaction_id"])
    return str(extra.get("tx_ref") or intent.idempotency_key)


def _check_match(intent: PaymentIntent, result: dict[str, Any]) -> str:
    """Return '' when the provider's verified record matches the intent, else a reason."""
    expected_ref = str((intent.extra or {}).get("tx_ref") or intent.idempotency_key)
    got_ref = str(result.get("tx_ref") or "")
    if not got_ref or got_ref != expected_ref:
        return f"reference mismatch (expected {expected_ref}, got {got_ref or 'none'})"
    currency = (result.get("currency") or "").upper()
    if currency != (intent.currency or "TZS").upper():
        return f"currency mismatch (expected {intent.currency}, got {currency or 'none'})"
    try:
        got_amount = to_decimal(result.get("amount"))
    except ValueError:
        return "provider did not report an amount"
    expected = to_decimal((intent.extra or {}).get("amount_expected") or intent.amount)
    if got_amount < expected:
        return f"amount below expected ({got_amount} < {expected})"
    return ""


async def settle_intent(db: Session, intent: PaymentIntent) -> dict[str, Any]:
    """Ask the provider for the truth and credit the ledger at most once."""
    if intent.status == SUCCEEDED:
        return {"status": SUCCEEDED, "credited": False, "duplicate": True}
    if intent.status in (BLOCKED, EXPIRED, MISMATCH, FAILED):
        return {"status": intent.status, "credited": False, "duplicate": False}
    provider = payment_provider_for(intent.provider_id)
    result = await provider.query_status(_verification_ref(intent))
    status = str(result.get("status") or "UNKNOWN").upper()
    now_iso = _now().isoformat()
    checks = int((intent.extra or {}).get("checks") or 0) + 1
    _merge_extra(intent, last_checked_at=now_iso, checks=checks,
                 provider_status=result.get("provider_status") or (intent.extra or {}).get("provider_status"))

    if status == SUCCEEDED:
        reason = _check_match(intent, result)
        if reason:
            intent.status = MISMATCH
            _merge_extra(intent, verification_error=reason, verification=redact(result.get("raw") or {}))
            _stats["mismatches"] += 1
            write_audit(db, None, "payments.mismatch", "payment_intent", str(intent.id),
                        f"{intent.provider_id} {intent.idempotency_key}: {reason}")
            db.commit()
            return {"status": MISMATCH, "credited": False, "duplicate": False, "error": reason}
        row = db.get(ParkingSession, intent.session_id) if intent.session_id else None
        if row is None:
            intent.status = MISMATCH
            _merge_extra(intent, verification_error="session not found")
            db.commit()
            return {"status": MISMATCH, "credited": False, "duplicate": False, "error": "session not found"}
        provider_txn = result.get("provider_transaction_id") or result.get("provider_ref") or intent.idempotency_key
        recorded = record_succeeded_payment(
            db, row,
            amount=float(to_decimal(result.get("amount"))),
            method=METHOD,
            provider_id=intent.provider_id,
            idempotency_key=f"mobile:{intent.idempotency_key}",
            intent=intent,
            provider_transaction_id=f"{intent.provider_id}:{provider_txn}",
            extra={"tx_ref": intent.idempotency_key, "provider_ref": result.get("provider_ref"),
                   "provider_status": result.get("provider_status")},
        )
        duplicate = bool(recorded.get("duplicate"))
        _merge_extra(intent, credited_at=now_iso, verification=redact(result.get("raw") or {}))
        if duplicate:
            _stats["duplicates"] += 1
        else:
            _stats["credited"] += 1
            write_audit(db, None, "payments.webhook", "parking_session", str(row.id),
                        f"{intent.provider_id} {intent.idempotency_key} {result.get('amount')} {intent.currency}")
        db.commit()
        return {
            "status": SUCCEEDED,
            "credited": not duplicate,
            "duplicate": duplicate,
            "transaction": transaction_dict(recorded["transaction"]),
        }

    if status == FAILED:
        intent.status = FAILED
        _merge_extra(intent, error=result.get("error") or result.get("provider_status") or "provider reported failure")
        _stats["failed"] += 1
        db.commit()
        return {"status": FAILED, "credited": False, "duplicate": False}

    # PENDING / UNKNOWN: keep waiting, but not forever.
    created = _aware(intent.created_at) or _now()
    if _now() - created > timedelta(minutes=max(1, int(settings.payments_intent_expiry_minutes))):
        intent.status = EXPIRED
        _merge_extra(intent, error="no confirmation before expiry")
        _stats["expired"] += 1
        db.commit()
        return {"status": EXPIRED, "credited": False, "duplicate": False}
    if result.get("error"):
        _merge_extra(intent, message=str(result.get("error"))[:200])
        _stats["last_error"] = str(result.get("error"))[:200]
    db.commit()
    return {"status": intent.status, "credited": False, "duplicate": False, "provider": status}


async def handle_webhook(db: Session, provider_id: str, *, raw_body: bytes, headers: dict[str, str]) -> tuple[int, dict]:
    """Authenticate, record, then verify server-side. Returns (http_status, body)."""
    pid = (provider_id or "").strip().lower()
    if not is_external_provider(pid):
        return 404, {"ok": False, "error": "unknown provider"}
    provider = payment_provider_for(pid)
    _stats["webhooks_received"] += 1
    verified = await provider.verify_callback({"raw_body": raw_body, "headers": dict(headers)})
    if not verified.get("verified"):
        _stats["webhooks_rejected"] += 1
        return 401, {"ok": False, "error": verified.get("error") or "unverified webhook"}
    intent = intent_by_reference(db, str(verified.get("tx_ref") or ""), provider_id=pid)
    if intent is None:
        _stats["webhooks_unknown_reference"] += 1
        # Acknowledge so the provider stops retrying; nothing is credited.
        return 202, {"ok": True, "ignored": True, "reason": "unknown reference"}
    events = list((intent.extra or {}).get("webhooks") or [])
    events.append({
        "at": _now().isoformat(),
        "event": verified.get("event"),
        "provider_status": verified.get("provider_status"),
        "provider_transaction_id": verified.get("provider_transaction_id"),
    })
    _merge_extra(intent, webhooks=events[-MAX_WEBHOOK_EVENTS:])
    if verified.get("provider_transaction_id") and not (intent.extra or {}).get("provider_transaction_id"):
        _merge_extra(intent, provider_transaction_id=verified["provider_transaction_id"])
    db.commit()
    outcome = await settle_intent(db, intent)
    return 200, {
        "ok": True,
        "status": outcome.get("status"),
        "credited": bool(outcome.get("credited")),
        "duplicate": bool(outcome.get("duplicate")),
        **({"error": outcome["error"]} if outcome.get("error") else {}),
    }


def pending_intents(db: Session, *, min_age_seconds: float = 15.0, limit: int = 25) -> list[PaymentIntent]:
    cutoff = _now() - timedelta(seconds=max(0.0, float(min_age_seconds)))
    rows = db.scalars(
        select(PaymentIntent)
        .where(PaymentIntent.provider_id.in_(EXTERNAL_PROVIDERS), PaymentIntent.status.in_(OPEN_STATES))
        .order_by(PaymentIntent.id.asc())
        .limit(int(limit) * 2)
    ).all()
    return [r for r in rows if (_aware(r.created_at) or cutoff) <= cutoff][: int(limit)]


async def reconcile_pending(
    db_factory: Callable[[], Session] | None = None, *, db: Session | None = None, limit: int = 25
) -> dict[str, Any]:
    """Convert PENDING intents whose webhook never arrived. Safe to run repeatedly."""
    started = time.monotonic()
    summary = {"checked": 0, "credited": 0, "failed": 0, "expired": 0, "mismatch": 0}
    owns_db = db is None
    if db is None:
        if db_factory is None:
            raise ValueError("reconcile_pending needs a db or a db_factory")
        db = db_factory()
    try:
        for intent in pending_intents(db, limit=limit):
            outcome = await settle_intent(db, intent)
            summary["checked"] += 1
            status = outcome.get("status")
            if outcome.get("credited"):
                summary["credited"] += 1
            elif status == FAILED:
                summary["failed"] += 1
            elif status == EXPIRED:
                summary["expired"] += 1
            elif status == MISMATCH:
                summary["mismatch"] += 1
    finally:
        if owns_db:
            db.close()
    _stats["reconcile_runs"] += 1
    _stats["reconcile_last_at"] = _now().isoformat()
    _stats["reconcile_last_checked"] = summary["checked"]
    summary["elapsed_ms"] = round((time.monotonic() - started) * 1000, 1)
    return summary


def payments_health(db: Session | None = None) -> dict[str, Any]:
    providers = {}
    for pid in EXTERNAL_PROVIDERS:
        provider = payment_provider_for(pid)
        health = getattr(provider, "health", None)
        providers[pid] = health() if callable(health) else {"provider_id": pid}
    body: dict[str, Any] = {
        "active_mobile_provider": active_mobile_provider_id(),
        "live_confirmation_required": bool(settings.payments_live_provider_confirmation_required),
        "live_confirmed": bool(settings.payments_live_provider_confirmed),
        "reconcile_seconds": float(settings.payments_reconcile_seconds),
        "providers": providers,
        "stats": stats(),
    }
    if db is not None:
        try:
            body["pending_intents"] = len(pending_intents(db, min_age_seconds=0, limit=500))
        except Exception as exc:  # health must not fail on a stats helper
            body["pending_intents_error"] = str(exc)[:120]
    return body
