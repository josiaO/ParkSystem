"""Time-outs that keep visits moving when a lane has no sensor for a step.

* A barrier was opened but no passage sensor confirmed the car went through:
  after ``passage_timeout_seconds`` the passage is assumed (entry → ACTIVE,
  exit → CLOSED) and recorded as ``PASSAGE_ASSUMED``. Without this, a lane
  with no loop wired keeps every visit half-open forever.
* Optional, off by default (``stranded_entry_minutes`` = 0): an entry
  attempt never authorized is cancelled after that many minutes and recorded
  as ``ENTRY_EXPIRED``. It is off because the car may have been let in by
  other means; on SERVER01 this cancelled every casual visit after 15 min and
  their exits found no session. Abandoned attempts are superseded when the
  plate enters again, and an unconfirmed entry seen at an exit is completed.

* A barrier command committed as REQUESTED that never got an answer (the
  process died between the Authorization Commit and the hardware answer) is
  marked INTERRUPTED with a ``GATE_COMMAND_INTERRUPTED`` decision for an
  operator. Nothing is re-sent automatically.

Runs on the Site Server only. Each row is handled in its own transaction.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domain.parking_engine import (
    ENTRY_CANCELLED,
    EXIT_GATE_OPEN_REQUESTED,
    GATE_OPEN_REQUESTED,
    LanePolicy,
    RECEIPT_PRESENTED,
    RECEIPT_PRINTING,
    SESSION_CREATED,
)
from app.models import ParkingSession

log = logging.getLogger("smartpark")

DEFAULT_PASSAGE_TIMEOUT_SECONDS = 60
DEFAULT_STRANDED_ENTRY_MINUTES = 0
BATCH = 200
STRANDED_STATES = (SESSION_CREATED, RECEIPT_PRINTING, RECEIPT_PRESENTED)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _since(row: ParkingSession) -> datetime | None:
    return _aware(row.updated_at) or _aware(row.created_at)


def _setting(cfg: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(cfg.get(key, default))
    except (TypeError, ValueError):
        return float(default)


def sweep_once(db: Session, *, now: datetime | None = None, cfg: dict[str, Any] | None = None) -> dict[str, int]:
    from app.services.decisions import record_access_decision
    from app.services.parking_sessions import cancel_entry_attempt, mark_vehicle_passed
    from app.services.simulation import parking_settings

    now = _aware(now) or datetime.now(timezone.utc)
    cfg = cfg if cfg is not None else parking_settings(db)
    counts = {"entry_passage_assumed": 0, "exit_passage_assumed": 0, "entry_expired": 0, "gate_interrupted": 0}
    policy = LanePolicy(receipt_required_before_open=True)

    passage_timeout = _setting(cfg, "passage_timeout_seconds", DEFAULT_PASSAGE_TIMEOUT_SECONDS)
    if passage_timeout > 0:
        cutoff = now - timedelta(seconds=passage_timeout)
        rows = db.scalars(
            select(ParkingSession)
            .where(ParkingSession.lifecycle.in_([GATE_OPEN_REQUESTED, EXIT_GATE_OPEN_REQUESTED]))
            .where(or_(ParkingSession.updated_at < cutoff,
                       (ParkingSession.updated_at.is_(None)) & (ParkingSession.created_at < cutoff)))
            .order_by(ParkingSession.id).limit(BATCH)
        ).all()
        for row in rows:
            side = "EXIT" if row.lifecycle == EXIT_GATE_OPEN_REQUESTED else "ENTRY"
            try:
                # Assumed, not sensed: for a linked vehicle group this counts only
                # as EXIT_LANE evidence (the exit lane identified the car and the
                # barrier accepted). Groups that require passage proof stay locked.
                mark_vehicle_passed(db, row, policy=policy, side=side, evidence="EXIT_LANE")
            except Exception as exc:
                db.rollback()
                log.warning("passage time-out failed session=%s: %s", row.id, exc)
                continue
            counts["exit_passage_assumed" if side == "EXIT" else "entry_passage_assumed"] += 1
            record_access_decision(
                db, session=row, plate=row.plate, gate=None, lane_direction=side, outcome="PASSAGE_ASSUMED",
                reason=f"no passage signal within {int(passage_timeout)} s of the barrier command",
                parker_kind=row.parker_kind or "CASUAL", automatic=True, barrier_opened=False,
            )

    stranded_minutes = _setting(cfg, "stranded_entry_minutes", DEFAULT_STRANDED_ENTRY_MINUTES)
    if stranded_minutes > 0:
        cutoff = now - timedelta(minutes=stranded_minutes)
        rows = db.scalars(
            select(ParkingSession)
            .where(ParkingSession.lifecycle.in_(STRANDED_STATES))
            .where(ParkingSession.status != "CLOSED")
            .where(or_(ParkingSession.updated_at < cutoff,
                       (ParkingSession.updated_at.is_(None)) & (ParkingSession.created_at < cutoff)))
            .order_by(ParkingSession.id).limit(BATCH)
        ).all()
        for row in rows:
            try:
                cancel_entry_attempt(db, row, policy=policy)
            except Exception as exc:
                db.rollback()
                log.warning("stranded entry expiry failed session=%s: %s", row.id, exc)
                continue
            if row.lifecycle == ENTRY_CANCELLED:
                counts["entry_expired"] += 1
                record_access_decision(
                    db, session=row, plate=row.plate, gate=None, lane_direction="ENTRY", outcome="ENTRY_EXPIRED",
                    reason=f"entry not authorized within {int(stranded_minutes)} min (receipt/printer/driver left)",
                    parker_kind=row.parker_kind or "CASUAL", automatic=True, barrier_opened=False,
                )
    from app.services.decisions import interrupt_stale_gate_requests

    try:
        interrupted = interrupt_stale_gate_requests(db, now=now)
    except Exception as exc:
        db.rollback()
        interrupted = []
        log.warning("interrupted gate command sweep failed: %s", exc)
    counts["gate_interrupted"] = len(interrupted)
    from app.services import evidence

    try:
        counts["evidence_missing"] = evidence.mark_stale_pending(db, now=now)
    except Exception as exc:
        db.rollback()
        counts["evidence_missing"] = 0
        log.warning("evidence sweep failed: %s", exc)
    for row in interrupted:
        log.warning("GATE COMMAND INTERRUPTED command=%s gate=%s session=%s side=%s",
                    row.command_uuid, row.gate_id, row.session_id, row.side)
    if any(counts.values()):
        log.info("LANE SWEEP %s", counts)
    return counts


async def sweeper_loop(session_factory: Callable[[], Session] | None = None, interval: float = 30.0) -> None:
    from app.db import short_session

    factory = session_factory or short_session
    while True:
        try:
            def _run() -> None:
                with factory() as db:
                    sweep_once(db)
                # A paid car still inside after its exit grace owes more.
                from app.infrastructure.payments.ledger import reopen_expired_graces
                with factory() as db:
                    reopen_expired_graces(db)

            await asyncio.to_thread(_run)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("LANE SWEEP failed: %s", exc)
        await asyncio.sleep(interval)
