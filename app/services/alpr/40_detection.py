from __future__ import annotations

def _ocr_result_text(ocr) -> tuple[str, float]:
    text = clean_ocr_text(getattr(ocr, "text", None) or getattr(ocr, "plate", None) or "")
    conf = getattr(ocr, "confidence", None)
    if isinstance(conf, (list, tuple)):
        conf = float(statistics.mean(conf)) if conf else 0.0
    return text, float(conf or 0)

def _country_name() -> str:
    explicit = str(getattr(settings, "alpr_country", "") or "").strip().lower()
    if explicit:
        return explicit
    validation = str(getattr(settings, "plate_validation", "") or "").strip().upper()
    if validation == "TZ":
        return "tanzania"
    return ""

def _apply_country_profile(text: str, confidence: float) -> tuple[str, float]:
    """Apply a country profile only when the site selected one.

    Reported confidence is always the raw OCR score. Tanzania shape matching
    is a sort tie-break only — never add 0.35 so a 30% read becomes 65%.
    """
    raw = max(0.0, min(float(confidence or 0), 1.0))
    if _country_name() in {"tanzania", "tz"}:
        plate = _fix_tz_ocr_plate(text)
        return plate, raw
    plate = normalize_plate(clean_ocr_text(text))
    return plate, raw

def _tz_plate_rank(plate: str) -> int:
    """Prefer classic TZ T###XXX plates when ranking equal-confidence hits."""
    p = normalize_plate(plate)
    if re.fullmatch(r"T\d{3}[A-Z]{3}", p):
        return 2
    if re.fullmatch(r"T\d{3}[A-Z]{2,3}", p):
        return 1
    return 0

def _tz_plate_score(plate: str, confidence: float) -> float:
    """Deprecated sort helper. Returns raw confidence; does not invent a score."""
    return max(0.0, min(float(confidence or 0), 1.0))

def _fix_tz_ocr_plate(text: str) -> str:
    """Light Tanzania-oriented OCR cleanup (digit/letter positions), not a retrain."""
    raw = clean_ocr_text(text)
    plate = normalize_plate(raw)
    if len(plate) < MIN_PLATE_CHARS:
        return plate
    # Classic TZ private plate: T + 3 digits + 3 letters.
    if len(plate) >= 7 and plate[0] == "T":
        chars = list(plate)
        for i in range(1, min(4, len(chars))):
            if chars[i] == "O":
                chars[i] = "0"
            elif chars[i] == "I" or chars[i] == "L":
                chars[i] = "1"
            elif chars[i] == "S":
                chars[i] = "5"
            elif chars[i] == "B":
                chars[i] = "8"
        for i in range(4, len(chars)):
            if chars[i] == "0":
                chars[i] = "O"
            elif chars[i] == "1":
                chars[i] = "I"
            elif chars[i] == "5":
                chars[i] = "S"
            elif chars[i] == "8":
                chars[i] = "B"
        plate = "".join(chars)
    return normalize_plate(plate)

def _detection_score(detection) -> float:
    for name in ("confidence", "conf", "score"):
        value = getattr(detection, name, None)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0

def _bbox_size(bbox) -> tuple[int, int]:
    try:
        width = int(getattr(bbox, "x2")) - int(getattr(bbox, "x1"))
        height = int(getattr(bbox, "y2")) - int(getattr(bbox, "y1"))
    except Exception:
        return 0, 0
    return width, height

def plate_box_ok(bbox, image_width: int, image_height: int) -> bool:
    """Reject sky/sign boxes that are not plate-shaped."""
    width, height = _bbox_size(bbox)
    if width < MIN_PLATE_WIDTH_PX or height < MIN_PLATE_HEIGHT_PX:
        return False
    if image_width >= 80 and width < max(MIN_PLATE_WIDTH_PX, int(image_width * 0.018)):
        return False
    if image_width >= 80 and width > int(image_width * 0.85):
        return False
    if image_height >= 80 and height > int(image_height * 0.55):
        return False
    aspect = width / float(height)
    return MIN_PLATE_ASPECT <= aspect <= MAX_PLATE_ASPECT

def accept_ocr_plate(text: str, confidence: float, *, bbox=None, image_size: tuple[int, int] | None = None) -> bool:
    """Do not invent a plate from an empty scene or a non-plate crop."""
    plate = normalize_plate(clean_ocr_text(text))
    if len(plate) < MIN_PLATE_CHARS:
        return False
    if is_empty_scene_ocr(plate, confidence=confidence):
        return False
    assessed = assess_plate(plate, str(getattr(settings, "plate_validation", "") or "NONE"), confidence=confidence)
    if not assessed.get("likely"):
        return False
    floor = float(getattr(settings, "alpr_min_ocr_confidence", 0.40) or 0.40)
    if plate_shape_score(plate) >= 2:
        floor = min(floor, float(getattr(settings, "alpr_min_ocr_confidence_shaped", 0.28) or 0.28))
    if float(confidence or 0) < floor:
        return False
    if bbox is not None and image_size:
        if not plate_box_ok(bbox, image_size[0], image_size[1]):
            return False
    return True

def _predict_crop_then_ocr(engine, bgr, *, save_crops: bool = False) -> list[PlateHit]:
    """Detect on the given frame, then OCR only the padded plate crop.

    FastALPR's stock predict() already crops, but with zero padding. We pad,
    upscale, and enhance the crop so OCR reads the plate — not the car body.
    Prefer Tanzania-shaped plates when several candidates appear.
    """
    detections = engine.detector.predict(bgr)
    return _hits_from_detections(engine, bgr, detections, save_crops=save_crops)

def _hits_from_detections(engine, bgr, detections, *, save_crops: bool = False) -> list[PlateHit]:
    hits: list[PlateHit] = []
    image_w = int(bgr.shape[1])
    image_h = int(bgr.shape[0])
    min_det = float(getattr(settings, "alpr_detector_confidence", 0.26) or 0.26)
    for detection in detections or []:
        crop_started = time.monotonic()
        bbox = getattr(detection, "bounding_box", None)
        if bbox is None:
            continue
        if _detection_score(detection) < min_det:
            continue
        if not plate_box_ok(bbox, image_w, image_h):
            continue
        crop, _xy = _crop_bgr(
            bgr,
            bbox,
            pad_ratio=float(getattr(settings, "alpr_crop_padding_ratio", 0.18) or 0.18),
        )
        if crop is None or getattr(crop, "size", 0) == 0:
            continue
        crop_ready = time.monotonic()
        rectified_crop, rectified = _rectify_plate_crop(crop)
        low_light = _low_light(rectified_crop)
        ocr_input = _prepare_ocr_crop(rectified_crop, enhance=low_light)
        ocr_started = time.monotonic()
        try:
            ocr = engine.ocr.predict(ocr_input)
        except Exception as exc:
            raise RuntimeError(f"FastALPR plate-crop OCR failed: {exc}") from exc
        text, conf = _ocr_result_text(ocr)
        plate, _rank = _apply_country_profile(text, conf)
        accepted = accept_ocr_plate(plate, conf, bbox=bbox, image_size=(image_w, image_h))
        # The first normal-light pass is cheap. Retry exactly once on an
        # enhanced crop when it is empty or weak; the old condition retried
        # only already-accepted text, losing plates that needed enhancement.
        if not low_light and (not accepted or conf < float(settings.recognition_high_confidence)):
            try:
                enhanced = engine.ocr.predict(_prepare_ocr_crop(rectified_crop, enhance=True))
                enhanced_text, enhanced_conf = _ocr_result_text(enhanced)
                enhanced_plate, _rank = _apply_country_profile(enhanced_text, enhanced_conf)
                enhanced_ok = accept_ocr_plate(
                    enhanced_plate, enhanced_conf, bbox=bbox, image_size=(image_w, image_h)
                )
                if enhanced_ok and (not accepted or enhanced_conf > conf):
                    text, conf, plate, accepted = enhanced_text, enhanced_conf, enhanced_plate, True
            except Exception:
                pass
        ocr_finished = time.monotonic()
        raw_conf = max(0.0, min(float(conf or 0), 1.0))
        if not accept_ocr_plate(plate, raw_conf, bbox=bbox, image_size=(image_w, image_h)):
            continue
        box = bbox_dict(bbox) or {}
        box["image_width"] = image_w
        box["image_height"] = image_h
        left, top, right, bottom = _xy
        box["crop"] = {"x1": int(left), "y1": int(top), "x2": int(right), "y2": int(bottom)}
        hits.append(
            PlateHit(
                plate_raw=text,
                plate_normalized=plate,
                plate_confidence=raw_conf,
                # Save the readable view used by OCR, not the raw tiny plate
                # rectangle. The full vehicle snapshot remains unchanged.
                plate_crop_path=_save_crop_bgr(_prepare_ocr_crop(rectified_crop, enhance=True)) if save_crops else None,
                bbox=box,
                detector_confidence=_detection_score(detection),
                timings={"crop_ms": round((crop_ready - crop_started) * 1000, 1),
                         "perspective_rectified": rectified,
                         "ocr_ms": round((ocr_finished - ocr_started) * 1000, 1),
                         "crop_ready_at": crop_ready, "ocr_started_at": ocr_started,
                         "ocr_finished_at": ocr_finished},
            )
        )
    hits.sort(
        key=lambda h: (_tz_plate_rank(h.plate_normalized), h.plate_confidence),
        reverse=True,
    )
    return hits

def _hits_from_predict(rows, crop_source: str) -> list[PlateHit]:
    """Legacy path kept for tests that mock engine.predict()."""
    hits: list[PlateHit] = []
    for row in rows or []:
        ocr = getattr(row, "ocr", None)
        text = clean_ocr_text(getattr(ocr, "text", None) or getattr(row, "text", None))
        plate = normalize_plate(text)
        conf = getattr(ocr, "confidence", None)
        if conf is None:
            conf = getattr(row, "confidence", None)
        if isinstance(conf, (list, tuple)):
            conf = float(statistics.mean(conf)) if conf else 0.0
        raw_conf = float(conf or 0)
        if not accept_ocr_plate(plate, raw_conf):
            continue
        det = getattr(row, "detection", None)
        bbox = getattr(det, "bounding_box", None) if det is not None else None
        hits.append(
            PlateHit(
                plate_raw=text,
                plate_normalized=plate,
                plate_confidence=raw_conf,
                plate_crop_path=_crop_path(crop_source, bbox) if crop_source else None,
                bbox=bbox_dict(bbox),
            )
        )
    return hits

def locate_plate_boxes(
    jpeg: bytes,
    *,
    detect_roi: str | None = None,
    detect_zoom: float | None = None,
) -> tuple[list[dict], dict]:
    """Detector only. Returns plate boxes in full-frame pixels.

    ``available`` is False when the detector could not run. An empty list
    with ``available`` True means the zone was searched and no plate is there.
    OCR is not called.
    """
    if not jpeg or not fastalpr_installed():
        return [], {"available": False, "reason": "detector-unavailable", "detail": _availability_detail()}
    try:
        bgr = decode_alpr_image(jpeg)
        engine = _load_engine()
    except Exception as exc:
        return [], {"available": False, "reason": "detector-unavailable", "detail": _remember_engine_error(exc)}
    if not hasattr(engine, "detector"):
        return [], {"available": False, "reason": "detector-unavailable"}
    started = time.monotonic()
    try:
        view, dx, dy = _roi_crop(bgr, detect_roi, detect_zoom)
        detections = _shift_detections(engine.detector.predict(view), dx, dy)
    except Exception as exc:
        return [], {"available": False, "reason": "detector-unavailable", "detail": _remember_engine_error(exc)}
    width, height = int(bgr.shape[1]), int(bgr.shape[0])
    min_det = float(getattr(settings, "alpr_detector_confidence", 0.26) or 0.26)
    boxes: list[dict] = []
    for item in detections or []:
        bbox = getattr(item, "bounding_box", None)
        if bbox is None or not plate_box_ok(bbox, width, height):
            continue
        if _detection_score(item) < min_det:
            continue
        box = bbox_dict(bbox) or {}
        box["image_width"] = width
        box["image_height"] = height
        box["confidence"] = _detection_score(item)
        from app.services.camera_framing import box_in_detection_zone
        if not box_in_detection_zone(box, detect_roi):
            continue
        boxes.append(box)
    boxes.sort(
        key=lambda item: (float(item.get("confidence") or 0), int(item["x2"]) - int(item["x1"])),
        reverse=True,
    )
    finished = time.monotonic()
    # The worker immediately performs crop OCR on this same frame. Keep the
    # decoded BGR image in the internal metadata so that path does not decode
    # the JPEG a second time. Callers that serialize this metadata should drop
    # the private buffer first; it is intentionally not part of any event.
    return boxes, {"available": True, "image_width": width, "image_height": height,
                   "detector_ms": round((finished - started) * 1000, 1),
                   "detector_started_at": started, "detector_finished_at": finished,
                   "_decoded_bgr": bgr}
