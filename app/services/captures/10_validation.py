from __future__ import annotations

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
    source = str(capture.get("source") or "").lower()
    local_read = source in {"fastalpr", "local"} or "fastalpr" in source
    # A software detector rectangle is not an independent native vehicle signal.
    have_vehicle = not local_read and bool(capture.get("have_vehicle") or native.get("have_vehicle"))
    if plate and is_empty_scene_ocr(plate, confidence=conf):
        plate = ""
    source = str(capture.get("source") or native.get("source") or "").lower()
    if source in {"fastalpr", "local"} or "fastalpr" in source:
        have_vehicle = bool(capture.get("have_vehicle"))
    box = native.get("bbox") if isinstance(native.get("bbox"), dict) else None
    if not isinstance(box, dict):
        raw_box = capture.get("bbox") or capture.get("plate_box")
        box = raw_box if isinstance(raw_box, dict) else bbox_from_lp_box(raw_box)

    if have_vehicle and not (source in {"fastalpr", "local"} or "fastalpr" in source):
        if plate and not plausible_vehicle_plate(plate, confidence=conf) and conf < 0.85:
            return False, "vehicle-but-implausible-plate"
        if plate:
            return True, "native-vehicle"
        # A camera "vehicle" flag with no plate and no plate-shaped box is an
        # empty lane. Do not store that picture.
        if allow_empty_vehicle and _bbox_aspect(box) is not None:
            return True, "native-vehicle"
        return False, "empty-scene"

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

def looks_like_no_plate_card(jpeg: bytes) -> bool:
    """The camera's blue 无车牌 graphic, not a photograph of a plate."""
    if not jpeg or jpeg[:2] != b"\xff\xd8":
        return False
    try:
        from PIL import Image
        image = Image.open(BytesIO(jpeg)).convert("RGB")
    except Exception:
        return False
    image.thumbnail((48, 48))
    raw = image.tobytes()
    total = len(raw) // 3
    if total < 16:
        return False
    blue = 0
    for index in range(0, total * 3, 3):
        red, green, blue_ch = raw[index], raw[index + 1], raw[index + 2]
        if blue_ch > 140 and blue_ch > red + 40 and blue_ch > green + 20:
            blue += 1
    return blue / total >= 0.5

def camera_crop_usable(crop: bytes, jpeg: bytes, plate_raw: str = "") -> bool:
    """A camera vehicle-picture is usable only when it is a real plate photo.

    无车牌 and the solid blue result card are the camera's Chinese OCR miss.
    Those bytes must not be sent to OCR or shown as the plate crop.
    """
    from app.core.plate import is_camera_no_plate

    if is_camera_no_plate(plate_raw) or looks_like_no_plate_card(crop):
        return False
    return _looks_like_plate_crop(crop, jpeg)

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
