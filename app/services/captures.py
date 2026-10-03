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
from app.core.plate import is_empty_scene_ocr, normalize_plate
from app.models import Camera, VehicleCapture, as_utc, utcnow
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
PLATE_CROP_PAD = 0.18  # keep characters inside the crop without the whole car


def _bbox_aspect(box: dict | None) -> float | None:
    if not isinstance(box, dict):
        return None
    w = int(box.get("x2") or 0) - int(box.get("x1") or 0)
    h = int(box.get("y2") or 0) - int(box.get("y1") or 0)
    if w < 8 or h < 4:
        return None
    return w / float(h)


def plausible_vehicle_plate(plate: str | None, *, confidence: float = 0.0) -> bool:
    """Reject all-letter sign text and other non-plate strings."""
    p = normalize_plate(plate)
    if len(p) < MIN_PLATE_LEN or len(p) > MAX_PLATE_LEN:
        return False
    if p in _PLATE_DENYLIST:
        return False
    if is_empty_scene_ocr(p, confidence=confidence):
        return False
    letters = sum(ch.isalpha() for ch in p)
    digits = sum(ch.isdigit() for ch in p)
    # Numeric-only and letter-only registrations exist internationally. A
    # detector box/confidence supplies the vehicle evidence, not a TZ shape.
    return letters + digits == len(p)


def should_persist_vehicle_capture(
    capture: dict | None,
    *,
    coil_occupied: bool = False,
    allow_empty_vehicle: bool = True,
    plate_policy: str = "NONE",
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
    if plate and is_empty_scene_ocr(plate, confidence=conf):
        plate = ""
    source = str(capture.get("source") or native.get("source") or "").lower()
    box = native.get("bbox") if isinstance(native.get("bbox"), dict) else None
    if not isinstance(box, dict):
        raw_box = capture.get("bbox") or capture.get("plate_box")
        box = raw_box if isinstance(raw_box, dict) else bbox_from_lp_box(raw_box)

    if have_vehicle:
        if plate and not plausible_vehicle_plate(plate, confidence=conf) and conf < 0.85:
            return False, "vehicle-but-implausible-plate"
        if plate or allow_empty_vehicle:
            return True, "native-vehicle"
        return False, "vehicle-no-plate"

    tz_like = str(plate_policy).upper() == "TZ" and bool(_TZ_PLATE_RE.match(plate))
    min_conf = MIN_FASTALPR_CONF_TZ if tz_like else MIN_FASTALPR_CONF
    if coil_occupied and plate and plausible_vehicle_plate(plate, confidence=conf) and conf >= min_conf:
        return True, "coil-plate"

    if not plate:
        return False, "no-vehicle-no-plate"

    if not plausible_vehicle_plate(plate, confidence=conf):
        return False, "implausible-plate"

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


def _jpeg_from_ref(ref: str | None) -> bytes:
    """Load a previously saved crop/snapshot from a relative path or /media URL."""
    text = str(ref or "").strip()
    if not text:
        return b""
    if text.startswith("/media/"):
        text = text[len("/media/"):]
    parts = text.replace("\\", "/").split("/")
    if len(parts) != 2:
        return b""
    from app.services.preview import media_path
    path = media_path(parts[0], parts[1])
    if path is None:
        return b""
    try:
        data = path.read_bytes()
    except Exception:
        return b""
    return data if data[:2] == b"\xff\xd8" else b""


def _xyxy(box: dict | None) -> tuple[float, float, float, float] | None:
    if not isinstance(box, dict):
        return None
    try:
        x1, y1 = float(box.get("x1")), float(box.get("y1"))
        x2, y2 = float(box.get("x2")), float(box.get("y2"))
    except (TypeError, ValueError):
        return None
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def _box_on_image(box: dict | None, width: int, height: int) -> tuple[int, int, int, int] | None:
    """Map a detector box onto jpeg pixels (handles resized FastALPR frames and 0–1 boxes)."""
    coords = _xyxy(box)
    if coords is None or width < 8 or height < 8:
        return None
    x1, y1, x2, y2 = coords
    src_w = int((box or {}).get("image_width") or 0)
    src_h = int((box or {}).get("image_height") or 0)
    max_x, max_y = max(x1, x2), max(y1, y2)
    if 0 <= x1 <= 1 and 0 <= y1 <= 1 and 0 < x2 <= 1.5 and 0 < y2 <= 1.5 and max_x <= 1.5 and max_y <= 1.5:
        x1, x2 = x1 * width, x2 * width
        y1, y2 = y1 * height, y2 * height
    elif src_w > 0 and src_h > 0 and (src_w != width or src_h != height):
        x1 = x1 * width / float(src_w)
        x2 = x2 * width / float(src_w)
        y1 = y1 * height / float(src_h)
        y2 = y2 * height / float(src_h)
    left = max(0, min(width - 1, int(round(x1))))
    top = max(0, min(height - 1, int(round(y1))))
    right = max(left + 1, min(width, int(round(x2))))
    bottom = max(top + 1, min(height, int(round(y2))))
    if right - left < 8 or bottom - top < 8:
        return None
    return left, top, right, bottom


def _padded_box(xyxy: tuple[int, int, int, int], width: int, height: int, *, pad_ratio: float = PLATE_CROP_PAD) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = xyxy
    bw, bh = max(1, x2 - x1), max(1, y2 - y1)
    pad_x = max(4, int(round(bw * pad_ratio)))
    pad_y = max(4, int(round(bh * pad_ratio * 1.2)))
    left = max(0, x1 - pad_x)
    top = max(0, y1 - pad_y)
    right = min(width, x2 + pad_x)
    bottom = min(height, y2 + pad_y)
    return left, top, right, bottom


def _looks_like_plate_crop(crop: bytes, jpeg: bytes) -> bool:
    """Reject full-frame 'crops' so we can recrop from the plate box."""
    if crop[:2] != b"\xff\xd8":
        return False
    try:
        from PIL import Image
        crop_img = Image.open(BytesIO(crop))
        crop_img.load()
        cw, ch = crop_img.size
    except Exception:
        return True
    if cw < 12 or ch < 8:
        return False
    aspect = cw / float(ch)
    if aspect < 1.3 or aspect > 10:
        return False
    if jpeg[:2] != b"\xff\xd8":
        return True
    try:
        from PIL import Image
        frame = Image.open(BytesIO(jpeg))
        frame.load()
        fw, fh = frame.size
    except Exception:
        return True
    if fw >= 32 and cw >= fw * 0.55:
        return False
    if fh >= 32 and ch >= fh * 0.45:
        return False
    return True


def _crop_from_bbox(jpeg: bytes, box: dict | None, *, pad_ratio: float = PLATE_CROP_PAD) -> bytes:
    if not jpeg or jpeg[:2] != b"\xff\xd8" or not box:
        return b""
    try:
        from PIL import Image
    except Exception:
        return b""
    try:
        img = Image.open(BytesIO(jpeg)).convert("RGB")
        xyxy = _box_on_image(box, img.width, img.height)
        if xyxy is None:
            return b""
        left, top, right, bottom = _padded_box(xyxy, img.width, img.height, pad_ratio=pad_ratio)
        crop = img.crop((left, top, right, bottom))
        if crop.width < 8 or crop.height < 8:
            return b""
        if crop.width < 240:
            scale = 240 / float(crop.width)
            crop = crop.resize(
                (max(1, int(crop.width * scale)), max(1, int(crop.height * scale))),
                Image.Resampling.LANCZOS,
            )
        out = BytesIO()
        crop.save(out, format="JPEG", quality=92)
        return out.getvalue()
    except Exception:
        return b""


def _plate_jpeg(jpeg: bytes, crop: bytes, box: dict | None, capture: dict | None) -> bytes:
    capture = capture or {}
    plate_jpeg = crop if _looks_like_plate_crop(crop, jpeg) else b""
    if plate_jpeg[:2] != b"\xff\xd8":
        plate_jpeg = _jpeg_from_ref(capture.get("plate_crop_path") or capture.get("crop_url"))
    if plate_jpeg[:2] != b"\xff\xd8" or not _looks_like_plate_crop(plate_jpeg, jpeg):
        fallback = _crop_from_bbox(jpeg, box)
        if fallback[:2] == b"\xff\xd8":
            plate_jpeg = fallback
    return plate_jpeg if plate_jpeg[:2] == b"\xff\xd8" else b""


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
        "visit_id": getattr(row, "visit_id", None) or "",
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "fusion": (row.bbox or {}).get("fusion") if isinstance(row.bbox, dict) else None,
        "native_plate": (row.bbox or {}).get("native_plate") if isinstance(row.bbox, dict) else "",
        "local_plate": (row.bbox or {}).get("local_plate") if isinstance(row.bbox, dict) else "",
        "needs_review": bool((row.bbox or {}).get("needs_review")) if isinstance(row.bbox, dict) else False,
        "pending_confirmation": bool((row.bbox or {}).get("pending_confirmation")) if isinstance(row.bbox, dict) else False,
        "ai_review": getattr(row, "ai_review", None) or None,
    }


def find_capture_for_session(db: Session, *, plate: str = "", camera_id: int | None = None) -> VehicleCapture | None:
    """Best stored still for a visit: matching plate, else latest still on that camera."""
    plate = normalize_plate(plate)
    if plate:
        matched = db.scalar(
            select(VehicleCapture)
            .where(VehicleCapture.plate == plate)
            .order_by(VehicleCapture.id.desc())
        )
        if matched:
            return matched
    if camera_id:
        return latest_for_camera(db, int(camera_id))
    return None


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
        from app.services.site_policy import site_policy
        allowed, _reason = should_persist_vehicle_capture(
            capture, coil_occupied=coil_occupied, allow_empty_vehicle=True,
            plate_policy=site_policy(db).get("plate_validation", "NONE"),
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
    try:
        from PIL import Image
        if jpeg[:2] == b"\xff\xd8":
            frame = Image.open(BytesIO(jpeg))
            box.setdefault("image_width", int(frame.width))
            box.setdefault("image_height", int(frame.height))
    except Exception:
        pass
    box = attach_fusion_audit(box, capture)
    plate_jpeg = _plate_jpeg(jpeg, crop, box, capture)
    if image_id:
        existing = db.scalar(
            select(VehicleCapture).where(
                VehicleCapture.camera_id == camera.id,
                VehicleCapture.image_id == image_id,
            )
        )
        if existing:
            updated = False
            incoming_plate = native.get("plate") or ""
            if incoming_plate and existing.plate != incoming_plate:
                if plausible_vehicle_plate(incoming_plate) or force:
                    existing.plate = incoming_plate
                    existing.plate_raw = native.get("plate_raw") or existing.plate_raw
                    existing.confidence = float(native.get("confidence") or existing.confidence or 0)
                    updated = True
            elif incoming_plate and float(native.get("confidence") or 0) > float(existing.confidence or 0):
                existing.confidence = float(native.get("confidence") or existing.confidence or 0)
                updated = True
            existing.bbox = attach_fusion_audit(box or existing.bbox, capture)
            if plate_jpeg[:2] == b"\xff\xd8":
                existing.crop_path = _write_jpeg("crops", f"cam{camera.id}-img{image_id}-plate.jpg", plate_jpeg)
                updated = True
            if jpeg[:2] == b"\xff\xd8" and not existing.snapshot_path:
                existing.snapshot_path = _write_jpeg("snapshots", f"cam{camera.id}-img{image_id}-car.jpg", jpeg)
                updated = True
            if updated:
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
            created = as_utc(latest.created_at)
            age = (utcnow() - created).total_seconds() if created is not None else 999999.0
            # image_id=0 is a weak identity. Reuse it only for a burst of the
            # same callback/frame, never forever; otherwise an old plate can
            # become the camera's permanent "latest vehicle".
            if 0 <= age <= 1.0:
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
        visit_id=str((capture or {}).get("visit_id") or ""),
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
