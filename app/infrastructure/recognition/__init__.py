"""Recognition providers wrap existing native HVX callbacks and FastALPR."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.plate import apply_site_plate
from app.domain.recognition import empty_vehicle_event
from app.infrastructure.recognition.fastalpr import FastALPRProvider
from app.infrastructure.recognition.native_hvx import HVXNativeALPRProvider

PROVIDERS: dict[str, Any] = {
    "hvx_native": HVXNativeALPRProvider(),
    "fastalpr": FastALPRProvider(),
}


def recognition_provider_for(provider_id: str | None = None):
    key = (provider_id or "fastalpr").strip().lower()
    return PROVIDERS.get(key) or PROVIDERS["fastalpr"]


def list_recognition_providers() -> list[str]:
    return sorted(PROVIDERS)


def normalize_event(
    *,
    camera_id: int | None = None,
    site_id: int | None = 1,
    lane_id: str | None = None,
    plate: str = "",
    plate_raw: str = "",
    confidence: float = 0.0,
    source: str = "FASTALPR",
    image_ref: str | None = None,
    plate_crop_ref: str | None = None,
    occurred_at: str | None = None,
    extra: dict[str, Any] | None = None,
    plate_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = plate_policy or {}
    applied = apply_site_plate(
        plate_raw or plate,
        normalization=str(policy.get("plate_normalization") or "ALNUM_UPPER"),
        validation=str(policy.get("plate_validation") or "NONE"),
    )
    body = empty_vehicle_event(
        event_id=uuid.uuid4().hex,
        camera_id=camera_id,
        site_id=site_id,
        lane_id=lane_id,
        occurred_at=occurred_at or datetime.now(timezone.utc).isoformat(),
        vehicle_detected=bool(applied["normalized_plate"]),
        plate_text=applied["normalized_plate"],
        plate_country=policy.get("country_code"),
        plate_region=policy.get("region_code"),
        confidence=float(confidence or 0),
        image_ref=image_ref,
        plate_crop_ref=plate_crop_ref,
        source=source,
        raw_plate=applied["raw_plate"],
        normalized_plate=applied["normalized_plate"],
        recognition_confidence=float(confidence or 0),
        validation_result=applied["validation_result"],
    )
    if extra:
        body.update(extra)
    return body
