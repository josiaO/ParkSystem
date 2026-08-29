"""HVX native ALPR provider. Wraps existing callback mapping; does not talk to NetSDK."""

from __future__ import annotations

from typing import Any

from app.services.camera_lpr import native_from_sdk_capture


class HVXNativeALPRProvider:
    id = "hvx_native"

    async def process(self, event_or_frame: dict[str, Any]) -> dict[str, Any]:
        capture = event_or_frame.get("capture") or event_or_frame
        hit = native_from_sdk_capture(capture)
        from app.infrastructure.recognition import normalize_event

        return normalize_event(
            camera_id=event_or_frame.get("camera_id"),
            site_id=event_or_frame.get("site_id"),
            lane_id=event_or_frame.get("lane_id"),
            plate=str(hit.get("plate") or ""),
            plate_raw=str(hit.get("plate_raw") or hit.get("plate") or ""),
            confidence=float(hit.get("confidence") or 0),
            source="HVX_NATIVE",
            image_ref=event_or_frame.get("image_ref"),
            plate_crop_ref=event_or_frame.get("plate_crop_ref"),
            extra={"bbox": hit.get("bbox"), "native": hit},
            plate_policy=event_or_frame.get("plate_policy"),
        )
