"""Shared session presentation for kiosk/operator and Driver surfaces.

The parking/session/payment services remain authoritative. This module only
projects that state into UI contracts and deliberately keeps the public Driver
projection free of database, camera, node, visit and access-plan identifiers.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.site import DEFAULT_SITE_ID
from app.models import Gate, ParkingSession
from app.services.access import lookup_entitlement
from app.services.kiosk_lookup import image_fields, stay_for
from app.services.simulation import quote_session
from app.services.site_policy import as_site_local, site_policy


def _payment_status(row: ParkingSession, *, paid: bool, remaining: float) -> str:
    if paid or remaining <= 0.0001 or row.status == "PAID":
        return "PAID"
    value = str(row.payment_status or "").upper()
    return value if value else ("UNPAID" if remaining > 0 else "FREE")


def _entry_gate_name(db: Session, row: ParkingSession) -> str:
    gate_id = getattr(row, "entry_gate_id", None) or getattr(row, "gate_id", None)
    if not gate_id:
        return ""
    gate = db.get(Gate, int(gate_id))
    return str(gate.name or "") if gate else ""


def _can_exit(db: Session, row: ParkingSession, *, paid: bool, remaining: float) -> bool:
    if row.status == "CLOSED":
        return False
    if paid or remaining <= 0.0001:
        return True
    # Keep the decision aligned with the exit controller's entitlement rule
    # without exposing the subscription or vehicle record to the Driver.
    entitlement = lookup_entitlement(
        db,
        row.plate,
        at=datetime.now(timezone.utc),
        site_id=(row.site_id or DEFAULT_SITE_ID),
        strict=True,
    )
    return bool(entitlement.registered or (row.parker_kind or "CASUAL").upper() not in {"", "CASUAL"})


def session_presentation(db: Session, row: ParkingSession, *, audience: str = "driver") -> dict:
    """Return the common session/payment/evidence view.

    ``audience='driver'`` is safe for an opaque receipt-token bearer. The
    operator projection adds only the identifiers needed by the authenticated
    kiosk controls; both projections use the same due/paid/image calculations.
    """
    if row.status not in ("CLOSED", "PAID"):
        quote_session(db, row, persist=False)

    due = float(row.amount_due or 0)
    paid_amount = float(row.amount_paid or 0)
    remaining = max(0.0, due - paid_amount)
    paid = remaining <= 0.0001 or row.status == "PAID"
    payment_stage = "PAID" if paid and due > 0 else ("NO_PAYMENT_REQUIRED" if not remaining else "PAYMENT_REQUIRED")
    images = image_fields(db, row)
    stay = stay_for(row)
    status = _payment_status(row, paid=paid, remaining=remaining)
    body = {
        "ok": True,
        "token": row.public_token,
        "plate": row.plate,
        "entry_gate": _entry_gate_name(db, row),
        "entry_time": as_site_local(row.entry_time, site_policy(db)).isoformat() if row.entry_time else None,
        "exit_time": as_site_local(row.exit_time, site_policy(db)).isoformat() if row.exit_time else None,
        "currency": row.currency or "TZS",
        "amount_due": due,
        "amount_paid": paid_amount,
        "amount_remaining": remaining,
        "payment_status": status,
        "status": row.status,
        "paid": paid,
        "payment_stage": payment_stage,
        "online_payment_available": False,
        "kiosk_payment_available": True,
        "payable": remaining > 0.0001,
        "can_exit": _can_exit(db, row, paid=paid, remaining=remaining),
        "pay_blocked_reason": "" if remaining > 0.0001 else "This vehicle does not have a fee to pay.",
        "receipt_url": f"/p/{row.public_token}" if row.public_token else None,
        "qr_url": f"/p/{row.public_token}/qr.png" if row.public_token else None,
        "image_note": images.get("image_note") or "",
        "snapshot_url": images.get("snapshot_url"),
        "crop_url": images.get("crop_url"),
        **stay,
    }
    if audience == "operator":
        body.update({
            "session_id": row.id,
            "gate_id": row.gate_id,
            "image_plate": images.get("image_plate") or "",
            "image_matches_plate": images.get("image_matches_plate"),
            "parker_kind": getattr(row, "parker_kind", None) or "CASUAL",
        })
    return body

