"""Linked-vehicle authorization groups: slot claims, exit evidence, manual exit, reconciliation.

Rules live in app/domain/vehicle_groups.py. This module applies them to the
database. The guarantees:

* A slot is claimed in the **same transaction** that inserts the parking
  session (``claim_for_session`` is called by ``parking_sessions.start_entry``
  between flush and commit). If the claim fails, the session is not created.
* PostgreSQL: the group row is locked ``FOR UPDATE`` first, so competing lanes
  queue behind each other and the loser sees the winner's slot. The partial
  unique index ``uq_vehicle_group_occupancy_live_slot`` is the final authority
  in every database (SQLite included): two live occupancies can never hold the
  same (group, slot).
* A slot is released only by exit evidence the group's policy accepts, by an
  operator's confirmation, or by a supervisor. A barrier-open command alone
  never releases it; manual boom openings do not touch sessions or slots.
* Every change of an occupancy writes an ``exit_confirmations`` audit row.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.domain import vehicle_groups as vg
from app.domain.site import DEFAULT_SITE_ID
from app.models import (
    ExitConfirmation,
    ParkingSession,
    RegisteredVehicle,
    User,
    VehicleGroup,
    VehicleGroupOccupancy,
    VisitorPass,
    as_utc,
    utcnow,
)

log = logging.getLogger("smartpark")

ACTION_AUTO_RELEASED = "AUTO_RELEASED"
ACTION_EXIT_UNCONFIRMED = "EXIT_UNCONFIRMED"
ACTION_MANUAL_CONFIRMED = "MANUAL_EXIT_CONFIRMED"
ACTION_MANUAL_UNCERTAIN = "MANUAL_EXIT_UNCERTAIN"
ACTION_SUPERVISOR_RELEASED = "SUPERVISOR_RELEASED"
ACTION_SUPERVISOR_KEPT_INSIDE = "SUPERVISOR_KEPT_INSIDE"
ACTION_SUPERVISOR_KEPT_LOCKED = "SUPERVISOR_KEPT_LOCKED"
ACTION_SEEN_AT_ENTRY = "RELEASED_SEEN_AT_ENTRY"

MIN_REASON = 3


class NeedsSupervisor(PermissionError):
    """An uncertain exit is under reconciliation; only a supervisor may decide it."""


# ------------------------------------------------------------------ helpers

def _postgres(db: Session) -> bool:
    try:
        return db.get_bind().dialect.name == "postgresql"
    except Exception:
        return False


def _reason(text: str | None) -> str:
    text = (text or "").strip()
    if len(text) < MIN_REASON:
        raise ValueError(f"A reason (at least {MIN_REASON} characters) is required")
    return text[:240]


def _operator_name(user: User | None) -> str:
    if user is None:
        return ""
    return str(user.full_name or user.username or f"user {user.id}")[:120]


def policy_of(group: VehicleGroup) -> vg.GroupPolicy:
    return vg.normalize_policy(group.kind, group.max_active_sessions, group.exit_release)


def group_display(group: VehicleGroup | None) -> str:
    if group is None:
        return ""
    return vg.display_name(group.kind, group.name, group.company_name or "", group.owner_name or "")


def held_occupancies(db: Session, group_id: int) -> list[VehicleGroupOccupancy]:
    return list(db.scalars(
        select(VehicleGroupOccupancy)
        .where(VehicleGroupOccupancy.group_id == int(group_id), VehicleGroupOccupancy.released_at.is_(None))
        .order_by(VehicleGroupOccupancy.slot)
    ).all())


def occupancy_for_session(db: Session, session_id: int, *, held_only: bool = True) -> VehicleGroupOccupancy | None:
    stmt = select(VehicleGroupOccupancy).where(VehicleGroupOccupancy.session_id == int(session_id))
    if held_only:
        stmt = stmt.where(VehicleGroupOccupancy.released_at.is_(None))
    return db.scalar(stmt.order_by(VehicleGroupOccupancy.id.desc()).limit(1))


def _apply(
    db: Session,
    occ: VehicleGroupOccupancy,
    event: str,
    *,
    action: str,
    evidence: str = "",
    reason: str = "",
    user: User | None = None,
    identified_by: str = "SYSTEM",
    session: ParkingSession | None = None,
    session_closed: bool = False,
    amount_owed: float = 0.0,
    currency: str = "",
    extra: dict | None = None,
) -> ExitConfirmation:
    """Move one occupancy through the domain machine and stage its audit row (no commit)."""
    previous = occ.state
    new = vg.next_state(previous, event)
    now = utcnow()
    occ.state = new
    occ.updated_at = now
    if new == vg.OCC_RELEASED:
        occ.released_at = now
        occ.release_evidence = (evidence or event)[:40]
        occ.release_reason = (reason or "")[:240]
        occ.released_by = user.id if user is not None else None
    elif new in (vg.OCC_EXIT_UNCONFIRMED, vg.OCC_RECONCILIATION) and occ.exit_reported_at is None:
        occ.exit_reported_at = now
    record = ExitConfirmation(
        site_id=int(occ.site_id or DEFAULT_SITE_ID),
        session_id=occ.session_id or (session.id if session is not None else None),
        occupancy_id=occ.id,
        group_id=occ.group_id,
        plate=(occ.plate or (session.plate if session is not None else "") or "")[:32],
        action=action,
        evidence=(evidence or "")[:40],
        identified_by=(identified_by or "")[:20],
        previous_state=previous,
        new_state=new,
        session_closed=bool(session_closed),
        operator_id=user.id if user is not None else None,
        operator_name=_operator_name(user),
        reason=(reason or "")[:240],
        entry_image_ref=((session.entry_image_ref if session is not None else "") or "")[:300],
        amount_owed=round(float(amount_owed or 0), 2),
        currency=(currency or "")[:8],
        extra=extra or None,
    )
    db.add(record)
    return record


# ------------------------------------------------------------------ entry: claim a slot

def claim_for_session(
    db: Session,
    *,
    session: ParkingSession,
    group_id: int,
    vehicle_id: int | None,
    plate: str,
) -> VehicleGroupOccupancy | None:
    """Claim a free slot of the group for this (flushed, uncommitted) session.

    Raises ``GroupOccupied`` when every slot is held. Returns None when the
    group is disabled or a FLEET with no limit (nothing to hold). The caller
    owns the transaction; an IntegrityError on flush means another lane took
    the slot concurrently and the caller must roll back and retry.
    """
    group = db.get(VehicleGroup, int(group_id))
    if group is None or not group.enabled:
        return None
    policy = policy_of(group)
    if not policy.enforced:
        return None
    if _postgres(db):
        # Serialize claims for this group across lanes, processes and nodes.
        db.execute(select(VehicleGroup.id).where(VehicleGroup.id == group.id).with_for_update())
    held = held_occupancies(db, group.id)
    plate = (plate or "").strip().upper()
    for occ in list(held):
        same_car = (vehicle_id is not None and occ.vehicle_id == vehicle_id) or (plate and occ.plate == plate)
        if same_car and occ.state == vg.OCC_EXIT_UNCONFIRMED:
            # Its last visit ended without exit proof, but the car is now at
            # the entry from outside: it did leave. Free its old slot.
            _apply(db, occ, vg.E_SEEN_AT_ENTRY, action=ACTION_SEEN_AT_ENTRY, evidence=vg.EV_SEEN_AT_ENTRY,
                   reason="same vehicle read at the entry", identified_by="SYSTEM")
            db.flush()
            held.remove(occ)
    used = {occ.slot for occ in held}
    free = next((slot for slot in range(1, policy.max_active_sessions + 1) if slot not in used), None)
    if free is None:
        raise vg.GroupOccupied(group_dict(group), [occupancy_dict(db, occ) for occ in held])
    occ = VehicleGroupOccupancy(
        site_id=int(session.site_id or DEFAULT_SITE_ID),
        group_id=group.id,
        slot=free,
        state=vg.OCC_ACTIVE,
        session_id=session.id,
        vehicle_id=vehicle_id,
        plate=plate[:32],
        claimed_at=utcnow(),
    )
    db.add(occ)
    db.flush()  # the partial unique index decides a concurrent race here
    return occ


def blockers_for(db: Session, group_id: int) -> tuple[dict, list[dict]] | None:
    """Pre-check for the entry lane: who holds the group, if it is full."""
    group = db.get(VehicleGroup, int(group_id))
    if group is None or not group.enabled:
        return None
    policy = policy_of(group)
    if not policy.enforced:
        return None
    held = held_occupancies(db, group.id)
    if len(held) < policy.max_active_sessions:
        return None
    return group_dict(group), [occupancy_dict(db, occ) for occ in held]


def consume_visitor_entry(db: Session, pass_id: int) -> None:
    """Count one entry on a visitor pass atomically; raises when it is used up."""
    result = db.execute(
        update(VisitorPass)
        .where(
            VisitorPass.id == int(pass_id),
            or_(VisitorPass.max_entries == 0, VisitorPass.entries_used < VisitorPass.max_entries),
        )
        .values(entries_used=VisitorPass.entries_used + 1)
    )
    if result.rowcount != 1:
        raise vg.VisitorPassExhausted(f"visitor pass {pass_id} has no entries left")


# ------------------------------------------------------------------ exit: release on evidence

def on_session_closed(db: Session, row: ParkingSession, *, evidence: str) -> VehicleGroupOccupancy | None:
    """Called inside the transaction that closes a grouped session (no commit)."""
    occ = occupancy_for_session(db, row.id)
    if occ is None:
        return None
    group = db.get(VehicleGroup, occ.group_id)
    policy = policy_of(group) if group is not None else vg.GroupPolicy()
    accepted = vg.releases(policy.exit_release, evidence)
    event = vg.E_CLOSED_CONFIRMED if accepted else vg.E_CLOSED_UNCONFIRMED
    released = vg.next_state(occ.state, event) == vg.OCC_RELEASED
    _apply(
        db, occ, event,
        action=ACTION_AUTO_RELEASED if released else ACTION_EXIT_UNCONFIRMED,
        evidence=evidence,
        reason=("exit evidence accepted" if released else
                f"visit closed without exit proof the group accepts ({evidence or 'none'})"),
        session=row, session_closed=True,
    )
    if not released:
        log.warning("vehicle group %s stays locked: session %s closed with evidence=%s state=%s",
                    occ.group_id, row.id, evidence, occ.state)
    return occ


def _close_session(db: Session, row: ParkingSession, *, at: datetime) -> dict[str, Any]:
    """Close an open session that left without the lane machine (manual/supervisor)."""
    from app.domain.parking import STORED_CLOSED
    from app.domain.parking_engine import CLOSED
    from app.services.manual_open import owed_snapshot

    money = owed_snapshot(db, row, at=at)
    row.status = STORED_CLOSED
    row.lifecycle = CLOSED
    row.exit_time = row.exit_time or at
    row.closed_at = at
    row.amount_due = money["due"]
    row.amount_paid = money["paid"]
    row.updated_at = at
    return money


def _session_open(row: ParkingSession) -> bool:
    return (row.status or "").upper() != "CLOSED" and row.closed_at is None


def _lock_session(db: Session, session_id: int) -> ParkingSession | None:
    stmt = select(ParkingSession).where(ParkingSession.id == int(session_id))
    if _postgres(db):
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def confirm_manual_exit(
    db: Session,
    *,
    session_id: int,
    user: User,
    reason: str,
    outcome: str = "LEFT",
    identified_by: str = "SESSION",
) -> dict[str, Any]:
    """A guard confirms (or cannot confirm) that a vehicle physically left.

    ``outcome="LEFT"``: the visit is closed (if still open) and the group slot
    is released. ``outcome="UNCERTAIN"``: nothing is closed or released; the
    slot moves to RECONCILIATION for a supervisor.
    """
    from app.domain.parking_engine import InvalidTransition
    from app.services.decisions import record_access_decision

    reason = _reason(reason)
    outcome = (outcome or "LEFT").strip().upper()
    if outcome not in {"LEFT", "UNCERTAIN"}:
        raise ValueError("Outcome must be LEFT or UNCERTAIN")
    identified_by = (identified_by or "SESSION").strip().upper()[:20]
    row = _lock_session(db, session_id)
    if row is None:
        raise LookupError("Session not found")
    occ = occupancy_for_session(db, row.id)
    is_open = _session_open(row)
    now = utcnow()
    if outcome == "LEFT":
        if occ is not None and occ.state == vg.OCC_RECONCILIATION:
            db.rollback()
            raise NeedsSupervisor("This exit is under reconciliation; a supervisor must decide it")
        if not is_open and occ is None:
            db.rollback()
            raise InvalidTransition("This visit is already closed and nothing is waiting for exit confirmation")
        money = _close_session(db, row, at=now) if is_open else {"owed": 0.0, "currency": row.currency or ""}
        if occ is not None:
            record = _apply(db, occ, vg.E_OPERATOR_CONFIRM, action=ACTION_MANUAL_CONFIRMED, evidence=vg.EV_OPERATOR,
                            reason=reason, user=user, identified_by=identified_by, session=row,
                            session_closed=is_open, amount_owed=money["owed"], currency=money["currency"])
        else:
            record = ExitConfirmation(
                site_id=int(row.site_id or DEFAULT_SITE_ID), session_id=row.id, plate=row.plate,
                action=ACTION_MANUAL_CONFIRMED, evidence=vg.EV_OPERATOR, identified_by=identified_by,
                previous_state="", new_state="", session_closed=is_open, operator_id=user.id,
                operator_name=_operator_name(user), reason=reason, entry_image_ref=row.entry_image_ref or "",
                amount_owed=round(float(money["owed"] or 0), 2), currency=money["currency"] or "",
            )
            db.add(record)
        db.commit()
        record_access_decision(
            db, session=row, plate=row.plate, gate=None, lane_direction="EXIT", outcome=ACTION_MANUAL_CONFIRMED,
            reason=reason[:200], parker_kind=row.parker_kind or "CASUAL", automatic=False, barrier_opened=False,
            extra={"confirmed_by": user.id, "identified_by": identified_by, "session_closed": is_open,
                   "unpaid": money["owed"], "group_id": occ.group_id if occ else None},
        )
    else:
        if occ is not None and occ.state != vg.OCC_RECONCILIATION:
            record = _apply(db, occ, vg.E_OPERATOR_UNCERTAIN, action=ACTION_MANUAL_UNCERTAIN, reason=reason,
                            user=user, identified_by=identified_by, session=row)
        else:
            state = occ.state if occ is not None else ""
            record = ExitConfirmation(
                site_id=int(row.site_id or DEFAULT_SITE_ID), session_id=row.id, occupancy_id=occ.id if occ else None,
                group_id=occ.group_id if occ else None, plate=row.plate, action=ACTION_MANUAL_UNCERTAIN,
                identified_by=identified_by, previous_state=state, new_state=state, operator_id=user.id,
                operator_name=_operator_name(user), reason=reason, entry_image_ref=row.entry_image_ref or "",
            )
            db.add(record)
        db.commit()
        record_access_decision(
            db, session=row, plate=row.plate, gate=None, lane_direction="EXIT", outcome=ACTION_MANUAL_UNCERTAIN,
            reason=reason[:200], parker_kind=row.parker_kind or "CASUAL", automatic=False, barrier_opened=False,
            extra={"reported_by": user.id, "identified_by": identified_by, "group_id": occ.group_id if occ else None},
        )
    db.refresh(row)
    return {"confirmation": confirmation_dict(record), "exit": manual_exit_view(db, row)}


def reconcile(
    db: Session,
    *,
    occupancy_id: int,
    user: User,
    reason: str,
    decision: str,
) -> dict[str, Any]:
    """Supervisor decision on a held slot: RELEASE (the car left) or KEEP_INSIDE."""
    from app.services.decisions import record_access_decision

    reason = _reason(reason)
    decision = (decision or "").strip().upper()
    if decision not in {"RELEASE", "KEEP_INSIDE"}:
        raise ValueError("Decision must be RELEASE or KEEP_INSIDE")
    stmt = select(VehicleGroupOccupancy).where(VehicleGroupOccupancy.id == int(occupancy_id))
    if _postgres(db):
        stmt = stmt.with_for_update()
    occ = db.scalar(stmt)
    if occ is None:
        raise LookupError("Occupancy not found")
    if occ.released_at is not None:
        raise vg.InvalidOccupancyTransition("This slot is already released")
    row = _lock_session(db, occ.session_id) if occ.session_id else None
    now = utcnow()
    closed_now = False
    money = {"owed": 0.0, "currency": ""}
    if decision == "RELEASE":
        if row is not None and _session_open(row):
            money = _close_session(db, row, at=now)
            closed_now = True
        record = _apply(db, occ, vg.E_SUPERVISOR_RELEASE, action=ACTION_SUPERVISOR_RELEASED, evidence=vg.EV_SUPERVISOR,
                        reason=reason, user=user, identified_by="SUPERVISOR", session=row, session_closed=closed_now,
                        amount_owed=money["owed"], currency=money["currency"])
    else:
        still_open = row is not None and _session_open(row)
        event = vg.E_SUPERVISOR_KEEP_INSIDE if still_open else vg.E_SUPERVISOR_KEEP_LOCKED
        action = ACTION_SUPERVISOR_KEPT_INSIDE if still_open else ACTION_SUPERVISOR_KEPT_LOCKED
        record = _apply(db, occ, event, action=action, reason=reason, user=user, identified_by="SUPERVISOR", session=row)
    db.commit()
    if row is not None:
        record_access_decision(
            db, session=row, plate=row.plate, gate=None, lane_direction="EXIT", outcome=record.action,
            reason=reason[:200], parker_kind=row.parker_kind or "CASUAL", automatic=False, barrier_opened=False,
            extra={"supervisor": user.id, "occupancy_id": occ.id, "group_id": occ.group_id,
                   "session_closed": closed_now, "unpaid": money["owed"]},
        )
    db.refresh(occ)
    return {"confirmation": confirmation_dict(record), "occupancy": occupancy_dict(db, occ)}


# ------------------------------------------------------------------ manual exit lookup

def find_exit_candidates(db: Session, query: str) -> list[dict[str, Any]]:
    """Identify a visit for manual exit by session number, receipt QR/link/reference or plate."""
    from app.core.plate import normalize_plate
    from app.domain.receipt_engine import extract_session_token, normalize_human_reference
    from app.services.kiosk_lookup import find_session

    raw = (query or "").strip()
    if not raw:
        return []
    rows: list[tuple[ParkingSession, str]] = []
    digits = raw.lstrip("#")
    if digits.isdigit() and (raw.startswith("#") or len(digits) <= 6):
        row = db.get(ParkingSession, int(digits))
        if row is not None:
            rows.append((row, "SESSION"))
    if not rows:
        row = find_session(db, raw)
        if row is not None:
            if extract_session_token(raw) or normalize_human_reference(raw):
                rows.append((row, "QR"))
            else:
                rows.append((row, "PLATE"))
    plate = normalize_plate(raw)
    if plate:
        # A plate can also have an unconfirmed exit from an older, closed visit.
        for occ in db.scalars(
            select(VehicleGroupOccupancy)
            .where(VehicleGroupOccupancy.plate == plate, VehicleGroupOccupancy.released_at.is_(None))
        ).all():
            if occ.session_id and all(r.id != occ.session_id for r, _ in rows):
                row = db.get(ParkingSession, occ.session_id)
                if row is not None:
                    rows.append((row, "PLATE"))
    out = []
    for row, how in rows:
        view = manual_exit_view(db, row)
        view["identified_by"] = how
        out.append(view)
    return out


def manual_exit_view(db: Session, row: ParkingSession) -> dict[str, Any]:
    """Everything a guard needs to decide: photo, plate, times, owner/company, slot state."""
    from app.services.kiosk_lookup import image_fields, stay_for
    from app.services.parking_sessions import snapshot

    occ = occupancy_for_session(db, row.id)
    group = db.get(VehicleGroup, row.authorization_group_id) if row.authorization_group_id else None
    vehicle = db.get(RegisteredVehicle, row.vehicle_id) if row.vehicle_id else None
    is_open = _session_open(row)
    try:
        images = image_fields(db, row)
    except Exception:
        images = {"snapshot_url": None, "crop_url": None, "image_note": "Entry photo unavailable."}
    entry = as_utc(row.entry_time)
    return {
        "session": snapshot(row),
        "session_id": row.id,
        "plate": row.plate,
        "status": row.status,
        "open": is_open,
        "entry_time": entry.isoformat() if entry else None,
        "exit_time": as_utc(row.exit_time).isoformat() if row.exit_time else None,
        "stay": stay_for(row),
        "parker_kind": row.parker_kind or "CASUAL",
        "owner_name": vehicle.owner_name if vehicle is not None else "",
        "group": group_dict(group) if group is not None else None,
        "belongs_to": group_display(group),
        "occupancy": occupancy_dict(db, occ) if occ is not None else None,
        "needs_supervisor": bool(occ is not None and occ.state == vg.OCC_RECONCILIATION),
        "can_confirm": bool(is_open or (occ is not None and occ.state != vg.OCC_RECONCILIATION)),
        "entry_image_ref": row.entry_image_ref or "",
        **images,
    }


# ------------------------------------------------------------------ dictionaries

def occupancy_dict(db: Session, occ: VehicleGroupOccupancy) -> dict[str, Any]:
    group = db.get(VehicleGroup, occ.group_id)
    row = db.get(ParkingSession, occ.session_id) if occ.session_id else None
    claimed = as_utc(occ.claimed_at)
    return {
        "id": occ.id,
        "group_id": occ.group_id,
        "group_name": group.name if group is not None else "",
        "belongs_to": group_display(group),
        "slot": occ.slot,
        "state": occ.state,
        "session_id": occ.session_id,
        "session_open": bool(row is not None and _session_open(row)),
        "vehicle_id": occ.vehicle_id,
        "plate": occ.plate,
        "claimed_at": claimed.isoformat() if claimed else None,
        "inside_seconds": int((datetime.now(timezone.utc) - claimed).total_seconds()) if claimed else None,
        "exit_reported_at": as_utc(occ.exit_reported_at).isoformat() if occ.exit_reported_at else None,
        "released_at": as_utc(occ.released_at).isoformat() if occ.released_at else None,
        "release_evidence": occ.release_evidence or "",
        "release_reason": occ.release_reason or "",
    }


def confirmation_dict(row: ExitConfirmation) -> dict[str, Any]:
    return {
        "id": row.id,
        "session_id": row.session_id,
        "occupancy_id": row.occupancy_id,
        "group_id": row.group_id,
        "plate": row.plate,
        "action": row.action,
        "evidence": row.evidence,
        "identified_by": row.identified_by,
        "previous_state": row.previous_state,
        "new_state": row.new_state,
        "session_closed": bool(row.session_closed),
        "operator_id": row.operator_id,
        "operator_name": row.operator_name,
        "reason": row.reason,
        "amount_owed": float(row.amount_owed or 0),
        "currency": row.currency,
        "created_at": as_utc(row.created_at).isoformat() if row.created_at else None,
    }


def group_dict(group: VehicleGroup, db: Session | None = None) -> dict[str, Any]:
    out = {
        "id": group.id,
        "name": group.name,
        "kind": group.kind,
        "company_name": group.company_name or "",
        "owner_name": group.owner_name or "",
        "contact_phone": group.contact_phone or "",
        "display_name": group_display(group),
        "max_active_sessions": int(group.max_active_sessions or 0),
        "exit_release": group.exit_release,
        "enabled": bool(group.enabled),
        "notes": group.notes or "",
    }
    if db is not None:
        members = list(db.scalars(
            select(RegisteredVehicle).where(RegisteredVehicle.group_id == group.id).order_by(RegisteredVehicle.plate)
        ).all())
        held = held_occupancies(db, group.id)
        out["members"] = [{"id": v.id, "plate": v.plate, "owner_name": v.owner_name or "", "enabled": bool(v.enabled)}
                          for v in members]
        out["inside"] = [occupancy_dict(db, occ) for occ in held]
        limit = int(group.max_active_sessions or 0)
        out["locked"] = bool(limit and len(held) >= limit)
    return out


# ------------------------------------------------------------------ group and visitor management

def save_group(db: Session, data: dict[str, Any], *, group: VehicleGroup | None = None, site_id: int = DEFAULT_SITE_ID) -> VehicleGroup:
    """Create or update a group from validated fields. Caller commits."""
    current = group or VehicleGroup(site_id=site_id)
    kind = data.get("kind", current.kind if group else vg.PRIVATE)
    policy = vg.normalize_policy(
        kind,
        data.get("max_active_sessions", current.max_active_sessions if group else None),
        data.get("exit_release", current.exit_release if group else None),
    )
    name = str(data.get("name", current.name or "") or "").strip()
    if not name:
        raise ValueError("Enter a group name")
    company = str(data.get("company_name", current.company_name or "") or "").strip()
    if policy.kind == vg.FLEET and not company:
        company = name
    current.name = name[:120]
    current.kind = policy.kind
    current.max_active_sessions = policy.max_active_sessions
    current.exit_release = policy.exit_release
    current.company_name = company[:160]
    for key, limit in (("owner_name", 160), ("contact_phone", 40)):
        if key in data:
            setattr(current, key, str(data[key] or "").strip()[:limit])
    if "notes" in data:
        current.notes = str(data["notes"] or "")
    if "enabled" in data:
        current.enabled = bool(data["enabled"])
    current.updated_at = utcnow()
    if group is None:
        db.add(current)
    return current


def active_visitor_pass(db: Session, plate: str, *, at: datetime | None = None,
                        site_id: int = DEFAULT_SITE_ID) -> VisitorPass | None:
    now = as_utc(at) or utcnow()
    for row in db.scalars(
        select(VisitorPass)
        .where(VisitorPass.site_id == int(site_id), VisitorPass.plate == plate,
               VisitorPass.enabled.is_(True), VisitorPass.revoked_at.is_(None))
        .order_by(VisitorPass.valid_until.desc())
    ).all():
        start, finish = as_utc(row.valid_from), as_utc(row.valid_until)
        if start is not None and start > now:
            continue
        if finish is None or finish < now:
            continue
        if row.max_entries and row.entries_used >= row.max_entries:
            continue
        return row
    return None


def visitor_pass_dict(db: Session, row: VisitorPass) -> dict[str, Any]:
    host = db.get(VehicleGroup, row.host_group_id) if row.host_group_id else None
    now = utcnow()
    finish = as_utc(row.valid_until)
    used_up = bool(row.max_entries and row.entries_used >= row.max_entries)
    state = "REVOKED" if row.revoked_at or not row.enabled else (
        "EXPIRED" if finish is not None and finish < now else ("USED" if used_up else "VALID"))
    return {
        "id": row.id,
        "plate": row.plate,
        "visitor_name": row.visitor_name or "",
        "host_group_id": row.host_group_id,
        "host_name": row.host_name or (host.company_name or host.name if host else ""),
        "belongs_to": group_display(host) if host else "",
        "purpose": row.purpose or "",
        "valid_from": as_utc(row.valid_from).isoformat() if row.valid_from else None,
        "valid_until": finish.isoformat() if finish else None,
        "max_entries": int(row.max_entries or 0),
        "entries_used": int(row.entries_used or 0),
        "state": state,
        "notes": row.notes or "",
    }


def pending_exits(db: Session, *, include_active: bool = True) -> list[dict[str, Any]]:
    states = list(vg.HELD_STATES) if include_active else [vg.OCC_EXIT_UNCONFIRMED, vg.OCC_RECONCILIATION]
    rows = db.scalars(
        select(VehicleGroupOccupancy)
        .where(VehicleGroupOccupancy.released_at.is_(None), VehicleGroupOccupancy.state.in_(states))
        .order_by(VehicleGroupOccupancy.claimed_at)
    ).all()
    return [occupancy_dict(db, occ) for occ in rows]
