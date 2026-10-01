"""Public receipt payment page helpers (QR → phone pay or kiosk scan)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.payments import payment_provider_for, record_succeeded_payment, transaction_dict
from app.models import ParkingSession
from app.services.simulation import quote_session, session_dict as sim_session_dict


def session_by_public_token(db: Session, token: str) -> ParkingSession | None:
    from app.services.kiosk_lookup import extract_receipt_token

    token = extract_receipt_token(token)
    if not token:
        return None
    return db.scalar(select(ParkingSession).where(ParkingSession.public_token == token))


def public_session_payload(db: Session, row: ParkingSession) -> dict:
    if row.status not in ("CLOSED", "PAID"):
        quote_session(db, row)
        db.commit()
        db.refresh(row)
    due = float(row.amount_due or 0)
    paid = float(row.amount_paid or 0)
    remaining = max(0.0, due - paid)
    paid_up = remaining <= 0.0001
    from app.services.kiosk_lookup import image_fields, stay_for

    stay = stay_for(row)
    images = image_fields(db, row)
    payable = remaining > 0.0001
    from app.services.mobile_payments import active_mobile_provider_id, external_provider_ids

    mobile_provider = active_mobile_provider_id()
    if mobile_provider in external_provider_ids():
        pay_methods = ["MOBILE_MONEY", "KIOSK_CASH"]
        pay_endpoint = "/api/public/payment-intents"
    else:
        from app.config import settings
        pay_methods = ["KIOSK_CASH"]
        pay_endpoint = ""
        if settings.allow_public_simulated_payments:
            pay_methods.insert(0, "MOBILE_SIMULATED")
            pay_endpoint = f"/p/{row.public_token}/pay"
    return {
        "mobile_provider": mobile_provider,
        "pay_endpoint": pay_endpoint,
        "ok": True,
        "token": row.public_token,
        "session_id": row.id,
        "plate": row.plate,
        "status": row.status,
        "parker_kind": getattr(row, "parker_kind", None) or "CASUAL",
        "entry_time": row.entry_time.isoformat() if row.entry_time else None,
        "exit_time": row.exit_time.isoformat() if row.exit_time else None,
        "currency": row.currency or "TZS",
        "amount_due": due,
        "amount_paid": paid,
        "amount_remaining": remaining,
        "paid": paid_up or row.status == "PAID",
        "payable": payable,
        "pay_blocked_reason": "" if payable else "This vehicle does not have a fee to pay.",
        "receipt_url": f"/p/{row.public_token}",
        "qr_url": f"/p/{row.public_token}/qr.png",
        "pay_methods": pay_methods if payable else [],
        "session": sim_session_dict(row),
        **stay,
        **images,
    }


async def pay_public_session(
    db: Session,
    row: ParkingSession,
    *,
    method: str = "MOBILE_SIMULATED",
    amount: float | None = None,
    operator_id: int | None = None,
) -> dict:
    """Settle via simulated mobile or kiosk ledger path.

    Real mobile-money aggregators must replace SimulatedPaymentProvider with a
    webhook that calls record_succeeded_payment only after verification.
    """
    quote_session(db, row)
    due = float(row.amount_due or 0)
    paid = float(row.amount_paid or 0)
    remaining = max(0.0, due - paid)
    if remaining <= 0.0001:
        return {"ok": True, "already_paid": True, **public_session_payload(db, row)}

    method = (method or "MOBILE_SIMULATED").strip().upper()
    pay_amount = float(amount) if amount is not None else remaining
    if pay_amount <= 0:
        raise ValueError("Nothing to pay")
    if pay_amount > remaining + 0.01:
        pay_amount = remaining

    if method in {"MOBILE_SIMULATED", "MOBILE_MONEY", "SIMULATED"}:
        from app.config import settings
        if not settings.allow_public_simulated_payments:
            raise PermissionError("Public simulated payments are disabled")
        provider = payment_provider_for("simulated")
        intent = await provider.create_intent({
            "session_id": row.id,
            "amount": pay_amount,
            "currency": row.currency or "TZS",
            "method": "MOBILE_SIMULATED",
            "token": row.public_token,
        })
        pending = await provider.initiate_collection(intent)
        verified = await provider.verify_callback({**pending, "token": row.public_token})
        if not verified.get("verified"):
            raise RuntimeError("Mobile payment was not verified")
        recorded = record_succeeded_payment(
            db,
            row,
            amount=pay_amount,
            method="MOBILE_SIMULATED",
            provider_id="simulated",
            operator_id=operator_id,
            idempotency_key=f"session:{row.id}:mobile:{pay_amount:.2f}",
        )
        return {
            "ok": True,
            "method": "MOBILE_SIMULATED",
            "transaction": transaction_dict(recorded["transaction"]),
            "duplicate": recorded["duplicate"],
            **public_session_payload(db, recorded["session"]),
        }

    if method in {"KIOSK_CASH", "CASH", "KIOSK"}:
        if operator_id is None:
            raise PermissionError("Kiosk cash requires a signed-in operator")
        recorded = record_succeeded_payment(
            db,
            row,
            amount=pay_amount,
            method="KIOSK_CASH",
            provider_id="kiosk_manual",
            operator_id=operator_id,
            idempotency_key=f"session:{row.id}:settle",
        )
        return {
            "ok": True,
            "method": "KIOSK_CASH",
            "transaction": transaction_dict(recorded["transaction"]),
            "duplicate": recorded["duplicate"],
            **public_session_payload(db, recorded["session"]),
        }

    raise ValueError(f"Unsupported pay method: {method}")
