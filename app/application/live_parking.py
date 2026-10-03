"""Authoritative live ENTRY bridge: persisted recognition -> EntryLaneController.

Simulation endpoints keep their own fixture-oriented flow. Real camera entry events
must pass through the parking application controller so receipt, authorization,
idempotency and gate state transitions are not duplicated in API callbacks.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.application.entry_lane import EntryLaneController, policy_from_parking_settings
from app.config import settings
from app.domain.recognition import (
    CONF_HIGH,
    CONF_LOW,
    CONF_MEDIUM,
    NormalizedRecognitionEvent,
)
from app.infrastructure.hardware.receipt_printers import receipt_printer_for
from app.models import Camera, Gate, VehicleCapture
from app.services.simulation import parking_settings


def _confidence_class(value: float) -> str:
    score = float(value or 0)
    if score >= float(settings.recognition_high_confidence):
        return CONF_HIGH
    if score >= float(settings.recognition_medium_confidence):
        return CONF_MEDIUM
    return CONF_LOW


def event_from_capture(camera: Camera, row: VehicleCapture, *, source: str = "camera") -> NormalizedRecognitionEvent:
    box = row.bbox if isinstance(row.bbox, dict) else {}
    confidence = float(row.confidence or 0)
    needs_review = bool(box.get("needs_review") or box.get("pending_confirmation"))
    klass = _confidence_class(confidence)
    event_id = str(row.event_id or f"capture-{row.id}")
    return NormalizedRecognitionEvent(
        event_id=event_id,
        site_id=int(camera.site_id),
        camera_id=int(camera.id),
        lane_id=camera.lane_id,
        occurred_at=row.created_at.isoformat() if row.created_at else "",
        provider=str(row.source or source or "CAMERA").upper(),
        plate_raw=str(row.plate_raw or row.plate or ""),
        plate_normalized=str(row.plate or ""),
        confidence=confidence,
        bbox=box or None,
        vehicle_detected=True,
        image_ref=f"/media/{row.snapshot_path}" if row.snapshot_path else None,
        plate_crop_ref=f"/media/{row.crop_path}" if row.crop_path else None,
        confidence_class=klass,
        needs_review=needs_review,
        accepted=bool(row.plate) and not needs_review and klass != CONF_LOW,
        mode=str(camera.recognition_mode or settings.alpr_mode or "FASTALPR_ONLY"),
        presence=True,
        visit_id=str(getattr(row, "visit_id", "") or box.get("visit_id") or ""),
    )


async def handle_live_entry(
    db: Session,
    *,
    camera: Camera,
    capture: VehicleCapture,
    gate: Gate | None,
    source: str = "camera",
) -> dict:
    cfg = parking_settings(db)
    policy = policy_from_parking_settings(cfg)
    printer = receipt_printer_for(
        str(cfg.get("printer_adapter") or settings.printer_adapter or "simulated"),
        str(cfg.get("printer_name") or settings.printer_name or ""),
    )
    controller = EntryLaneController(printer=printer)
    return await controller.submit(
        db,
        event_from_capture(camera, capture, source=source),
        gate=gate,
        camera=camera,
        policy=policy,
        occupied=True,
        simulated=False,
        source=source,
    )


async def handle_live_exit(
    db: Session,
    *,
    camera: Camera,
    capture: VehicleCapture,
    gate: Gate | None,
    source: str = "camera",
) -> dict:
    """Route a persisted real-camera exit capture into ExitLaneController."""
    from app.application.exit_lane import ExitLaneController

    cfg = parking_settings(db)
    policy = policy_from_parking_settings(cfg)
    controller = ExitLaneController()
    return await controller.submit_plate(
        db,
        plate=str(capture.plate or ""),
        event_id=str(capture.event_id or f"capture-{capture.id}"),
        site_id=int(camera.site_id),
        gate=gate,
        camera=camera,
        lane_id=camera.lane_id,
        policy=policy,
        occupied=True,
        source=source,
    )
