from __future__ import annotations

def _crop_path(image_path: str, bbox) -> str | None:
    if bbox is None:
        return None
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        img = Image.open(image_path)
        x1, y1, x2, y2 = int(bbox.x1), int(bbox.y1), int(bbox.x2), int(bbox.y2)
        pad_x = max(2, (x2 - x1) // 12)
        pad_y = max(2, (y2 - y1) // 8)
        crop = img.crop((max(0, x1 - pad_x), max(0, y1 - pad_y), min(img.width, x2 + pad_x), min(img.height, y2 + pad_y)))
        folder = settings.media_dir / "crops"
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / f"{uuid.uuid4().hex}.jpg"
        crop.convert("RGB").save(dest, quality=92)
        return dest.relative_to(settings.media_dir).as_posix()
    except Exception:
        return None

def clean_ocr_text(text: str | None) -> str:
    """Fast-plate-ocr pads with underscores; Tanzania plates are alphanumeric."""
    return str(text or "").replace("_", "").replace(" ", "").replace("\n", "").strip()

def decode_alpr_image(data: bytes):
    """Decode a phone/camera photo to BGR for FastALPR.predict.

    Applies EXIF rotation, converts to RGB, and rescales so the plate is large
    enough for the 384px detector without feeding a multi-megapixel original.
    """
    from io import BytesIO

    import numpy as np
    from PIL import Image, ImageOps

    img = Image.open(BytesIO(data))
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")
    width, height = img.size
    min_side = min(width, height)
    max_side = max(width, height)
    # Do not enlarge the full vehicle frame. The detector resizes internally;
    # upscaling the whole frame burns CPU without creating plate detail. Only the
    # detected plate crop is enlarged before OCR.
    if max_side > 1920:
        scale = 1920 / float(max_side)
        img = img.resize((max(1, int(width * scale)), max(1, int(height * scale))), Image.Resampling.LANCZOS)
    rgb = np.asarray(img)
    return rgb[:, :, ::-1].copy()

def _boost_contrast(bgr):
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    # Headlights create a dark plate next to clipped white pixels. A mild
    # gamma lift before local contrast recovers shadow detail without making a
    # second OCR call or changing the detector frame.
    try:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        if float(np.mean(gray)) < 82.0:
            gamma = 0.76
            lut = np.array([((index / 255.0) ** gamma) * 255.0 for index in range(256)], dtype=np.uint8)
            bgr = cv2.LUT(bgr, lut)
    except Exception:
        pass
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    light, a, b = cv2.split(lab)
    # Compress specular glare (headlights) before CLAHE so the plate crop is not washed out.
    try:
        hi = float(np.percentile(light, 98))
        if hi > 220:
            light = cv2.convertScaleAbs(light, alpha=0.82, beta=0)
    except Exception:
        pass
    clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
    light = clahe.apply(light)
    enhanced = cv2.cvtColor(cv2.merge((light, a, b)), cv2.COLOR_LAB2BGR)
    # A restrained unsharp mask restores character edges lost to motion blur;
    # keeping the weights low avoids amplifying JPEG/headlight halos.
    try:
        softened = cv2.GaussianBlur(enhanced, (0, 0), 1.0)
        enhanced = cv2.addWeighted(enhanced, 1.18, softened, -0.18, 0)
    except Exception:
        pass
    return enhanced

def _low_light(crop_bgr) -> bool:
    """Use one enhanced OCR pass for dark/IR plates instead of two passes."""
    try:
        import cv2
        import numpy as np
        gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
        return float(np.mean(gray)) < 78.0 or float(np.percentile(gray, 90)) < 125.0
    except Exception:
        return False

def _crop_bgr(bgr, bbox, *, pad_ratio: float = 0.12):
    """Crop plate region with padding. Returns (crop_bgr, xyxy_used)."""
    h, w = bgr.shape[:2]
    x1, y1, x2, y2 = int(bbox.x1), int(bbox.y1), int(bbox.x2), int(bbox.y2)
    bw, bh = max(1, x2 - x1), max(1, y2 - y1)
    pad_x = max(2, int(bw * pad_ratio))
    pad_y = max(2, int(bh * pad_ratio))
    left = max(0, x1 - pad_x)
    top = max(0, y1 - pad_y)
    right = min(w, x2 + pad_x)
    bottom = min(h, y2 + pad_y)
    crop = bgr[top:bottom, left:right]
    return crop, (left, top, right, bottom)

def _prepare_ocr_crop(crop_bgr, *, enhance: bool = True):
    """Upscale and lightly enhance the plate crop before OCR — never OCR the full car."""
    if crop_bgr is None or getattr(crop_bgr, "size", 0) == 0:
        return crop_bgr
    try:
        import cv2
        import numpy as np
    except ImportError:
        return crop_bgr
    h, w = crop_bgr.shape[:2]
    # OCR models like ~a few hundred px wide plates.
    target_w = int(getattr(settings, "alpr_ocr_target_width", 320) or 320)
    if w < target_w:
        scale = target_w / float(max(w, 1))
        crop_bgr = cv2.resize(
            crop_bgr,
            (max(1, int(w * scale)), max(1, int(h * scale))),
            interpolation=cv2.INTER_CUBIC,
        )
    boosted = _boost_contrast(crop_bgr) if enhance else None
    return boosted if boosted is not None else crop_bgr

def _rectify_plate_crop(crop_bgr):
    """Perspective-correct a visibly skewed plate, when its border is clear.

    The detector returns an axis-aligned box, while a Tanzanian plate can be
    viewed at an angle and become a trapezoid.  We only warp a strong,
    plate-shaped quadrilateral found *inside that already validated crop*.
    If no reliable quadrilateral is present, the original crop is returned;
    this keeps ordinary plates and low-light frames on the existing path.
    """
    if crop_bgr is None or getattr(crop_bgr, "size", 0) == 0:
        return crop_bgr, False
    try:
        import cv2
        import numpy as np
    except ImportError:
        return crop_bgr, False
    try:
        height, width = crop_bgr.shape[:2]
        if width < 48 or height < 16:
            return crop_bgr, False
        gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        edges = cv2.Canny(gray, 45, 140)
        edges = cv2.morphologyEx(
            edges,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (5, 3)),
            iterations=1,
        )
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        crop_area = float(width * height)
        candidates = []
        for contour in contours:
            area = float(cv2.contourArea(contour))
            if area < crop_area * 0.16 or area > crop_area * 0.96:
                continue
            perimeter = float(cv2.arcLength(contour, True))
            if perimeter <= 0:
                continue
            approx = cv2.approxPolyDP(contour, perimeter * 0.035, True)
            if len(approx) != 4 or not cv2.isContourConvex(approx):
                continue
            points = approx.reshape(4, 2).astype("float32")
            top_width = float(np.linalg.norm(points[1] - points[0]))
            bottom_width = float(np.linalg.norm(points[2] - points[3]))
            left_height = float(np.linalg.norm(points[3] - points[0]))
            right_height = float(np.linalg.norm(points[2] - points[1]))
            long_side = max(top_width, bottom_width)
            short_side = max(1.0, min(left_height, right_height))
            aspect = long_side / short_side
            if not (1.35 <= aspect <= 8.0):
                continue
            # Favor a large, central plate border over a random car-panel edge.
            center = points.mean(axis=0)
            distance = float(np.linalg.norm(center - np.array([width / 2, height / 2])))
            score = area * (1.0 - min(0.7, distance / max(width, height)))
            candidates.append((score, points, aspect))
        if not candidates:
            return crop_bgr, False
        _, points, aspect = max(candidates, key=lambda item: item[0])
        sums = points.sum(axis=1)
        diffs = points[:, 0] - points[:, 1]
        ordered = np.array([
            points[np.argmin(sums)],
            points[np.argmin(diffs)],
            points[np.argmax(sums)],
            points[np.argmax(diffs)],
        ], dtype="float32")
        out_width = max(160, min(640, int(round(max(width * 0.8, 320)))))
        out_height = max(32, min(160, int(round(out_width / max(aspect, 1.35)))))
        target = np.array([
            [0, 0], [out_width - 1, 0],
            [out_width - 1, out_height - 1], [0, out_height - 1],
        ], dtype="float32")
        matrix = cv2.getPerspectiveTransform(ordered, target)
        rectified = cv2.warpPerspective(
            crop_bgr, matrix, (out_width, out_height),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )
        if rectified is None or getattr(rectified, "size", 0) == 0:
            return crop_bgr, False
        return rectified, True
    except Exception:
        # Rectification is an enhancement, never a reason to lose a frame.
        return crop_bgr, False

def _save_crop_bgr(crop_bgr) -> str | None:
    if crop_bgr is None or getattr(crop_bgr, "size", 0) == 0:
        return None
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        rgb = crop_bgr[:, :, ::-1]
        folder = settings.media_dir / "crops"
        folder.mkdir(parents=True, exist_ok=True)
        output = BytesIO()
        Image.fromarray(rgb).save(output, format="JPEG", quality=95)
        from app.services.captures import _write_jpeg
        data = output.getvalue()
        return _write_jpeg("crops", f"ocr-{hashlib.sha256(data).hexdigest()[:24]}.jpg", data)
    except Exception:
        return None

def parse_detect_roi(value: str | None = None) -> tuple[float, float, float, float] | None:
    raw = str(value if value is not None else getattr(settings, "alpr_detect_roi", "") or "").strip()
    if raw.lower() in {"", "off", "none", "full"}:
        return None
    try:
        parts = [float(item) for item in raw.replace(";", ",").split(",") if item.strip()]
    except ValueError:
        return None
    if len(parts) != 4:
        return None
    x1, y1, x2, y2 = parts
    if not (0.0 <= x1 < x2 <= 1.0 and 0.0 <= y1 < y2 <= 1.0):
        return None
    # 8% of the frame is enough for a lane trigger box. The old 40% floor
    # blocked the tighter locator an operator draws on the live view.
    if (x2 - x1) < 0.08 or (y2 - y1) < 0.08:
        return None
    return x1, y1, x2, y2

def _roi_crop(bgr, detect_roi: str | None = None, detect_zoom: float | None = None):
    """Crop to the recognition zone, then apply digital zoom. Returns (view, x_off, y_off).

    ``detect_roi`` is a per-camera override (``x1,y1,x2,y2`` or ``off``).
    None uses the site-wide ``alpr_detect_roi`` setting. ``off`` is the full frame.
    ``detect_zoom`` above 1 keeps the center of that zone (2 keeps the middle half).
    Boxes found in the crop are shifted back by the returned offsets.
    """
    from app.services.camera_framing import parse_detect_zoom

    roi = parse_detect_roi(detect_roi) if detect_roi is not None else parse_detect_roi()
    if bgr is None or getattr(bgr, "size", 0) == 0:
        return bgr, 0, 0
    if roi is None:
        view, left, top = bgr, 0, 0
    else:
        height, width = bgr.shape[:2]
        left = max(0, min(width - 1, int(width * roi[0])))
        top = max(0, min(height - 1, int(height * roi[1])))
        right = max(left + 1, min(width, int(width * roi[2])))
        bottom = max(top + 1, min(height, int(height * roi[3])))
        if right - left < 32 or bottom - top < 32:
            return bgr, 0, 0
        view = bgr[top:bottom, left:right]
    zoom = parse_detect_zoom(detect_zoom)
    if zoom <= 1.01:
        return view, left, top
    view_h, view_w = view.shape[:2]
    keep_w = max(32, int(view_w / zoom))
    keep_h = max(32, int(view_h / zoom))
    if keep_w >= view_w and keep_h >= view_h:
        return view, left, top
    cx, cy = view_w // 2, view_h // 2
    zoom_left = max(0, min(view_w - keep_w, cx - keep_w // 2))
    zoom_top = max(0, min(view_h - keep_h, cy - keep_h // 2))
    return view[zoom_top:zoom_top + keep_h, zoom_left:zoom_left + keep_w], left + zoom_left, top + zoom_top

def _shift_detections(detections, dx: int, dy: int):
    if not detections or (not dx and not dy):
        return list(detections or [])
    from types import SimpleNamespace

    shifted = []
    for detection in detections:
        bbox = getattr(detection, "bounding_box", None)
        if bbox is None:
            shifted.append(detection)
            continue
        box = SimpleNamespace(
            x1=int(getattr(bbox, "x1", 0)) + dx,
            y1=int(getattr(bbox, "y1", 0)) + dy,
            x2=int(getattr(bbox, "x2", 0)) + dx,
            y2=int(getattr(bbox, "y2", 0)) + dy,
        )
        shifted.append(
            SimpleNamespace(
                bounding_box=box,
                confidence=_detection_score(detection),
            )
        )
    return shifted
