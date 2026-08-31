"""Typed application event contracts. Modules communicate via these shapes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.domain.recognition import empty_vehicle_event


EVENT_VEHICLE_DETECTED = "VehicleDetected"
EVENT_PLATE_RECOGNIZED = "PlateRecognized"
EVENT_WATCHLIST_MATCHED = "WatchlistMatched"
EVENT_PARKING_SESSION_STARTED = "ParkingSessionStarted"
EVENT_PARKING_FEE_CALCULATED = "ParkingFeeCalculated"
EVENT_PAYMENT_CONFIRMED = "PaymentConfirmed"
EVENT_EXIT_AUTHORIZED = "ExitAuthorized"
EVENT_GATE_COMMAND_REQUESTED = "GateCommandRequested"
EVENT_GATE_OPENED = "GateOpened"

ALL_EVENT_KINDS = (
    EVENT_VEHICLE_DETECTED,
    EVENT_PLATE_RECOGNIZED,
    EVENT_WATCHLIST_MATCHED,
    EVENT_PARKING_SESSION_STARTED,
    EVENT_PARKING_FEE_CALCULATED,
    EVENT_PAYMENT_CONFIRMED,
    EVENT_EXIT_AUTHORIZED,
    EVENT_GATE_COMMAND_REQUESTED,
    EVENT_GATE_OPENED,
)


def _base_event(kind: str, **fields: Any) -> dict[str, Any]:
    body = {
        "kind": kind,
        "event_id": str(uuid4()),
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "site_id": None,
        "payload": {},
    }
    body.update(fields)
    return body


def plate_recognized(
    *,
    site_id: int | None = None,
    camera_id: int | None = None,
    lane_id: int | None = None,
    plate_text_raw: str = "",
    plate_text_normalized: str = "",
    country_code: str | None = None,
    region_code: str | None = None,
    confidence: float = 0.0,
    recognition_provider: str = "FASTALPR",
    image_ref: str | None = None,
    plate_crop_ref: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Country-neutral normalized recognition contract."""
    vehicle = empty_vehicle_event(
        event_id=str(uuid4()),
        site_id=site_id,
        camera_id=camera_id,
        lane_id=lane_id,
        occurred_at=datetime.now(timezone.utc).isoformat(),
        vehicle_detected=True,
        plate_text=plate_text_normalized,
        raw_plate=plate_text_raw,
        normalized_plate=plate_text_normalized,
        plate_country=country_code,
        plate_region=region_code,
        confidence=confidence,
        recognition_confidence=confidence,
        image_ref=image_ref,
        plate_crop_ref=plate_crop_ref,
        source=recognition_provider,
    )
    return _base_event(
        EVENT_PLATE_RECOGNIZED,
        site_id=site_id,
        payload={
            **vehicle,
            "plate_text_raw": plate_text_raw,
            "plate_text_normalized": plate_text_normalized,
            "country_code": country_code,
            "region_code": region_code,
            "recognition_provider": recognition_provider,
            **extra,
        },
    )


def vehicle_detected(**fields: Any) -> dict[str, Any]:
    return _base_event(EVENT_VEHICLE_DETECTED, payload=dict(fields))


def watchlist_matched(plate: str, watchlist_id: int | None = None, **fields: Any) -> dict[str, Any]:
    return _base_event(
        EVENT_WATCHLIST_MATCHED,
        payload={"plate": plate, "watchlist_id": watchlist_id, **fields},
    )


def parking_session_started(session_id: int, plate: str, **fields: Any) -> dict[str, Any]:
    return _base_event(
        EVENT_PARKING_SESSION_STARTED,
        payload={"session_id": session_id, "plate": plate, **fields},
    )


def parking_fee_calculated(session_id: int, amount: float, currency: str, **fields: Any) -> dict[str, Any]:
    return _base_event(
        EVENT_PARKING_FEE_CALCULATED,
        payload={"session_id": session_id, "amount": amount, "currency": currency, **fields},
    )


def payment_confirmed(session_id: int, transaction_id: int, **fields: Any) -> dict[str, Any]:
    return _base_event(
        EVENT_PAYMENT_CONFIRMED,
        payload={"session_id": session_id, "transaction_id": transaction_id, **fields},
    )


def exit_authorized(session_id: int, plate: str, **fields: Any) -> dict[str, Any]:
    return _base_event(
        EVENT_EXIT_AUTHORIZED,
        payload={"session_id": session_id, "plate": plate, **fields},
    )


def gate_command_requested(gate_id: int, reason: str, **fields: Any) -> dict[str, Any]:
    return _base_event(
        EVENT_GATE_COMMAND_REQUESTED,
        payload={"gate_id": gate_id, "reason": reason, **fields},
    )


def gate_opened(gate_id: int, command_uuid: str, **fields: Any) -> dict[str, Any]:
    return _base_event(
        EVENT_GATE_OPENED,
        payload={"gate_id": gate_id, "command_uuid": command_uuid, **fields},
    )


def from_recognition_dict(recognition: dict[str, Any]) -> dict[str, Any]:
    """Bridge legacy normalized recognition dicts to PlateRecognized contract."""
    event = plate_recognized(
        site_id=recognition.get("site_id"),
        camera_id=recognition.get("camera_id"),
        lane_id=recognition.get("lane_id"),
        plate_text_raw=recognition.get("raw_plate") or recognition.get("plate_text") or "",
        plate_text_normalized=recognition.get("normalized_plate") or recognition.get("plate_text") or "",
        country_code=recognition.get("plate_country"),
        region_code=recognition.get("plate_region"),
        confidence=float(recognition.get("confidence") or recognition.get("recognition_confidence") or 0),
        recognition_provider=str(recognition.get("source") or "FASTALPR"),
        image_ref=recognition.get("image_ref"),
        plate_crop_ref=recognition.get("plate_crop_ref"),
    )
    if recognition.get("event_id"):
        event["event_id"] = recognition["event_id"]
    return event
