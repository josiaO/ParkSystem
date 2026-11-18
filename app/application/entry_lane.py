"""Entry lane orchestrator. Callbacks submit an event; this module runs the sequence.

Presence → recognition candidate → admission → session → print → taken →
idempotent OPEN → vehicle passed → ACTIVE. Does not live in a FastAPI route,
camera callback, or UI. HVX GPIO stays in gates.controller.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable
from uuid import uuid4

from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from app.config import settings
from app.db import release_connection
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

# A repeat read of the same approach is normal; an open visit older than this
# for a car now at the entry means its exit was missed and needs an operator.
STALE_VISIT_SECONDS = 600

# One car read twice with a one-character OCR difference (T189EKP/T188EKP,
# 1302BLB/T302BLB) 2-3 s apart opened two sessions and would print two
# tickets. A near-identical plate on the same entry gate this soon is the same
# car: it is reported as a duplicate and the barrier is not opened again.
LOOKALIKE_WINDOW_SECONDS = 10.0
LOOKALIKE_MIN_SIMILARITY = 0.85


def recent_lookalike_session(db: Session, plate: str, gate_id: int | None) -> ParkingSession | None:
    """A session just opened on this gate for a plate one OCR slip away."""
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.core.plate import plate_similarity

    if not plate or gate_id is None:
        return None
    rows = db.scalars(
        select(ParkingSession)
        .where(or_(ParkingSession.entry_gate_id == int(gate_id), ParkingSession.gate_id == int(gate_id)))
        .order_by(ParkingSession.id.desc())
        .limit(5)
    ).all()
    now = datetime.now(timezone.utc)
    for row in rows:
        created = row.created_at
        if created is None:
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if (now - created).total_seconds() > LOOKALIKE_WINDOW_SECONDS:
            break                      # newest first: everything after is older
        other = str(row.plate or "")
        if other and other != plate and plate_similarity(other, plate) >= LOOKALIKE_MIN_SIMILARITY:
            return row
    return None


def _correct_stay_plate(db: Session, row: ParkingSession, stay, *, gate, parker_kind: str) -> str:
    """Move the visit to the stay's best-supported plate; returns the old plate if changed.

    Only an unpaid casual visit is corrected, and never onto a plate that
    already has its own open visit on this site.
    """
    from app.services.parking_sessions import active_for_plate

    best = stay.best_plate()
    old = str(row.plate or "")
    scores = stay.scores()
    if not best or best == old or scores.get(best, 0.0) <= scores.get(old, 0.0):
        return ""                          # a tie never moves the plate
    if float(row.amount_paid or 0) > 0 or (row.parker_kind or "CASUAL").upper() != "CASUAL":
        return ""
    other = active_for_plate(db, best, site_id=int(row.site_id or 1))
    if other is not None and other.id != row.id:
        return ""
    row.plate = best
    db.commit()
    db.refresh(row)
    scores = {p: round(v, 2) for p, v in scores.items()}
    record_access_decision(
        db, session=row, plate=best, gate=gate, lane_direction="ENTRY",
        outcome="PLATE_CORRECTED", reason=f"{old} -> {best} by {stay.repeats + 1} reads {scores}",
        parker_kind=parker_kind, barrier_opened=False,
    )
    return old


def policy_from_parking_settings(cfg: dict[str, Any] | None) -> LanePolicy:
    cfg = cfg or {}
    resolved = resolve_receipt_policy(cfg)
    return LanePolicy(
        receipt_required_before_open=policy_requires_taken(resolved),
        print_receipt_on_entry=policy_should_print(resolved),
        passage_sensing=str(
            cfg.get("passage_sensing")
            or ("WAIT_FOR_PASSAGE" if str(getattr(settings, "deployment_profile", "DEVELOPMENT")).upper() != "DEVELOPMENT" else "OPEN_COMMAND_COUNTS_AS_PASSED")
        ).upper(),
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
        entitlement = lookup_entitlement(db, plate, site_id=event_site_id, strict=True)
        if entitlement.registered and entitlement.plate:
            plate = entitlement.plate
        parker_kind = entitlement.kind if entitlement.registered else "CASUAL"
        subscriber = _is_subscriber(parker_kind) and policy.subscriber_skip_receipt

        # Repeated captures of a car still waiting at this entry: one visit,
        # and its plate follows the best-supported read (app/services/lane_stay).
        stay = None
        if camera is not None and not entitlement.registered:
            from app.services import lane_stay

            stay = lane_stay.observe(int(camera.id), plate, rec.confidence)
            if stay.repeats and stay.session_id:
                same = db.get(ParkingSession, int(stay.session_id))
                if same is not None and same.exit_time is None and same.closed_at is None:
                    return self._same_stay(db, same, stay, gate=gate, plate=plate, parker_kind=parker_kind,
                                           entitlement=entitlement, source=source)

        lookalike = None if entitlement.registered else recent_lookalike_session(db, plate, gate.id if gate else None)
        if lookalike is not None:
            if stay is not None:
                from app.services import lane_stay

                lane_stay.attach_session(int(camera.id), lookalike.id)
            record_access_decision(
                db, session=lookalike, plate=plate, gate=gate, lane_direction="ENTRY",
                outcome="DUPLICATE", reason=f"lookalike of {lookalike.plate} read moments ago",
                parker_kind=parker_kind, barrier_opened=False,
            )
            return {
                "ok": True,
                "action": "ENTRY",
                "reason": "duplicate_lookalike",
                "created_session": False,
                "duplicate": True,
                "barrier_opened": False,
                "existing_lifecycle": lookalike.lifecycle,
                "assistance_required": False,
                "stale_visit": False,
                "session": snapshot(lookalike),
                "entitlement": entitlement.__dict__,
                "source": source,
                "message": f"{plate} looks like {lookalike.plate} read moments ago on this gate; treated as the same car.",
            }

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
        if stay is not None:
            from app.services import lane_stay

            lane_stay.attach_session(int(camera.id), row.id)
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
            # No command is sent for a duplicate, so the barrier did not open
            # now. An old open visit for this plate (a missed exit) needs an
            # operator: report it instead of claiming the barrier opened.
            entered = row.entry_time.isoformat() if row.entry_time else ""
            from datetime import datetime, timezone
            created_at = row.created_at if row.created_at is None or row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc)
            stale_visit = bool(created_at and (datetime.now(timezone.utc) - created_at).total_seconds() > STALE_VISIT_SECONDS)
            return {
                "ok": True,
                "action": "ENTRY",
                "reason": "duplicate",
                "created_session": False,
                "duplicate": True,
                "barrier_opened": False,
                "existing_lifecycle": row.lifecycle,
                "assistance_required": stale_visit,
                "stale_visit": stale_visit,
                "session": snapshot(row),
                "entitlement": entitlement.__dict__,
                "source": source,
                "message": f"Open visit already exists for {row.plate} (since {entered or 'unknown'}). Barrier not opened.",
            }

        need_receipt = bool(policy.receipt_required_before_open) and not subscriber
        skip_print = subscriber and not entitlement.print_receipt
        from app.services.developer import printing_enabled
        should_print = printing_enabled(db) and (not skip_print) and (
            policy.print_receipt_on_entry or need_receipt or auto_take or entitlement.print_receipt
        )
        if should_print:
            printer = self._printer()
            if (
                need_receipt
                and str(getattr(settings, "deployment_profile", "DEVELOPMENT")).upper() != "DEVELOPMENT"
                and str(getattr(printer, "id", "")).lower() in {"simulated", "simulated_kiosk"}
            ):
                record_access_decision(
                    db, session=row, plate=row.plate, gate=gate, lane_direction="ENTRY",
                    outcome="ASSISTANCE_REQUIRED", reason="production printer is simulated",
                    parker_kind=parker_kind, barrier_opened=False,
                )
                return {
                    "ok": False,
                    "action": "ENTRY",
                    "reason": "printer_not_configured",
                    "created_session": True,
                    "duplicate": False,
                    "barrier_opened": False,
                    "assistance_required": True,
                    "session": snapshot(row),
                    "message": "A physical receipt printer must be configured before this lane can open.",
                }
            printed = await print_entry_receipt(db, row, printer=printer, policy=policy)
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

    def _same_stay(self, db: Session, row: ParkingSession, stay, *, gate, plate: str, parker_kind: str,
                   entitlement, source: str) -> dict[str, Any]:
        """Another capture of the car this stay already opened a visit for."""
        corrected_from = _correct_stay_plate(db, row, stay, gate=gate, parker_kind=parker_kind)
        record_access_decision(
            db, session=row, plate=plate, gate=gate, lane_direction="ENTRY",
            outcome="DUPLICATE", reason=f"same car still at the entry (read {stay.repeats + 1}: {plate})",
            parker_kind=parker_kind, barrier_opened=False,
        )
        message = f"{plate}: the same car is still at the entry; visit {row.plate} kept."
        if corrected_from:
            message = f"Plate corrected {corrected_from} -> {row.plate} after {stay.repeats + 1} reads of the same car."
        return {
            "ok": True,
            "action": "ENTRY",
            "reason": "plate_corrected" if corrected_from else "same_stay",
            "created_session": False,
            "duplicate": True,
            "barrier_opened": False,
            "existing_lifecycle": row.lifecycle,
            "assistance_required": False,
            "stale_visit": False,
            "plate_corrected_from": corrected_from or None,
            "stay_reads": stay.repeats + 1,
            "session": snapshot(row),
            "entitlement": entitlement.__dict__,
            "source": source,
            "message": message,
        }

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
        entitlement = lookup_entitlement(db, row.plate, site_id=row.site_id, strict=True)
        return await self._authorize_and_open(
            db, row, gate=gate or (db.get(Gate, row.gate_id) if row.gate_id else None),
            camera=camera, policy=policy, entitlement=entitlement, source="receipt_taken", created=False,
        )

    async def operator_admit_without_receipt(
        self,
        db: Session,
        row: ParkingSession,
        *,
        reason: str,
        user_id: int | None,
        policy: LanePolicy | None = None,
        gate: Gate | None = None,
        camera: Camera | None = None,
    ) -> dict[str, Any]:
        """Audited operator exception when no receipt can be confirmed.

        Used when the printer is missing/failed or no taken sensor is fitted.
        It records RECEIPT_OPERATOR_OVERRIDE in the audit log and then uses
        the normal authorization path (idempotent command claim, gate
        controller, access decision). It never runs for a closed/cancelled
        session and never bypasses developer gate switches.
        """
        from app.domain.parking_engine import ENTRY_CANCELLED
        from app.services.parking_sessions import mark_receipt_taken as persist_taken
        from app.services.receipt_jobs import operator_override

        policy = policy or LanePolicy(receipt_required_before_open=True)
        if row.lifecycle == ENTRY_CANCELLED or (row.status or "").upper() == "CLOSED":
            return {"ok": False, "action": "ENTRY", "reason": "session_closed", "barrier_opened": False,
                    "session": snapshot(row), "message": "This visit is closed or cancelled."}
        if row.lifecycle not in {GATE_OPEN_REQUESTED, VEHICLE_PASSED, ACTIVE}:
            operator_override(db, row, reason=reason, user_id=user_id)
            row.receipt_taken_at = row.receipt_taken_at or row.receipt_printed_at
            persist_taken(db, row, policy=policy)
            # The lifecycle needs RECEIPT_TAKEN to authorize entry, but the
            # record must say this was an operator override, not a sensor.
            row.receipt_status = "OVERRIDE"
            db.commit()
            db.refresh(row)
        entitlement = lookup_entitlement(db, row.plate, site_id=row.site_id, strict=True)
        return await self._authorize_and_open(
            db, row, gate=gate or (db.get(Gate, row.gate_id) if row.gate_id else None),
            camera=camera, policy=policy, entitlement=entitlement, source="operator_override", created=False,
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
        entitlement = lookup_entitlement(db, row.plate, site_id=row.site_id, strict=True)
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
        from app.services.developer import automatic_gate_opening_enabled, gate_opening_enabled, printing_enabled
        if policy.receipt_required_before_open and not printing_enabled(db):
            record_access_decision(
                db, session=row, plate=row.plate, gate=gate, lane_direction="ENTRY",
                outcome="ASSISTANCE_REQUIRED", reason="developer printing disabled",
                parker_kind=row.parker_kind or "CASUAL", barrier_opened=False,
            )
            return {
                "ok": False, "action": "ENTRY", "reason": "developer_printing_disabled",
                "created_session": created, "duplicate": False, "barrier_opened": False,
                "assistance_required": True, "session": snapshot(row),
                "entitlement": entitlement.__dict__, "source": source,
                "message": "Developer mode has printing disabled, so the receipt-required gate stays closed.",
            }
        if gate is not None and not automatic_gate_opening_enabled(db):
            record_access_decision(
                db, session=row, plate=row.plate, gate=gate, lane_direction="ENTRY",
                outcome="DEVELOPER_BLOCKED", reason="automatic gate opening disabled",
                parker_kind=row.parker_kind or "CASUAL", barrier_opened=False,
            )
            return {
                "ok": True, "action": "ENTRY", "reason": "developer_automatic_gate_disabled",
                "created_session": created, "duplicate": False, "barrier_opened": False,
                "assistance_required": False, "session": snapshot(row),
                "entitlement": entitlement.__dict__, "source": source,
                "message": "Developer mode is holding the automatic gate command; the session remains available for retry.",
            }
        if gate is not None and not gate_opening_enabled(db):
            record_access_decision(
                db, session=row, plate=row.plate, gate=gate, lane_direction="ENTRY",
                outcome="DEVELOPER_BLOCKED", reason="gate opening disabled",
                parker_kind=row.parker_kind or "CASUAL", barrier_opened=False,
            )
            return {
                "ok": True, "action": "ENTRY", "reason": "developer_gate_opening_disabled",
                "created_session": created, "duplicate": False, "barrier_opened": False,
                "assistance_required": False, "session": snapshot(row),
                "entitlement": entitlement.__dict__, "source": source,
                "message": "Developer mode has gate opening disabled; paper can be taken but the barrier will stay closed.",
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
            claimed = db.execute(update(ParkingSession).where(
                ParkingSession.id == row.id,
                or_(ParkingSession.open_command_uuid == "", ParkingSession.open_command_uuid.is_(None)),
            ).values(open_command_uuid=command_uuid))
            db.commit()
            db.refresh(row)
            if claimed.rowcount != 1:
                return {"ok": True, "action": "ENTRY", "reason": "gate_command_in_progress",
                        "duplicate": True, "barrier_opened": False, "session": snapshot(row)}
        opened = None
        from app.services.lane_timing import mark
        if gate is not None:
            mark("gate_requested", command_uuid=command_uuid)
        if gate is not None and self.opener is not None:
            cameras = _cameras(gate, camera)
            release_connection(db)
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
            release_connection(db)
            opened = await _pulse_gate(
                db, gate, cameras, reason=f"entry {row.plate}", side="ENTRY",
                led_text="WELCOME", session=row, automatic=True,
                command_uuid=command_uuid,
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
        barrier_command_accepted = bool(opened is None or (opened and opened.ok))
        passage_complete = policy.passage_fallback()
        barrier_opened = barrier_command_accepted and gate is not None and passage_complete
        record_access_decision(
            db, session=row, plate=row.plate, gate=gate, lane_direction="ENTRY",
            outcome="ENTRY_AUTHORIZED", reason="entry complete",
            parker_kind=row.parker_kind or "CASUAL", barrier_opened=barrier_opened,
        )
        return {
            "ok": True,
            "action": "ENTRY",
            "reason": "active",
            "created_session": created,
            "duplicate": False,
            "barrier_opened": barrier_opened,
            "barrier_command_accepted": barrier_command_accepted and gate is not None,
            "passage_required": not passage_complete,
            "assistance_required": False,
            "session": snapshot(row),
            "barrier": opened.__dict__ if opened is not None else {"ok": False, "message": "No gate assigned — session saved, barrier skipped"},
            "entitlement": entitlement.__dict__,
            "source": source,
            "message": (
                f"Registered {entitlement.kind} plate {row.plate} — barrier command accepted; waiting for passage."
                if entitlement.registered and gate is not None and not passage_complete
                else (f"Registered {entitlement.kind} plate {row.plate} — barrier opened."
                      if entitlement.registered and gate is not None
                      else ("Barrier command accepted; waiting for passage." if gate is not None and not passage_complete
                            else ("Barrier opening." if gate is not None else "Session saved. Assign this camera to a Gate to open barriers.")))
            ),
        }
