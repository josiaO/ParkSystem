"""Local FastALPR boundary.

A plate event is the only thing the rest of SmartPark should see. This module
never invents plates: if FastALPR is missing, it reports that instead of
substituting a simulated reading on a real camera frame.
"""

from __future__ import annotations

import os
import re
import statistics
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app.config import settings
from app.core.consensus import detect_coverage
from app.core.plate import (
    assess_plate,
    is_empty_scene_ocr,
    normalize_plate,
    plate_shape_score,
)
from app.services.camera_lpr import camera_contract

_lock = threading.Lock()
_engine = None


@dataclass
class PlateHit:
    plate_raw: str
    plate_normalized: str
    plate_confidence: float
    plate_crop_path: str | None = None
    bbox: dict | None = None
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def as_dict(self) -> dict:
        crop = self.plate_crop_path
        return {
            "plate": self.plate_normalized or self.plate_raw,
            "plate_raw": self.plate_raw,
            "plate_normalized": self.plate_normalized,
            "confidence": self.plate_confidence,
            "plate_crop_path": crop,
            "crop_url": f"/media/{crop}" if crop else None,
            "bbox": self.bbox,
            "event_id": self.event_id,
        }


def bbox_dict(bbox) -> dict | None:
    if bbox is None:
        return None
    try:
        return {
            "x1": int(getattr(bbox, "x1")),
            "y1": int(getattr(bbox, "y1")),
            "x2": int(getattr(bbox, "x2")),
            "y2": int(getattr(bbox, "y2")),
        }
    except Exception:
        return None


def annotate_image(image_path: str, hits: list[PlateHit], dest_name: str | None = None) -> str | None:
    boxes = [hit for hit in hits if hit.bbox]
    if not boxes:
        return None
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    try:
        img = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(img)
        for hit in boxes:
            box = hit.bbox or {}
            xy = [box["x1"], box["y1"], box["x2"], box["y2"]]
            draw.rectangle(xy, outline="#22c55e", width=max(3, img.width // 400))
            label = f"{hit.plate_normalized} {hit.plate_confidence:.0%}"
            tx, ty = xy[0], max(0, xy[1] - 22)
            draw.rectangle([tx, ty, tx + 8 * len(label), ty + 20], fill="#166534")
            draw.text((tx + 4, ty + 2), label, fill="#ffffff")
        folder = settings.media_dir / "annotated"
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / (dest_name or f"{uuid.uuid4().hex}.jpg")
        img.save(dest, quality=85)
        return str(dest.relative_to(settings.media_dir))
    except Exception:
        return None


DETECTOR_MODEL = "yolo-v9-t-384-license-plate-end2end"
DETECTOR_ONNX = "yolo-v9-t-384-license-plates-end2end.onnx"
OCR_MODEL = "cct-xs-v2-global-model"
OCR_ONNX = "cct_xs_v2_global.onnx"
OCR_CONFIG = "cct_xs_v2_global_plate_config.yaml"


def bundled_alpr_dir() -> Path | None:
    """USB/install folder: SMARTPARK_HOME/models/fastalpr, else repo models/fastalpr."""
    candidates = []
    home = os.environ.get("SMARTPARK_HOME")
    if home:
        candidates.append(Path(home) / "models" / "fastalpr")
    extra = os.environ.get("SMARTPARK_ALPR_MODEL_DIR")
    if extra:
        candidates.append(Path(extra))
    candidates.append(Path(__file__).resolve().parents[2] / "models" / "fastalpr")
    for path in candidates:
        if (path / DETECTOR_ONNX).is_file() or (path / "detector" / DETECTOR_ONNX).is_file():
            return path
    return None


def _copy_if_needed(src: Path, dest: Path) -> bool:
    if not src.is_file():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size == src.stat().st_size and dest.stat().st_mtime >= src.stat().st_mtime:
        return True
    dest.write_bytes(src.read_bytes())
    return dest.is_file()


def ensure_alpr_model_cache() -> dict:
    """Copy bundled ONNX files into FastALPR's user cache so Windows has no internet download."""
    src = bundled_alpr_dir()
    detector_src = None
    ocr_src = None
    cfg_src = None
    if src is not None:
        detector_src = next((p for p in (src / DETECTOR_ONNX, src / "detector" / DETECTOR_ONNX) if p.is_file()), None)
        ocr_src = next((p for p in (src / OCR_ONNX, src / "ocr" / OCR_ONNX) if p.is_file()), None)
        cfg_src = next((p for p in (src / OCR_CONFIG, src / "ocr" / OCR_CONFIG) if p.is_file()), None)
    cache_home = Path.home() / ".cache"
    detector_dest = cache_home / "open-image-models" / DETECTOR_MODEL / DETECTOR_ONNX
    ocr_dest = cache_home / "fast-plate-ocr" / OCR_MODEL / OCR_ONNX
    cfg_dest = cache_home / "fast-plate-ocr" / OCR_MODEL / OCR_CONFIG
    ok_det = _copy_if_needed(detector_src, detector_dest) if detector_src else detector_dest.is_file()
    ok_ocr = _copy_if_needed(ocr_src, ocr_dest) if ocr_src else ocr_dest.is_file()
    ok_cfg = _copy_if_needed(cfg_src, cfg_dest) if cfg_src else cfg_dest.is_file()
    return {
        "bundled_dir": str(src) if src else None,
        "detector": ok_det,
        "ocr": ok_ocr and ok_cfg,
        "detector_path": str(detector_dest) if ok_det else None,
        "ocr_path": str(ocr_dest) if ok_ocr else None,
        "ocr_config_path": str(cfg_dest) if ok_cfg else None,
    }


def fastalpr_installed() -> bool:
    try:
        import fast_alpr  # noqa: F401

        return True
    except ImportError:
        return False


def status() -> dict:
    installed = fastalpr_installed()
    models = ensure_alpr_model_cache() if installed else {"bundled_dir": str(bundled_alpr_dir() or ""), "detector": False, "ocr": False}
    contract = camera_contract()
    return {
        "backend": "fastalpr" if installed else "none",
        "installed": installed,
        "loaded": _engine is not None,
        "available": installed,
        "models": models,
        "country": settings.alpr_country or None,
        "csf": settings.alpr_csf,
        "native_engine": "qy_Net_RegImageRecvEx",
        "local_engine": "fastalpr" if installed else "none",
        "camera": contract,
        "detect": detect_coverage(
            fps=float(getattr(settings, "detect_fps", 5.0) or 5.0),
            dwell_seconds=1.0,
            min_frames=2,
        ),
        "engine_id": "fastalpr",
        "detail": (
            "The camera snaps the JPEG. FastALPR detects the plate, crops it with padding, "
            "then reads only that crop. Country profile: "
            f"{_country_name() or 'neutral'}. "
            "Replace the ONNX pack to retrain, or register another PlateEngine to change libraries."
            if installed
            else "FastALPR is not installed in this copy. Install the fast-alpr package and the ONNX model pack."
        ),
    }


def _load_engine():
    global _engine
    with _lock:
        if _engine is None:
            from fast_alpr import ALPR

            models = ensure_alpr_model_cache()
            kwargs = {
                "detector_model": DETECTOR_MODEL,
                "detector_conf_thresh": float(getattr(settings, "alpr_detector_confidence", 0.26) or 0.26),
                "ocr_device": "cpu",
                "detector_providers": ["CPUExecutionProvider"],
                "ocr_providers": ["CPUExecutionProvider"],
            }
            if models.get("ocr_path") and models.get("ocr_config_path"):
                kwargs["ocr_model"] = None
                kwargs["ocr_model_path"] = models["ocr_path"]
                kwargs["ocr_config_path"] = models["ocr_config_path"]
            else:
                kwargs["ocr_model"] = OCR_MODEL
            _engine = ALPR(**kwargs)
        return _engine


def unload_engine() -> None:
    """Drop the loaded reader so the next frame picks up a new model pack."""
    global _engine
    with _lock:
        _engine = None


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
        return str(dest.relative_to(settings.media_dir))
    except Exception:
        return None


MIN_PLATE_CHARS = 5
MIN_PLATE_ASPECT = 1.35
MAX_PLATE_ASPECT = 8.0
MIN_PLATE_WIDTH_PX = 24
MIN_PLATE_HEIGHT_PX = 8


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
    except ImportError:
        return None
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    light, a, b = cv2.split(lab)
    # Compress specular glare (headlights) before CLAHE so the plate crop is not washed out.
    try:
        import numpy as np
        hi = float(np.percentile(light, 98))
        if hi > 220:
            light = cv2.convertScaleAbs(light, alpha=0.85, beta=0)
    except Exception:
        pass
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    light = clahe.apply(light)
    return cv2.cvtColor(cv2.merge((light, a, b)), cv2.COLOR_LAB2BGR)


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


def _prepare_ocr_crop(crop_bgr):
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
    boosted = _boost_contrast(crop_bgr)
    return boosted if boosted is not None else crop_bgr


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
        dest = folder / f"{uuid.uuid4().hex}.jpg"
        Image.fromarray(rgb).save(dest, quality=95)
        return str(dest.relative_to(settings.media_dir))
    except Exception:
        return None


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
    if (x2 - x1) < 0.4 or (y2 - y1) < 0.4:
        return None
    return x1, y1, x2, y2


def _roi_crop(bgr, detect_roi: str | None = None):
    """Crop to the recognition zone. Returns (view, x_off, y_off).

    ``detect_roi`` is a per-camera override (``x1,y1,x2,y2`` or ``off``).
    None uses the site-wide ``alpr_detect_roi`` setting. ``off`` is the full frame.
    Boxes found in the crop are shifted back by the returned offsets.
    """
    roi = parse_detect_roi(detect_roi) if detect_roi is not None else parse_detect_roi()
    if roi is None or bgr is None or getattr(bgr, "size", 0) == 0:
        return bgr, 0, 0
    height, width = bgr.shape[:2]
    left = max(0, min(width - 1, int(width * roi[0])))
    top = max(0, min(height - 1, int(height * roi[1])))
    right = max(left + 1, min(width, int(width * roi[2])))
    bottom = max(top + 1, min(height, int(height * roi[3])))
    if right - left < 32 or bottom - top < 32:
        return bgr, 0, 0
    return bgr[top:bottom, left:right], left, top


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


def _detection_score(detection) -> float:
    for name in ("confidence", "conf", "score"):
        value = getattr(detection, name, None)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 1.0


def _bbox_size(bbox) -> tuple[int, int]:
    try:
        width = int(getattr(bbox, "x2")) - int(getattr(bbox, "x1"))
        height = int(getattr(bbox, "y2")) - int(getattr(bbox, "y1"))
    except Exception:
        return 0, 0
    return width, height


def plate_box_ok(bbox, image_width: int, image_height: int) -> bool:
    """Reject sky/sign boxes that are not plate-shaped. ParkWatch uses a recognition zone."""
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
        ocr_input = _prepare_ocr_crop(crop)
        try:
            ocr = engine.ocr.predict(ocr_input)
        except Exception:
            continue
        text, conf = _ocr_result_text(ocr)
        plate, _rank = _apply_country_profile(text, conf)
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
                plate_crop_path=_save_crop_bgr(crop) if save_crops else None,
                bbox=box,
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


def recognize_plate_crop_bytes(jpeg: bytes, *, camera_label: str = "plate-crop") -> dict:
    """OCR a JPEG that is already a plate crop, skipping full-frame detection.

    Native ALPR cameras often provide a plate JPEG alongside the vehicle image.
    Re-reading that crop is the cheapest ParkWatch-style software verification:
    camera event -> plate crop -> FastPlateOCR. Generic cameras still use the
    detector-first path because they do not know the plate box.
    """
    started = time.monotonic()
    if not jpeg or not fastalpr_installed():
        return {"ok": False, "backend": "none", "plates": [], "detail": "plate crop unavailable"}
    try:
        bgr = decode_alpr_image(jpeg)
        engine = _load_engine()
        ocr_input = _prepare_ocr_crop(bgr)
        ocr = engine.ocr.predict(ocr_input)
        text, conf = _ocr_result_text(ocr)
        plate, _rank = _apply_country_profile(text, conf)
        raw_conf = max(0.0, min(float(conf or 0), 1.0))
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
            plate_crop_path=_save_crop_bgr(bgr),
            bbox=None,
        )
        return {
            "ok": True,
            "backend": "fastalpr",
            "pipeline": "crop_ocr",
            "plates": [hit.as_dict()],
            "count": 1,
            "best": hit.as_dict(),
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


def plate_still_present(jpeg: bytes, *, detect_roi: str | None = None) -> bool | None:
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
        view, dx, dy = _roi_crop(bgr, detect_roi)
        detections = _shift_detections(engine.detector.predict(view), dx, dy)
    except Exception:
        return None
    width, height = int(bgr.shape[1]), int(bgr.shape[0])
    for item in detections or []:
        bbox = getattr(item, "bounding_box", None)
        if bbox is not None and plate_box_ok(bbox, width, height):
            return True
    return False


def recognize_bgr(bgr, *, crop_source: str, save_crops: bool = False, detect_roi: str | None = None) -> tuple[list[PlateHit], dict]:
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
                view, dx, dy = _roi_crop(bgr, detect_roi)
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
        # ParkWatch filters 无车牌. A second full-frame CLAHE detect on empty
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
                    view, dx, dy = _roi_crop(boosted, detect_roi)
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
    hits, meta = recognize_bgr(bgr, crop_source="", save_crops=persist, detect_roi=detect_roi)
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
            image_rel = str(image.relative_to(settings.media_dir))
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
