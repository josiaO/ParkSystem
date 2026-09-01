"""Plate event → session → receipt/gate.

Casual cars follow receipt policy. Registered plates auto-open.
Live cameras and simulation share this path. HVX GPIO stays in gates.controller.
"""

from __future__ import annotations

import secrets
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.core.plate import normalize_plate
from app.domain.gates import should_pulse_physical
from app.infrastructure.payments.ledger import record_succeeded_payment
from app.models import Camera, Gate, ParkingSession, SiteSetting, utcnow
from app.services.access import Entitlement, lookup_entitlement
from app.services.decisions import record_access_decision, record_gate_command
from app.services.fee_engine import calculate_car1_fee, ensure_car1_tariff, load_active_rules
from app.services.gates import controller
from app.services.led_udp import send_led_text
from app.services.receipts import (
    issue_receipt,
    policy_requires_taken,
    policy_should_print,
    resolve_receipt_policy,
)

DEFAULT_PARKING_SETTINGS = {
    "receipt_required_before_open": False,
    "receipt_policy": "PRINT_AND_OPEN",
    "exit_requires_payment": True,
    "pay_prompt": "Pay {amount} {currency}",
    "printer_adapter": "simulated",
    "printer_name": "",
}

OPEN_STATUSES = {"WAITING_RECEIPT", "ACTIVE", "PAID", "OPEN"}


def parking_settings(db: Session) -> dict:
    row = db.get(SiteSetting, "parking")
    merged = dict(DEFAULT_PARKING_SETTINGS)
    if row and isinstance(row.value, dict):
        merged.update(row.value)
    policy = resolve_receipt_policy(merged)
    merged["receipt_policy"] = policy
    merged["receipt_required_before_open"] = policy_requires_taken(policy)
    return merged


def save_parking_settings(db: Session, payload: dict) -> dict:
    current = parking_settings(db)
    keys = set(DEFAULT_PARKING_SETTINGS) | {"receipt_policy"}
    for key in keys:
        if key in payload and payload[key] is not None:
            current[key] = payload[key]
    if "receipt_policy" in payload and payload["receipt_policy"]:
        current["receipt_policy"] = str(payload["receipt_policy"]).strip().upper()
        current["receipt_required_before_open"] = policy_requires_taken(current["receipt_policy"])
    elif "receipt_required_before_open" in payload:
        current["receipt_policy"] = (
            "REQUIRE_TAKEN_BEFORE_OPEN" if payload["receipt_required_before_open"] else "PRINT_AND_OPEN"
        )
    row = db.get(SiteSetting, "parking")
    if row is None:
        row = SiteSetting(key="parking", value=current)
        db.add(row)
    else:
        row.value = current
    if current.get("printer_name") and str(current.get("printer_adapter") or "simulated") == "simulated":
        current["printer_adapter"] = "system"
        row.value = current
    if not current.get("printer_name") and str(current.get("printer_adapter") or "") in {"system", "usb", "a4", "thermal"}:
        current["printer_adapter"] = "simulated"
        row.value = current
    db.commit()
    return parking_settings(db)


def session_dict(row: ParkingSession) -> dict:
    token = row.public_token or ""
    return {
        "id": row.id,
        "plate": row.plate,
        "gate_id": row.gate_id,
        "camera_id": row.camera_id,
        "lane_direction": row.lane_direction,
        "car_type": row.car_type,
        "status": row.status,
        "receipt_status": row.receipt_status or "",
        "simulated": bool(row.simulated),
        "parker_kind": getattr(row, "parker_kind", None) or "CASUAL",
        "access_plan_id": getattr(row, "access_plan_id", None),
        "vehicle_id": getattr(row, "vehicle_id", None),
        "public_token": token,
        "receipt_url": f"/p/{token}" if token else None,
        "qr_url": f"/p/{token}/qr.png" if token else None,
        "entry_time": row.entry_time.isoformat() if row.entry_time else None,
        "exit_time": row.exit_time.isoformat() if row.exit_time else None,
        "currency": row.currency,
        "amount_due": float(row.amount_due or 0),
        "amount_paid": float(row.amount_paid or 0),
        "breakdown": row.breakdown or [],
    }


def _side_camera(gate: Gate, side: str) -> Camera | None:
    want = (side or "ENTRY").upper()
    for camera in gate.cameras or []:
        if (camera.lane_direction or "").upper() == want:
            return camera
    return None


def _active_for_plate(db: Session, plate: str) -> ParkingSession | None:
    return db.scalar(
        select(ParkingSession)
        .where(ParkingSession.plate == plate, ParkingSession.status.in_(tuple(OPEN_STATUSES)))
        .order_by(ParkingSession.id.desc())
    )


def receipt_text(row: ParkingSession, cfg: dict) -> str:
    when = (row.entry_time or utcnow()).strftime("%Y-%m-%d %H:%M:%S UTC")
    policy = resolve_receipt_policy(cfg)
    wait = "Gate opens only after this receipt is taken.\n" if policy_requires_taken(policy) else "Keep this receipt for payment.\n"
    return (
        f"{app_settings.site_name} receipt\n"
        f"Plate: {row.plate}\n"
        f"Lane: {row.lane_direction}\n"
        f"Entry: {when}\n"
        f"Ref: {row.public_token}\n"
        f"Kind: {getattr(row, 'parker_kind', None) or 'CASUAL'}\n"
        f"{wait}"
    )


def create_entry(
    db: Session,
    *,
    plate: str,
    gate: Gate,
    side: str,
    simulated: bool = False,
    entitlement: Entitlement | None = None,
    status: str = "WAITING_RECEIPT",
    receipt_status: str = "PRINTED",
) -> ParkingSession:
    plate = normalize_plate(plate)
    if not plate:
        raise ValueError("Enter a number plate")
    existing = _active_for_plate(db, plate)
    if existing:
        return existing
    camera = _side_camera(gate, side)
    token = secrets.token_urlsafe(10)
    tariff = ensure_car1_tariff(db)
    entitlement = entitlement or Entitlement(plate=plate)
    row = ParkingSession(
        plate=plate,
        gate_id=gate.id,
        camera_id=camera.id if camera else None,
        lane_direction=(side or "ENTRY").upper(),
        status=status,
        receipt_status=receipt_status,
        public_token=token,
        simulated=bool(simulated),
        currency=(tariff.currency if tariff else "TZS"),
        parker_kind=entitlement.kind if entitlement.registered else "CASUAL",
        access_plan_id=entitlement.plan_id,
        vehicle_id=entitlement.vehicle_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


async def _pulse_gate(
    db: Session,
    gate: Gate | None,
    cameras: list[Camera],
    *,
    reason: str,
    side: str,
    led_text: str,
    session: ParkingSession | None = None,
    automatic: bool = True,
):
    if not gate or not cameras:
        return None
    dry_run = not should_pulse_physical(gate=gate, automatic=automatic)
    started = time.perf_counter()
    opened = await controller().open(
        gate, cameras, reason, side=side,
        dry_run=dry_run,
        led_text=led_text,
    )
    try:
        from app.services.health import note_gate
        note_gate(bool(opened and opened.ok), (time.perf_counter() - started) * 1000)
    except Exception:
        pass
    if opened.ok and not opened.simulated:
        gate.physical_control_verified = True
        db.commit()
    record_gate_command(
        db,
        gate=gate,
        session=session,
        reason=reason,
        automatic=automatic,
        dry_run=dry_run,
        ok=bool(opened and opened.ok),
        message=(opened.message if opened else "") or "",
    )
    return opened


def _attach_latency(result: dict, started: float) -> dict:
    result["latency_ms"] = int((time.perf_counter() - started) * 1000)
    return result


async def handle_plate_event(
    db: Session,
    *,
    plate: str,
    gate: Gate,
    side: str,
    simulated: bool = False,
    alpr: dict | None = None,
    source: str = "camera",
) -> dict:
    """Shared entry/exit path for live cameras and simulation."""
    started = time.perf_counter()
    side = (side or "ENTRY").upper()
    plate = normalize_plate(plate)
    if not plate:
        raise ValueError("No number plate")
    entitlement = lookup_entitlement(db, plate)
    if entitlement.registered and entitlement.plate:
        plate = normalize_plate(entitlement.plate)
    if side == "EXIT":
        result = await handle_exit(db, plate=plate, gate=gate, side=side)
        result["action"] = "EXIT"
        result["alpr"] = alpr
        result["source"] = source
        session_row = None
        if result.get("session") and result["session"].get("id"):
            session_row = db.get(ParkingSession, result["session"]["id"])
        record_access_decision(
            db,
            session=session_row,
            plate=plate,
            gate=gate,
            lane_direction=side,
            outcome="EXIT_AUTHORIZED" if result.get("opened") else (
                "DENIED_NO_SESSION" if not result.get("ok") else "DENIED_PAYMENT"
            ),
            reason=str(result.get("message") or result.get("say") or ""),
            parker_kind=(result.get("session") or {}).get("parker_kind") or "CASUAL",
            barrier_opened=bool(result.get("opened")),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        return _attach_latency(result, started)

    cfg = parking_settings(db)
    policy = resolve_receipt_policy(cfg)
    existing = _active_for_plate(db, plate)
    auto = bool(entitlement.registered and entitlement.auto_open)
    status = "ACTIVE" if auto or not policy_requires_taken(policy) else "WAITING_RECEIPT"
    want_print = policy_should_print(policy) or (auto and bool(entitlement.print_receipt))
    if auto:
        status = "ACTIVE"
    receipt_status = "PRINTED" if want_print else "NONE"
    row = create_entry(
        db, plate=plate, gate=gate, side=side, simulated=simulated,
        entitlement=entitlement, status=status, receipt_status=receipt_status,
    )
    duplicate = existing is not None
    issued = None
    slip = receipt_text(row, cfg)

    async def _print_now():
        nonlocal issued, slip
        if want_print and not duplicate:
            issued = await issue_receipt(
                db, row, gate=gate,
                adapter_id=cfg.get("printer_adapter"),
                printer_name=cfg.get("printer_name") or "",
            )
            slip = (issued or {}).get("receipt") or slip

    if auto:
        if duplicate:
            camera = _side_camera(gate, side)
            cameras = [camera] if camera else list(gate.cameras or [])
            opened = await _pulse_gate(
                db, gate, cameras,
                reason=f"{entitlement.kind} re-entry {row.plate}",
                side=side, led_text="WELCOME", session=row, automatic=True,
            )
            result = {
                "ok": True,
                "action": "ENTRY",
                "session": session_dict(row),
                "receipt": slip if want_print else "",
                "barrier_opened": bool(opened and opened.ok),
                "barrier": opened.__dict__ if opened else {"ok": False, "message": "No camera on that side to pulse"},
                "entitlement": entitlement.__dict__,
                "duplicate": True,
                "alpr": alpr,
                "source": source,
                "message": f"Registered {entitlement.kind} plate {row.plate} — barrier opened.",
            }
            return _finish_entry(db, result, row, gate, started, "ENTRY_AUTHORIZED")
        await _print_now()
        taken = await take_receipt(db, row, reason=f"{entitlement.kind} auto-open {row.plate}")
        result = {
            "ok": True,
            "action": "ENTRY",
            "session": taken["session"],
            "receipt": slip if want_print else "",
            "print": (issued or {}).get("print"),
            "qr_url": (issued or {}).get("qr_url") or f"/p/{row.public_token}/qr.png",
            "barrier_opened": bool((taken.get("barrier") or {}).get("ok")),
            "barrier": taken.get("barrier"),
            "entitlement": entitlement.__dict__,
            "duplicate": duplicate,
            "alpr": alpr,
            "source": source,
            "message": f"Registered {entitlement.kind} plate {row.plate} — barrier opened.",
        }
        return _finish_entry(db, result, row, gate, started, "ENTRY_AUTHORIZED")

    if not policy_requires_taken(policy):
        await _print_now()
        taken = await take_receipt(db, row, reason=f"{source} auto-open {row.plate}")
        taken["ok"] = True
        taken["action"] = "ENTRY"
        taken["receipt"] = slip
        taken["print"] = (issued or {}).get("print")
        taken["qr_url"] = (issued or {}).get("qr_url")
        taken["barrier_opened"] = bool((taken.get("barrier") or {}).get("ok"))
        taken["entitlement"] = entitlement.__dict__
        taken["alpr"] = alpr
        taken["source"] = source
        taken["duplicate"] = duplicate
        taken["message"] = "Receipt sent to the printer. Barrier opening."
        return _finish_entry(db, taken, row, gate, started, "ENTRY_AUTHORIZED")

    await _print_now()
    result = {
        "ok": True,
        "action": "ENTRY",
        "session": session_dict(row),
        "receipt": slip,
        "print": (issued or {}).get("print"),
        "qr_url": (issued or {}).get("qr_url"),
        "barrier_opened": False,
        "entitlement": entitlement.__dict__,
        "duplicate": duplicate,
        "alpr": alpr,
        "source": source,
        "message": (
            "Open session already exists for this plate."
            if duplicate
            else "Receipt printed. Take the receipt to open the barrier."
        ),
    }
    return _finish_entry(db, result, row, gate, started, "WAITING_RECEIPT")


def _finish_entry(
    db: Session,
    result: dict,
    row: ParkingSession,
    gate: Gate,
    started: float,
    outcome: str,
) -> dict:
    _attach_latency(result, started)
    record_access_decision(
        db,
        session=row,
        plate=row.plate,
        gate=gate,
        lane_direction=row.lane_direction or "ENTRY",
        outcome=outcome,
        reason=str(result.get("message") or ""),
        parker_kind=getattr(row, "parker_kind", None) or "CASUAL",
        barrier_opened=bool(result.get("barrier_opened")),
        latency_ms=int(result.get("latency_ms") or 0),
    )
    return result


async def take_receipt(db: Session, row: ParkingSession, *, reason: str = "simulation receipt taken") -> dict:
    cfg = parking_settings(db)
    gate = db.get(Gate, row.gate_id) if row.gate_id else None
    camera = db.get(Camera, row.camera_id) if row.camera_id else None
    cameras = [camera] if camera else list(gate.cameras or []) if gate else []
    row.receipt_status = "TAKEN" if row.receipt_status != "NONE" else "NONE"
    row.status = "ACTIVE"
    db.commit()
    opened = await _pulse_gate(
        db, gate, cameras, reason=reason, side=row.lane_direction or "ENTRY", led_text="WELCOME",
        session=row, automatic=True,
    )
    return {
        "session": session_dict(row),
        "receipt_required": bool(cfg.get("receipt_required_before_open")),
        "barrier": opened.__dict__ if opened else {"ok": False, "message": "No camera on that side to pulse"},
    }


def quote_session(db: Session, row: ParkingSession, *, at: datetime | None = None) -> dict:
    at = at or datetime.now(timezone.utc)
    rules = load_active_rules(db, row.car_type or "Car1")
    fee = calculate_car1_fee(row.entry_time, at, rules)
    row.amount_due = fee.due
    row.breakdown = list(fee.breakdown or [])
    row.currency = fee.currency
    db.commit()
    return fee.__dict__


async def handle_exit(db: Session, *, plate: str, gate: Gate, side: str) -> dict:
    plate = normalize_plate(plate)
    entitlement = lookup_entitlement(db, plate)
    row = _active_for_plate(db, plate)
    camera = _side_camera(gate, side)
    cameras = [camera] if camera else list(gate.cameras or [])
    registered_exit = bool(entitlement.registered and entitlement.auto_open)
    subscriber_session = bool(row and (getattr(row, "parker_kind", None) or "CASUAL") != "CASUAL")

    if registered_exit or subscriber_session:
        if row:
            quote_session(db, row)
            row.amount_due = 0
            row.amount_paid = 0
            row.status = "CLOSED"
            row.exit_time = utcnow()
            row.lane_direction = (side or "EXIT").upper()
            db.commit()
        opened = await _pulse_gate(
            db, gate, cameras, reason=f"{entitlement.kind or 'registered'} exit {plate}",
            side=side, led_text="THANKYOU", session=row, automatic=True,
        )
        return {
            "ok": True,
            "opened": bool(opened and opened.ok),
            "pay_required": False,
            "say": "Thank you",
            "session": session_dict(row) if row else None,
            "entitlement": entitlement.__dict__,
            "barrier": opened.__dict__ if opened else {"ok": False, "message": "No camera on that side to pulse"},
            "message": f"Registered {entitlement.kind or 'vehicle'} — exit opened.",
        }

    if not row:
        return {"ok": False, "opened": False, "message": f"No open session for {plate}", "say": "Pay at kiosk"}
    fee = quote_session(db, row)
    cfg = parking_settings(db)
    due = float(row.amount_due or 0)
    paid = float(row.amount_paid or 0)
    must_pay = bool(cfg.get("exit_requires_payment")) and due > paid
    prompt = str(cfg.get("pay_prompt") or DEFAULT_PARKING_SETTINGS["pay_prompt"]).format(
        amount=f"{due:.0f}", currency=row.currency or "TZS",
    )
    if must_pay:
        if camera and (camera.display_ip or "").strip():
            try:
                await send_led_text(
                    camera.display_ip,
                    prompt[:16],
                    dry_run=not app_settings.gate_physical_control_enabled,
                )
            except Exception:
                pass
        return {
            "ok": True,
            "opened": False,
            "pay_required": True,
            "say": prompt,
            "session": session_dict(row),
            "fee": fee,
            "message": prompt,
        }
    opened = await _pulse_gate(
        db, gate, cameras, reason=f"exit {plate}", side=side, led_text="THANKYOU",
        session=row, automatic=True,
    )
    row.status = "CLOSED"
    row.exit_time = utcnow()
    row.lane_direction = (side or "EXIT").upper()
    db.commit()
    return {
        "ok": True,
        "opened": bool(opened and opened.ok),
        "pay_required": False,
        "say": "Thank you",
        "session": session_dict(row),
        "barrier": opened.__dict__ if opened else {"ok": False, "message": "No camera on that side"},
        "fee": fee,
        "message": opened.message if opened else "No actuator",
    }


simulate_exit = handle_exit


def mark_paid(
    db: Session,
    row: ParkingSession,
    *,
    operator_id: int | None = None,
    method: str = "KIOSK_CASH",
) -> ParkingSession:
    quote_session(db, row)
    recorded = record_succeeded_payment(
        db,
        row,
        amount=float(row.amount_due or 0),
        method=method,
        provider_id="kiosk_manual",
        operator_id=operator_id,
        idempotency_key=f"session:{row.id}:settle",
    )
    return recorded["session"]
