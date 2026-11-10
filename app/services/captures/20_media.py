from __future__ import annotations

def _write_jpeg(kind: str, name: str, data: bytes) -> str:
    folder = settings.media_dir / kind
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / name
    if not data:
        return ""
    index_key = str(folder.resolve())
    index = _MEDIA_HASH_INDEX.setdefault(index_key, {})
    signature = _media_signature(data)
    existing = index.get(signature)
    if existing and (folder / existing).is_file():
        log.debug("evidence write skipped duplicate kind=%s existing=%s", kind, existing)
        return (Path(kind) / existing).as_posix()
    # Do not rebuild this index by reading every historical JPEG.  A busy gate
    # can have many thousands of evidence files, and that one-time scan used to
    # run on the first capture after every process restart.  Deterministic names
    # and the in-process index still deduplicate the normal hot path; an exact
    # same-name check below protects late/replayed callbacks.
    # Late native callbacks can repeat the same image_id/capture. Preserve the
    # first evidence file; a changed image with the same name is still accepted.
    if dest.is_file():
        try:
            if dest.read_bytes() == data:
                index[signature] = name
                return (Path(kind) / name).as_posix()
        except OSError:
            pass
    dest.write_bytes(data)
    for old_signature, old_name in list(index.items()):
        if old_name == name and old_signature != signature:
            index.pop(old_signature, None)
    index[signature] = name
    return (Path(kind) / name).as_posix()

def _reuse_media_ref(ref: str | None, kind: str, data: bytes) -> str:
    """Reuse evidence already archived by the recognition worker."""
    raw = str(ref or "").strip().replace("\\", "/")
    if raw.startswith("/media/"):
        raw = raw[len("/media/"):]
    parts = Path(raw).parts
    if len(parts) != 2 or parts[0] != kind or parts[1] in {"", ".", ".."}:
        return ""
    path = settings.media_dir / kind / parts[1]
    try:
        if path.is_file() and (not data or path.read_bytes() == data):
            return Path(kind, parts[1]).as_posix()
    except OSError:
        return ""
    return ""

def _plate_crop_name(camera_id: int, image_id: int, capture: dict | None, plate: str = "") -> str:
    """Use OCR text in the crop filename while keeping evidence unique."""
    normalized = normalize_plate(plate or (capture or {}).get("plate") or "")
    label = normalized or "UNREAD"
    identity = str((capture or {}).get("event_id") or (capture or {}).get("visit_id") or "")
    identity = re.sub(r"[^A-Za-z0-9_-]+", "", identity)[:24]
    suffix = f"img{int(image_id)}" if int(image_id or 0) else (identity or f"t{int(time.time() * 1000) % 1_000_000_000}")
    return f"cam{int(camera_id)}-{label}-{suffix}-plate.jpg"

def _jpeg_from_ref(ref: str | None) -> bytes:
    """Load a previously saved crop/snapshot from a relative path or /media URL."""
    text = str(ref or "").strip().split("?", 1)[0]
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

def detection_zone_jpeg(
    jpeg: bytes,
    *,
    detect_roi: str | None = None,
    detect_zoom: float | None = None,
) -> bytes:
    """Return the camera frame cropped to the recognition admission zone.

    This is the event snapshot, not the plate OCR crop. Keeping it separate
    means the saved snapshot shows the useful stopping area while the plate
    crop still uses the detector's full-frame coordinates and padding.
    """
    if not jpeg or jpeg[:2] != b"\xff\xd8":
        return b""
    try:
        from PIL import Image
        import numpy as np
        from app.services.alpr import _roi_crop, decode_alpr_image

        bgr = decode_alpr_image(jpeg)
        view, _dx, _dy = _roi_crop(bgr, detect_roi, detect_zoom)
        if view is None or getattr(view, "size", 0) == 0:
            return b""
        output = BytesIO()
        Image.fromarray(np.asarray(view)[:, :, ::-1]).save(output, format="JPEG", quality=92)
        return output.getvalue()
    except Exception:
        return b""

def _enhance_crop_jpeg(crop: bytes) -> bytes:
    """Create the readable evidence crop while keeping the car snapshot raw."""
    if not crop or crop[:2] != b"\xff\xd8":
        return b""
    try:
        from app.services.alpr import _prepare_ocr_crop, decode_alpr_image
        from PIL import Image

        bgr = decode_alpr_image(crop)
        enhanced = _prepare_ocr_crop(bgr, enhance=True)
        if enhanced is None or getattr(enhanced, "size", 0) == 0:
            return crop
        output = BytesIO()
        Image.fromarray(enhanced[:, :, ::-1]).save(output, format="JPEG", quality=95)
        return output.getvalue() or crop
    except Exception:
        # Optional enhancement must never make evidence disappear on a minimal
        # installation; the raw crop is the safe fallback.
        return crop

def _plate_jpeg(jpeg: bytes, crop: bytes, box: dict | None, capture: dict | None) -> bytes:
    capture = capture or {}
    # The SDK vehicle-picture buffer is often smaller/softer than the
    # panorama. When the native usLpBox exists, recrop the panorama first so
    # night evidence and OCR use the highest-resolution pixels available.
    plate_jpeg = _crop_from_bbox(jpeg, box) if jpeg[:2] == b"\xff\xd8" and box else b""
    if plate_jpeg[:2] != b"\xff\xd8":
        plate_jpeg = crop if _looks_like_plate_crop(crop, jpeg) else b""
    if plate_jpeg[:2] != b"\xff\xd8":
        plate_jpeg = _jpeg_from_ref(capture.get("plate_crop_path") or capture.get("crop_url"))
    if plate_jpeg[:2] != b"\xff\xd8" or not _looks_like_plate_crop(plate_jpeg, jpeg):
        fallback = _crop_from_bbox(jpeg, box)
        if fallback[:2] == b"\xff\xd8":
            plate_jpeg = fallback
    if plate_jpeg[:2] != b"\xff\xd8":
        return b""
    return _enhance_crop_jpeg(plate_jpeg) or plate_jpeg

def attach_fusion_audit(box: dict | None, capture: dict | None) -> dict:
    """Keep native vs FastALPR disagreement and timing on the capture row."""
    box = dict(box or {})
    if (capture or {}).get("timeline"):
        box["timeline"] = capture["timeline"]
    for key in ("detector_confidence", "frame_confidence", "consensus", "validation_result", "timings"):
        if (capture or {}).get(key) is not None:
            box[key] = capture[key]
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
