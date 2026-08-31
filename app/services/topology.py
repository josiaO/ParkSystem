"""Site topology: Site → Zone → Gate → Lane. Data-driven; no hard-coded gate counts."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.site import DEFAULT_SITE_ID
from app.models import Camera, Gate, Lane, Site, Zone


def ensure_default_site(db: Session) -> Site:
    site = db.get(Site, DEFAULT_SITE_ID)
    if site is None:
        site = Site(id=DEFAULT_SITE_ID, name="Default Site", timezone="UTC", locale="en", currency="USD")
        db.add(site)
        db.commit()
        db.refresh(site)
    return site


def apply_onboarding_topology(db: Session, topology: dict[str, Any] | None) -> dict[str, Any]:
    """Create gates/lanes from an onboarding draft. Presets avoid hard-coded mall layouts."""
    ensure_default_site(db)
    topology = topology or {}
    preset = str(topology.get("preset") or "").strip().lower()
    gates_spec = list(topology.get("gates") or [])

    if not gates_spec:
        if preset in ("1in1out", "parking_lite", "entry_exit"):
            gates_spec = [{
                "name": "Main Gate",
                "lanes": [
                    {"name": "Entry", "direction": "ENTRY"},
                    {"name": "Exit", "direction": "EXIT"},
                ],
            }]
        elif preset in ("bidirectional", "one_lane"):
            gates_spec = [{
                "name": "Main Gate",
                "lanes": [{"name": "Lane 1", "direction": "BIDIRECTIONAL", "bidirectional": True}],
            }]
        elif preset in ("lpr_only", "security", "none", "zero_gate"):
            gates_spec = []

    created_gates = 0
    created_lanes = 0
    for gspec in gates_spec:
        name = str(gspec.get("name") or "Gate").strip() or "Gate"
        existing = db.scalar(select(Gate).where(Gate.name == name))
        if existing is None:
            gate = Gate(name=name, mode="COMMISSIONING", enabled=True, site_id=DEFAULT_SITE_ID)
            db.add(gate)
            db.commit()
            db.refresh(gate)
            created_gates += 1
        else:
            gate = existing
        for lspec in gspec.get("lanes") or []:
            lname = str(lspec.get("name") or "Lane").strip() or "Lane"
            direction = str(lspec.get("direction") or "ENTRY").upper()
            bidirectional = bool(lspec.get("bidirectional")) or direction == "BIDIRECTIONAL"
            already = db.scalar(
                select(Lane).where(Lane.gate_id == gate.id, Lane.name == lname)
            )
            if already is None:
                create_lane(
                    db,
                    name=lname,
                    gate_id=gate.id,
                    direction=direction,
                    bidirectional=bidirectional,
                )
                created_lanes += 1

    return {
        "created_gates": created_gates,
        "created_lanes": created_lanes,
        "topology": site_topology(db),
    }

def zone_dict(row: Zone) -> dict[str, Any]:
    return {
        "id": row.id,
        "site_id": row.site_id,
        "name": row.name,
        "enabled": row.enabled,
    }


def lane_dict(row: Lane) -> dict[str, Any]:
    return {
        "id": row.id,
        "gate_id": row.gate_id,
        "zone_id": row.zone_id,
        "name": row.name,
        "direction": row.direction,
        "bidirectional": row.bidirectional,
        "enabled": row.enabled,
    }


def gate_topology_dict(gate: Gate, *, lanes: list[Lane], cameras: list[Camera]) -> dict[str, Any]:
    return {
        "id": gate.id,
        "name": gate.name,
        "mode": gate.mode,
        "enabled": gate.enabled,
        "site_id": gate.site_id,
        "zone_id": gate.zone_id,
        "lanes": [lane_dict(l) for l in lanes if l.gate_id == gate.id],
        "cameras": [
            {
                "id": c.id,
                "name": c.name,
                "lane_id": c.lane_id,
                "lane_direction": c.lane_direction,
                "enabled": c.enabled,
            }
            for c in cameras
            if c.gate_id == gate.id
        ],
    }


def site_topology(db: Session, site_id: int = DEFAULT_SITE_ID) -> dict[str, Any]:
    ensure_default_site(db)
    site = db.get(Site, site_id)
    zones = db.scalars(select(Zone).where(Zone.site_id == site_id).order_by(Zone.id)).all()
    gates = db.scalars(select(Gate).order_by(Gate.id)).all()
    if site_id != DEFAULT_SITE_ID:
        gates = [g for g in gates if g.site_id in (None, site_id)]
    lanes = db.scalars(select(Lane).order_by(Lane.id)).all()
    cameras = db.scalars(select(Camera).order_by(Camera.id)).all()
    unassigned_cameras = [c for c in cameras if c.gate_id is None]

    return {
        "site": {
            "id": site.id if site else site_id,
            "name": site.name if site else "Site",
            "timezone": site.timezone if site else "UTC",
            "locale": site.locale if site else "en",
            "currency": site.currency if site else "USD",
        },
        "zones": [zone_dict(z) for z in zones],
        "gates": [gate_topology_dict(g, lanes=list(lanes), cameras=list(cameras)) for g in gates],
        "security_cameras": [
            {"id": c.id, "name": c.name, "ip_address": c.ip_address, "enabled": c.enabled}
            for c in unassigned_cameras
        ],
        "counts": {
            "zones": len(zones),
            "gates": len(gates),
            "lanes": len(lanes),
            "cameras": len(cameras),
            "entry_lanes": sum(1 for l in lanes if l.direction == "ENTRY"),
            "exit_lanes": sum(1 for l in lanes if l.direction == "EXIT"),
            "bidirectional_lanes": sum(1 for l in lanes if l.bidirectional or l.direction == "BIDIRECTIONAL"),
        },
    }


def create_zone(db: Session, *, site_id: int, name: str) -> Zone:
    ensure_default_site(db)
    row = Zone(site_id=site_id, name=name.strip())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def create_lane(
    db: Session,
    *,
    name: str,
    gate_id: int | None = None,
    zone_id: int | None = None,
    direction: str = "ENTRY",
    bidirectional: bool = False,
) -> Lane:
    row = Lane(
        name=name.strip(),
        gate_id=gate_id,
        zone_id=zone_id,
        direction=direction.upper(),
        bidirectional=bidirectional or direction.upper() == "BIDIRECTIONAL",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def sync_gate_lanes_from_cameras(db: Session) -> int:
    """Create Lane rows from existing gate + camera direction pairs when lanes are empty."""
    existing = db.scalars(select(Lane)).first()
    if existing is not None:
        return 0
    created = 0
    for gate in db.scalars(select(Gate).order_by(Gate.id)).all():
        directions = {c.lane_direction for c in gate.cameras if c.enabled}
        for direction in sorted(directions or {"ENTRY"}):
            create_lane(db, name=f"{gate.name} {direction.title()}", gate_id=gate.id, direction=direction)
            created += 1
    return created
