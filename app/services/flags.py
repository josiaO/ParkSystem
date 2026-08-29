"""Feature flags. Env/settings are the default; site_settings.migration can override for rollback."""

from __future__ import annotations

from typing import Any

from app.domain.flags import (
    DEFAULT_FLAGS,
    LIVE_VIEW_DIRECT_LEGACY,
    LIVE_VIEW_MEDIAMTX,
    RECOGNITION_FASTALPR_LEGACY,
    RECOGNITION_FASTALPR_NEW,
)


def _csv_ids(value: Any) -> list[int]:
    if isinstance(value, list):
        out: list[int] = []
        for item in value:
            try:
                out.append(int(item))
            except (TypeError, ValueError):
                continue
        return out
    text = str(value or "").strip()
    if not text:
        return []
    ids: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return ids


def _from_settings() -> dict[str, Any]:
    from app.config import settings

    live = str(getattr(settings, "live_view_provider", LIVE_VIEW_DIRECT_LEGACY) or LIVE_VIEW_DIRECT_LEGACY).upper()
    if live not in {LIVE_VIEW_DIRECT_LEGACY, LIVE_VIEW_MEDIAMTX}:
        live = LIVE_VIEW_DIRECT_LEGACY
    recog = str(getattr(settings, "recognition_pipeline", RECOGNITION_FASTALPR_LEGACY) or RECOGNITION_FASTALPR_LEGACY).upper()
    if recog not in {RECOGNITION_FASTALPR_LEGACY, RECOGNITION_FASTALPR_NEW}:
        recog = RECOGNITION_FASTALPR_LEGACY
    return {
        "media_gateway_enabled": bool(getattr(settings, "media_gateway_enabled", False)),
        "media_gateway_camera_ids": _csv_ids(getattr(settings, "media_gateway_camera_ids", "")),
        "fastalpr_new_pipeline_enabled": bool(getattr(settings, "fastalpr_new_pipeline_enabled", False)),
        "webrtc_live_enabled": bool(getattr(settings, "webrtc_live_enabled", False)),
        "native_alpr_enabled": bool(getattr(settings, "native_alpr_enabled", True)),
        "live_view_provider": live,
        "recognition_pipeline": recog,
    }


def flags(db=None) -> dict[str, Any]:
    merged = {**DEFAULT_FLAGS, **_from_settings()}
    if db is None:
        return merged
    try:
        from app.models import SiteSetting
        row = db.get(SiteSetting, "migration")
        if row and isinstance(row.value, dict):
            extra = dict(row.value)
            if "media_gateway_camera_ids" in extra:
                extra["media_gateway_camera_ids"] = _csv_ids(extra["media_gateway_camera_ids"])
            merged.update({k: extra[k] for k in DEFAULT_FLAGS if k in extra})
    except Exception:
        pass
    return merged


def save_flags(db, payload: dict[str, Any]) -> dict[str, Any]:
    from app.models import SiteSetting

    current = flags(db)
    for key in DEFAULT_FLAGS:
        if key not in payload or payload[key] is None:
            continue
        if key == "media_gateway_camera_ids":
            current[key] = _csv_ids(payload[key])
        elif key in {"live_view_provider", "recognition_pipeline"}:
            current[key] = str(payload[key]).strip().upper()
        else:
            current[key] = bool(payload[key])
    stored = dict(current)
    stored["media_gateway_camera_ids"] = list(current["media_gateway_camera_ids"])
    row = db.get(SiteSetting, "migration")
    if row is None:
        db.add(SiteSetting(key="migration", value=stored))
    else:
        row.value = stored
    db.commit()
    return flags(db)


def media_mtx_for_camera(camera_id: int, db=None) -> bool:
    cfg = flags(db)
    if not cfg["media_gateway_enabled"]:
        return False
    allow = cfg["media_gateway_camera_ids"]
    return not allow or int(camera_id) in allow


def native_alpr_enabled(db=None) -> bool:
    return bool(flags(db).get("native_alpr_enabled", True))
