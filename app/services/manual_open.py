"""Record every barrier opening the parking engine did not authorize by itself.

A manual opening is the moment revenue and accountability leak: the boom goes
up, and ParkWatch used to log it as "Unknown vehicle, fee 0". Here each one
becomes a ``ManualOpenEvent`` that says which car was in the lane (latest plate
read and a photo), its open visit, how much it owed at that instant, who opened
it and why. Alerts are queued from that record (``app.services.alerts``).

Nothing in this module changes a parking session or sends a gate command.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.domain.site import DEFAULT_SITE_ID
from app.models import (
    MANUAL_SOURCE_UNCOMMANDED,
    Camera,
    Gate,
    GateCommandRecord,
    ManualOpenEvent,
    ParkingSession,
    User,
    VehicleCapture,
)

log = logging.getLogger("smartpark")

MEDIA_KIND = "manual"
LIVE_PHOTO_MAX_AGE_SECONDS = 10.0


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- lane

def lane_cameras(gate: Gate | None, side: str = "", camera: Camera | None = None) -> list[Camera]:
    """Cameras that watch the barrier being opened."""
    if camera is not None:
        return [camera]
    if gate is None:
        return []
    wanted = (side or "").upper()
    rows = [c for c in (gate.cameras or []) if c.enabled]
    if wanted in {"ENTRY", "EXIT"}:
        rows = [c for c in rows if (c.lane_direction or "").upper() == wanted]
    return rows


def lane_label(gate: Gate | None, side: str, camera: Camera | None) -> str:
    side = (side or (camera.lane_direction if camera is not None else "") or "").upper()
    name = (gate.name if gate is not None else "") or (camera.name if camera is not None else "") or "Lane"
    pretty = {"ENTRY": "Entry", "EXIT": "Exit"}.get(side, side.title())
    return f"{name} {pretty}".strip()


def latest_plate_capture(
    db: Session, camera_ids: Iterable[int], *, now: datetime, window_seconds: float,
) -> VehicleCapture | None:
    ids = [int(i) for i in camera_ids if i is not None]
    if not ids:
        return None
    since = now - timedelta(seconds=max(1.0, float(window_seconds)))
    return db.scalar(
        select(VehicleCapture)
        .where(
            VehicleCapture.camera_id.in_(ids),
            VehicleCapture.plate != "",
            VehicleCapture.created_at >= since,
        )
        .order_by(VehicleCapture.id.desc())
        .limit(1)
    )


# -------------------------------------------------------------------------- money

def owed_snapshot(db: Session, row: ParkingSession, *, at: datetime) -> dict[str, Any]:
    """What the visit owed at ``at``. Pure read: the session is not modified.

    Mirrors ExitLaneController's decision: subscribers owe nothing, a paid
    visit inside its exit grace owes its settled quote, otherwise the frozen
    entry tariff is priced to ``at`` and the ledger total is subtracted.
    """
    from app.domain.tariff_engine import quote_stay
    from app.infrastructure.payments.ledger import SUCCEEDED, paid_total
    from app.services.access import lookup_entitlement
    from app.services.fee_engine import load_active_rules, normalize_tariff_rules

    site_id = int(row.site_id or DEFAULT_SITE_ID)
    paid = float(paid_total(db, row.id))
    currency = row.currency or settings.fee_currency
    entry = _aware(row.entry_time)
    duration = int((at - entry).total_seconds()) if entry else None
    entitlement = lookup_entitlement(db, row.plate, at=at, site_id=site_id, strict=True)
    kind = entitlement.kind if entitlement.registered else (row.parker_kind or "CASUAL")
    if entitlement.registered or (row.parker_kind or "CASUAL").upper() not in {"", "CASUAL"}:
        return {"parker_kind": kind, "due": 0.0, "paid": paid, "owed": 0.0, "currency": currency,
                "duration_seconds": duration, "basis": "subscriber"}
    grace_until = _aware(row.payment_exit_grace_until)
    if row.payment_status == SUCCEEDED and grace_until is not None and at <= grace_until:
        due = float(row.amount_due or 0)
        basis = "payment_grace"
    else:
        rules = (
            normalize_tariff_rules(row.tariff_rules, car_type=row.car_type or "Car1")
            if row.tariff_rules else load_active_rules(db, row.car_type or "Car1", site_id=site_id)
        )
        try:
            quote = quote_stay(row.entry_time, at, rules)
            due = float(quote.due_minor)
            currency = quote.currency or currency
            basis = "tariff"
        except Exception as exc:  # a broken tariff must not stop the record
            log.warning("manual-open quote failed session=%s: %s", row.id, exc)
            due = float(row.amount_due or 0)
            basis = "stored_amount"
    return {"parker_kind": kind, "due": due, "paid": paid, "owed": max(0.0, due - paid),
            "currency": currency, "duration_seconds": duration, "basis": basis}


# -------------------------------------------------------------------------- media

def _write_media(name: str, data: bytes) -> str:
    if not data:
        return ""
    folder = settings.media_dir / MEDIA_KIND
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(data)
    return f"{MEDIA_KIND}/{name}"


def _read_media(ref: str) -> bytes:
    from app.services.preview import media_path

    ref = (ref or "").replace("\\", "/").removeprefix("/media/")
    if "/" not in ref:
        return b""
    kind, name = ref.split("/", 1)
    path = media_path(kind, name)
    try:
        return path.read_bytes() if path is not None else b""
    except OSError:
        return b""


def _live_jpeg(camera_id: int) -> bytes:
    """The newest live frame of the lane, if it is fresh."""
    try:
        from app.services.preview import get_state

        state = get_state(int(camera_id))
        jpeg = bytes(state.jpeg or b"")
        age = time.monotonic() - float(state.captured_at or 0)
        if jpeg and state.captured_at and age <= LIVE_PHOTO_MAX_AGE_SECONDS:
            return jpeg
    except Exception as exc:
        log.debug("manual-open live frame unavailable camera=%s: %s", camera_id, exc)
    return b""


def _evidence(stamp: str, capture: VehicleCapture | None, cameras: list[Camera]) -> tuple[str, str]:
    """(photo_ref, crop_ref) copied into the never-pruned ``manual`` folder."""
    photo = crop = ""
    if capture is not None:
        photo = _write_media(f"{stamp}-car.jpg", _read_media(capture.snapshot_path))
        crop = _write_media(f"{stamp}-plate.jpg", _read_media(capture.crop_path))
    if not photo:
        for camera in cameras:
            photo = _write_media(f"{stamp}-cam{camera.id}-live.jpg", _live_jpeg(camera.id))
            if photo:
                break
    return photo, crop


# ------------------------------------------------------------------- photo links

def photo_signature(event_id: int, expires: int) -> str:
    from app.security import _media_token_key

    message = f"manual-open.{int(event_id)}.{int(expires)}".encode("ascii")
    return hmac.new(_media_token_key(), message, hashlib.sha256).hexdigest()[:32]


def signed_photo_path(event: ManualOpenEvent, *, hours: int | None = None) -> str:
    """Relative URL that shows this event's photo without a login, until it expires."""
    hours = int(hours if hours is not None else settings.alerts_photo_link_hours or 24)
    expires = int(time.time()) + max(1, hours) * 3600
    return f"/manual-opens/{event.id}/photo.jpg?exp={expires}&sig={photo_signature(event.id, expires)}"


def verify_photo_signature(event_id: int, expires: int, signature: str) -> bool:
    if int(expires) < int(time.time()):
        return False
    return hmac.compare_digest(photo_signature(event_id, expires), str(signature or ""))


# ------------------------------------------------------------------------ record

def record_manual_open(
    db: Session,
    *,
    source: str,
    gate: Gate | None = None,
    camera: Camera | None = None,
    side: str = "",
    user: User | None = None,
    reason: str = "",
    command_ok: bool = False,
    command_message: str = "",
    session: ParkingSession | None = None,
    extra: dict | None = None,
    at: datetime | None = None,
    queue_alerts: bool = True,
) -> ManualOpenEvent:
    """Persist one manual opening with its car, visit and money, then queue alerts."""
    from app.services.parking_sessions import active_for_plate

    at = _aware(at) or _now()
    if camera is not None and gate is None and camera.gate_id:
        gate = db.get(Gate, camera.gate_id)
    side = (side or (camera.lane_direction if camera is not None else "") or "").upper()
    cameras = lane_cameras(gate, side, camera)
    site_id = int(
        (session.site_id if session is not None else 0)
        or (camera.site_id if camera is not None else 0)
        or (gate.site_id if gate is not None else 0)
        or DEFAULT_SITE_ID
    )

    capture = latest_plate_capture(
        db, [c.id for c in cameras], now=at, window_seconds=settings.manual_open_capture_window_seconds,
    )
    plate = (session.plate if session is not None else "") or (capture.plate if capture is not None else "")
    if session is None and plate:
        session = active_for_plate(db, plate, site_id=site_id)

    money: dict[str, Any] = {}
    if session is not None:
        money = owed_snapshot(db, session, at=at)

    stamp = f"{at.strftime('%Y%m%d-%H%M%S')}-{source.lower()}-{int(time.time() * 1000) % 100000}"
    photo, crop = _evidence(stamp, capture, cameras)
    seconds_before = None
    if capture is not None and capture.created_at is not None:
        seconds_before = round(max(0.0, (at - _aware(capture.created_at)).total_seconds()), 1)

    event = ManualOpenEvent(
        site_id=site_id,
        source=source,
        gate_id=gate.id if gate is not None and gate.id else None,
        camera_id=(camera.id if camera is not None else (cameras[0].id if len(cameras) == 1 else None)),
        lane_label=lane_label(gate, side, camera)[:120],
        side=side[:10],
        operator_id=user.id if user is not None else None,
        operator_name=((user.full_name or user.username) if user is not None else "")[:120],
        reason=(reason or "").strip()[:240],
        plate=(plate or "")[:32],
        plate_confidence=float(capture.confidence or 0) if capture is not None else 0.0,
        plate_seconds_before=seconds_before,
        capture_id=capture.id if capture is not None else None,
        photo_ref=photo,
        session_id=session.id if session is not None else None,
        parker_kind=str(money.get("parker_kind") or "")[:40],
        entry_time=_aware(session.entry_time) if session is not None else None,
        duration_seconds=money.get("duration_seconds"),
        amount_due=float(money.get("due") or 0),
        amount_paid=float(money.get("paid") or 0),
        amount_owed=float(money.get("owed") or 0),
        currency=str(money.get("currency") or (session.currency if session is not None else "") or settings.fee_currency)[:8],
        command_ok=bool(command_ok),
        command_message=(command_message or "")[:2000],
        extra={**(extra or {}), "crop_ref": crop, "money_basis": money.get("basis", "")},
        created_at=at,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    log.warning(
        "MANUAL OPEN id=%s source=%s lane=%s plate=%s owed=%s %s operator=%s ok=%s reason=%s",
        event.id, source, event.lane_label, event.plate or "-", event.amount_owed, event.currency,
        event.operator_name or "-", event.command_ok, event.reason,
    )
    if queue_alerts:
        from app.services import alerts

        try:
            alerts.queue_for_event(db, event)
        except Exception as exc:  # alerting problems never block the barrier path
            log.error("manual-open alert queueing failed id=%s: %s", event.id, exc, exc_info=True)
    return event


def safe_record_manual_open(db: Session, **kwargs) -> ManualOpenEvent | None:
    """``record_manual_open`` for request handlers: never raises."""
    try:
        return record_manual_open(db, **kwargs)
    except Exception as exc:
        log.error("manual-open record failed: %s", exc, exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass
        return None


def event_dict(event: ManualOpenEvent, *, with_photo_link: bool = True) -> dict[str, Any]:
    entry = _aware(event.entry_time)
    created = _aware(event.created_at)
    crop = str((event.extra or {}).get("crop_ref") or "")
    return {
        "id": event.id,
        "source": event.source,
        "lane": event.lane_label,
        "side": event.side,
        "gate_id": event.gate_id,
        "camera_id": event.camera_id,
        "operator_id": event.operator_id,
        "operator": event.operator_name,
        "reason": event.reason,
        "plate": event.plate,
        "plate_confidence": float(event.plate_confidence or 0),
        "plate_seconds_before": float(event.plate_seconds_before) if event.plate_seconds_before is not None else None,
        "session_id": event.session_id,
        "parker_kind": event.parker_kind,
        "entry_time": entry.isoformat() if entry else None,
        "duration_seconds": event.duration_seconds,
        "amount_due": float(event.amount_due or 0),
        "amount_paid": float(event.amount_paid or 0),
        "amount_owed": float(event.amount_owed or 0),
        "currency": event.currency,
        "command_ok": bool(event.command_ok),
        "command_message": event.command_message,
        "photo_url": f"/media/{event.photo_ref}" if event.photo_ref else None,
        "crop_url": f"/media/{crop}" if crop else None,
        "photo_link": signed_photo_path(event) if (with_photo_link and event.photo_ref) else None,
        "alert_status": event.alert_status,
        "acknowledged": event.acknowledged_at is not None,
        "acknowledged_at": _aware(event.acknowledged_at).isoformat() if event.acknowledged_at else None,
        "acknowledged_by": event.acknowledged_by,
        "acknowledge_note": event.acknowledge_note,
        "created_at": created.isoformat() if created else None,
    }


# ------------------------------------------------------- uncommanded detection

class BoomInputWatch:
    """Edge detector for a wired "boom up" input on a camera.

    Configure per camera in the ``alerts`` site setting::

        "boom_inputs": {"3": {"index": 5, "active": 1}}

    A rising edge with no Zirp gate command for that lane within
    ``manual_open_uncommanded_window_seconds`` is an uncommanded opening.
    """

    def __init__(self) -> None:
        self._state: dict[int, bool] = {}

    def reset(self) -> None:
        self._state.clear()

    def observe(self, camera_id: int, up: bool) -> bool:
        """True exactly on a down→up transition (the first sample only primes)."""
        camera_id = int(camera_id)
        previous = self._state.get(camera_id)
        self._state[camera_id] = bool(up)
        return previous is False and bool(up)


boom_watch = BoomInputWatch()

_boom_index_cache: dict[int, tuple[float, set[int]]] = {}
BOOM_INDEX_CACHE_SECONDS = 10.0


def boom_indexes_cached(camera_id: int) -> set[int]:
    """Configured boom-up input for a camera; cached because the scan runs 4x/s."""
    camera_id = int(camera_id)
    cached = _boom_index_cache.get(camera_id)
    now = time.monotonic()
    if cached is not None and now - cached[0] < BOOM_INDEX_CACHE_SECONDS:
        return cached[1]
    try:
        from app.db import short_session
        from app.services.alerts import boom_input_indexes

        with short_session() as db:
            indexes = boom_input_indexes(db, camera_id)
    except Exception:
        indexes = cached[1] if cached is not None else set()
    _boom_index_cache[camera_id] = (now, indexes)
    return indexes


def recent_zirp_open(db: Session, camera: Camera, *, at: datetime, window_seconds: float) -> bool:
    """Did Zirp itself command this lane's barrier just now?"""
    since = at - timedelta(seconds=max(0.5, float(window_seconds)))
    if camera.gate_id and db.scalar(
        select(GateCommandRecord.id).where(
            GateCommandRecord.gate_id == camera.gate_id,
            GateCommandRecord.created_at >= since,
            GateCommandRecord.ok == True,  # noqa: E712
        ).limit(1)
    ) is not None:
        return True
    clauses = [ManualOpenEvent.created_at >= since, ManualOpenEvent.source != MANUAL_SOURCE_UNCOMMANDED]
    lane = select(ManualOpenEvent.id).where(*clauses)
    if camera.gate_id:
        lane = lane.where(
            (ManualOpenEvent.camera_id == camera.id)
            | ((ManualOpenEvent.gate_id == camera.gate_id) & (ManualOpenEvent.side.in_([(camera.lane_direction or "").upper(), ""])))
        )
    else:
        lane = lane.where(ManualOpenEvent.camera_id == camera.id)
    return db.scalar(lane.limit(1)) is not None


def boom_input_config(db: Session, camera_id: int) -> dict | None:
    from app.services.alerts import alert_settings

    entry = (alert_settings(db).get("boom_inputs") or {}).get(str(int(camera_id)))
    if not isinstance(entry, dict) or "index" not in entry:
        return None
    try:
        return {"index": int(entry["index"]), "active": int(entry.get("active", 1))}
    except (TypeError, ValueError):
        return None


def observe_boom_input(db: Session, camera: Camera, value: int, *, at: datetime | None = None) -> ManualOpenEvent | None:
    """Feed one boom-input sample; records an UNCOMMANDED event on a bare rising edge."""
    config = boom_input_config(db, camera.id)
    if config is None:
        return None
    at = _aware(at) or _now()
    if not boom_watch.observe(camera.id, int(value) == config["active"]):
        return None
    if recent_zirp_open(db, camera, at=at, window_seconds=settings.manual_open_uncommanded_window_seconds):
        return None
    return record_manual_open(
        db,
        source=MANUAL_SOURCE_UNCOMMANDED,
        camera=camera,
        side=(camera.lane_direction or "").upper(),
        reason="Barrier rose without a Zirp command",
        command_ok=True,
        command_message="boom-up input",
        extra={"input_index": config["index"]},
        at=at,
    )
