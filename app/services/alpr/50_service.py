from __future__ import annotations

def recognize_plate_crop_bytes(jpeg: bytes, *, camera_label: str = "plate-crop") -> dict:
    """OCR a JPEG that is already a plate crop, skipping full-frame detection.

    Native ALPR cameras often provide a plate JPEG alongside the vehicle image.
    Re-reading that crop is the cheapest software verification:
    camera event -> plate crop -> FastPlateOCR. Generic cameras still use the
    detector-first path because they do not know the plate box.
    """
    started = time.monotonic()
    if not jpeg or not fastalpr_installed():
        return {"ok": False, "backend": "none", "plates": [], "detail": "plate crop unavailable"}
    try:
        bgr = decode_alpr_image(jpeg)
        engine = _load_engine()
        rectified, rectified_used = _rectify_plate_crop(bgr)
        # Night/IR crops need a deliberately bounded second pass.  The old
        # direct-crop path enhanced once but never retried a weak result, so a
        # dark native crop could be displayed as evidence yet fail OCR.
        attempts = [_prepare_ocr_crop(rectified, enhance=False)]
        if _low_light(rectified):
            attempts.append(_prepare_ocr_crop(rectified, enhance=True))
        text, conf, plate, raw_conf = "", 0.0, "", 0.0
        for index, ocr_input in enumerate(attempts):
            ocr = engine.ocr.predict(ocr_input)
            candidate_text, candidate_conf = _ocr_result_text(ocr)
            candidate_plate, _rank = _apply_country_profile(candidate_text, candidate_conf)
            candidate_raw_conf = max(0.0, min(float(candidate_conf or 0), 1.0))
            candidate_ok = accept_ocr_plate(candidate_plate, candidate_raw_conf)
            if candidate_ok and (not plate or candidate_raw_conf > raw_conf):
                text, conf, plate, raw_conf = candidate_text, candidate_conf, candidate_plate, candidate_raw_conf
            elif index == 0 and not plate:
                text, conf, plate, raw_conf = candidate_text, candidate_conf, candidate_plate, candidate_raw_conf
        if not accept_ocr_plate(plate, raw_conf):
            return {
                "ok": True, "backend": "fastalpr", "pipeline": "crop_ocr",
                "plates": [], "best": None,
                "latency_ms": round((time.monotonic() - started) * 1000, 2),
                "detail": "no readable plate in crop",
            }
        hit = PlateHit(
            plate_raw=text,
            plate_normalized=plate,
            plate_confidence=raw_conf,
            plate_crop_path=_save_crop_bgr(_prepare_ocr_crop(rectified, enhance=True)),
            bbox=None,
        )
        return {
            "ok": True,
            "backend": "fastalpr",
            "pipeline": "crop_ocr",
            "plates": [hit.as_dict()],
            "count": 1,
            "best": hit.as_dict(),
            "perspective_rectified": rectified_used,
            "latency_ms": round((time.monotonic() - started) * 1000, 2),
            "detail": "plate crop OCR",
        }
    except Exception as exc:
        return {
            "ok": False,
            "backend": "fastalpr",
            "pipeline": "crop_ocr",
            "plates": [],
            "best": None,
            "latency_ms": round((time.monotonic() - started) * 1000, 2),
            "detail": str(exc),
        }

def recognize_arrival_bytes(
    jpeg: bytes,
    *,
    camera_label: str = "arrival",
    detect_roi: str | None = None,
    detect_zoom: float | None = None,
    save_evidence: bool | None = None,
    detected_boxes: list | None = None,
    decoded_bgr=None,
    fallback_box: dict | None = None,
) -> dict:
    """When a plate is in the zone, crop it and OCR that crop. Never OCR the car.

    No plate box means no OCR. A detector that cannot run also means no OCR:
    reading the whole live frame is what made the gate slow and inaccurate.
    """
    started = time.monotonic()
    if detected_boxes is None:
        boxes, meta = locate_plate_boxes(jpeg, detect_roi=detect_roi, detect_zoom=detect_zoom)
        # OcxConfig's native rectangle is a capture hint, not the primary
        # software crop.  It is retained only when the current detector could
        # not produce a box for this event (for example a Windows model warm-up
        # or a dark/IR frame).
        if not boxes and isinstance(fallback_box, dict):
            boxes = [fallback_box]
            meta = {**meta, "available": True, "fallback": "ocxconfig-native-box"}
    else:
        boxes, meta = detected_boxes, {"available": True}
    if not meta.get("available"):
        return {
            "ok": False,
            "backend": "fastalpr",
            "pipeline": "arrival_crop_ocr",
            "plates": [],
            "count": 0,
            "best": None,
            "detail": meta.get("detail") or "detector unavailable; the live frame was not read",
        }
    if not boxes:
        return {
            "ok": True,
            "backend": "fastalpr",
            "pipeline": "arrival_crop_ocr",
            "plates": [],
            "count": 0,
            "best": None,
            "detail": "no plate in the detection zone",
        }
    try:
        # ``decoded_bgr`` is an internal fast path used after detector-first
        # recognition. Fall back to the public JPEG decode path if a caller
        # supplies an invalid buffer; this keeps the API failure-safe.
        bgr = decoded_bgr if decoded_bgr is not None else meta.get("_decoded_bgr")
        if getattr(bgr, "ndim", 0) != 3 or getattr(bgr, "size", 0) == 0:
            bgr = decode_alpr_image(jpeg)
        engine = _load_engine()
    except Exception:
        return {"ok": False, "backend": "fastalpr", "pipeline": "arrival_crop_ocr", "plates": [], "best": None, "detail": "could not decode frame"}
    from types import SimpleNamespace

    from app.services.camera_framing import box_in_detection_zone
    valid_boxes = []
    for box in boxes:
        try:
            candidate = SimpleNamespace(**{key: int(box[key]) for key in ("x1", "y1", "x2", "y2")})
            if (
                plate_box_ok(candidate, int(bgr.shape[1]), int(bgr.shape[0]))
                and box_in_detection_zone(
                    {**box, "image_width": int(bgr.shape[1]), "image_height": int(bgr.shape[0])},
                    detect_roi,
                )
            ):
                valid_boxes.append(box)
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    if not valid_boxes:
        return {"ok": True, "backend": "fastalpr", "pipeline": "arrival_crop_ocr", "plates": [], "best": None, "detail": "no valid plate crop"}
    best_box = max(valid_boxes, key=lambda box: (float(box.get("confidence") or 0),
                       (int(box["x2"]) - int(box["x1"])) * (int(box["y2"]) - int(box["y1"]))))
    detection = SimpleNamespace(
        bounding_box=SimpleNamespace(
            x1=int(best_box["x1"]), y1=int(best_box["y1"]),
            x2=int(best_box["x2"]), y2=int(best_box["y2"]),
        ),
        confidence=float(best_box.get("confidence") or 0),
    )
    persist = bool(save_evidence if save_evidence is not None else getattr(settings, "alpr_save_debug_frames", False))
    try:
        hits = _hits_from_detections(engine, bgr, [detection], save_crops=persist)
    except Exception as exc:
        from app.services.redaction import redact_text
        return {"ok": False, "backend": "fastalpr", "pipeline": "arrival_crop_ocr", "plates": [],
                "best": None, "detail": redact_text(str(exc))}
    plates = [hit.as_dict() for hit in hits]
    best = hits[0] if hits else None
    return {
        "ok": True,
        "backend": "fastalpr",
        "pipeline": "arrival_crop_ocr",
        "plates": plates,
        "count": len(plates),
        "best": best.as_dict() if best else None,
        "detail": "plate cropped, then read" if best else "plate crop was not readable",
        "latency_ms": round((time.monotonic() - started) * 1000, 1),
        "detector_ms": meta.get("detector_ms"),
    }

def plate_still_present(jpeg: bytes, *, detect_roi: str | None = None, detect_zoom: float | None = None) -> bool | None:
    """Detector-only presence check. Does not run OCR.

    True when a plate-shaped box is in the frame, False when the detector ran
    and found none, None when the detector could not run. None must not be
    treated as an empty lane.
    """
    if not jpeg or not fastalpr_installed():
        return None
    try:
        bgr = decode_alpr_image(jpeg)
        engine = _load_engine()
    except Exception:
        return None
    if not hasattr(engine, "detector"):
        return None
    try:
        view, dx, dy = _roi_crop(bgr, detect_roi, detect_zoom)
        detections = _shift_detections(engine.detector.predict(view), dx, dy)
    except Exception:
        return None
    width, height = int(bgr.shape[1]), int(bgr.shape[0])
    min_det = float(getattr(settings, "alpr_detector_confidence", 0.26) or 0.26)
    for item in detections or []:
        bbox = getattr(item, "bounding_box", None)
        # Keep departure detection consistent with the arrival detector.  A
        # low-confidence glare/sign box must not hold a published visit in
        # ``EVENT_PUBLISHED`` forever and block the next vehicle.
        if bbox is not None and _detection_score(item) >= min_det and plate_box_ok(bbox, width, height):
            return True
    return False

def recognize_bgr(
    bgr,
    *,
    crop_source: str,
    save_crops: bool = False,
    detect_roi: str | None = None,
    detect_zoom: float | None = None,
) -> tuple[list[PlateHit], dict]:
    started = time.monotonic()
    if not fastalpr_installed():
        return [], {
            "backend": "none",
            "ok": False,
            "error": "FastALPR is not installed — not substituting simulated plates",
            "latency_ms": 0,
        }
    try:
        engine = _load_engine()
        last_error = None
        detections = []
        plate_shaped = []
        try:
            if hasattr(engine, "detector") and hasattr(engine, "ocr"):
                view, dx, dy = _roi_crop(bgr, detect_roi, detect_zoom)
                detections = _shift_detections(engine.detector.predict(view), dx, dy)
                image_size = (int(bgr.shape[1]), int(bgr.shape[0]))
                plate_shaped = [
                    item for item in detections
                    if getattr(item, "bounding_box", None) is not None
                    and plate_box_ok(item.bounding_box, image_size[0], image_size[1])
                ]
                hits = _hits_from_detections(engine, bgr, plate_shaped, save_crops=save_crops)
            else:
                hits = _hits_from_predict(engine.predict(bgr), crop_source)
                detections = hits
                plate_shaped = hits
        except Exception as exc:
            last_error = str(exc)
            hits = []
            detections = []
            plate_shaped = []
        if hits:
            return hits, {
                "backend": "fastalpr",
                "ok": True,
                "pipeline": "detect_crop_ocr",
                "latency_ms": round((time.monotonic() - started) * 1000, 2),
                "count": len(hits),
            }
        # Filter 无车牌. A second full-frame CLAHE detect on empty
        # asphalt doubles CPU and is how ZC ghosts appear. Only retry when the
        # detector already found a plate-shaped box (glare / dirty plate).
        if not plate_shaped:
            return [], {
                "backend": "fastalpr",
                "ok": True,
                "pipeline": "detect_crop_ocr",
                "error": last_error,
                "latency_ms": round((time.monotonic() - started) * 1000, 2),
                "count": 0,
            }
        boosted = _boost_contrast(bgr)
        if boosted is not None:
            try:
                if hasattr(engine, "detector") and hasattr(engine, "ocr"):
                    view, dx, dy = _roi_crop(boosted, detect_roi, detect_zoom)
                    retry = _shift_detections(engine.detector.predict(view), dx, dy)
                    hits = _hits_from_detections(engine, boosted, retry, save_crops=save_crops)
                else:
                    hits = _hits_from_predict(engine.predict(boosted), crop_source)
            except Exception as exc:
                last_error = str(exc)
                hits = []
            if hits:
                return hits, {
                    "backend": "fastalpr",
                    "ok": True,
                    "pipeline": "detect_crop_ocr",
                    "latency_ms": round((time.monotonic() - started) * 1000, 2),
                    "count": len(hits),
                }
        return [], {
            "backend": "fastalpr",
            "ok": True,
            "pipeline": "detect_crop_ocr",
            "error": last_error,
            "latency_ms": round((time.monotonic() - started) * 1000, 2),
            "count": 0,
        }
    except Exception as exc:
        return [], {
            "backend": "fastalpr",
            "ok": False,
            "error": str(exc),
            "latency_ms": round((time.monotonic() - started) * 1000, 2),
        }

def recognize_file(image_path: str) -> tuple[list[PlateHit], dict]:
    """Run FastALPR on a JPEG/PNG. Never falls back to simulated plates."""
    source = Path(image_path)
    if not source.is_file():
        return [], {"backend": "fastalpr", "ok": False, "error": "image not found", "latency_ms": 0}
    try:
        bgr = decode_alpr_image(source.read_bytes())
    except Exception:
        return [], {"backend": "fastalpr", "ok": False, "error": "could not decode image", "latency_ms": 0}
    return recognize_bgr(bgr, crop_source=str(source))

def recognize_bytes(
    jpeg: bytes,
    *,
    camera_label: str = "frame",
    save_evidence: bool | None = None,
    detect_roi: str | None = None,
    detect_zoom: float | None = None,
) -> dict:
    """Run FastALPR on a camera frame or simulation upload. Never invents plates.

    Continuous lane OCR must not write a unique JPEG per frame (that filled disks).
    Decode in memory. Debug frames are off unless explicitly requested.
    """
    if not jpeg:
        return {"ok": False, "backend": "none", "plates": [], "detail": "empty frame"}
    if not fastalpr_installed():
        return {
            "ok": False,
            "backend": "none",
            "plates": [],
            "detail": "FastALPR is not installed — not substituting simulated plates",
        }
    try:
        bgr = decode_alpr_image(jpeg)
    except Exception:
        return {
            "ok": False,
            "backend": "fastalpr",
            "plates": [],
            "detail": "could not decode that photo",
        }
    persist = bool(save_evidence if save_evidence is not None else getattr(settings, "alpr_save_debug_frames", False))
    hits, meta = recognize_bgr(
        bgr, crop_source="", save_crops=persist, detect_roi=detect_roi, detect_zoom=detect_zoom,
    )
    plates = [hit.as_dict() for hit in hits]
    best = max(hits, key=lambda h: h.plate_confidence) if hits else None
    annotated = None
    image_rel = ""
    if hits and persist:
        # One rotating debug file per camera label — never uuid-per-frame.
        folder = settings.media_dir / "alpr"
        folder.mkdir(parents=True, exist_ok=True)
        safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in camera_label)[:80] or "frame"
        image = folder / f"{safe}-latest.jpg"
        try:
            from PIL import Image
            Image.fromarray(bgr[:, :, ::-1]).save(image, quality=85)
            image_rel = image.relative_to(settings.media_dir).as_posix()
            annotated = annotate_image(str(image), hits, dest_name=f"{safe}-latest.jpg")
        except Exception:
            image_rel = ""
            annotated = None
    return {
        "ok": bool(hits) or bool(meta.get("ok")),
        "backend": meta.get("backend"),
        "pipeline": meta.get("pipeline") or "detect_crop_ocr",
        "plates": plates,
        "count": len(plates),
        "best": best.as_dict() if best else None,
        "latency_ms": meta.get("latency_ms"),
        "detail": meta.get("error") or (f"{len(plates)} plate(s)" if plates else "no plate in frame"),
        "image_path": image_rel,
        "image_url": f"/media/{image_rel}" if image_rel else None,
        "annotated_path": annotated,
        "annotated_url": f"/media/{annotated}" if annotated else None,
    }
