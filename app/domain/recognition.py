"""Recognition provider contract. Parking consumes only normalized events."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol, runtime_checkable


RECOGNITION_SOURCES = ("HVX_NATIVE", "FASTALPR", "ONVIF_ANALYTICS", "OPERATOR")
RECOGNITION_MODES = ("NATIVE_ONLY", "FASTALPR_ONLY", "HYBRID")
CONF_HIGH = "HIGH"
CONF_MEDIUM = "MEDIUM"
CONF_LOW = "LOW"
CONFIDENCE_CLASSES = (CONF_HIGH, CONF_MEDIUM, CONF_LOW)


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
        "provider": "FASTALPR",
        "raw_plate": "",
        "plate_raw": "",
        "normalized_plate": "",
        "plate_normalized": "",
        "plate_type": None,
        "recognition_confidence": 0.0,
        "validation_result": "NONE",
        "bbox": None,
        "visit_id": "",
    }
    body.update(overrides)
    if "provider" not in overrides and body.get("source"):
        body["provider"] = body["source"]
    if "source" not in overrides and body.get("provider"):
        body["source"] = body["provider"]
    if "plate_raw" not in overrides and body.get("raw_plate"):
        body["plate_raw"] = body["raw_plate"]
    if "raw_plate" not in overrides and body.get("plate_raw"):
        body["raw_plate"] = body["plate_raw"]
    if "plate_normalized" not in overrides and body.get("normalized_plate"):
        body["plate_normalized"] = body["normalized_plate"]
    if "normalized_plate" not in overrides and body.get("plate_normalized"):
        body["normalized_plate"] = body["plate_normalized"]
        body["plate_text"] = body.get("plate_text") or body["plate_normalized"]
    return body


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class NormalizedRecognitionEvent:
    """One stable vehicle read. Native ALPR and FastALPR share this shape."""

    event_id: str
    site_id: int | None
    camera_id: int | None
    lane_id: int | None
    occurred_at: str
    provider: str
    plate_raw: str
    plate_normalized: str
    confidence: float
    bbox: dict[str, Any] | None
    vehicle_detected: bool
    image_ref: str | None
    plate_crop_ref: str | None
    confidence_class: str = CONF_MEDIUM
    needs_review: bool = False
    accepted: bool = True
    mode: str = "FASTALPR_ONLY"
    presence: bool | None = None
    consensus: dict[str, Any] | None = None
    fusion: dict[str, Any] | None = None
    visit_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        body = asdict(self)
        return empty_vehicle_event(
            plate_text=self.plate_normalized,
            recognition_confidence=self.confidence,
            **body,
        )

    def as_entry_candidate(self) -> dict[str, Any] | None:
        """Parking-facing payload. LOW / held / empty plates are not candidates."""
        if (
            not self.accepted
            or self.needs_review
            or self.confidence_class == CONF_LOW
            or not self.plate_normalized
            or not self.event_id
        ):
            return None
        return {
            "event_id": self.event_id,
            "site_id": self.site_id,
            "camera_id": self.camera_id,
            "lane_id": self.lane_id,
            "plate_raw": self.plate_raw,
            "plate_normalized": self.plate_normalized,
            "image_ref": self.image_ref or "",
            "occurred_at": self.occurred_at,
            "provider": self.provider,
            "confidence": self.confidence,
            "visit_id": self.visit_id or "",
        }

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "NormalizedRecognitionEvent":
        payload = data.get("payload") if isinstance(data.get("payload"), dict) else data
        plate_norm = str(
            payload.get("plate_normalized")
            or payload.get("normalized_plate")
            or payload.get("plate_text")
            or ""
        )
        plate_raw = str(payload.get("plate_raw") or payload.get("raw_plate") or payload.get("plate_text_raw") or plate_norm)
        conf = float(payload.get("confidence") or payload.get("recognition_confidence") or 0)
        return cls(
            event_id=str(data.get("event_id") or payload.get("event_id") or ""),
            site_id=_as_int(data.get("site_id") if data.get("site_id") is not None else payload.get("site_id")),
            camera_id=_as_int(payload.get("camera_id")),
            lane_id=_as_int(payload.get("lane_id")),
            occurred_at=str(data.get("occurred_at") or payload.get("occurred_at") or ""),
            provider=str(payload.get("provider") or payload.get("source") or payload.get("recognition_provider") or "FASTALPR"),
            plate_raw=plate_raw,
            plate_normalized=plate_norm,
            confidence=conf,
            bbox=payload.get("bbox") if isinstance(payload.get("bbox"), dict) else None,
            vehicle_detected=bool(payload.get("vehicle_detected", True)),
            image_ref=payload.get("image_ref"),
            plate_crop_ref=payload.get("plate_crop_ref"),
            confidence_class=str(payload.get("confidence_class") or CONF_MEDIUM),
            needs_review=bool(payload.get("needs_review")),
            accepted=bool(payload.get("accepted", not payload.get("needs_review"))),
            mode=str(payload.get("mode") or payload.get("recognition_mode") or "FASTALPR_ONLY"),
            presence=payload.get("presence"),
            consensus=payload.get("consensus") if isinstance(payload.get("consensus"), dict) else None,
            fusion=payload.get("fusion") if isinstance(payload.get("fusion"), dict) else None,
            visit_id=str(payload.get("visit_id") or data.get("visit_id") or ""),
        )
