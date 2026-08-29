"""Recognition provider contract. Parking consumes only normalized events."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


RECOGNITION_SOURCES = ("HVX_NATIVE", "FASTALPR", "ONVIF_ANALYTICS", "OPERATOR")
RECOGNITION_MODES = ("NATIVE_ONLY", "FASTALPR_ONLY", "HYBRID")


@runtime_checkable
class RecognitionProvider(Protocol):
    id: str

    async def process(self, event_or_frame: dict[str, Any]) -> dict[str, Any]: ...


def empty_vehicle_event(**overrides: Any) -> dict[str, Any]:
    body = {
        "event_id": "",
        "camera_id": None,
        "site_id": None,
        "lane_id": None,
        "occurred_at": None,
        "vehicle_detected": False,
        "plate_text": "",
        "plate_country": None,
        "plate_region": None,
        "confidence": 0.0,
        "vehicle_type": None,
        "vehicle_color": None,
        "image_ref": None,
        "plate_crop_ref": None,
        "source": "FASTALPR",
        "raw_plate": "",
        "normalized_plate": "",
        "plate_type": None,
        "recognition_confidence": 0.0,
        "validation_result": "NONE",
    }
    body.update(overrides)
    return body
