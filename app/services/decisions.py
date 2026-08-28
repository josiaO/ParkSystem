"""Persist access decisions and gate commands after the working engine acts.

These tables are an audit of parking outcomes. They do not call HVX, GPIO, or
payment providers.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import AccessDecision, Gate, GateCommandRecord, ParkingSession


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
    row = AccessDecision(
        session_id=session.id if session else None,
        plate=plate,
        gate_id=gate.id if gate else None,
        lane_direction=(lane_direction or "ENTRY").upper(),
        outcome=outcome,
        reason=reason[:200],
        parker_kind=parker_kind or "CASUAL",
        automatic=automatic,
        barrier_opened=bool(barrier_opened),
        latency_ms=int(latency_ms or 0),
        extra=extra or {},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


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
) -> GateCommandRecord:
    row = GateCommandRecord(
        command_uuid=command_uuid or str(uuid.uuid4()),
        gate_id=gate.id if gate else None,
        session_id=session.id if session else None,
        reason=(reason or "")[:200],
        automatic=bool(automatic),
        dry_run=bool(dry_run),
        ok=bool(ok),
        message=message or "",
    )
    db.add(row)
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
