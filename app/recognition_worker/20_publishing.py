from __future__ import annotations

def note_reading(
    track: PlateTrack,
    plate: str,
    now: float,
    *,
    hold_seconds: float = 20.0,
    consensus_seconds: float = 2.0,
    confidence: float = 1.0,
) -> bool:
    """Publish once per visit after agreeing reads; never re-publish while visible."""
    track.hold_seconds = float(hold_seconds)
    track.window_seconds = float(consensus_seconds)
    return track.observe(plate, now, confidence=confidence).publish

def note_reading_detail(track: PlateTrack, plate: str, now: float, *, confidence: float = 1.0, allow_single: bool = True) -> TrackDecision:
    return track.observe(plate, now, confidence=confidence, allow_single=allow_single)

def strong_read(event: dict, plate_policy: dict) -> bool:
    from app.core.plate import apply_site_plate

    box = event.get("bbox") or {}
    crop = box.get("crop") or {}
    valid = apply_site_plate(str(event.get("normalized_plate") or ""),
                             validation=str(plate_policy.get("plate_validation") or "NONE"))
    return (float(event.get("detector_confidence") or 0) >= 0.85
            and int(crop.get("x2", 0)) - int(crop.get("x1", 0)) >= 80
            and int(crop.get("y2", 0)) - int(crop.get("y1", 0)) >= 20
            and bool(valid.get("validation_ok")))

def publish_recognition(event: dict) -> dict:
    from app.domain.events import from_recognition_dict
    from app.services.events import publish

    return publish(from_recognition_dict(event))

def _publish_frame(event: dict, jpeg: bytes) -> dict:
    """Archive evidence once per consensus event, not on each decoder frame."""
    from app.services.captures import detection_zone_jpeg, _crop_from_bbox, _enhance_crop_jpeg, _write_jpeg

    if not event.get("vehicle_detected", True) or not event.get("normalized_plate"):
        raise ValueError("recognition event has no vehicle plate")
    box = event.get("bbox")
    if not isinstance(box, dict) or not isinstance(box.get("crop"), dict):
        raise ValueError("recognition event has no valid plate box")

    identifier = str(event["event_id"])
    if not identifier.isalnum() or len(identifier) > 64:
        raise ValueError("Invalid recognition event ID")
    relative = f"recognition-{identifier}.jpg"
    snapshot = detection_zone_jpeg(
        jpeg,
        detect_roi=event.get("detect_roi"),
        detect_zoom=event.get("detect_zoom"),
    ) or jpeg
    saved = _write_jpeg("snapshots", relative, snapshot)
    event["image_ref"] = f"/media/{saved}"
    event["snapshot_zone"] = True
    crop = _crop_from_bbox(jpeg, event.get("bbox"))
    crop = _enhance_crop_jpeg(crop) or crop
    if crop:
        relative_crop = f"recognition-{identifier}.jpg"
        saved_crop = _write_jpeg("crops", relative_crop, crop)
        event["plate_crop_ref"] = f"/media/{saved_crop}"
    return publish_recognition(event)
