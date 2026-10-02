"""Persist parking sessions through the domain lifecycle.

Parking authority is the database: transactions and constraints, not
process-global maps. Callers drive events. Camera and barrier adapters
stay out of this module.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.parking import OPEN_STORED
from app.domain.parking_engine import (
    ACTIVE,
    AUTHORIZATION_DECISION,
    AUTHORIZED,
    CLOSED,
    DENIED_PAYMENT_REQUIRED,
    ENTRY_AUTHORIZED,
    ENTRY_CANCELLED,
    EXIT_GATE_OPEN_REQUESTED,
    EXIT_VEHICLE_DETECTED,
    EXIT_VEHICLE_PASSED,
    GATE_OPEN_REQUESTED,
    IDENTITY_RESOLVED,
    InvalidTransition,
    LanePolicy,
    RECEIPT_PRESENTED,
    RECEIPT_PRINTING,
    RECEIPT_TAKEN,
    SESSION_CREATED,
    SESSION_RESOLVED,
    TARIFF_CALCULATED,
    VEHICLE_DETECTED,
    VEHICLE_PASSED,
    apply_transition,
    infer_lifecycle,
    stored_status_for,
)
from app.domain.receipt_engine import new_human_reference, new_public_token
from app.domain.recognition import NormalizedRecognitionEvent
from app.domain.site import DEFAULT_SITE_ID
from app.core.plate import plate_similarity
from app.config import settings
from app.models import ParkingSession, as_utc, utcnow


def _policy(**over) -> LanePolicy:
    if isinstance(over.get("policy"), LanePolicy):
        return over["policy"]
    return LanePolicy(
        receipt_required_before_open=bool(over.get("receipt_required_before_open", False)),
        passage_sensing=str(over.get("passage_sensing") or "OPEN_COMMAND_COUNTS_AS_PASSED"),
        subscriber_skip_receipt=over.get("subscriber_skip_receipt", True),
    )


def _current(row: ParkingSession) -> str:
    return row.lifecycle or infer_lifecycle(row.status, side=row.lane_direction)


def _commit_transition(db: Session, row: ParkingSession, target: str, policy: LanePolicy) -> ParkingSession:
    current = _current(row)
    nxt = apply_transition(current, target, policy, parker_kind=row.parker_kind)
    if nxt == current and row.lifecycle == target:
        return row
    row.lifecycle = nxt
    receipt_required = bool(policy.receipt_required_before_open) and (row.parker_kind or "CASUAL").upper() == "CASUAL"
    row.status = stored_status_for(nxt, previous=row.status, receipt_required=receipt_required)
    row.updated_at = utcnow()
    if nxt == RECEIPT_PRINTING and not row.receipt_printed_at:
        row.receipt_status = row.receipt_status or "PRINTING"
    if nxt == RECEIPT_PRESENTED:
        row.receipt_status = "PRINTED"
        row.receipt_printed_at = row.receipt_printed_at or utcnow()
    if nxt == RECEIPT_TAKEN:
        row.receipt_status = "TAKEN"
        row.receipt_taken_at = row.receipt_taken_at or utcnow()
    if nxt == CLOSED:
        row.status = "CLOSED"
        row.exit_time = row.exit_time or utcnow()
        row.closed_at = row.closed_at or utcnow()
    if nxt == ENTRY_CANCELLED:
        row.status = "CLOSED"
        row.closed_at = row.closed_at or utcnow()
    db.commit()
    db.refresh(row)
    return row


def _allocate_identity(db: Session) -> tuple[str, str]:
    for _ in range(8):
        token = new_public_token()
        ref = new_human_reference()
        taken_token = db.scalar(select(ParkingSession.id).where(ParkingSession.public_token == token))
        taken_ref = db.scalar(select(ParkingSession.id).where(ParkingSession.human_reference == ref))
        if taken_token is None and taken_ref is None:
            return token, ref
    raise RuntimeError("Could not allocate a unique receipt token")


def session_by_entry_event(db: Session, site_id: int, event_id: str) -> ParkingSession | None:
    if not event_id:
        return None
    return db.scalar(
        select(ParkingSession).where(
            ParkingSession.site_id == site_id, ParkingSession.entry_event_id == event_id
        )
    )


def active_for_plate(
    db: Session,
    plate: str,
    *,
    site_id: int = DEFAULT_SITE_ID,
    for_update: bool = False,
) -> ParkingSession | None:
    plate = (plate or "").strip().upper()
    if not plate:
        return None
    stmt = (
        select(ParkingSession)
        .where(
            ParkingSession.site_id == site_id,
            ParkingSession.plate == plate,
            ParkingSession.status.in_(tuple(OPEN_STORED)),
        )
        .order_by(ParkingSession.id.desc())
    )
    if for_update:
        # PostgreSQL production: serialize competing exit-lane claims for the
        # same active session. SQLite ignores FOR UPDATE and remains suitable
        # for local development/tests, not multi-lane production authority.
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def recent_similar_entry(
    db: Session,
    plate: str,
    *,
    site_id: int,
    camera_id: int | None,
    lane_id: int | None,
) -> ParkingSession | None:
    """Collapse near-identical OCR reads from the same physical approach.

    Exact duplicate protection is enforced by database indexes. This extra
    guard handles the practical OCR case where one vehicle is read as
    T285DQP and, a moment later, T285DOP before it has left the entry lane.
    It is deliberately short-lived and lane/camera scoped so two legitimate
    similar registrations elsewhere are never merged.
    """
    if camera_id is None and lane_id is None:
        return None
    now = utcnow()
    window = float(getattr(settings, "entry_dedupe_seconds", 3.0) or 3.0)
    threshold = float(getattr(settings, "entry_dedupe_similarity", 0.85) or 0.85)
    stmt = (
        select(ParkingSession)
        .where(
            ParkingSession.site_id == int(site_id),
            ParkingSession.status.in_(tuple(OPEN_STORED)),
        )
        .order_by(ParkingSession.id.desc())
        .limit(20)
    )
    # PostgreSQL serializes competing entry claims; SQLite development still
    # relies on the unique exact-plate/event indexes.
    try:
        if db.get_bind().dialect.name != "sqlite":
            stmt = stmt.with_for_update()
    except Exception:
        pass
    for row in db.scalars(stmt).all():
        same_approach = (
            (camera_id is not None and row.camera_id == camera_id)
            or (lane_id is not None and row.entry_lane_id == lane_id)
        )
        if not same_approach:
            continue
        created = as_utc(row.created_at)
        if created is None:
            continue
        age = (now - created).total_seconds()
        if age < 0 or age > window:
            continue
        if plate_similarity(row.plate, plate) >= threshold:
            return row
    return None


def start_entry(
    db: Session,
    *,
    plate: str,
    event_id: str,
    site_id: int = DEFAULT_SITE_ID,
    plate_raw: str = "",
    gate_id: int | None = None,
    lane_id: int | None = None,
    camera_id: int | None = None,
    image_ref: str = "",
    parker_kind: str = "CASUAL",
    policy: LanePolicy | None = None,
) -> tuple[ParkingSession, bool]:
    """Create or reuse a site session for one recognition/presence event.

    Returns ``(session, created)``. Same ``event_id`` or an already-open plate
    at this site is reused (no second session).
    """
    policy = policy or LanePolicy()
    plate = (plate or "").strip().upper()
    if not plate:
        raise ValueError("No number plate")
    existing = session_by_entry_event(db, site_id, event_id)
    if existing is not None:
        return existing, False
    open_row = active_for_plate(db, plate, site_id=site_id)
    if open_row is not None:
        return open_row, False
    near_duplicate = recent_similar_entry(
        db,
        plate,
        site_id=site_id,
        camera_id=camera_id,
        lane_id=lane_id,
    )
    if near_duplicate is not None:
        return near_duplicate, False
    token, human = _allocate_identity(db)
    row = ParkingSession(
        site_id=site_id,
        plate=plate,
        plate_raw=(plate_raw or plate)[:32],
        plate_status="RESOLVED",
        gate_id=gate_id,
        entry_gate_id=gate_id,
        camera_id=camera_id,
        entry_lane_id=lane_id,
        lane_direction="ENTRY",
        status="WAITING_RECEIPT" if policy.receipt_required_before_open and parker_kind.upper() == "CASUAL" else "ACTIVE",
        lifecycle=VEHICLE_DETECTED,
        public_token=token,
        human_reference=human,
        entry_event_id=event_id or "",
        entry_image_ref=image_ref or "",
        parker_kind=parker_kind or "CASUAL",
        receipt_status="",
    )
    db.add(row)
    try:
        db.flush()
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        dup = session_by_entry_event(db, site_id, event_id) or active_for_plate(db, plate, site_id=site_id)
        if dup is None:
            raise
        return dup, False
    _commit_transition(db, row, IDENTITY_RESOLVED, policy)
    _commit_transition(db, row, SESSION_CREATED, policy)
    return row, True


def start_entry_from_recognition(
    db: Session,
    event: NormalizedRecognitionEvent | dict[str, Any],
    *,
    gate_id: int | None = None,
    policy: LanePolicy | None = None,
    parker_kind: str = "CASUAL",
) -> tuple[ParkingSession | None, bool]:
    """Create a session only from a normalized recognition event.

    LOW-confidence, held, or incomplete events return ``(None, False)``.
    """
    rec = event if isinstance(event, NormalizedRecognitionEvent) else NormalizedRecognitionEvent.from_mapping(event)
    candidate = rec.as_entry_candidate()
    if candidate is None:
        return None, False
    site_id = int(candidate["site_id"] or DEFAULT_SITE_ID)
    return start_entry(
        db,
        plate=str(candidate["plate_normalized"]),
        event_id=str(candidate["event_id"]),
        site_id=site_id,
        plate_raw=str(candidate.get("plate_raw") or ""),
        gate_id=gate_id,
        lane_id=candidate.get("lane_id"),
        camera_id=candidate.get("camera_id"),
        image_ref=str(candidate.get("image_ref") or ""),
        parker_kind=parker_kind,
        policy=policy,
    )


def advance(db: Session, row: ParkingSession, target: str, *, policy: LanePolicy | None = None) -> ParkingSession:
    return _commit_transition(db, row, target, policy or LanePolicy())


def complete_casual_entry(db: Session, row: ParkingSession, *, policy: LanePolicy | None = None) -> ParkingSession:
    """Drive SESSION_CREATED through ACTIVE using lane policy (no hardware)."""
    policy = policy or LanePolicy()
    subscriber = (row.parker_kind or "CASUAL").upper() not in {"CASUAL", ""}
    if policy.receipt_required_before_open and not subscriber:
        for step in (RECEIPT_PRINTING, RECEIPT_PRESENTED, RECEIPT_TAKEN, ENTRY_AUTHORIZED, GATE_OPEN_REQUESTED):
            row = advance(db, row, step, policy=policy)
    else:
        row = advance(db, row, ENTRY_AUTHORIZED, policy=policy)
        row = advance(db, row, GATE_OPEN_REQUESTED, policy=policy)
    if policy.passage_fallback():
        row = advance(db, row, ACTIVE, policy=policy)
    else:
        row = advance(db, row, VEHICLE_PASSED, policy=policy)
        row = advance(db, row, ACTIVE, policy=policy)
    return row


def mark_receipt_taken(db: Session, row: ParkingSession, *, policy: LanePolicy | None = None) -> ParkingSession:
    policy = policy or LanePolicy(receipt_required_before_open=True)
    current = _current(row)
    if current in {RECEIPT_TAKEN, ENTRY_AUTHORIZED, GATE_OPEN_REQUESTED, VEHICLE_PASSED, ACTIVE}:
        return row
    if current == SESSION_CREATED:
        row = advance(db, row, RECEIPT_PRINTING, policy=policy)
        row = advance(db, row, RECEIPT_PRESENTED, policy=policy)
    elif current == RECEIPT_PRINTING:
        row = advance(db, row, RECEIPT_PRESENTED, policy=policy)
    return advance(db, row, RECEIPT_TAKEN, policy=policy)


def cancel_entry_attempt(db: Session, row: ParkingSession, *, policy: LanePolicy | None = None) -> ParkingSession:
    """Vehicle left before the receipt was taken. Releases the open-plate lock."""
    policy = policy or LanePolicy(receipt_required_before_open=True)
    current = _current(row)
    if current == ENTRY_CANCELLED or row.status == "CLOSED":
        return row
    return advance(db, row, ENTRY_CANCELLED, policy=policy)


def request_entry_open(db: Session, row: ParkingSession, *, command_uuid: str, policy: LanePolicy | None = None) -> ParkingSession:
    policy = policy or LanePolicy()
    current = _current(row)
    if (
        command_uuid
        and row.open_command_uuid == command_uuid
        and current in {GATE_OPEN_REQUESTED, VEHICLE_PASSED, ACTIVE}
    ):
        return row
    if current in {GATE_OPEN_REQUESTED, VEHICLE_PASSED, ACTIVE}:
        return row
    if current == SESSION_CREATED and policy.receipt_required_before_open and (row.parker_kind or "CASUAL").upper() == "CASUAL":
        raise InvalidTransition("SESSION_CREATED -> GATE_OPEN_REQUESTED is not allowed")
    if current == RECEIPT_TAKEN:
        row = advance(db, row, ENTRY_AUTHORIZED, policy=policy)
        current = _current(row)
    subscriber = (row.parker_kind or "CASUAL").upper() not in {"CASUAL", ""}
    skip_receipt = (not policy.receipt_required_before_open) or (subscriber and policy.subscriber_skip_receipt)
    if current == SESSION_CREATED and skip_receipt:
        row = advance(db, row, ENTRY_AUTHORIZED, policy=policy)
        current = _current(row)
    if current != ENTRY_AUTHORIZED:
        raise InvalidTransition(f"{current} -> GATE_OPEN_REQUESTED is not allowed")
    row = advance(db, row, GATE_OPEN_REQUESTED, policy=policy)
    row.open_command_uuid = command_uuid
    db.commit()
    db.refresh(row)
    return row


def mark_vehicle_passed(db: Session, row: ParkingSession, *, policy: LanePolicy | None = None, side: str = "ENTRY") -> ParkingSession:
    policy = policy or LanePolicy()
    current = _current(row)
    if (side or "ENTRY").upper() == "EXIT":
        if current in {CLOSED, EXIT_VEHICLE_PASSED}:
            return row
        if current == EXIT_GATE_OPEN_REQUESTED:
            row = advance(db, row, EXIT_VEHICLE_PASSED, policy=policy)
        if _current(row) == EXIT_VEHICLE_PASSED:
            return advance(db, row, CLOSED, policy=policy)
        raise InvalidTransition(f"{current} -> EXIT_VEHICLE_PASSED is not allowed")
    if current in {VEHICLE_PASSED, ACTIVE}:
        if current == VEHICLE_PASSED:
            return advance(db, row, ACTIVE, policy=policy)
        return row
    if current == GATE_OPEN_REQUESTED:
        row = advance(db, row, VEHICLE_PASSED, policy=policy)
        return advance(db, row, ACTIVE, policy=policy)
    raise InvalidTransition(f"{current} -> VEHICLE_PASSED is not allowed")


def start_exit(
    db: Session,
    *,
    plate: str,
    event_id: str,
    site_id: int = DEFAULT_SITE_ID,
    lane_id: int | None = None,
    camera_id: int | None = None,
    gate_id: int | None = None,
    policy: LanePolicy | None = None,
    paid: bool | None = None,
) -> tuple[ParkingSession | None, str]:
    """Resolve the site-wide open session and run the exit machine to a decision.

    Returns ``(session, outcome)`` where outcome is AUTHORIZED, DENIED_PAYMENT_REQUIRED,
    or empty if no session. Duplicate ``event_id`` does not close twice.
    """
    policy = policy or LanePolicy()
    plate = (plate or "").strip().upper()
    if event_id:
        by_exit = db.scalar(
            select(ParkingSession).where(
                ParkingSession.site_id == site_id, ParkingSession.exit_event_id == event_id
            )
        )
        if by_exit is not None:
            return by_exit, _current(by_exit)
    row = active_for_plate(db, plate, site_id=site_id, for_update=True)
    if row is None:
        return None, ""
    if row.exit_event_id and event_id and row.exit_event_id == event_id:
        return row, _current(row)
    current = _current(row)
    if (
        row.exit_event_id
        and event_id
        and row.exit_event_id != event_id
        and current != DENIED_PAYMENT_REQUIRED
    ):
        # One event owns an in-flight exit attempt. A different event may only
        # take over after a payment denial, when a new approach is expected.
        return row, current
    if current == CLOSED:
        return row, CLOSED

    # Claim the session for this physical exit attempt before lifecycle commits
    # release the row lock. This is the durable duplicate-suppression boundary.
    row.exit_event_id = event_id or row.exit_event_id
    row.exit_lane_id = lane_id if lane_id is not None else row.exit_lane_id
    row.exit_camera_id = camera_id if camera_id is not None else row.exit_camera_id
    if gate_id is not None:
        row.exit_gate_id = gate_id
    row.lane_direction = "EXIT"
    db.commit()
    db.refresh(row)

    if _current(row) == ACTIVE:
        row = advance(db, row, EXIT_VEHICLE_DETECTED, policy=policy)
    elif _current(row) not in {
        EXIT_VEHICLE_DETECTED, SESSION_RESOLVED, TARIFF_CALCULATED, AUTHORIZATION_DECISION,
        AUTHORIZED, DENIED_PAYMENT_REQUIRED, EXIT_GATE_OPEN_REQUESTED, EXIT_VEHICLE_PASSED,
    }:
        raise InvalidTransition(f"cannot exit from {_current(row)}")
    if _current(row) == DENIED_PAYMENT_REQUIRED:
        row = advance(db, row, TARIFF_CALCULATED, policy=policy)
    if _current(row) == EXIT_VEHICLE_DETECTED:
        row = advance(db, row, SESSION_RESOLVED, policy=policy)
    if _current(row) == SESSION_RESOLVED:
        row = advance(db, row, TARIFF_CALCULATED, policy=policy)
    if _current(row) == TARIFF_CALCULATED:
        row = advance(db, row, AUTHORIZATION_DECISION, policy=policy)
    due = float(row.amount_due or 0)
    have = float(row.amount_paid or 0)
    subscriber = (row.parker_kind or "CASUAL").upper() not in {"CASUAL", ""}
    allow = subscriber or (paid if paid is not None else have >= due)
    if _current(row) == AUTHORIZATION_DECISION:
        row = advance(db, row, AUTHORIZED if allow else DENIED_PAYMENT_REQUIRED, policy=policy)
    return row, _current(row)


def complete_authorized_exit(db: Session, row: ParkingSession, *, policy: LanePolicy | None = None, command_uuid: str = "") -> ParkingSession:
    policy = policy or LanePolicy()
    if _current(row) == DENIED_PAYMENT_REQUIRED:
        raise InvalidTransition("DENIED_PAYMENT_REQUIRED -> EXIT_GATE_OPEN_REQUESTED is not allowed")
    if _current(row) == AUTHORIZED:
        row = advance(db, row, EXIT_GATE_OPEN_REQUESTED, policy=policy)
    if command_uuid:
        if row.exit_open_command_uuid == command_uuid and _current(row) in {CLOSED, EXIT_GATE_OPEN_REQUESTED, EXIT_VEHICLE_PASSED}:
            return row
        row.exit_open_command_uuid = command_uuid
        db.commit()
    if policy.passage_fallback() and _current(row) == EXIT_GATE_OPEN_REQUESTED:
        # Commissioning fallback only: a successful OPEN command is treated as
        # passage when no physical passage sensor is configured.
        return advance(db, row, CLOSED, policy=policy)
    # With WAIT_FOR_PASSAGE, the session deliberately remains open until a
    # loop/beam/sensor calls mark_vehicle_passed(side="EXIT").
    return row


def snapshot(row: ParkingSession) -> dict[str, Any]:
    return {
        "id": row.id,
        "site_id": row.site_id,
        "plate": row.plate,
        "status": row.status,
        "lifecycle": _current(row),
        "entry_lane_id": row.entry_lane_id,
        "exit_lane_id": row.exit_lane_id,
        "gate_id": row.gate_id,
        "entry_gate_id": getattr(row, "entry_gate_id", None),
        "exit_gate_id": getattr(row, "exit_gate_id", None),
        "camera_id": row.camera_id,
        "simulated": bool(row.simulated),
        "entry_event_id": row.entry_event_id,
        "exit_event_id": row.exit_event_id,
        "public_token": row.public_token,
        "human_reference": row.human_reference,
        "print_job_id": row.print_job_id,
        "print_job_status": row.print_job_status,
        "print_retry_count": int(row.print_retry_count or 0),
        "parker_kind": row.parker_kind,
        "receipt_status": row.receipt_status,
        "open_command_uuid": row.open_command_uuid,
        "exit_open_command_uuid": getattr(row, "exit_open_command_uuid", ""),
    }
