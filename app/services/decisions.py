"""Persist access decisions and gate commands.

Authorization Commit (docs/ZIRP_HIGH_THROUGHPUT_ARCHITECTURE.md section 4):
a lane controller *stages* the access decision and a REQUESTED gate command
(``stage_access_decision`` / ``stage_gate_request``, no commit) in the same
transaction as its session claim, and commits once, before any barrier
command is sent. ``record_gate_command`` then stores the hardware answer and
``finalize_access_decision`` the final outcome. A REQUESTED command that never
got an answer (restart, crash) becomes INTERRUPTED through
``interrupt_stale_gate_requests`` and is shown to an operator.

Nothing here calls HVX, GPIO, or payment providers.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AccessDecision, Gate, GateCommandRecord, ParkingSession

GATE_REQUESTED = "REQUESTED"
GATE_ACCEPTED = "ACCEPTED"
GATE_FAILED = "FAILED"
GATE_INTERRUPTED = "INTERRUPTED"

# A barrier command answers within a few seconds (GPIO hold 0.5 s, Board
# grace 0.3 s, HTTP time-outs). REQUESTED for longer than this means the
# process died or the answer was lost.
GATE_REQUEST_ANSWER_SECONDS = 60


def stage_access_decision(
    db: Session,
    *,
    session: ParkingSession | None,
    plate: str,
    gate: Gate | None,
    lane_direction: str,
    outcome: str,
    reason: str,
    parker_kind: str = "CASUAL",
    automatic: bool = True,
    barrier_opened: bool = False,
    latency_ms: int = 0,
    extra: dict[str, Any] | None = None,
) -> AccessDecision:
    """Add a decision row to the current transaction without committing."""
    row = AccessDecision(
        session_id=session.id if session else None,
        plate=plate,
        gate_id=gate.id if gate else None,
        lane_direction=(lane_direction or "ENTRY").upper(),
        outcome=outcome,
        reason=(reason or "")[:200],
        parker_kind=parker_kind or "CASUAL",
        automatic=automatic,
        barrier_opened=bool(barrier_opened),
        latency_ms=int(latency_ms or 0),
        extra=extra or {},
    )
    db.add(row)
    return row


def record_access_decision(
    db: Session,
    *,
    session: ParkingSession | None,
    plate: str,
    gate: Gate | None,
    lane_direction: str,
    outcome: str,
    reason: str,
    parker_kind: str = "CASUAL",
    automatic: bool = True,
    barrier_opened: bool = False,
    latency_ms: int = 0,
    extra: dict[str, Any] | None = None,
) -> AccessDecision:
    row = stage_access_decision(
        db, session=session, plate=plate, gate=gate, lane_direction=lane_direction, outcome=outcome,
        reason=reason, parker_kind=parker_kind, automatic=automatic, barrier_opened=barrier_opened,
        latency_ms=latency_ms, extra=extra,
    )
    db.commit()
    db.refresh(row)
    return row


def finalize_access_decision(
    db: Session,
    decision: AccessDecision,
    *,
    outcome: str,
    reason: str,
    barrier_opened: bool,
    extra: dict[str, Any] | None = None,
) -> AccessDecision:
    """Write the final outcome onto a decision committed before the command."""
    decision = db.merge(decision)
    decision.outcome = outcome
    decision.reason = (reason or "")[:200]
    decision.barrier_opened = bool(barrier_opened)
    if extra:
        decision.extra = {**(decision.extra or {}), **extra}
    db.commit()
    db.refresh(decision)
    return decision


def _command(db: Session, command_uuid: str) -> GateCommandRecord | None:
    return db.scalar(select(GateCommandRecord).where(GateCommandRecord.command_uuid == command_uuid))


def stage_gate_request(
    db: Session,
    *,
    gate: Gate | None,
    session: ParkingSession | None,
    reason: str,
    automatic: bool,
    command_uuid: str,
    side: str = "",
) -> GateCommandRecord:
    """Add a REQUESTED gate command (or re-arm one for a retry), no commit."""
    existing = _command(db, command_uuid)
    if existing is not None:
        if existing.state != GATE_ACCEPTED:
            existing.state = GATE_REQUESTED
            existing.completed_at = None
        return existing
    row = GateCommandRecord(
        command_uuid=command_uuid,
        gate_id=gate.id if gate else None,
        session_id=session.id if session else None,
        reason=(reason or "")[:200],
        automatic=bool(automatic),
        dry_run=False,
        ok=False,
        message="",
        state=GATE_REQUESTED,
        side=(side or "").upper()[:10],
    )
    db.add(row)
    return row


def ensure_gate_request_committed(
    db: Session,
    *,
    gate: Gate | None,
    session: ParkingSession | None,
    reason: str,
    automatic: bool,
    command_uuid: str,
    side: str = "",
) -> GateCommandRecord:
    """Make sure a REQUESTED row for this command is durable before sending it.

    Lane controllers commit it together with their decision; manual opens and
    other callers of ``_pulse_gate`` get it here.
    """
    existing = _command(db, command_uuid)
    if existing is not None and existing.state == GATE_REQUESTED:
        return existing
    row = stage_gate_request(db, gate=gate, session=session, reason=reason, automatic=automatic,
                             command_uuid=command_uuid, side=side)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        row = _command(db, command_uuid)
        if row is None:
            raise
    return row


def interrupt_stale_gate_requests(
    db: Session,
    *,
    now: datetime | None = None,
    older_than_seconds: float = GATE_REQUEST_ANSWER_SECONDS,
) -> list[GateCommandRecord]:
    """REQUESTED commands with no answer: mark INTERRUPTED and tell an operator.

    The barrier may or may not have moved. Nothing is re-sent automatically:
    the session keeps its claim, and an operator retries (same command uuid)
    or the passage time-out / an exit read completes the visit.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=older_than_seconds)
    rows = db.scalars(
        select(GateCommandRecord)
        .where(GateCommandRecord.state == GATE_REQUESTED, GateCommandRecord.created_at < cutoff)
        .order_by(GateCommandRecord.id).limit(200)
    ).all()
    for row in rows:
        row.state = GATE_INTERRUPTED
        row.completed_at = now
        row.message = row.message or "no answer recorded: restart or crash between authorization and barrier answer"
        session = db.get(ParkingSession, row.session_id) if row.session_id else None
        stage_access_decision(
            db, session=session, plate=(session.plate if session else ""),
            gate=db.get(Gate, row.gate_id) if row.gate_id else None,
            lane_direction=row.side or "ENTRY", outcome="GATE_COMMAND_INTERRUPTED",
            reason="barrier command authorized but its result was never recorded; check the lane",
            parker_kind=(session.parker_kind if session else "CASUAL") or "CASUAL",
            barrier_opened=False, extra={"command_uuid": row.command_uuid},
        )
    if rows:
        db.commit()
    return list(rows)


def record_gate_command(
    db: Session,
    *,
    gate: Gate | None,
    session: ParkingSession | None,
    reason: str,
    automatic: bool,
    dry_run: bool,
    ok: bool,
    message: str = "",
    command_uuid: str | None = None,
    side: str = "",
) -> GateCommandRecord:
    """Store the hardware answer for a command (normally its REQUESTED row)."""
    key = command_uuid or str(uuid.uuid4())
    existing = _command(db, key)
    if existing is not None:
        # Same command UUID is one logical command: the answer completes its
        # REQUESTED row, and a retry may improve a failed outcome. It never
        # creates a second row or downgrades an accepted command.
        return _apply_answer(db, existing, ok=ok, dry_run=dry_run, message=message)
    row = GateCommandRecord(
        command_uuid=key,
        gate_id=gate.id if gate else None,
        session_id=session.id if session else None,
        reason=(reason or "")[:200],
        automatic=bool(automatic),
        dry_run=bool(dry_run),
        ok=bool(ok),
        message=message or "",
        state=GATE_ACCEPTED if ok else GATE_FAILED,
        side=(side or "").upper()[:10],
        completed_at=datetime.now(timezone.utc),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        # A retry can race the first writer. command_uuid is the durable
        # idempotency key, so return the winner rather than surfacing a 500.
        db.rollback()
        existing = _command(db, key)
        if existing is None:
            raise
        return _apply_answer(db, existing, ok=ok, dry_run=dry_run, message=message)
    db.refresh(row)
    return row


def _apply_answer(db: Session, row: GateCommandRecord, *, ok: bool, dry_run: bool, message: str) -> GateCommandRecord:
    if row.ok and (not ok or row.state in {GATE_ACCEPTED, ""}):
        # Never downgrade an accepted command; an accepted one is final.
        return row
    row.ok = bool(ok)
    row.dry_run = bool(dry_run)
    row.message = message or row.message
    row.state = GATE_ACCEPTED if ok else GATE_FAILED
    row.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def decision_dict(row: AccessDecision) -> dict:
    return {
        "id": row.id,
        "session_id": row.session_id,
        "plate": row.plate,
        "gate_id": row.gate_id,
        "lane_direction": row.lane_direction,
        "outcome": row.outcome,
        "reason": row.reason,
        "parker_kind": row.parker_kind,
        "automatic": bool(row.automatic),
        "barrier_opened": bool(row.barrier_opened),
        "latency_ms": int(row.latency_ms or 0),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
