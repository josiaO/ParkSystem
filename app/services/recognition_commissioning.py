"""Recognition commissioning diagnostics.

This module is intentionally diagnostic-only.  It never persists a plate,
creates a parking session, or controls a barrier.  It summarizes the same
camera/media/recognition paths used by production and can run one explicit
software read against the latest evidence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.infrastructure.hardware.cameras import adapter_has_native_plates
from app.models import Camera, VehicleCapture
from app.services.camera_lpr import local_from_fastalpr, plate_capture_quality
from app.services.captures import capture_dict, latest_for_camera
from app.services.ocr_policy import camera_recognition_mode
from app.services.preview import get_state
from app.services.stream_roles import ROLE_DETECT, ROLE_MAIN, ROLE_SUB, resolve_role_row


def _worker_row(camera_id: int) -> dict[str, Any]:
    from app.recognition_worker import worker_health, worker_owns_software_reads

    health = worker_health()
    row = next(
        (
            dict(item)
            for item in (health.get("cameras") or [])
            if isinstance(item, dict) and int(item.get("camera_id") or 0) == int(camera_id)
        ),
        {},
    )
    return {
        "owns_continuous_software_reads": bool(worker_owns_software_reads(camera_id)),
        "worker_ok": bool(health.get("ok")),
        "heartbeat_age_seconds": health.get("heartbeat_age_seconds"),
        **row,
    }


def _media_row(camera_id: int) -> dict[str, Any]:
    from app.services.preview import live_metrics
    from app.infrastructure.media.registry import media_telemetry

    local = next(
        (dict(row) for row in live_metrics() if int(row.get("camera_id") or 0) == int(camera_id)),
        {},
    )
    try:
        telemetry = dict(media_telemetry(camera_id) or {})
    except Exception as exc:
        telemetry = {"state": "UNKNOWN", "error": str(exc)[:200]}
    return {
        "connection_state": local.get("connection_state") or telemetry.get("state") or "DISCONNECTED",
        "live_fps": local.get("fps") or 0,
        "live_frame_age_ms": local.get("live_frame_age_ms"),
        "detect_frame_age_ms": local.get("detect_frame_age_ms") if local.get("detect_frame_age_ms") is not None else local.get("ai_frame_age_ms"),
        "source_fps": local.get("source_fps") or 0,
        "frozen": bool(local.get("frozen")),
        "duplicate_frames": local.get("duplicate_frames") or 0,
        "frames_changed": local.get("frames_changed") or 0,
        "ai_processed_fps": local.get("ai_processed_fps") or 0,
        "ai_samples_dropped": local.get("ai_samples_dropped") or 0,
        "codec": local.get("codec") or telemetry.get("codec") or "",
        "transport": local.get("transport") or "",
        "reconnects": local.get("reconnects") or 0,
        "frames_received": local.get("frames_received") or 0,
        "frames_dropped_live": local.get("frames_dropped_live") or 0,
        "frames_sampled_ai": local.get("frames_sampled_ai") or 0,
        "frames_dropped_ai": local.get("frames_dropped_ai") or 0,
        "warnings": list(local.get("warnings") or []),
        "mediamtx": telemetry,
    }


def _latest_capture(db: Session, camera: Camera) -> tuple[VehicleCapture | None, dict[str, Any] | None]:
    row = latest_for_camera(db, camera.id)
    if row is None:
        return None, None
    body = capture_dict(row)
    body["capture_quality"] = plate_capture_quality(body.get("bbox"))
    body["age_seconds"] = None
    if row.created_at is not None:
        created = row.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        body["age_seconds"] = max(0.0, (datetime.now(timezone.utc) - created).total_seconds())
    fusion = dict(body.get("fusion") or {})
    body["native"] = {
        "plate": body.get("native_plate") or fusion.get("native_plate") or "",
        "confidence": float(fusion.get("native_confidence") or 0),
    }
    body["local"] = {
        "plate": body.get("local_plate") or fusion.get("local_plate") or "",
        "confidence": float(fusion.get("local_confidence") or 0),
    }
    return row, body


def _detect_recommendation(camera: Camera, capture: dict[str, Any] | None) -> dict[str, Any]:
    profiles = dict(camera.stream_profiles or {})
    detect = resolve_role_row(profiles, ROLE_DETECT)
    main = resolve_role_row(profiles, ROLE_MAIN)
    sub = resolve_role_row(profiles, ROLE_SUB)
    quality = dict((capture or {}).get("capture_quality") or {})
    width = int(quality.get("plate_width_px") or 0)
    current_source = str((profiles.get(ROLE_DETECT) or {}).get("source") or ROLE_SUB).upper()

    recommendation = current_source or ROLE_SUB
    reason = "Keep the configured DETECT role until measured plate size says otherwise."
    if width and width < 100 and (main.get("uri") or main.get("url") or profiles.get(ROLE_MAIN)):
        recommendation = ROLE_MAIN
        reason = (
            f"Latest plate is only {width}px wide. Use MAIN for DETECT or tighten camera framing "
            "until the plate is consistently at least about 100–130px wide."
        )
    elif width >= 130 and (sub.get("uri") or sub.get("url") or profiles.get(ROLE_SUB)):
        recommendation = ROLE_SUB
        reason = f"Latest plate is {width}px wide; SUB is sufficient for recognition and costs less to decode."
    elif width >= 100:
        reason = f"Latest plate is {width}px wide and is usable; keep DETECT stable and measure day/night accuracy."

    return {
        "configured_source": current_source,
        "recommended_source": recommendation,
        "reason": reason,
        "detect_profile": detect,
        "main_profile": main,
        "sub_profile": sub,
    }


def _recommendations(camera: Camera, capture: dict[str, Any] | None, media: dict[str, Any], worker: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    native = adapter_has_native_plates(camera)
    mode = camera_recognition_mode(camera)
    quality = dict((capture or {}).get("capture_quality") or {})
    width = int(quality.get("plate_width_px") or 0)

    if native and mode != "NATIVE_WITH_LOCAL_VERIFY":
        out.append({
            "severity": "info",
            "code": "MODE_HYBRID_RECOMMENDED",
            "message": "This camera can originate plate metadata. HYBRID event verification gives native OCR plus one software reread of the event image/crop.",
        })
    if not native and mode != "LOCAL_ONLY":
        out.append({
            "severity": "warning",
            "code": "MODE_LOCAL_REQUIRED",
            "message": "This camera has no native plate capability; FASTALPR_ONLY is the correct recognition mode.",
        })
    if width and width < 75:
        out.append({
            "severity": "critical",
            "code": "PLATE_TOO_SMALL",
            "message": f"The latest plate is only {width}px wide. Improve zoom/framing or use a higher-resolution DETECT stream before tuning OCR.",
        })
    elif width and width < 100:
        out.append({
            "severity": "warning",
            "code": "PLATE_MARGINAL",
            "message": f"The latest plate is {width}px wide. Aim for roughly 100–130px or more at the recognition point.",
        })
    if media.get("live_frame_age_ms") is not None and float(media["live_frame_age_ms"]) > 1000:
        out.append({
            "severity": "warning",
            "code": "LIVE_STALE",
            "message": f"Live video is stale ({float(media['live_frame_age_ms']):.0f} ms frame age). Check camera transport/GOP/network before OCR tuning.",
        })
    if worker.get("owns_continuous_software_reads") and native:
        out.append({
            "severity": "warning",
            "code": "NATIVE_CAMERA_CONTINUOUS_OCR",
            "message": "A native-LPR camera is using continuous software reads. Prefer event-image verification to reduce decode/inference load.",
        })
    if not out:
        out.append({
            "severity": "ok",
            "code": "BASELINE_OK",
            "message": "No immediate commissioning issue is visible from the latest diagnostics.",
        })
    return out


def commissioning_snapshot(db: Session, camera: Camera) -> dict[str, Any]:
    """Return a no-side-effect commissioning snapshot for one camera."""
    _row, capture = _latest_capture(db, camera)
    state = get_state(camera.id)
    alpr = dict(state.alpr or {})
    local = local_from_fastalpr(alpr)
    media = _media_row(camera.id)
    worker = _worker_row(camera.id)
    detect = _detect_recommendation(camera, capture)
    native_capable = adapter_has_native_plates(camera)
    mode = camera_recognition_mode(camera)
    strategy = (
        "EVENT_VERIFY"
        if native_capable and mode == "NATIVE_WITH_LOCAL_VERIFY"
        else "NATIVE_EVENTS"
        if native_capable and mode == "NATIVE_ONLY"
        else "CONTINUOUS_DETECT"
    )

    return {
        "camera_id": camera.id,
        "camera_name": camera.name,
        "site_id": camera.site_id,
        "lane_direction": camera.lane_direction,
        "adapter_id": camera.adapter_id,
        "status": camera.status,
        "recognition": {
            "mode": "HYBRID" if mode == "NATIVE_WITH_LOCAL_VERIFY" else ("FASTALPR_ONLY" if mode == "LOCAL_ONLY" else "NATIVE_ONLY"),
            "strategy": strategy,
            "native_capable": native_capable,
            "local_engine": "fastalpr",
            "latest_local": {
                "plate": local.get("plate") or "",
                "confidence": float(local.get("confidence") or 0),
                "pipeline": alpr.get("pipeline") or "",
                "latency_ms": alpr.get("latency_ms"),
                "backend": alpr.get("backend") or "",
                "crop_url": (alpr.get("best") or {}).get("crop_url") if isinstance(alpr.get("best"), dict) else None,
            },
        },
        "capture": capture,
        "media": media,
        "worker": worker,
        "detect_stream": detect,
        "recommendations": _recommendations(camera, capture, media, worker),
    }


def _safe_media_bytes(relative: str) -> bytes:
    text = str(relative or "").replace("\\", "/").strip("/")
    if not text or ".." in text.split("/"):
        return b""
    root = settings.media_dir.resolve()
    path = (root / text).resolve()
    if root not in path.parents or not path.is_file():
        return b""
    try:
        data = path.read_bytes()
    except OSError:
        return b""
    return data if data[:2] == b"\xff\xd8" else b""


def diagnostic_evidence(db: Session, camera: Camera) -> tuple[bytes, str]:
    """Prefer the latest persisted plate crop, then event snapshot, then live cache."""
    row = latest_for_camera(db, camera.id)
    if row is not None:
        crop = _safe_media_bytes(row.crop_path)
        if crop:
            return crop, "plate_crop"
        snapshot = _safe_media_bytes(row.snapshot_path)
        if snapshot:
            return snapshot, "event_snapshot"
    state = get_state(camera.id)
    if state.jpeg[:2] == b"\xff\xd8":
        return state.jpeg, "live_frame"
    return b"", "none"


def diagnostic_read(db: Session, camera: Camera) -> dict[str, Any]:
    """Run one explicit software read without persistence or parking side effects."""
    jpeg, source = diagnostic_evidence(db, camera)
    if not jpeg:
        return {
            "ok": False,
            "camera_id": camera.id,
            "evidence_source": source,
            "detail": "No persisted plate crop, event snapshot, or cached live frame is available.",
        }
    if source == "plate_crop":
        from app.services.alpr import recognize_plate_crop_bytes

        result = recognize_plate_crop_bytes(jpeg, camera_label=f"commissioning-cam-{camera.id}-crop")
    else:
        from app.infrastructure.recognition.engines import recognize_frame

        result = recognize_frame(jpeg, camera_label=f"commissioning-cam-{camera.id}-{source}")
    return {
        "camera_id": camera.id,
        "evidence_source": source,
        **dict(result or {}),
    }
