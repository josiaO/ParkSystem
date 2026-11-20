"""HTTP boundary for linked-vehicle groups, visitor passes, manual exit and reconciliation.

Rules and transactions live in app/services/vehicle_groups.py; this module
only validates input, checks permissions and writes the audit log.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.plate import normalize_plate
from app.db import get_db
from app.domain import vehicle_groups as vg
from app.models import (
    ExitConfirmation,
    RegisteredVehicle,
    User,
    VehicleGroup,
    VehicleGroupOccupancy,
    VisitorPass,
    as_utc,
    utcnow,
)
from app.security import require, require_any
from app.services import vehicle_groups as svc
from app.services.audit import write_audit

from .module_routes import ModuleRoute


class GroupIn(BaseModel):
    name: str
    kind: str = vg.PRIVATE
    company_name: str = ""
    owner_name: str = ""
    contact_phone: str = ""
    max_active_sessions: int | None = None
    exit_release: str = vg.RELEASE_EXIT_LANE
    enabled: bool = True
    notes: str = ""
    vehicle_ids: list[int] | None = None


class GroupPatch(BaseModel):
    name: str | None = None
    kind: str | None = None
    company_name: str | None = None
    owner_name: str | None = None
    contact_phone: str | None = None
    max_active_sessions: int | None = None
    exit_release: str | None = None
    enabled: bool | None = None
    notes: str | None = None


class MembersIn(BaseModel):
    vehicle_ids: list[int] = Field(default_factory=list)


class VisitorIn(BaseModel):
    plate: str
    visitor_name: str = ""
    host_group_id: int | None = None
    host_name: str = ""
    purpose: str = ""
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    hours: float | None = Field(default=None, gt=0, le=24 * 31)
    max_entries: int = Field(default=1, ge=0, le=1000)
    notes: str = ""


class ExitConfirmIn(BaseModel):
    session_id: int
    outcome: str = "LEFT"          # LEFT | UNCERTAIN
    reason: str
    identified_by: str = "SESSION"  # SESSION | PLATE | QR


class ReconcileIn(BaseModel):
    occupancy_id: int
    decision: str                   # RELEASE | KEEP_INSIDE
    reason: str


def _group_or_404(db: Session, group_id: int) -> VehicleGroup:
    row = db.get(VehicleGroup, group_id)
    if row is None:
        raise HTTPException(404, "Group not found")
    return row


def _set_members(db: Session, group: VehicleGroup, vehicle_ids: list[int]) -> None:
    wanted = {int(v) for v in vehicle_ids}
    for vehicle in db.scalars(select(RegisteredVehicle).where(RegisteredVehicle.group_id == group.id)).all():
        if vehicle.id not in wanted:
            vehicle.group_id = None
    for vehicle_id in wanted:
        vehicle = db.get(RegisteredVehicle, vehicle_id)
        if vehicle is None:
            raise HTTPException(404, f"Vehicle {vehicle_id} not found")
        if vehicle.site_id != group.site_id:
            raise HTTPException(400, f"{vehicle.plate} belongs to another site")
        vehicle.group_id = group.id


def register() -> APIRouter:
    router = APIRouter(route_class=ModuleRoute)

    # ------------------------------------------------------------ groups

    @router.get("/vehicle-groups")
    def list_groups(db: Session = Depends(get_db), _: User = Depends(require("subscribers.view"))):
        rows = db.scalars(select(VehicleGroup).order_by(VehicleGroup.kind, VehicleGroup.name)).all()
        return [svc.group_dict(row, db) for row in rows]

    @router.get("/vehicle-groups/{group_id}")
    def get_group(group_id: int, db: Session = Depends(get_db), _: User = Depends(require("subscribers.view"))):
        return svc.group_dict(_group_or_404(db, group_id), db)

    @router.post("/vehicle-groups")
    def create_group(payload: GroupIn, db: Session = Depends(get_db), user: User = Depends(require("subscribers.manage"))):
        data = payload.model_dump(exclude={"vehicle_ids"})
        try:
            group = svc.save_group(db, data)
            db.flush()
            if payload.vehicle_ids is not None:
                _set_members(db, group, payload.vehicle_ids)
            db.commit()
        except ValueError as exc:
            db.rollback()
            raise HTTPException(400, str(exc)) from exc
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, "A group with that name already exists") from exc
        write_audit(db, user, "vehicle_group.create", "vehicle_group", str(group.id),
                    f"{group.kind} {group.name} limit={group.max_active_sessions} release={group.exit_release}")
        return svc.group_dict(group, db)

    @router.patch("/vehicle-groups/{group_id}")
    def update_group(group_id: int, payload: GroupPatch, db: Session = Depends(get_db),
                     user: User = Depends(require("subscribers.manage"))):
        group = _group_or_404(db, group_id)
        before = f"{group.kind} limit={group.max_active_sessions} release={group.exit_release} enabled={group.enabled}"
        try:
            svc.save_group(db, payload.model_dump(exclude_unset=True), group=group)
            db.commit()
        except ValueError as exc:
            db.rollback()
            raise HTTPException(400, str(exc)) from exc
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, "A group with that name already exists") from exc
        after = f"{group.kind} limit={group.max_active_sessions} release={group.exit_release} enabled={group.enabled}"
        write_audit(db, user, "vehicle_group.update", "vehicle_group", str(group.id), f"{group.name}: {before} -> {after}")
        return svc.group_dict(group, db)

    @router.put("/vehicle-groups/{group_id}/members")
    def set_members(group_id: int, payload: MembersIn, db: Session = Depends(get_db),
                    user: User = Depends(require("subscribers.manage"))):
        group = _group_or_404(db, group_id)
        _set_members(db, group, payload.vehicle_ids)
        db.commit()
        write_audit(db, user, "vehicle_group.members", "vehicle_group", str(group.id),
                    f"{group.name}: {sorted(payload.vehicle_ids)}"[:240])
        return svc.group_dict(group, db)

    @router.delete("/vehicle-groups/{group_id}")
    def delete_group(group_id: int, db: Session = Depends(get_db), user: User = Depends(require("subscribers.manage"))):
        group = _group_or_404(db, group_id)
        if svc.held_occupancies(db, group.id):
            raise HTTPException(409, "A vehicle of this group is inside or its exit is not confirmed. "
                                     "Confirm the exit first, or disable the group instead.")
        used = db.scalar(select(func.count(VehicleGroupOccupancy.id)).where(VehicleGroupOccupancy.group_id == group.id)) or 0
        for vehicle in db.scalars(select(RegisteredVehicle).where(RegisteredVehicle.group_id == group.id)).all():
            vehicle.group_id = None
        if used:
            # History references this group: keep the row, switch it off.
            group.enabled = False
            group.updated_at = utcnow()
            action = "vehicle_group.disable"
        else:
            db.delete(group)
            action = "vehicle_group.delete"
        db.commit()
        write_audit(db, user, action, "vehicle_group", str(group_id), group.name)
        return {"ok": True, "deleted": not used, "disabled": bool(used)}

    # ------------------------------------------------------------ visitor passes

    @router.get("/visitor-passes")
    def list_visitors(
        active_only: bool = Query(default=False),
        db: Session = Depends(get_db),
        _: User = Depends(require_any("visitors.manage", "subscribers.view")),
    ):
        rows = db.scalars(select(VisitorPass).order_by(VisitorPass.valid_until.desc()).limit(500)).all()
        out = [svc.visitor_pass_dict(db, row) for row in rows]
        return [row for row in out if row["state"] == "VALID"] if active_only else out

    @router.post("/visitor-passes")
    def create_visitor(payload: VisitorIn, db: Session = Depends(get_db),
                       user: User = Depends(require_any("visitors.manage", "subscribers.manage"))):
        plate = normalize_plate(payload.plate)
        if not plate:
            raise HTTPException(400, "Enter a number plate")
        start = as_utc(payload.valid_from) or utcnow()
        if payload.valid_until is not None:
            finish = as_utc(payload.valid_until)
        else:
            finish = start + timedelta(hours=float(payload.hours or 12))
        if finish <= start:
            raise HTTPException(400, "The pass must end after it starts")
        if (finish - start) > timedelta(days=31):
            raise HTTPException(400, "A visitor pass lasts at most 31 days; register the vehicle instead")
        if payload.host_group_id is not None and db.get(VehicleGroup, payload.host_group_id) is None:
            raise HTTPException(404, "Host group not found")
        row = VisitorPass(
            plate=plate, visitor_name=payload.visitor_name.strip()[:160], host_group_id=payload.host_group_id,
            host_name=payload.host_name.strip()[:160], purpose=payload.purpose.strip()[:240],
            valid_from=start, valid_until=finish, max_entries=payload.max_entries, created_by=user.id,
            notes=payload.notes or "",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        write_audit(db, user, "visitor_pass.create", "visitor_pass", str(row.id),
                    f"{plate} until {finish.isoformat()} entries={payload.max_entries}")
        return svc.visitor_pass_dict(db, row)

    @router.post("/visitor-passes/{pass_id}/revoke")
    def revoke_visitor(pass_id: int, payload: dict = Body(default_factory=dict), db: Session = Depends(get_db),
                       user: User = Depends(require_any("visitors.manage", "subscribers.manage"))):
        row = db.get(VisitorPass, pass_id)
        if row is None:
            raise HTTPException(404, "Visitor pass not found")
        row.enabled = False
        row.revoked_at = row.revoked_at or utcnow()
        db.commit()
        write_audit(db, user, "visitor_pass.revoke", "visitor_pass", str(row.id),
                    f"{row.plate}: {str((payload or {}).get('reason') or '')}"[:240])
        return svc.visitor_pass_dict(db, row)

    # ------------------------------------------------------------ manual exit and reconciliation

    @router.get("/exits/lookup")
    def lookup_exit(q: str = Query(..., min_length=1), db: Session = Depends(get_db),
                    _: User = Depends(require("exits.confirm"))):
        """Find the visit by session number, scanned receipt QR/link/reference or plate."""
        found = svc.find_exit_candidates(db, q)
        if not found:
            raise HTTPException(404, "No visit found for that session, receipt or plate")
        return found

    @router.get("/exits/pending")
    def pending(include_active: bool = Query(default=True), db: Session = Depends(get_db),
                _: User = Depends(require("exits.confirm"))):
        return svc.pending_exits(db, include_active=include_active)

    @router.post("/exits/confirm")
    def confirm_exit(payload: ExitConfirmIn, db: Session = Depends(get_db), user: User = Depends(require("exits.confirm"))):
        try:
            result = svc.confirm_manual_exit(
                db, session_id=payload.session_id, user=user, reason=payload.reason,
                outcome=payload.outcome, identified_by=payload.identified_by,
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except svc.NeedsSupervisor as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:  # includes InvalidTransition / InvalidOccupancyTransition
            raise HTTPException(409 if "already" in str(exc) or "->" in str(exc) else 400, str(exc)) from exc
        confirmation = result["confirmation"]
        write_audit(db, user, f"exit.{confirmation['action'].lower()}", "parking_session", str(payload.session_id),
                    f"{confirmation['plate']} via {confirmation['identified_by']}: {payload.reason}"[:240])
        return result

    @router.post("/exits/reconcile")
    def reconcile(payload: ReconcileIn, db: Session = Depends(get_db), user: User = Depends(require("exits.reconcile"))):
        try:
            result = svc.reconcile(db, occupancy_id=payload.occupancy_id, user=user, reason=payload.reason,
                                   decision=payload.decision)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409 if "->" in str(exc) or "already" in str(exc) else 400, str(exc)) from exc
        confirmation = result["confirmation"]
        write_audit(db, user, f"exit.{confirmation['action'].lower()}", "vehicle_group_occupancy",
                    str(payload.occupancy_id), f"{confirmation['plate']}: {payload.reason}"[:240])
        return result

    @router.get("/exits/confirmations")
    def confirmations(limit: int = Query(default=100, ge=1, le=1000), session_id: int | None = None,
                      db: Session = Depends(get_db), _: User = Depends(require("exits.confirm"))):
        stmt = select(ExitConfirmation).order_by(ExitConfirmation.id.desc()).limit(limit)
        if session_id is not None:
            stmt = stmt.where(ExitConfirmation.session_id == session_id)
        return [svc.confirmation_dict(row) for row in db.scalars(stmt).all()]

    return router
