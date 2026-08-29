"""FastALPR provider. Wraps app.services.alpr.recognize_bytes. Does not own cameras."""

from __future__ import annotations

from typing import Any

from app.services.alpr import recognize_bytes
from app.services.camera_lpr import local_from_fastalpr


class FastALPRProvider:
    id = "fastalpr"

    async def process(self, event_or_frame: dict[str, Any]) -> dict[str, Any]:
        jpeg = event_or_frame.get("jpeg") or b""
        label = str(event_or_frame.get("camera_label") or event_or_frame.get("camera_id") or "frame")
        result = recognize_bytes(jpeg, camera_label=str(label))
        local = local_from_fastalpr(result)
        from app.infrastructure.recognition import normalize_event

        return normalize_event(
            camera_id=event_or_frame.get("camera_id"),
            site_id=event_or_frame.get("site_id"),
            lane_id=event_or_frame.get("lane_id"),
            plate=str(local.get("plate") or ""),
            plate_raw=str(local.get("plate_raw") or local.get("plate") or ""),
            confidence=float(local.get("confidence") or 0),
            source="FASTALPR",
            image_ref=result.get("image_url") or event_or_frame.get("image_ref"),
            plate_crop_ref=(local.get("crop_url") or (local.get("best") or {}).get("crop_url") if isinstance(local, dict) else None),
            extra={"local": local, "backend": result.get("backend"), "ok": result.get("ok")},
            plate_policy=event_or_frame.get("plate_policy"),
        )
