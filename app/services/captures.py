"""Save each car event: full snapshot, plate crop, extracted characters.

Works for native camera callbacks and FastALPR (or a future in-house engine).
Does not change barrier, fee, or SDK login.
"""

from __future__ import annotations

import time
from io import BytesIO
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Camera, VehicleCapture
from app.services.camera_lpr import bbox_from_lp_box, native_from_sdk_capture


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
    }


def persist_event(
    db: Session,
    camera: Camera,
    *,
    jpeg: bytes,
    crop: bytes,
    capture: dict | None,
) -> VehicleCapture | None:
    jpeg = jpeg or b""
    crop = crop or b""
    if jpeg[:2] != b"\xff\xd8" and crop[:2] == b"\xff\xd8":
        jpeg = crop
    native = native_from_sdk_capture(capture)
    image_id = int((capture or {}).get("image_id") or 0)
    if jpeg[:2] != b"\xff\xd8" and crop[:2] != b"\xff\xd8" and not native.get("plate"):
        return None
    box = native.get("bbox")
    if not isinstance(box, dict):
        box = bbox_from_lp_box((capture or {}).get("plate_box"))
    if isinstance(box, dict) and native.get("source"):
        box = {**box, "source": native.get("source")}
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
                existing.plate = native.get("plate") or existing.plate
                existing.plate_raw = native.get("plate_raw") or existing.plate_raw
                existing.confidence = float(native.get("confidence") or existing.confidence or 0)
                if box:
                    existing.bbox = box
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
