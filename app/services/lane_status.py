"""Operator-facing lane status. Technical stream details stay in Hardware Lab."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.i18n import t
from app.config import settings
from app.infrastructure.hardware.registry import camera_adapter_id
from app.models import Camera, CameraStatus, Gate
from app.services.captures import latest_for_cameras
from app.services.ocr_policy import LOCAL_ONLY, NATIVE_ONLY, camera_recognition_mode
from app.services.media_gateway import gateway
from app.services.site_cameras import side_label
from app.services.site_policy import site_policy


ONLINE_CAMERA = {CameraStatus.SDK_CONNECTED.value, CameraStatus.VIDEO_CONNECTED.value}


def _label(language: str, key: str, fallback: str) -> str:
    return t(key, language=language) or fallback


def _lane_label(camera: Camera) -> str:
    side = side_label(camera.lane_direction)
    if camera.gate and camera.gate.name:
        return f"{camera.gate.name} {side}".strip()
    return (camera.name or "").strip() or f"Camera {camera.id}"


def camera_operator_status(
    camera: Camera,
    *,
    language: str = "en",
    db: Session | None = None,
    latest=None,
) -> dict[str, Any]:
    media = gateway.session(camera.id)
    live = media.live.latest() if media else None
    pumping = bool(media and media.producer is not None and not media.producer.done())
    camera_ok = camera.status in ONLINE_CAMERA or pumping or bool(live)
    live_ok = bool(live and live.age_ms() <= settings.stale_stream_seconds * 1000)
    canonical = camera_recognition_mode(camera)
    if canonical == LOCAL_ONLY:
        recog_mode = "FASTALPR_ONLY"
    elif canonical == NATIVE_ONLY:
        recog_mode = "NATIVE_ONLY"
    else:
        recog_mode = "HYBRID"
    if camera_ok:
        recog = _label(language, "status.ready", "Ready")
    else:
        recog = _label(language, "status.offline", "Offline")
    from app.services.node_scope import camera_active_on_this_installation, describe_recognition_scope
    if not camera_active_on_this_installation(camera, db=db):
        scope = describe_recognition_scope(db)
        recog = "NODE NOT ASSIGNED TO GATE" if scope["mode"] == "unassigned" else "OTHER GATE"
    barrier = _label(language, "status.ready", "Ready") if camera.gate and camera.gate.enabled else _label(language, "status.unknown", "Unknown")
    live_state = media.state if media else "DISCONNECTED"
    if live_state == "DEGRADED":
        live_text = _label(language, "status.degraded", "Degraded")
    elif live_ok:
        live_text = _label(language, "status.online", "Online")
    else:
        live_text = _label(language, "status.offline", "Offline")
    last_plate = ""
    pending = False
    if db is not None and latest is None:
        latest = latest_for_cameras(db, [camera.id]).get(int(camera.id))
    if latest is not None:
        last_plate = latest.plate or ""
        pending = bool(isinstance(latest.bbox, dict) and latest.bbox.get("pending_confirmation"))
    gate_mode = str(camera.gate.mode if camera.gate else "")
    waiting = _label(language, "status.waiting", "Waiting for confirmation") if pending else ""
    return {
        "camera_id": camera.id,
        "name": camera.name,
        "lane": camera.gate.name if camera.gate else "",
        "side": side_label(camera.lane_direction),
        "label": _lane_label(camera),
        "camera": _label(language, "status.online", "Online") if camera_ok else _label(language, "status.offline", "Offline"),
        "live_video": live_text,
        "plate_recognition": recog,
        "barrier": barrier,
        "adapter_id": camera_adapter_id(camera),
        "recognition_mode": recog_mode,
        "status": camera.status,
        "last_plate": last_plate,
        "gate_mode": gate_mode or "COMMISSIONING",
        "pending_confirmation": pending,
        "manual_action": waiting,
        "camera_ok": camera_ok,
    }


def lane_operator_status(db: Session) -> dict[str, Any]:
    policy = site_policy(db)
    language = str(policy.get("language") or "en")
    cameras = list(db.scalars(
        select(Camera).options(joinedload(Camera.gate)).order_by(Camera.id)
    ).all())
    gates = list(db.scalars(select(Gate).order_by(Gate.id)).all())
    # The dashboard polls this endpoint frequently. Fetch the last evidence
    # row for all cameras together instead of issuing one query per lane.
    latest = latest_for_cameras(db, [camera.id for camera in cameras])
    lanes = []
    for camera in cameras:
        last = latest.get(int(camera.id))
        lanes.append(camera_operator_status(camera, language=language, db=db, latest=last))
    return {
        "site": {
            "name": policy.get("name"),
            "timezone": policy.get("timezone"),
            "currency": policy.get("currency"),
            "language": language,
        },
        "lanes": lanes,
        "gates": [{"id": g.id, "name": g.name, "mode": g.mode, "enabled": g.enabled} for g in gates],
    }
