"""Operator-facing lane status. Technical stream details stay in Hardware Lab."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.i18n import t
from app.infrastructure.hardware.cameras import adapter_has_native_plates
from app.infrastructure.hardware.registry import camera_adapter_id
from app.models import Camera, CameraStatus, Gate
from app.services.media_gateway import gateway
from app.services.site_cameras import side_label
from app.services.site_policy import site_policy


ONLINE_CAMERA = {CameraStatus.SDK_CONNECTED.value, CameraStatus.VIDEO_CONNECTED.value}


def _label(language: str, key: str, fallback: str) -> str:
    return t(key, language=language) or fallback


def camera_operator_status(camera: Camera, *, language: str = "en") -> dict[str, Any]:
    media = gateway.session(camera.id)
    live = media.live.latest() if media else None
    pumping = bool(media and media.producer is not None and not media.producer.done())
    camera_ok = camera.status in ONLINE_CAMERA or pumping or bool(live)
    live_ok = pumping or bool(live)
    native = adapter_has_native_plates(camera)
    recog_mode = str(getattr(camera, "recognition_mode", None) or ("NATIVE_ONLY" if native else "FASTALPR_ONLY"))
    if camera_ok:
        recog = _label(language, "status.ready", "Ready")
    else:
        recog = _label(language, "status.offline", "Offline")
    barrier = _label(language, "status.ready", "Ready") if camera.gate and camera.gate.enabled else _label(language, "status.unknown", "Unknown")
    live_state = media.state if media else "DISCONNECTED"
    if live_state == "DEGRADED":
        live_text = _label(language, "status.degraded", "Degraded")
    elif live_ok:
        live_text = _label(language, "status.online", "Online")
    else:
        live_text = _label(language, "status.offline", "Offline")
    return {
        "camera_id": camera.id,
        "name": camera.name,
        "lane": camera.gate.name if camera.gate else "",
        "side": side_label(camera.lane_direction),
        "label": f"{camera.gate.name} {side_label(camera.lane_direction)}".strip() or camera.name,
        "camera": _label(language, "status.online", "Online") if camera_ok else _label(language, "status.offline", "Offline"),
        "live_video": live_text,
        "plate_recognition": recog,
        "barrier": barrier,
        "adapter_id": camera_adapter_id(camera),
        "recognition_mode": recog_mode,
        "status": camera.status,
    }


def lane_operator_status(db: Session) -> dict[str, Any]:
    policy = site_policy(db)
    language = str(policy.get("language") or "en")
    cameras = list(db.scalars(select(Camera).order_by(Camera.id)).all())
    gates = list(db.scalars(select(Gate).order_by(Gate.id)).all())
    lanes = [camera_operator_status(camera, language=language) for camera in cameras]
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
