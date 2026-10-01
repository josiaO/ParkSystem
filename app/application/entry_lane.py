"""Entry lane orchestrator. Callbacks submit an event; this module runs the sequence.

Presence → recognition candidate → admission → session → print → taken →
idempotent OPEN → vehicle passed → ACTIVE. Does not live in a FastAPI route,
camera callback, or UI. HVX GPIO stays in gates.controller.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable
from uuid import uuid4

from sqlalchemy.orm import Session

from app.domain.parking_engine import (
    ACTIVE,
    ENTRY_AUTHORIZED,
    GATE_OPEN_REQUESTED,
    LanePolicy,
    RECEIPT_TAKEN,
    VEHICLE_PASSED,
)
from app.domain.recognition import NormalizedRecognitionEvent
from app.infrastructure.hardware.receipt_printers import receipt_printer_for
from app.models import Camera, Gate, ParkingSession
from app.services.access import lookup_entitlement
from app.services.decisions import record_access_decision, record_gate_command
from app.services.parking_sessions import (
    cancel_entry_attempt,
    mark_vehicle_passed,
    request_entry_open,
    snapshot,
    start_entry_from_recognition,
)
from app.services.receipt_jobs import mark_receipt_taken, print_entry_receipt
from app.services.receipts import policy_requires_taken, policy_should_print, resolve_receipt_policy


GateOpener = Callable[..., Awaitable[Any]]


def policy_from_parking_settings(cfg: dict[str, Any] | None) -> LanePolicy:
    cfg = cfg or {}
    resolved = resolve_receipt_policy(cfg)
    return LanePolicy(
        receipt_required_before_open=policy_requires_taken(resolved),
        print_receipt_on_entry=policy_should_print(resolved),
        subscriber_skip_receipt=True,
    )


def _is_subscriber(kind: str | None) -> bool:
    return (kind or "CASUAL").upper() not in {"CASUAL", ""}


def _cameras(gate: Gate | None, camera: Camera | None, side: str = "ENTRY") -> list[Camera]:
    if camera is not None:
        return [camera]
    if gate is None:
        return []
    want = (side or "ENTRY").upper()
    return [row for row in (gate.cameras or []) if (row.lane_direction or "").upper() == want]


class EntryLaneController:
    """One application service for the full casual/subscriber entry path."""

    def __init__(self, *, printer=None, opener: GateOpener | None = None) -> None:
        self.printer = printer
        self.opener = opener

    def _printer(self):
        if self.printer is None:
            self.printer = receipt_printer_for("simulated_kiosk")
        return self.printer

    async def submit(
        self,
        db: Session,
        event: NormalizedRecognitionEvent | dict[str, Any],
        *,
        gate: Gate | None = None,
        camera: Camera | None = None,
        policy: LanePolicy | None = None,
        occupied: bool | None = True,
        auto_take: bool = False,
        simulated: bool = False,
        source: str = "camera",
    ) -> dict[str, Any]:
        """Ingest one recognition event. Does not pulse a gate until authorized."""
        policy = policy or LanePolicy(receipt_required_before_open=True)
        rec = event if isinstance(event, NormalizedRecognitionEvent) else NormalizedRecognitionEvent.from_mapping(event)
        if occupied is False:
            return {
                "ok": False,
                "action": "ENTRY",
                "reason": "no_presence",
                "created_session": False,
                "barrier_opened": False,
                "assistance_required": False,
                "duplicate": False,
                "session": None,
                "message": "No vehicle presence on this lane.",
            }
        if rec.as_entry_candidate() is None:
            return {
                "ok": False,
                "action": "ENTRY",
                "reason": "recognition_timeout",
                "created_session": False,
                "barrier_opened": False,
                "assistance_required": False,
                "duplicate": False,
                "session": None,
                "message": "No parking candidate from recognition.",
            }

        plate = rec.plate_normalized
        event_site_id = int(rec.site_id or (camera.site_id if camera is not None else 0) or (gate.site_id if gate is not None else 0) or 1)
        entitlement = lookup_entitlement(db, plate, site_id=event_site_id)
        if entitlement.registered and entitlement.plate:
            plate = entitlement.plate
        parker_kind = entitlement.kind if entitlement.registered else "CASUAL"
        subscriber = _is_subscriber(parker_kind) and policy.subscriber_skip_receipt

        payload = rec.as_dict()
        payload["plate_normalized"] = plate
        payload["plate_text"] = plate
        row, created = start_entry_from_recognition(
            db, payload, gate_id=gate.id if gate else None, policy=policy, parker_kind=parker_kind,
        )
        if row is None:
            return {
                "ok": False,
                "action": "ENTRY",
                "reason": "recognition_timeout",
                "created_session": False,
                "barrier_opened": False,
                "session": None,
                "message": "No parking candidate from recognition.",
            }
        if entitlement.registered:
            row.access_plan_id = entitlement.plan_id
            row.vehicle_id = entitlement.vehicle_id
            row.simulated = bool(simulated)
            db.commit()
            db.refresh(row)
        elif simulated and not row.simulated:
            row.simulated = True
            db.commit()
            db.refresh(row)

        if not created:
            already_open = row.lifecycle in {GATE_OPEN_REQUESTED, VEHICLE_PASSED, ACTIVE}
            return {
                "ok": True,
                "action": "ENTRY",
                "reason": "duplicate",
                "created_session": False,
                "duplicate": True,
                "barrier_opened": already_open,
                "assistance_required": False,
                "session": snapshot(row),
                "entitlement": entitlement.__dict__,
                "source": source,
                "message": "Open session already exists for this plate.",
            }

        need_receipt = bool(policy.receipt_required_before_open) and not subscriber
        skip_print = subscriber and not entitlement.print_receipt
        should_print = (not skip_print) and (
            policy.print_receipt_on_entry or need_receipt or auto_take or entitlement.print_receipt
        )
        if should_print:
            printed = await print_entry_receipt(db, row, printer=self._printer(), policy=policy)
            db.refresh(row)
            if printed.get("assistance_required") and need_receipt:
                record_access_decision(
                    db, session=row, plate=row.plate, gate=gate, lane_direction="ENTRY",
                    outcome="ASSISTANCE_REQUIRED", reason=str(printed.get("error") or "printer failed"),
                    parker_kind=parker_kind, barrier_opened=False,
                )
                return {
                    "ok": False,
                    "action": "ENTRY",
                    "reason": "printer_failed",
                    "created_session": True,
                    "duplicate": False,
                    "barrier_opened": False,
                    "assistance_required": True,
                    "session": snapshot(row),
                    "print": printed,
                    "entitlement": entitlement.__dict__,
                    "source": source,
                    "message": "Printer failed. Gate stays closed.",
                }
            if need_receipt and not auto_take:
                record_access_decision(
                    db, session=row, plate=row.plate, gate=gate, lane_direction="ENTRY",
                    outcome="WAITING_RECEIPT", reason="receipt presented",
                    parker_kind=parker_kind, barrier_opened=False,
                )
                return {
                    "ok": True,
                    "action": "ENTRY",
                    "reason": "waiting_receipt",
                    "created_session": True,
                    "duplicate": False,
                    "barrier_opened": False,
                    "assistance_required": False,
                    "session": snapshot(row),
                    "print": printed,
                    "qr_payload": printed.get("qr_payload"),
                    "entitlement": entitlement.__dict__,
                    "source": source,
                    "message": "Receipt printed. Take the receipt to open the barrier.",
                }
            if need_receipt:
                await mark_receipt_taken(db, row, printer=self._printer(), policy=policy)
                db.refresh(row)

        return await self._authorize_and_open(
            db, row, gate=gate, camera=camera, policy=policy,
            entitlement=entitlement, source=source, created=True,
        )

    async def confirm_receipt_taken(
        self,
        db: Session,
        row: ParkingSession,
        *,
        policy: LanePolicy | None = None,
        gate: Gate | None = None,
        camera: Camera | None = None,
        sensor_confirmed: bool = False,
    ) -> dict[str, Any]:
        policy = policy or LanePolicy(receipt_required_before_open=True)
        await mark_receipt_taken(
            db, row, printer=self._printer(), policy=policy, sensor_confirmed=sensor_confirmed,
        )
        db.refresh(row)
        entitlement = lookup_entitlement(db, row.plate, site_id=row.site_id)
        return await self._authorize_and_open(
            db, row, gate=gate or (db.get(Gate, row.gate_id) if row.gate_id else None),
            camera=camera, policy=policy, entitlement=entitlement, source="receipt_taken", created=False,
        )

    async def retry_gate(
        self,
        db: Session,
        row: ParkingSession,
        *,
        policy: LanePolicy | None = None,
        gate: Gate | None = None,
        camera: Camera | None = None,
        command_uuid: str = "",
    ) -> dict[str, Any]:
        policy = policy or LanePolicy(receipt_required_before_open=True)
        entitlement = lookup_entitlement(db, row.plate, site_id=row.site_id)
        return await self._authorize_and_open(
            db, row, gate=gate or (db.get(Gate, row.gate_id) if row.gate_id else None),
            camera=camera, policy=policy, entitlement=entitlement, source="gate_retry",
            created=False, command_uuid=command_uuid,
        )

    async def vehicle_left(
        self,
        db: Session,
        row: ParkingSession,
        *,
        policy: LanePolicy | None = None,
    ) -> dict[str, Any]:
        policy = policy or LanePolicy(receipt_required_before_open=True)
        if row.lifecycle in {RECEIPT_TAKEN, ENTRY_AUTHORIZED, GATE_OPEN_REQUESTED, VEHICLE_PASSED, ACTIVE}:
            return {"ok": False, "reason": "too_late", "session": snapshot(row), "barrier_opened": False}
        row = cancel_entry_attempt(db, row, policy=policy)
        return {
            "ok": True,
            "reason": "vehicle_left",
            "session": snapshot(row),
            "barrier_opened": False,
            "lifecycle": row.lifecycle,
        }

    async def _authorize_and_open(
        self,
        db: Session,
        row: ParkingSession,
        *,
        gate: Gate | None,
        camera: Camera | None,
        policy: LanePolicy,
        entitlement,
        source: str,
        created: bool,
        command_uuid: str = "",
    ) -> dict[str, Any]:
        if row.lifecycle in {GATE_OPEN_REQUESTED, VEHICLE_PASSED, ACTIVE}:
            return {
                "ok": True,
                "action": "ENTRY",
                "reason": "already_open",
                "created_session": created,
                "duplicate": True,
                "barrier_opened": True,
                "assistance_required": False,
                "session": snapshot(row),
                "entitlement": entitlement.__dict__,
                "source": source,
                "message": "Gate command already applied.",
            }
        existing_command = row.open_command_uuid or ""
        command_uuid = command_uuid or existing_command or uuid4().hex
        if existing_command and source != "gate_retry":
            return {
                "ok": True,
                "action": "ENTRY",
                "reason": "gate_command_in_progress",
                "created_session": created,
                "duplicate": True,
                "barrier_opened": False,
                "assistance_required": False,
                "session": snapshot(row),
                "entitlement": entitlement.__dict__,
                "source": source,
                "message": "An entry barrier command is already in progress.",
                "open_command_uuid": existing_command,
            }
        if not row.open_command_uuid:
            row.open_command_uuid = command_uuid
            db.commit()
            db.refresh(row)
        opened = None
        if gate is not None and self.opener is not None:
            cameras = _cameras(gate, camera)
            opened = await self.opener(
                db, gate, cameras, reason=f"entry {row.plate}", session=row, side="ENTRY",
                command_uuid=command_uuid,
            )
            record_gate_command(
                db, gate=gate, session=row, reason=f"entry {row.plate}",
                automatic=True, dry_run=bool(getattr(opened, "simulated", False)),
                ok=bool(opened and opened.ok), message=getattr(opened, "message", "") or "",
                command_uuid=command_uuid,
            )
            if not opened or not opened.ok:
                record_access_decision(
                    db, session=row, plate=row.plate, gate=gate, lane_direction="ENTRY",
                    outcome="GATE_UNAVAILABLE", reason=getattr(opened, "message", "") or "gate unavailable",
                    parker_kind=row.parker_kind or "CASUAL", barrier_opened=False,
                )
                return {
                    "ok": False,
                    "action": "ENTRY",
                    "reason": "gate_unavailable",
                    "created_session": created,
                    "duplicate": False,
                    "barrier_opened": False,
                    "assistance_required": True,
                    "session": snapshot(row),
                    "entitlement": entitlement.__dict__,
                    "source": source,
                    "message": "Gate controller unavailable. Session kept; not reprinting.",
                    "open_command_uuid": command_uuid,
                }
        elif gate is not None and self.opener is None:
            from app.services.simulation import _pulse_gate
            cameras = _cameras(gate, camera)
            opened = await _pulse_gate(
                db, gate, cameras, reason=f"entry {row.plate}", side="ENTRY",
                led_text="WELCOME", session=row, automatic=True,
            )
            if opened is not None and not opened.ok:
                record_access_decision(
                    db, session=row, plate=row.plate, gate=gate, lane_direction="ENTRY",
                    outcome="GATE_UNAVAILABLE", reason=opened.message or "gate unavailable",
                    parker_kind=row.parker_kind or "CASUAL", barrier_opened=False,
                )
                return {
                    "ok": False,
                    "action": "ENTRY",
                    "reason": "gate_unavailable",
                    "created_session": created,
                    "barrier_opened": False,
                    "assistance_required": True,
                    "session": snapshot(row),
                    "entitlement": entitlement.__dict__,
                    "source": source,
                    "message": "Gate controller unavailable. Session kept; not reprinting.",
                }

        row = request_entry_open(db, row, command_uuid=command_uuid, policy=policy)
        if policy.passage_fallback():
            row = mark_vehicle_passed(db, row, policy=policy)
        barrier_ok = bool(opened is None or (opened and opened.ok))
        record_access_decision(
            db, session=row, plate=row.plate, gate=gate, lane_direction="ENTRY",
            outcome="ENTRY_AUTHORIZED", reason="entry complete",
            parker_kind=row.parker_kind or "CASUAL", barrier_opened=barrier_ok and gate is not None,
        )
        return {
            "ok": True,
            "action": "ENTRY",
            "reason": "active",
            "created_session": created,
            "duplicate": False,
            "barrier_opened": barrier_ok and gate is not None,
            "assistance_required": False,
            "session": snapshot(row),
            "barrier": opened.__dict__ if opened is not None else {"ok": False, "message": "No gate assigned — session saved, barrier skipped"},
            "entitlement": entitlement.__dict__,
            "source": source,
            "message": (
                f"Registered {entitlement.kind} plate {row.plate} — barrier opened."
                if entitlement.registered and gate is not None
                else ("Barrier opening." if gate is not None else "Session saved. Assign this camera to a Gate to open barriers.")
            ),
        }
