"""Access plans and registered plates. Registered plates auto-open; casuals use receipts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.plate import correct_ocr_confusions, normalize_plate, plate_similarity
from app.domain.site import DEFAULT_SITE_ID
from app.models import AccessPlan, RegisteredVehicle, as_utc, utcnow

REGISTERED_FUZZY_MIN = 0.85

DEFAULT_PLANS = (
    {"name": "Monthly Tenant", "kind": "MONTHLY", "auto_open": True, "print_receipt": False},
    {"name": "Annual Tenant", "kind": "ANNUAL", "auto_open": True, "print_receipt": False},
    {"name": "Staff", "kind": "STAFF", "auto_open": True, "print_receipt": False},
    {"name": "VIP", "kind": "VIP", "auto_open": True, "print_receipt": False},
    {"name": "Contractor", "kind": "CONTRACTOR", "auto_open": True, "print_receipt": True},
)


@dataclass
class Entitlement:
    kind: str = "CASUAL"
    auto_open: bool = False
    print_receipt: bool = False
    plan_id: int | None = None
    plan_name: str = ""
    vehicle_id: int | None = None
    owner_name: str = ""
    plate: str = ""

    @property
    def registered(self) -> bool:
        return self.kind != "CASUAL" and self.vehicle_id is not None


def ensure_access_plans(db: Session, *, site_id: int = DEFAULT_SITE_ID) -> list[AccessPlan]:
    rows = list(db.scalars(
        select(AccessPlan).where(AccessPlan.site_id == site_id).order_by(AccessPlan.id)
    ).all())
    if rows:
        return rows
    for spec in DEFAULT_PLANS:
        db.add(AccessPlan(site_id=site_id, **spec))
    db.commit()
    return list(db.scalars(
        select(AccessPlan).where(AccessPlan.site_id == site_id).order_by(AccessPlan.id)
    ).all())


def _in_window(vehicle: RegisteredVehicle, at: datetime) -> bool:
    now_ts = (as_utc(at) or utcnow()).timestamp()
    start = as_utc(vehicle.valid_from)
    finish = as_utc(vehicle.valid_until)
    if start is not None and start.timestamp() > now_ts:
        return False
    if finish is not None and finish.timestamp() < now_ts:
        return False
    return True


def _fuzzy_match_vehicle(
    db: Session,
    plate: str,
    *,
    at: datetime | None = None,
    min_similarity: float = REGISTERED_FUZZY_MIN,
    site_id: int = DEFAULT_SITE_ID,
) -> RegisteredVehicle | None:
    """Match OCR reads that are close to a saved plate (1–2 character edits)."""
    now = at or utcnow()
    best: RegisteredVehicle | None = None
    best_score = 0.0
    for row in db.scalars(select(RegisteredVehicle).where(
        RegisteredVehicle.site_id == site_id,
        RegisteredVehicle.enabled.is_(True),
    )):
        if not _in_window(row, now):
            continue
        plan = row.plan
        if plan is not None and not plan.enabled:
            continue
        score = plate_similarity(plate, row.plate)
        if score >= min_similarity and score > best_score:
            best_score = score
            best = row
    return best


def lookup_entitlement(
    db: Session,
    plate: str,
    *,
    at: datetime | None = None,
    site_id: int = DEFAULT_SITE_ID,
) -> Entitlement:
    plate = normalize_plate(plate)
    if not plate:
        return Entitlement()
    vehicle = db.scalar(select(RegisteredVehicle).where(
        RegisteredVehicle.site_id == site_id,
        RegisteredVehicle.plate == plate,
    ))
    if vehicle is None:
        known = [
            row.plate
            for row in db.scalars(select(RegisteredVehicle).where(
                RegisteredVehicle.site_id == site_id,
                RegisteredVehicle.enabled.is_(True),
            )).all()
        ]
        from app.services.site_policy import site_policy

        validation = str(site_policy(db).get("plate_validation") or "NONE")
        fixed = correct_ocr_confusions(plate, known_plates=known, policy=validation)
        if fixed.get("plate") and fixed["plate"] != plate:
            vehicle = db.scalar(select(RegisteredVehicle).where(
                RegisteredVehicle.site_id == site_id,
                RegisteredVehicle.plate == fixed["plate"],
            ))
    if vehicle is None:
        vehicle = _fuzzy_match_vehicle(db, plate, at=at, site_id=site_id)
    if vehicle is None or not vehicle.enabled:
        return Entitlement(plate=plate)
    now = at or utcnow()
    if not _in_window(vehicle, now):
        return Entitlement(plate=plate, owner_name=vehicle.owner_name, vehicle_id=vehicle.id)
    plan = vehicle.plan
    if plan is not None and not plan.enabled:
        return Entitlement(plate=plate, owner_name=vehicle.owner_name, vehicle_id=vehicle.id)
    kind = (plan.kind if plan else "SUBSCRIBER") or "SUBSCRIBER"
    return Entitlement(
        kind=kind,
        auto_open=True if plan is None else bool(plan.auto_open),
        print_receipt=bool(plan.print_receipt) if plan else False,
        plan_id=plan.id if plan else None,
        plan_name=plan.name if plan else "",
        vehicle_id=vehicle.id,
        owner_name=vehicle.owner_name,
        plate=vehicle.plate,
    )


def plan_dict(row: AccessPlan) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "kind": row.kind,
        "auto_open": bool(row.auto_open),
        "print_receipt": bool(row.print_receipt),
        "enabled": bool(row.enabled),
        "notes": row.notes or "",
        "vehicle_count": len(row.vehicles or []),
    }


def vehicle_dict(row: RegisteredVehicle) -> dict:
    return {
        "id": row.id,
        "plate": row.plate,
        "owner_name": row.owner_name or "",
        "plan_id": row.plan_id,
        "plan_name": row.plan.name if row.plan else "",
        "plan_kind": row.plan.kind if row.plan else "",
        "auto_open": bool(row.plan.auto_open) if row.plan else True,
        "enabled": bool(row.enabled),
        "valid_from": row.valid_from.isoformat() if row.valid_from else None,
        "valid_until": row.valid_until.isoformat() if row.valid_until else None,
        "notes": row.notes or "",
    }
