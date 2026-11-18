"""Authoritative parking exit orchestration.

Presence/identity -> site-wide session -> fresh tariff/payment decision ->
idempotent barrier command -> vehicle passage -> CLOSED.

This module is deliberately independent from camera SDK callbacks and UI routes.
Plate recognition and QR fallback both resolve into the same controller.
"""

from __future__ import annotations

import logging

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.domain.parking_engine import (
    AUTHORIZED,
    CLOSED,
    DENIED_PAYMENT_REQUIRED,
    EXIT_GATE_OPEN_REQUESTED,
    EXIT_VEHICLE_PASSED,
    LanePolicy,
)
from app.domain.site import DEFAULT_SITE_ID
from app.db import release_connection
from app.infrastructure.payments.ledger import SUCCEEDED, paid_total
from app.models import Camera, Gate, ParkingSession, utcnow
from app.services.access import lookup_entitlement
from app.services.decisions import record_access_decision, record_gate_command
from app.services.fee_engine import load_active_rules, normalize_tariff_rules
from app.services.parking_sessions import (
    complete_authorized_exit,
    mark_vehicle_passed,
    snapshot,
    start_exit,
)
from app.domain.tariff_engine import quote_stay

log = logging.getLogger("smartpark")


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

        site_id = int(row.site_id or DEFAULT_SITE_ID)
        rules = normalize_tariff_rules(row.tariff_rules, car_type=row.car_type or "Car1") if row.tariff_rules else load_active_rules(
            db, row.car_type or "Car1", site_id=site_id
        )
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
        confidence: float | None = None,
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
        stay = None
        if camera is not None:
            # Repeated captures of one car at this exit (app/services/lane_stay):
            # act on the best-supported read, and only once the barrier opened.
            from app.services import lane_stay

            stay = lane_stay.observe(int(camera.id), plate, confidence)
            if stay.repeats and stay.barrier_opened:
                return {
                    "ok": True, "action": "EXIT", "reason": "same_stay", "duplicate": True,
                    "barrier_opened": False, "session": None, "stay_reads": stay.repeats + 1,
                    "message": f"{plate}: the same car is still at the exit; the barrier already opened for it.",
                }
            best = stay.best_plate()
            if best and best != plate:
                plate = best
        from app.services.parking_sessions import active_for_plate
        if event_id:
            previous = db.scalar(select(ParkingSession).where(
                ParkingSession.site_id == site_id, ParkingSession.exit_event_id == event_id,
            ))
            if previous is not None and (previous.exit_open_command_uuid or previous.closed_at is not None):
                return {"ok": True, "action": "EXIT", "reason": "duplicate", "duplicate": True,
                        "barrier_opened": bool(previous.exit_open_command_uuid), "session": snapshot(previous),
                        "message": "This exit event already belongs to its original session."}
        row = active_for_plate(db, plate, site_id=site_id)
        if row is None and stay is not None and plate in stay.reported_no_session:
            # The same car, still waiting, already raised "no session" for this
            # plate: check again (done above) but do not alert again.
            return {
                "ok": False, "action": "EXIT", "reason": "same_stay_no_session", "duplicate": True,
                "barrier_opened": False, "pay_required": False, "session": None,
                "stay_reads": stay.repeats + 1,
                "message": f"{plate}: still no active session (already reported for this car).",
            }
        if row is None:
            from app.services.kiosk_lookup import near_matches

            # Exact match only for the barrier. Close plates are offered to the
            # operator as "did you mean", never acted on automatically.
            suggestions = [{k: v for k, v in item.items() if k != "token"} for item in near_matches(db, plate, site_id=site_id)]
            record_access_decision(
                db, session=None, plate=plate, gate=gate, lane_direction="EXIT",
                outcome="DENIED_NO_SESSION", reason="no active site session",
                barrier_opened=False,
                extra={"suggestions": suggestions} if suggestions else None,
            )
            if stay is not None:
                stay.reported_no_session.add(plate)
            message = f"No active parking session for {plate}. Scan the receipt QR or call an operator."
            if suggestions:
                message += " Did you mean " + " or ".join(item["plate"] for item in suggestions) + "? Check with the receipt."
            return {
                "ok": False, "action": "EXIT", "reason": "no_session",
                "barrier_opened": False, "pay_required": False, "session": None,
                "suggestions": suggestions,
                "message": message,
            }
        result = await self._submit_session(
            db, row=row, event_id=event_id, gate=gate, camera=camera,
            lane_id=lane_id, policy=policy, at=at, source=source,
        )
        if stay is not None and result.get("barrier_opened"):
            from app.services import lane_stay

            lane_stay.mark_opened(int(camera.id))
        return result

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
        row_site_id = int(row.site_id or DEFAULT_SITE_ID) if row is not None else None
        if row is None or row_site_id != int(site_id) or row.status == "CLOSED":
            return {
                "ok": False, "action": "EXIT", "reason": "invalid_qr",
                "barrier_opened": False, "pay_required": False, "session": None,
                "message": "Receipt QR does not identify an active session at this site.",
            }
        mismatch = self._camera_plate_mismatch(db, row, gate=gate, camera=camera, at=at)
        out = await self._submit_session(
            db, row=row, event_id=event_id, gate=gate, camera=camera,
            lane_id=lane_id, policy=policy, at=at, source=source,
        )
        if mismatch:
            # The receipt decides the exit; the camera disagreement is evidence
            # for the operator, never a reason to deny automatically.
            out["plate_mismatch"] = mismatch
            out["message"] = (
                f"{out.get('message') or ''} Check the car: the exit camera read "
                f"{mismatch['camera_plate']}, but this receipt is for {mismatch['session_plate']}."
            ).strip()
            record_access_decision(
                db, session=row, plate=row.plate, gate=gate, lane_direction="EXIT",
                outcome="QR_PLATE_MISMATCH",
                reason=f"QR session {mismatch['session_plate']} vs camera {mismatch['camera_plate']}",
                parker_kind=row.parker_kind or "CASUAL",
                barrier_opened=bool(out.get("barrier_opened")),
                extra={"source": source, **mismatch},
            )
        return out

    QR_CAMERA_READ_WINDOW_SECONDS = 120

    def _camera_plate_mismatch(
        self, db: Session, row: ParkingSession, *, gate: Gate | None, camera: Camera | None, at: datetime | None,
    ) -> dict[str, Any] | None:
        """The latest recent exit-camera read at this lane, if it names another plate."""
        from datetime import timedelta

        from app.core.plate import normalize_plate, plate_similarity
        from app.models import VehicleCapture

        if gate is None and camera is None:
            return None
        now = _aware(at) or datetime.now(timezone.utc)
        query = select(VehicleCapture).where(
            VehicleCapture.lane_direction == "EXIT",
            VehicleCapture.created_at >= now - timedelta(seconds=self.QR_CAMERA_READ_WINDOW_SECONDS),
            VehicleCapture.plate != "",
        )
        if camera is not None:
            query = query.where(VehicleCapture.camera_id == camera.id)
        else:
            query = query.where(VehicleCapture.gate_id == gate.id)
        latest = db.scalar(query.order_by(VehicleCapture.id.desc()).limit(1))
        if latest is None:
            return None
        camera_plate, session_plate = normalize_plate(latest.plate), normalize_plate(row.plate)
        if not camera_plate or camera_plate == session_plate:
            return None
        created = _aware(latest.created_at)
        return {
            "camera_plate": camera_plate,
            "session_plate": session_plate,
            "capture_id": latest.id,
            "camera_id": latest.camera_id,
            "similarity": round(plate_similarity(camera_plate, session_plate), 2),
            "seconds_ago": round((now - created).total_seconds(), 1) if created else None,
        }

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
        site_id = int(row.site_id or DEFAULT_SITE_ID)
        entitlement = lookup_entitlement(db, row.plate, at=at, site_id=site_id, strict=True)
        financial = self._fresh_financial_state(db, row, at=at, entitlement=entitlement)
        db.commit()
        db.refresh(row)

        from app.domain.parking_engine import InvalidTransition

        visit = row
        try:
            row, outcome = start_exit(
                db,
                plate=row.plate,
                event_id=event_id,
                site_id=site_id,
                lane_id=lane_id,
                camera_id=camera.id if camera else None,
                gate_id=gate.id if gate else None,
                policy=policy,
                paid=bool(financial["allow"]),
            )
        except InvalidTransition as exc:
            # E.g. a visit still waiting for its entry receipt: it cannot leave
            # automatically. Tell the operator instead of raising.
            db.rollback()
            record_access_decision(
                db, session=visit, plate=visit.plate, gate=gate, lane_direction="EXIT",
                outcome="ASSISTANCE_REQUIRED", reason=f"visit incomplete: {exc}"[:200],
                parker_kind=visit.parker_kind or "CASUAL", barrier_opened=False,
            )
            return {
                "ok": False, "action": "EXIT", "reason": "visit_incomplete",
                "barrier_opened": False, "assistance_required": True, "session": snapshot(visit),
                "message": f"Visit for {visit.plate} is not complete ({visit.lifecycle}). Operator: check the car and close or admit it.",
            }
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
                "payment_url": f"/p/{row.public_token}" if row.public_token else None,
                "qr_url": f"/p/{row.public_token}/qr.png" if row.public_token else None,
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

        if row.exit_open_command_uuid:
            return {"ok": True, "action": "EXIT", "reason": "gate_command_in_progress",
                    "duplicate": True, "barrier_opened": False, "session": snapshot(row),
                    "financial": financial, "message": "An exit barrier command already owns this session."}
        command_uuid = uuid4().hex
        if not row.exit_open_command_uuid:
            claimed = db.execute(update(ParkingSession).where(
                ParkingSession.id == row.id,
                or_(ParkingSession.exit_open_command_uuid == "", ParkingSession.exit_open_command_uuid.is_(None)),
            ).values(exit_open_command_uuid=command_uuid))
            db.commit()
            db.refresh(row)
            if claimed.rowcount != 1:
                return {"ok": True, "action": "EXIT", "reason": "gate_command_in_progress",
                        "duplicate": True, "barrier_opened": False, "session": snapshot(row), "financial": financial}
        cameras = _cameras(gate, camera)
        from app.services.lane_timing import mark
        mark("gate_requested", command_uuid=command_uuid)
        try:
            if self.opener is None:
                from app.services.simulation import _pulse_gate
                release_connection(db)
                opened = await _pulse_gate(
                    db, gate, cameras, reason=f"exit {row.plate}", side="EXIT",
                    led_text="THANKYOU", session=row, automatic=True,
                    command_uuid=command_uuid,
                )
            else:
                release_connection(db)
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
        except BaseException:
            db.rollback()
            self._release_exit_claim(db, row, command_uuid)
            raise

        if opened is None or not opened.ok:
            # The boom did not accept the command: give the claim back so the
            # camera's next read, the QR fallback or an operator can retry.
            # Compare-and-clear: never release a claim another attempt owns.
            self._release_exit_claim(db, row, command_uuid)
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
        passage_complete = row.lifecycle == CLOSED
        record_access_decision(
            db, session=row, plate=row.plate, gate=gate, lane_direction="EXIT",
            outcome="EXIT_AUTHORIZED", reason=financial["reason"],
            parker_kind=row.parker_kind or "CASUAL", barrier_opened=passage_complete,
            extra={"source": source, **financial},
        )
        return {
            "ok": True, "action": "EXIT",
            "reason": "closed" if row.lifecycle == CLOSED else "waiting_passage",
            "pay_required": False,
            # Backwards-compatible UI meaning: the open command was accepted.
            # `passage_required` and the session lifecycle distinguish this
            # from physical passage confirmation.
            "barrier_opened": True,
            "barrier_command_accepted": True,
            "passage_required": not passage_complete,
            "assistance_required": False, "session": snapshot(row),
            "financial": financial,
            "message": "Exit authorized. Barrier opening.",
        }

    @staticmethod
    def _release_exit_claim(db: Session, row: ParkingSession, command_uuid: str) -> None:
        try:
            db.execute(update(ParkingSession).where(
                ParkingSession.id == row.id,
                ParkingSession.exit_open_command_uuid == command_uuid,
            ).values(exit_open_command_uuid=""))
            db.commit()
            db.refresh(row)
        except Exception:
            db.rollback()
            log.exception("could not release exit command claim session_id=%s", row.id)

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
