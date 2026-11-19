from __future__ import annotations

def capture_dict(row: VehicleCapture) -> dict:
    chars = " ".join(list(row.plate)) if row.plate else ""
    snapshot = (row.snapshot_path or "").replace("\\", "/")
    crop = (row.crop_path or "").replace("\\", "/")
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
        "snapshot_url": f"/media/{snapshot}" if snapshot else None,
        "crop_url": f"/media/{crop}" if crop else None,
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

def find_capture_for_session(
    db: Session,
    *,
    plate: str = "",
    camera_id: int | None = None,
    event_id: str = "",
    visit_id: str = "",
    image_ref: str = "",
) -> VehicleCapture | None:
    """Return evidence belonging to this visit, never a later plate read.

    Event/visit identity is authoritative.  A session's persisted entry image
    reference is a second session-bound identity for older or partially
    upgraded rows. Plate-only fallback is retained only for legacy sessions
    that predate those identifiers; camera fallback is deliberately removed
    because it can show an unrelated vehicle.
    """
    plate = normalize_plate(plate)
    event_id = str(event_id or "").strip()
    visit_id = str(visit_id or "").strip()
    image_ref = str(image_ref or "").strip().split("?", 1)[0].replace("\\", "/")
    if image_ref.startswith("/media/"):
        image_ref = image_ref[len("/media/"):]
    image_parts = [part for part in image_ref.split("/") if part]
    if len(image_parts) != 2:
        image_ref = ""
    if camera_id and event_id:
        matched = db.scalar(
            select(VehicleCapture).where(
                VehicleCapture.camera_id == int(camera_id),
                VehicleCapture.event_id == event_id,
            ).order_by(VehicleCapture.id.desc()).limit(1)
        )
        if matched:
            return matched
    if camera_id and visit_id:
        matched = db.scalar(
            select(VehicleCapture).where(
                VehicleCapture.camera_id == int(camera_id),
                VehicleCapture.visit_id == visit_id,
            ).order_by(VehicleCapture.id.desc()).limit(1)
        )
        if matched:
            return matched
    if image_ref:
        image_filter = or_(
            VehicleCapture.snapshot_path == image_ref,
            VehicleCapture.crop_path == image_ref,
        )
        stmt = select(VehicleCapture).where(image_filter)
        if camera_id:
            stmt = stmt.where(VehicleCapture.camera_id == int(camera_id))
        matched = db.scalar(stmt.order_by(VehicleCapture.id.desc()))
        if matched:
            return matched
    if event_id or visit_id:
        return None
    if plate:
        matched = db.scalar(
            select(VehicleCapture)
            .where(VehicleCapture.plate == plate)
            .order_by(VehicleCapture.id.desc()).limit(1)
        )
        if matched:
            return matched
    return None

def prune_unreferenced_media(db: Session, *, retention_days: int | None = None) -> dict[str, int]:
    """Remove expired, unreferenced evidence files without touching receipts.

    Capture rows are the retention authority.  A file is never removed while
    a capture still points to it, which keeps public receipts and operator
    evidence valid even when the cleanup job runs concurrently with capture
    ingestion.
    """
    import time

    days = max(1, int(retention_days if retention_days is not None else getattr(settings, "media_retention_days", 14) or 14))
    cutoff = time.time() - days * 86400
    referenced: set[str] = set()
    for snapshot, crop in db.execute(select(VehicleCapture.snapshot_path, VehicleCapture.crop_path)).all():
        for value in (snapshot, crop):
            text = str(value or "").replace("\\", "/").lstrip("/")
            if text:
                referenced.add(text)
    removed = 0
    scanned = 0
    for kind in ("snapshots", "crops", "annotated", "alpr", "recognition"):
        folder = settings.media_dir / kind
        if not folder.is_dir():
            continue
        for path in folder.glob("*.jpg"):
            scanned += 1
            relative = Path(kind, path.name).as_posix()
            if relative in referenced or path.name.startswith("live-"):
                continue
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except OSError:
                continue
    return {"scanned": scanned, "removed": removed, "retention_days": days}

def _capture_by_identity(db: Session, camera_id: int, capture: dict | None) -> VehicleCapture | None:
    for key in ("visit_id", "event_id"):
        value = str((capture or {}).get(key) or "")
        if value:
            existing = db.scalar(select(VehicleCapture).where(
                VehicleCapture.camera_id == camera_id, getattr(VehicleCapture, key) == value,
            ))
            if existing is not None:
                return existing
    return None

def _discard_unreferenced_media(db: Session, *refs: str) -> None:
    """Remove files created by a losing concurrent insert.

    Capture evidence is written before the row commit so the row can reference
    it. If a database uniqueness race rejects that insert, those files would
    otherwise remain as duplicate/orphan media forever.
    """
    for raw in refs:
        relative = str(raw or "").replace("\\", "/")
        parts = Path(relative).parts
        if len(parts) != 2 or parts[0] not in {"snapshots", "crops", "annotated", "alpr", "recognition"}:
            continue
        in_use = db.scalar(select(func.count(VehicleCapture.id)).where(
            or_(VehicleCapture.snapshot_path == relative, VehicleCapture.crop_path == relative)
        ))
        if in_use:
            continue
        path = settings.media_dir / parts[0] / parts[1]
        try:
            path.unlink(missing_ok=True)
        except OSError:
            log.debug("Could not remove orphan capture media: %s", path, exc_info=True)

def _box_iou(left: dict | None, right: dict | None) -> float:
    a = _xyxy(left)
    b = _xyxy(right)
    if a is None or b is None:
        return 0.0
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    intersection = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if intersection <= 0:
        return 0.0
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - intersection
    return intersection / union if union > 0 else 0.0

def _recent_native_duplicate(
    db: Session,
    camera: Camera,
    capture: dict | None,
    native: dict,
    *,
    force: bool,
) -> VehicleCapture | None:
    """Collapse repeated native callbacks before writing another evidence file.

    The HVX SDK may assign a new image ID to each callback for one car. The
    visit ID normally protects the database, but an SDK reconnect or a late
    callback can create a new visit ID. Same-camera native reads with the same
    plate and nearby plate geometry are still one physical read during the
    short repeat window. Explicit/maintenance writes use ``force`` and are
    never collapsed here.
    """
    if force:
        return None
    source = str((capture or {}).get("source") or native.get("source") or "").lower()
    if "fastalpr" in source or source in {"local", "simulation", "simulated"}:
        return None
    plate = normalize_plate(native.get("plate") or "")
    if not plate:
        return None
    latest = latest_for_camera(db, camera.id)
    if latest is None or normalize_plate(latest.plate or "") != plate:
        return None
    created = as_utc(latest.created_at)
    if created is None:
        return None
    age = (utcnow() - created).total_seconds()
    window = float(getattr(settings, "native_repeat_window_seconds", 8.0) or 8.0)
    if age < 0 or age > window:
        return None
    # QY realtime image IDs and plate boxes can change on every callback while
    # one car is moving. The repeat window is the reliable physical boundary;
    # requiring box overlap allowed one car to create several captures.
    log.info(
        "native capture duplicate suppressed camera_id=%s plate=%s age_seconds=%.2f",
        camera.id,
        plate,
        age,
    )
    return latest

def _read_plate(capture: dict | None, native: dict) -> str:
    return str(native.get("plate") or (capture or {}).get("plate") or "").strip().upper()


def _read_confidence(capture: dict | None, native: dict) -> float | None:
    """Recognition confidence of this read (0-1), or None when there is no plate."""
    for value in (native.get("confidence"), (capture or {}).get("confidence"), (capture or {}).get("score")):
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        return number / 100.0 if number > 1.0 else number
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
    defer_evidence: bool = False,
) -> VehicleCapture | None:
    """Store one camera vehicle event.

    ``defer_evidence`` (live camera events): a new capture row is committed
    with reserved photo names and ``evidence_state='PENDING'``; the zone
    snapshot and plate crop are produced and written afterwards by
    ``app.services.evidence``, so the access decision does not wait for them.
    """
    from app.services.developer import capture_enabled
    if not capture_enabled(db):
        return None
    # Calibration test mode: every vehicle read for this camera (camera
    # trigger or ZIRP's own) ends here. The calibration window shows it; no
    # capture row is written, so no parking session and no barrier command.
    from app.services import capture_calibration as _calibration
    _native_read = native_from_sdk_capture(capture)
    if _calibration.in_test_mode(int(camera.id)):
        _test_box = _native_read.get("bbox") if isinstance(_native_read.get("bbox"), dict) else (
            bbox_from_lp_box((capture or {}).get("plate_box")) or (capture or {}).get("bbox"))
        _verdict = _calibration.check_capture(
            int(camera.id), _test_box if isinstance(_test_box, dict) else None, jpeg or b"",
            plate=_read_plate(capture, _native_read), plate_confidence=_read_confidence(capture, _native_read))
        _calibration.note_read(
            int(camera.id), plate=str(_native_read.get("plate") or (capture or {}).get("plate") or ""),
            confidence=float(_native_read.get("confidence") or 0.0),
            source=str((capture or {}).get("source") or _native_read.get("source") or "camera"),
            test_mode=True, accepted=(_verdict is None or _verdict.eligible), jpeg=jpeg or b"",
        )
        if _verdict is not None and not _verdict.eligible:
            _calibration.note_rejected(int(camera.id), plate=str(_native_read.get("plate") or ""),
                                       reasons=_verdict.reasons, candidate=_verdict, jpeg=jpeg or b"")
        return None
    existing = _capture_by_identity(db, camera.id, capture)
    if existing is not None:
        return existing
    jpeg = jpeg or b""
    crop = crop or b""
    if jpeg[:2] != b"\xff\xd8" and crop[:2] == b"\xff\xd8":
        jpeg = crop
    native = native_from_sdk_capture(capture)
    image_id = int((capture or {}).get("image_id") or 0)
    if jpeg[:2] != b"\xff\xd8" and crop[:2] != b"\xff\xd8" and not native.get("plate"):
        return None
    # The zone snapshot and the plate crop are image work (about 150 ms per
    # car on SITE-PC01): produced on first use, and for deferred evidence only
    # after the decision.
    zone_args = None
    if not (capture or {}).get("snapshot_zone") and jpeg[:2] == b"\xff\xd8":
        from app.services.camera_framing import framing_from_profiles

        framing = framing_from_profiles(getattr(camera, "stream_profiles", None))
        zone_args = {
            "detect_roi": (capture or {}).get("detect_roi") or framing["detect_roi"],
            "detect_zoom": (capture or {}).get("detect_zoom") or framing["detect_zoom"],
        }
    _made: dict[str, bytes] = {}

    def make_snapshot() -> bytes:
        if "snapshot" not in _made:
            _made["snapshot"] = (detection_zone_jpeg(jpeg, **zone_args) or jpeg) if zone_args else jpeg
        return _made["snapshot"]
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
    raw_box = (capture or {}).get("bbox") if isinstance((capture or {}).get("bbox"), dict) else {}
    for key in ("image_width", "image_height", "confidence"):
        # The camera-side box drops the picture size and detector score;
        # the calibration check needs both.
        if box.get(key) in (None, "") and raw_box.get(key) not in (None, ""):
            box[key] = raw_box[key]
    if not force:
        # A car is never read outside its camera's capture calibration,
        # whatever triggered the read (camera, ZIRP video, worker). Only an
        # explicit operator action (force) bypasses it.
        verdict = _calibration.check_capture(int(camera.id), box, jpeg,
                                             plate=_read_plate(capture, _native_read),
                                             plate_confidence=_read_confidence(capture, _native_read))
        if verdict is not None and not verdict.eligible:
            _calibration.note_rejected(
                int(camera.id), plate=str(_native_read.get("plate") or (capture or {}).get("plate") or ""),
                reasons=verdict.reasons, candidate=verdict, jpeg=jpeg or b"",
            )
            return None
        _calibration.note_stored(int(camera.id))
    if native.get("source"):
        box["source"] = native.get("source")
    # Preserve the camera's read-only OcxConfig geometry for diagnostics and
    # evidence review. It is metadata only; it never schedules another query
    # or capture.
    if native.get("plate_region"):
        box["native_plate_region"] = native["plate_region"]
    if native.get("stop_line"):
        box["native_stop_line"] = native["stop_line"]
    for key in (
        "capture_mode", "native_min_plate_width", "native_max_plate_width",
        "camera_timestamp", "vehicle_id", "snapshot_index",
    ):
        if native.get(key) is not None:
            box[key] = native[key]
    try:
        from PIL import Image
        if jpeg[:2] == b"\xff\xd8":
            frame = Image.open(BytesIO(jpeg))
            box.setdefault("image_width", int(frame.width))
            box.setdefault("image_height", int(frame.height))
    except Exception:
        pass
    box = attach_fusion_audit(box, capture)

    def make_crop() -> bytes:
        if "crop" not in _made:
            _made["crop"] = _plate_jpeg(jpeg, crop, box, capture)
        return _made["crop"]
    has_identity = bool((capture or {}).get("visit_id") or (capture or {}).get("event_id"))
    if image_id and not has_identity:
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
            incoming = bbox_from_lp_box(box)
            already = bbox_from_lp_box(existing.bbox)
            if incoming:
                merged = dict(existing.bbox or {})
                merged.update(incoming)
                if box.get("image_width"):
                    merged["image_width"] = box.get("image_width")
                    merged["image_height"] = box.get("image_height")
                if box.get("source"):
                    merged["source"] = box.get("source")
                existing.bbox = attach_fusion_audit(merged, capture)
                updated = True
            elif not already:
                existing.bbox = attach_fusion_audit(box or existing.bbox, capture)
            plate_jpeg = make_crop()
            if plate_jpeg[:2] == b"\xff\xd8":
                existing.crop_path = _reuse_media_ref((capture or {}).get("plate_crop_ref"), "crops", plate_jpeg) or _write_jpeg(
                    "crops", _plate_crop_name(camera.id, image_id, capture, incoming_plate or existing.plate), plate_jpeg,
                )
                updated = True
            if not existing.snapshot_path and make_snapshot()[:2] == b"\xff\xd8":
                existing.snapshot_path = _reuse_media_ref((capture or {}).get("image_ref"), "snapshots", make_snapshot()) or _write_jpeg(
                    "snapshots", f"cam{camera.id}-img{image_id}-car.jpg", make_snapshot(),
                )
                updated = True
            if updated:
                db.commit()
                db.refresh(existing)
            return existing
    elif not has_identity:
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
                # The picture callback and the plate-info report can arrive as
                # two image_id=0 events. Keep the one that actually has usLpBox.
                incoming = bbox_from_lp_box(box)
                already = bbox_from_lp_box(latest.bbox)
                if incoming and not already:
                    latest.bbox = attach_fusion_audit({**(latest.bbox or {}), **incoming}, capture)
                    plate_jpeg = make_crop()
                    if plate_jpeg[:2] == b"\xff\xd8":
                        latest.crop_path = _write_jpeg(
                            "crops", _plate_crop_name(camera.id, 0, capture, latest.plate), plate_jpeg,
                        )
                    db.commit()
                    db.refresh(latest)
                return latest
    recent_duplicate = _recent_native_duplicate(db, camera, capture, native, force=force)
    if recent_duplicate is not None:
        return recent_duplicate
    stamp = f"cam{camera.id}-img{image_id or int(time.time() * 1000) % 1_000_000_000}"
    crop_name = _plate_crop_name(camera.id, image_id, capture, native.get("plate"))
    deferred = bool(
        defer_evidence
        and not (capture or {}).get("image_ref")
        and not (capture or {}).get("plate_crop_ref")
        and (jpeg[:2] == b"\xff\xd8" or crop[:2] == b"\xff\xd8")
    )
    if deferred:
        # Reserve the names now; the files follow the decision.
        snapshot_path = f"snapshots/{stamp}-car.jpg" if jpeg[:2] == b"\xff\xd8" else ""
        crop_path = f"crops/{crop_name}"
    else:
        snapshot_jpeg = make_snapshot()
        plate_jpeg = make_crop()
        snapshot_path = (
            _reuse_media_ref((capture or {}).get("image_ref"), "snapshots", snapshot_jpeg)
            or _write_jpeg("snapshots", f"{stamp}-car.jpg", snapshot_jpeg)
        ) if snapshot_jpeg[:2] == b"\xff\xd8" else ""
        crop_path = (
            _reuse_media_ref((capture or {}).get("plate_crop_ref"), "crops", plate_jpeg)
            or _write_jpeg("crops", crop_name, plate_jpeg)
        ) if plate_jpeg[:2] == b"\xff\xd8" else ""
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
        evidence_state="PENDING" if deferred else "",
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _capture_by_identity(db, camera.id, capture)
        if existing is None and image_id > 0:
            existing = db.scalar(select(VehicleCapture).where(
                VehicleCapture.camera_id == camera.id,
                VehicleCapture.image_id == image_id,
            ))
        if not deferred:
            # Deferred names were only reserved: nothing was written, and the
            # winner may own a file with the same name.
            _discard_unreferenced_media(db, snapshot_path, crop_path)
        if existing is None:
            raise
        return existing
    db.refresh(row)
    if deferred:
        from app.services import evidence

        evidence.submit(evidence.EvidenceJob(
            capture_id=int(row.id), snapshot_ref=snapshot_path, crop_ref=crop_path,
            make_snapshot=make_snapshot, make_crop=make_crop,
        ))
    return row
