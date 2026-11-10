from __future__ import annotations

"""Plate event → session → receipt/gate.

Casual cars follow receipt policy. Registered plates auto-open.
Live cameras and simulation share this path. HVX GPIO stays in gates.controller.
"""

import time

from datetime import datetime, timezone

from sqlalchemy import select

from sqlalchemy.orm import Session

from app.config import settings as app_settings

from app.core.plate import normalize_plate, plate_similarity

from app.domain.gates import should_pulse_physical

from app.infrastructure.payments.ledger import record_succeeded_payment

from app.domain.site import DEFAULT_SITE_ID

from app.models import Camera, Gate, ParkingSession, SiteSetting, as_utc, utcnow

from app.services.access import Entitlement, lookup_entitlement

from app.services.decisions import record_access_decision, record_gate_command

from app.services.fee_engine import calculate_car1_fee, ensure_car1_tariff, load_active_rules, normalize_tariff_rules

from app.services.gates import GateCommandResult, controller

from app.services.led_udp import send_led_text

from app.domain.receipt_engine import session_qr_payload

from app.services.parking_sessions import _allocate_identity

from app.services.receipts import (
    issue_receipt,
    policy_requires_taken,
    policy_should_print,
    resolve_receipt_policy,
)

from app.services.site_policy import as_site_local, site_policy

DEFAULT_PARKING_SETTINGS = {
    # Development keeps the fast simulator behavior.  A configured or
    # production deployment is made fail-closed by parking_settings() below.
    "receipt_required_before_open": False,
    "receipt_policy": "PRINT_AND_OPEN",
    "passage_sensing": "OPEN_COMMAND_COUNTS_AS_PASSED",
    "exit_requires_payment": True,
    "pay_prompt": "Pay {amount} {currency}",
    "printer_adapter": "simulated",
    "printer_name": "",
    "payment_exit_grace_seconds": 15 * 60,
}

OPEN_STATUSES = {"WAITING_RECEIPT", "ACTIVE", "PAID", "OPEN"}

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
    command_uuid: str = "",
):
    if not gate or not cameras:
        return None
    from app.services.developer import gate_opening_enabled
    if not gate_opening_enabled(db):
        blocked = GateCommandResult(
            ok=False,
            simulated=True,
            message="Developer mode has gate opening disabled",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        record_gate_command(
            db, gate=gate, session=session, reason=reason, automatic=automatic,
            dry_run=True, ok=False, message=blocked.message,
            command_uuid=command_uuid or None,
        )
        return blocked
    dry_run = bool(session is not None and session.simulated) or not should_pulse_physical(gate=gate, automatic=automatic)
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
        command_uuid=command_uuid or None,
    )
    return opened

async def handle_plate_event(
    db: Session,
    *,
    plate: str,
    gate: Gate | None,
    side: str,
    simulated: bool = False,
    alpr: dict | None = None,
    source: str = "camera",
    camera: Camera | None = None,
) -> dict:
    """Simulation harness plus temporary legacy EXIT orchestration.

    Real ENTRY camera events are forbidden here and must use
    app.application.entry_lane.EntryLaneController through live_parking.
    Phase 6 will replace the remaining EXIT branch with ExitLaneController.
    """
    started = time.perf_counter()
    side = (side or "ENTRY").upper()
    if not simulated:
        raise RuntimeError(
            f"live {side} must use the parking application controller, not simulation.handle_plate_event"
        )
    plate = normalize_plate(plate)
    if not plate:
        raise ValueError("No number plate")
    entitlement = lookup_entitlement(
        db, plate,
        site_id=(getattr(gate, "site_id", None) or getattr(camera, "site_id", None) or DEFAULT_SITE_ID),
        strict=True,
    )
    if entitlement.registered and entitlement.plate:
        plate = normalize_plate(entitlement.plate)
    if side == "EXIT":
        result = await handle_exit(db, plate=plate, gate=gate, side=side, camera=camera)
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
        camera=camera,
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
            pulse_camera = camera or (_side_camera(gate, side) if gate else None)
            cameras = [pulse_camera] if pulse_camera else list((gate.cameras if gate else None) or [])
            opened = await _pulse_gate(
                db, gate, cameras,
                reason=f"{entitlement.kind} re-entry {row.plate}",
                side=side, led_text="WELCOME", session=row, automatic=True,
            ) if gate else None
            result = {
                "ok": True,
                "action": "ENTRY",
                "session": session_dict(row),
                "receipt": slip if want_print else "",
                "barrier_opened": bool(opened and opened.ok),
                "barrier": opened.__dict__ if opened else {"ok": False, "message": "No gate assigned — session saved, barrier skipped"},
                "entitlement": entitlement.__dict__,
                "duplicate": True,
                "alpr": alpr,
                "source": source,
                "message": f"Registered {entitlement.kind} plate {row.plate} — barrier opened." if opened else f"Registered {entitlement.kind} plate {row.plate} — session active (assign a Gate to open barriers).",
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
        taken["message"] = (
            "Receipt sent to the printer. Barrier opening."
            if gate
            else "Session saved. Assign this camera to a Gate to open barriers."
        )
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

async def handle_exit(db: Session, *, plate: str, gate: Gate | None, side: str, camera: Camera | None = None) -> dict:
    plate = normalize_plate(plate)
    entitlement = lookup_entitlement(
        db, plate,
        site_id=(getattr(gate, "site_id", None) or getattr(camera, "site_id", None) or DEFAULT_SITE_ID),
        strict=True,
    )
    row = _active_for_plate(db, plate)
    pulse_camera = camera or (_side_camera(gate, side) if gate else None)
    cameras = [pulse_camera] if pulse_camera else list((gate.cameras if gate else None) or [])
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
        led_cam = pulse_camera or camera
        if led_cam and (led_cam.display_ip or "").strip():
            try:
                await send_led_text(
                    led_cam.display_ip,
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
