"""Authoritative parking exit orchestration.

Presence/identity -> site-wide session -> fresh tariff/payment decision ->
idempotent barrier command -> vehicle passage -> CLOSED.

This module is deliberately independent from camera SDK callbacks and UI routes.
Plate recognition and QR fallback both resolve into the same controller.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from uuid import uuid4

from sqlalchemy.orm import Session

from app.domain.parking_engine import (
    AUTHORIZED,
    CLOSED,
    DENIED_PAYMENT_REQUIRED,
    EXIT_GATE_OPEN_REQUESTED,
    EXIT_VEHICLE_PASSED,
    LanePolicy,
)
from app.infrastructure.payments.ledger import SUCCEEDED, paid_total
from app.models import Camera, Gate, ParkingSession, utcnow
from app.services.access import lookup_entitlement
from app.services.decisions import record_access_decision, record_gate_command
from app.services.fee_engine import load_active_rules
from app.services.parking_sessions import (
    complete_authorized_exit,
    mark_vehicle_passed,
    snapshot,
    start_exit,
)
from app.domain.tariff_engine import quote_stay


GateOpener = Callable[..., Awaitable[Any]]


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _cameras(gate: Gate | None, camera: Camera | None) -> list[Camera]:
    if camera is not None:
        return [camera]
    if gate is None:
        return []
    return [
        row for row in (gate.cameras or [])
        if row.enabled and (row.lane_direction or "").upper() == "EXIT"
    ]


class ExitLaneController:
    """One application service for plate and QR based exits."""

    def __init__(self, *, opener: GateOpener | None = None) -> None:
        self.opener = opener

    def _fresh_financial_state(
        self,
        db: Session,
        row: ParkingSession,
        *,
        at: datetime,
        entitlement,
    ) -> dict[str, Any]:
        subscriber = bool(entitlement.registered) or (row.parker_kind or "CASUAL").upper() not in {"", "CASUAL"}
        if subscriber:
            row.amount_due = 0
            row.breakdown = ["subscriber/access-plan"]
            db.flush()
            return {
                "subscriber": True,
                "in_payment_grace": False,
                "due": 0,
                "paid": float(paid_total(db, row.id)),
                "allow": True,
                "reason": "subscriber",
            }

        grace_until = _aware(row.payment_exit_grace_until)
        in_payment_grace = bool(
            row.payment_status == SUCCEEDED
            and grace_until is not None
            and at <= grace_until
        )
        paid = float(paid_total(db, row.id))

        if in_payment_grace:
            # The amount was already authoritatively quoted and settled when
            # payment succeeded. Do not move the price during the configured
            # walk/drive-to-exit grace period.
            due = float(row.amount_due or 0)
            row.amount_paid = paid
            db.flush()
            return {
                "subscriber": False,
                "in_payment_grace": True,
                "due": due,
                "paid": paid,
                "allow": paid + 0.0001 >= due,
                "reason": "payment_grace",
            }

        rules = load_active_rules(db, row.car_type or "Car1", site_id=row.site_id)
        quote = quote_stay(row.entry_time, at, rules)
        row.amount_due = quote.due_minor
        row.amount_paid = paid
        row.currency = quote.currency
        row.breakdown = list(quote.breakdown)
        db.flush()
        allow = paid + 0.0001 >= float(quote.due_minor)
        return {
            "subscriber": False,
            "in_payment_grace": False,
            "due": float(quote.due_minor),
            "paid": paid,
            "allow": allow,
            "reason": "free_or_paid" if allow else "payment_required",
            "quote": {
                "duration_seconds": quote.duration_seconds,
                "due_minor": quote.due_minor,
                "currency": quote.currency,
                "breakdown": list(quote.breakdown),
                "in_grace": quote.in_grace,
            },
        }

    async def submit_plate(
        self,
        db: Session,
        *,
        plate: str,
        event_id: str,
        site_id: int,
        gate: Gate | None = None,
        camera: Camera | None = None,
        lane_id: int | None = None,
        policy: LanePolicy | None = None,
        occupied: bool | None = True,
        at: datetime | None = None,
        source: str = "camera",
    ) -> dict[str, Any]:
        if occupied is False:
            return {
                "ok": False, "action": "EXIT", "reason": "no_presence",
                "barrier_opened": False, "session": None,
                "message": "No vehicle presence on this exit lane.",
            }
        plate = (plate or "").strip().upper()
        if not plate:
            return {
                "ok": False, "action": "EXIT", "reason": "no_identity",
                "barrier_opened": False, "session": None,
                "message": "No plate was resolved.",
            }
        from app.services.parking_sessions import active_for_plate
        row = active_for_plate(db, plate, site_id=site_id)
        if row is None:
            record_access_decision(
                db, session=None, plate=plate, gate=gate, lane_direction="EXIT",
                outcome="DENIED_NO_SESSION", reason="no active site session",
                barrier_opened=False,
            )
            return {
                "ok": False, "action": "EXIT", "reason": "no_session",
                "barrier_opened": False, "pay_required": False, "session": None,
                "message": f"No active parking session for {plate}. Scan the receipt QR or call an operator.",
            }
        return await self._submit_session(
            db, row=row, event_id=event_id, gate=gate, camera=camera,
            lane_id=lane_id, policy=policy, at=at, source=source,
        )

    async def submit_qr(
        self,
        db: Session,
        *,
        raw_scan: str,
        event_id: str,
        site_id: int,
        gate: Gate | None = None,
        camera: Camera | None = None,
        lane_id: int | None = None,
        policy: LanePolicy | None = None,
        at: datetime | None = None,
        source: str = "qr",
    ) -> dict[str, Any]:
        from app.domain.receipt_engine import extract_session_token
        from app.services.public_pay import session_by_public_token

        token = extract_session_token(raw_scan)
        row = session_by_public_token(db, token) if token else None
        if row is None or int(row.site_id) != int(site_id) or row.status == "CLOSED":
            return {
                "ok": False, "action": "EXIT", "reason": "invalid_qr",
                "barrier_opened": False, "pay_required": False, "session": None,
                "message": "Receipt QR does not identify an active session at this site.",
            }
        return await self._submit_session(
            db, row=row, event_id=event_id, gate=gate, camera=camera,
            lane_id=lane_id, policy=policy, at=at, source=source,
        )

    async def _submit_session(
        self,
        db: Session,
        *,
        row: ParkingSession,
        event_id: str,
        gate: Gate | None,
        camera: Camera | None,
        lane_id: int | None,
        policy: LanePolicy | None,
        at: datetime | None,
        source: str,
    ) -> dict[str, Any]:
        policy = policy or LanePolicy()
        at = _aware(at) or datetime.now(timezone.utc)
        entitlement = lookup_entitlement(db, row.plate, at=at, site_id=row.site_id, strict=True)
        financial = self._fresh_financial_state(db, row, at=at, entitlement=entitlement)
        db.commit()
        db.refresh(row)

        row, outcome = start_exit(
            db,
            plate=row.plate,
            event_id=event_id,
            site_id=row.site_id,
            lane_id=lane_id,
            camera_id=camera.id if camera else None,
            gate_id=gate.id if gate else None,
            policy=policy,
            paid=bool(financial["allow"]),
        )
        if row is None:
            return {
                "ok": False, "action": "EXIT", "reason": "no_session",
                "barrier_opened": False, "session": None,
                "message": "Parking session disappeared while resolving exit.",
            }

        if row.exit_event_id and event_id and row.exit_event_id != event_id and outcome in {
            AUTHORIZED, EXIT_GATE_OPEN_REQUESTED, EXIT_VEHICLE_PASSED, CLOSED
        }:
            return {
                "ok": True,
                "action": "EXIT",
                "reason": "exit_in_progress",
                "pay_required": False,
                "barrier_opened": outcome in {EXIT_GATE_OPEN_REQUESTED, EXIT_VEHICLE_PASSED, CLOSED},
                "duplicate": True,
                "session": snapshot(row),
                "financial": financial,
                "message": "Another exit event already owns this parking session.",
            }

        if outcome == DENIED_PAYMENT_REQUIRED:
            record_access_decision(
                db, session=row, plate=row.plate, gate=gate, lane_direction="EXIT",
                outcome="DENIED_PAYMENT_REQUIRED",
                reason=f"due={financial['due']} paid={financial['paid']}",
                parker_kind=row.parker_kind or "CASUAL", barrier_opened=False,
                extra={"source": source, **financial},
            )
            return {
                "ok": True,
                "action": "EXIT",
                "reason": "payment_required",
                "pay_required": True,
                "barrier_opened": False,
                "session": snapshot(row),
                "financial": financial,
                "message": f"Payment required: {row.currency} {financial['due']:.0f}.",
            }

        if outcome not in {AUTHORIZED, EXIT_GATE_OPEN_REQUESTED, EXIT_VEHICLE_PASSED, CLOSED}:
            return {
                "ok": False, "action": "EXIT", "reason": "review",
                "pay_required": False, "barrier_opened": False,
                "session": snapshot(row), "financial": financial,
                "message": f"Exit state {outcome} requires review.",
            }

        if outcome in {EXIT_GATE_OPEN_REQUESTED, EXIT_VEHICLE_PASSED, CLOSED}:
            return {
                "ok": True, "action": "EXIT", "reason": "duplicate",
                "pay_required": False, "barrier_opened": outcome != CLOSED or row.closed_at is not None,
                "duplicate": True, "session": snapshot(row), "financial": financial,
                "message": "Exit command already applied.",
            }

        return await self._open_authorized(
            db, row=row, gate=gate, camera=camera, policy=policy,
            financial=financial, source=source,
        )

    async def _open_authorized(
        self,
        db: Session,
        *,
        row: ParkingSession,
        gate: Gate | None,
        camera: Camera | None,
        policy: LanePolicy,
        financial: dict[str, Any],
        source: str,
    ) -> dict[str, Any]:
        if gate is None:
            return {
                "ok": False, "action": "EXIT", "reason": "gate_unassigned",
                "pay_required": False, "barrier_opened": False,
                "assistance_required": True, "session": snapshot(row),
                "financial": financial,
                "message": "Exit is authorized but no barrier is assigned to this lane.",
            }

        command_uuid = row.exit_open_command_uuid or uuid4().hex
        if not row.exit_open_command_uuid:
            row.exit_open_command_uuid = command_uuid
            db.commit()
            db.refresh(row)
        cameras = _cameras(gate, camera)
        if self.opener is None:
            from app.services.simulation import _pulse_gate
            opened = await _pulse_gate(
                db, gate, cameras, reason=f"exit {row.plate}", side="EXIT",
                led_text="THANKYOU", session=row, automatic=True,
                command_uuid=command_uuid,
            )
        else:
            opened = await self.opener(
                db, gate, cameras, reason=f"exit {row.plate}", session=row,
                side="EXIT", command_uuid=command_uuid,
            )
            record_gate_command(
                db, gate=gate, session=row, reason=f"exit {row.plate}",
                automatic=True, dry_run=bool(getattr(opened, "simulated", False)),
                ok=bool(opened and opened.ok), message=getattr(opened, "message", "") or "",
                command_uuid=command_uuid,
            )

        if opened is None or not opened.ok:
            record_access_decision(
                db, session=row, plate=row.plate, gate=gate, lane_direction="EXIT",
                outcome="GATE_UNAVAILABLE", reason=getattr(opened, "message", "") or "gate unavailable",
                parker_kind=row.parker_kind or "CASUAL", barrier_opened=False,
                extra={"source": source, **financial},
            )
            return {
                "ok": False, "action": "EXIT", "reason": "gate_unavailable",
                "pay_required": False, "barrier_opened": False,
                "assistance_required": True, "session": snapshot(row),
                "financial": financial,
                "message": "Exit authorized, but the barrier did not open. Session remains active.",
            }

        row = complete_authorized_exit(db, row, policy=policy, command_uuid=command_uuid)
        record_access_decision(
            db, session=row, plate=row.plate, gate=gate, lane_direction="EXIT",
            outcome="EXIT_AUTHORIZED", reason=financial["reason"],
            parker_kind=row.parker_kind or "CASUAL", barrier_opened=True,
            extra={"source": source, **financial},
        )
        return {
            "ok": True, "action": "EXIT",
            "reason": "closed" if row.lifecycle == CLOSED else "waiting_passage",
            "pay_required": False, "barrier_opened": True,
            "assistance_required": False, "session": snapshot(row),
            "financial": financial,
            "message": "Exit authorized. Barrier opening.",
        }

    async def vehicle_passed(
        self,
        db: Session,
        row: ParkingSession,
        *,
        policy: LanePolicy | None = None,
    ) -> dict[str, Any]:
        policy = policy or LanePolicy()
        row = mark_vehicle_passed(db, row, policy=policy, side="EXIT")
        return {
            "ok": True,
            "action": "EXIT",
            "reason": "closed",
            "barrier_opened": True,
            "session": snapshot(row),
            "message": "Vehicle passed. Parking session closed.",
        }
