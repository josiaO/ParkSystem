"""Save each car event: full snapshot, plate crop, extracted characters.

Works for native camera callbacks and FastALPR (or a future in-house engine).
Does not change barrier, fee, or SDK login.

Snapshots are vehicle events only — empty scenes and non-car OCR (signs, walls)
must not create VehicleCapture rows.
"""

from __future__ import annotations

import re
import time
from io import BytesIO
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.plate import normalize_plate
from app.models import Camera, VehicleCapture
from app.services.camera_lpr import bbox_from_lp_box, native_from_sdk_capture


# Common false OCR from roadside signs / UI chrome — not vehicle plates.
_PLATE_DENYLIST = frozenset({
    "STATION", "POLICE", "TAXI", "STOP", "ENTRY", "EXIT", "OPEN", "CLOSE",
    "DANGER", "PARKING", "WELCOME", "THANKYOU", "THANK", "PLEASE", "SLOW",
    "SPEED", "CAMERA", "SMARTPARK", "DAHUA", "HIKVISION",
})
_TZ_PLATE_RE = re.compile(r"^T\d{3}[A-Z]{2,3}$")
MIN_PLATE_LEN = 5
MAX_PLATE_LEN = 10
MIN_FASTALPR_CONF = 0.35
MIN_FASTALPR_CONF_TZ = 0.22
MIN_PLATE_ASPECT = 1.4  # plate boxes are wider than tall
MAX_PLATE_ASPECT = 8.0


def _bbox_aspect(box: dict | None) -> float | None:
    if not isinstance(box, dict):
        return None
    w = int(box.get("x2") or 0) - int(box.get("x1") or 0)
    h = int(box.get("y2") or 0) - int(box.get("y1") or 0)
    if w < 8 or h < 4:
        return None
    return w / float(h)


def plausible_vehicle_plate(plate: str | None) -> bool:
    """Reject all-letter sign text and other non-plate strings."""
    p = normalize_plate(plate)
    if len(p) < MIN_PLATE_LEN or len(p) > MAX_PLATE_LEN:
        return False
    if p in _PLATE_DENYLIST:
        return False
    letters = sum(ch.isalpha() for ch in p)
    digits = sum(ch.isdigit() for ch in p)
    # Vehicle plates mix letters and digits (TZ T###XXX, etc.).
    return letters >= 1 and digits >= 2


def should_persist_vehicle_capture(
    capture: dict | None,
    *,
    coil_occupied: bool = False,
    allow_empty_vehicle: bool = True,
) -> tuple[bool, str]:
    """Return whether this frame is a car event worth writing to disk/DB.

    Allowed when:
    - native ANPR reports a vehicle (have_vehicle), optionally with empty plate yet
    - coil/ground-loop says occupied and a plausible plate was read
    - FastALPR/native plate is plausible, confident, and (for OCR) has a plate-like bbox
    """
    capture = capture or {}
    native = native_from_sdk_capture(capture)
    plate = normalize_plate(native.get("plate") or capture.get("plate") or "")
    conf = float(
        native.get("confidence")
        or capture.get("score")
        or capture.get("confidence")
        or 0
    )
    have_vehicle = bool(capture.get("have_vehicle") or native.get("have_vehicle"))
    source = str(capture.get("source") or native.get("source") or "").lower()
    box = native.get("bbox") if isinstance(native.get("bbox"), dict) else None
    if not isinstance(box, dict):
        raw_box = capture.get("bbox") or capture.get("plate_box")
        box = raw_box if isinstance(raw_box, dict) else bbox_from_lp_box(raw_box)

    if have_vehicle:
        if plate and not plausible_vehicle_plate(plate) and conf < 0.85:
            return False, "vehicle-but-implausible-plate"
        if plate or allow_empty_vehicle:
            return True, "native-vehicle"
        return False, "vehicle-no-plate"

    if coil_occupied and plate and plausible_vehicle_plate(plate) and conf >= MIN_FASTALPR_CONF_TZ:
        return True, "coil-plate"

    if not plate:
        return False, "no-vehicle-no-plate"

    if not plausible_vehicle_plate(plate):
        return False, "implausible-plate"

    tz_like = bool(_TZ_PLATE_RE.match(plate))
    min_conf = MIN_FASTALPR_CONF_TZ if tz_like else MIN_FASTALPR_CONF
    if conf < min_conf:
        return False, "low-confidence"

    if source in {"fastalpr", "local", ""} or "fastalpr" in source:
        aspect = _bbox_aspect(box)
        if aspect is None:
            # FastALPR without a detector box is usually a false full-frame OCR.
            if not tz_like or conf < 0.55:
                return False, "no-plate-bbox"
        elif aspect < MIN_PLATE_ASPECT or aspect > MAX_PLATE_ASPECT:
            return False, "bbox-not-plate-shaped"

    return True, "plausible-plate"


def _write_jpeg(kind: str, name: str, data: bytes) -> str:
    folder = settings.media_dir / kind
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / name
    dest.write_bytes(data)
    return str(Path(kind) / name)


def _crop_from_bbox(jpeg: bytes, box: dict | None) -> bytes:
    if not jpeg or not box:
        return b""
    try:
        from PIL import Image
    except Exception:
        return b""
    try:
        img = Image.open(BytesIO(jpeg)).convert("RGB")
        x1, y1, x2, y2 = int(box["x1"]), int(box["y1"]), int(box["x2"]), int(box["y2"])
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(img.width, x2), min(img.height, y2)
        if x2 - x1 < 8 or y2 - y1 < 8:
            return b""
        out = BytesIO()
        img.crop((x1, y1, x2, y2)).save(out, format="JPEG", quality=90)
        return out.getvalue()
    except Exception:
        return b""


def attach_fusion_audit(box: dict | None, capture: dict | None) -> dict:
    """Keep native vs FastALPR disagreement on the capture row (bbox JSON)."""
    box = dict(box or {})
    capture = capture or {}
    fusion = capture.get("fusion") if isinstance(capture.get("fusion"), dict) else {}
    native_plate = str(fusion.get("native_plate") or capture.get("native_plate") or "")
    local_plate = str(fusion.get("local_plate") or capture.get("local_plate") or "")
    if fusion:
        box["fusion"] = fusion
    if native_plate:
        box["native_plate"] = native_plate
    if local_plate:
        box["local_plate"] = local_plate
    box["needs_review"] = bool(fusion.get("needs_review") or capture.get("needs_review"))
    box["pending_confirmation"] = bool(capture.get("pending_confirmation") or box["needs_review"])
    box["disagreed"] = bool(fusion.get("disagreed") or (native_plate and local_plate and native_plate != local_plate))
    return box


def capture_dict(row: VehicleCapture) -> dict:
    chars = " ".join(list(row.plate)) if row.plate else ""
    return {
        "id": row.id,
        "camera_id": row.camera_id,
        "gate_id": row.gate_id,
        "lane_direction": row.lane_direction,
        "plate": row.plate,
        "plate_raw": row.plate_raw,
        "characters": chars,
        "confidence": float(row.confidence or 0),
        "image_id": row.image_id,
        "snapshot_url": f"/media/{row.snapshot_path}" if row.snapshot_path else None,
        "crop_url": f"/media/{row.crop_path}" if row.crop_path else None,
        "bbox": row.bbox,
        "source": getattr(row, "source", None) or ((row.bbox or {}).get("source") if isinstance(row.bbox, dict) else None),
        "plate_country": getattr(row, "plate_country", None) or "",
        "plate_region": getattr(row, "plate_region", None) or "",
        "event_id": getattr(row, "event_id", None) or "",
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "fusion": (row.bbox or {}).get("fusion") if isinstance(row.bbox, dict) else None,
        "native_plate": (row.bbox or {}).get("native_plate") if isinstance(row.bbox, dict) else "",
        "local_plate": (row.bbox or {}).get("local_plate") if isinstance(row.bbox, dict) else "",
        "needs_review": bool((row.bbox or {}).get("needs_review")) if isinstance(row.bbox, dict) else False,
        "pending_confirmation": bool((row.bbox or {}).get("pending_confirmation")) if isinstance(row.bbox, dict) else False,
    }


def persist_event(
    db: Session,
    camera: Camera,
    *,
    jpeg: bytes,
    crop: bytes,
    capture: dict | None,
    coil_occupied: bool = False,
    force: bool = False,
) -> VehicleCapture | None:
    jpeg = jpeg or b""
    crop = crop or b""
    if jpeg[:2] != b"\xff\xd8" and crop[:2] == b"\xff\xd8":
        jpeg = crop
    native = native_from_sdk_capture(capture)
    image_id = int((capture or {}).get("image_id") or 0)
    if jpeg[:2] != b"\xff\xd8" and crop[:2] != b"\xff\xd8" and not native.get("plate"):
        return None
    if not force:
        allowed, _reason = should_persist_vehicle_capture(
            capture, coil_occupied=coil_occupied, allow_empty_vehicle=True,
        )
        if not allowed:
            return None
    box = native.get("bbox")
    if not isinstance(box, dict):
        box = bbox_from_lp_box((capture or {}).get("plate_box"))
    if not isinstance(box, dict):
        raw_box = (capture or {}).get("bbox")
        box = raw_box if isinstance(raw_box, dict) else {}
    else:
        box = dict(box)
    if native.get("source"):
        box["source"] = native.get("source")
    box = attach_fusion_audit(box, capture)
    plate_jpeg = crop if crop[:2] == b"\xff\xd8" else _crop_from_bbox(jpeg, box)
    if image_id:
        existing = db.scalar(
            select(VehicleCapture).where(
                VehicleCapture.camera_id == camera.id,
                VehicleCapture.image_id == image_id,
            )
        )
        if existing:
            if native.get("plate") and existing.plate != native.get("plate"):
                # Only upgrade empty/weak rows with a plausible plate.
                if plausible_vehicle_plate(native.get("plate")) or force:
                    existing.plate = native.get("plate") or existing.plate
                    existing.plate_raw = native.get("plate_raw") or existing.plate_raw
                    existing.confidence = float(native.get("confidence") or existing.confidence or 0)
                    existing.bbox = attach_fusion_audit(box or existing.bbox, capture)
                    if plate_jpeg[:2] == b"\xff\xd8":
                        existing.crop_path = _write_jpeg("crops", f"cam{camera.id}-img{image_id}-plate.jpg", plate_jpeg)
                    if jpeg[:2] == b"\xff\xd8" and not existing.snapshot_path:
                        existing.snapshot_path = _write_jpeg("snapshots", f"cam{camera.id}-img{image_id}-car.jpg", jpeg)
                    db.commit()
                    db.refresh(existing)
            return existing
    else:
        latest = latest_for_camera(db, camera.id)
        if (
            latest
            and latest.plate
            and latest.plate == (native.get("plate") or "")
            and latest.snapshot_path
        ):
            return latest
    stamp = f"cam{camera.id}-img{image_id or int(time.time() * 1000) % 1_000_000_000}"
    snapshot_path = _write_jpeg("snapshots", f"{stamp}-car.jpg", jpeg) if jpeg[:2] == b"\xff\xd8" else ""
    crop_path = _write_jpeg("crops", f"{stamp}-plate.jpg", plate_jpeg) if plate_jpeg[:2] == b"\xff\xd8" else ""
    row = VehicleCapture(
        camera_id=camera.id,
        gate_id=camera.gate_id,
        lane_direction=(camera.lane_direction or "ENTRY").upper(),
        plate=native.get("plate") or "",
        plate_raw=native.get("plate_raw") or "",
        confidence=float(native.get("confidence") or 0),
        image_id=image_id,
        snapshot_path=snapshot_path,
        crop_path=crop_path,
        bbox=box,
        source=str((capture or {}).get("source") or native.get("source") or ""),
        event_id=str((capture or {}).get("event_id") or ""),
        plate_country=str((capture or {}).get("plate_country") or ""),
        plate_region=str((capture or {}).get("plate_region") or ""),
        plate_type=str((capture or {}).get("plate_type") or ""),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def latest_for_camera(db: Session, camera_id: int) -> VehicleCapture | None:
    return db.scalar(
        select(VehicleCapture)
        .where(VehicleCapture.camera_id == camera_id)
        .order_by(VehicleCapture.id.desc())
    )


def list_captures(db: Session, *, gate_id: int | None = None, limit: int = 20) -> list[VehicleCapture]:
    stmt = select(VehicleCapture).order_by(VehicleCapture.id.desc()).limit(max(1, min(int(limit), 100)))
    if gate_id is not None:
        stmt = stmt.where(VehicleCapture.gate_id == gate_id)
    return list(db.scalars(stmt).all())


def apply_operator_plate_correction(row: VehicleCapture, plate: str) -> VehicleCapture:
    """Set the operator plate without erasing the original OCR string."""
    chosen = normalize_plate(plate)
    if not chosen:
        raise ValueError("Corrected plate is empty")
    original = row.plate_raw or row.plate
    if not row.plate_raw:
        row.plate_raw = original
    box = dict(row.bbox or {})
    box["operator_plate"] = chosen
    box["ocr_plate"] = original
    box["needs_review"] = False
    box["pending_confirmation"] = False
    box["fusion"] = {
        **(box.get("fusion") or {}),
        "method": "OPERATOR_CORRECTED",
        "resolved_plate": chosen,
        "needs_review": False,
    }
    row.bbox = box
    row.plate = chosen
    return row
