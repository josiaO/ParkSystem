"""Local FastALPR boundary.

A plate event is the only thing the rest of SmartPark should see. This module
never invents plates: if FastALPR is missing, it reports that instead of
substituting a simulated reading on a real camera frame.
"""

from __future__ import annotations

import os
import statistics
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app.config import settings
from app.core.plate import normalize_plate
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
    if dest.is_file() and dest.stat().st_size == src.stat().st_size:
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
        "detail": (
            "FastALPR is the vendor-independent local OCR. HVX cameras may also send a native plate; "
            "when they do not (or you change camera brand), FastALPR reads the JPEG automatically on a coil/presence trigger."
            if installed
            else "Local FastALPR is not installed in this copy. Native camera plates still work if the adapter provides them."
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
                "detector_conf_thresh": 0.25,
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


MIN_PLATE_CHARS = 4


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
    if min_side < 720:
        scale = 720 / float(min_side)
        img = img.resize((max(1, int(width * scale)), max(1, int(height * scale))), Image.Resampling.LANCZOS)
        width, height = img.size
        max_side = max(width, height)
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
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    light = clahe.apply(light)
    return cv2.cvtColor(cv2.merge((light, a, b)), cv2.COLOR_LAB2BGR)


def _hits_from_predict(rows, crop_source: str) -> list[PlateHit]:
    hits: list[PlateHit] = []
    for row in rows or []:
        ocr = getattr(row, "ocr", None)
        text = clean_ocr_text(getattr(ocr, "text", None) or getattr(row, "text", None))
        plate = normalize_plate(text)
        if len(plate) < MIN_PLATE_CHARS:
            continue
        conf = getattr(ocr, "confidence", None)
        if conf is None:
            conf = getattr(row, "confidence", None)
        if isinstance(conf, (list, tuple)):
            conf = float(statistics.mean(conf)) if conf else 0.0
        det = getattr(row, "detection", None)
        bbox = getattr(det, "bounding_box", None) if det is not None else None
        hits.append(
            PlateHit(
                plate_raw=text,
                plate_normalized=plate,
                plate_confidence=float(conf or 0),
                plate_crop_path=_crop_path(crop_source, bbox),
                bbox=bbox_dict(bbox),
            )
        )
    return hits


def recognize_bgr(bgr, *, crop_source: str) -> tuple[list[PlateHit], dict]:
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
        variants = [bgr]
        boosted = _boost_contrast(bgr)
        if boosted is not None:
            variants.append(boosted)
        for variant in variants:
            try:
                hits = _hits_from_predict(engine.predict(variant), crop_source)
            except Exception as exc:
                last_error = str(exc)
                continue
            if hits:
                return hits, {
                    "backend": "fastalpr",
                    "ok": True,
                    "latency_ms": round((time.monotonic() - started) * 1000, 2),
                    "count": len(hits),
                }
        return [], {
            "backend": "fastalpr",
            "ok": True,
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


def recognize_bytes(jpeg: bytes, *, camera_label: str = "frame") -> dict:
    """Run FastALPR on a camera frame or simulation upload. Never invents plates."""
    if not jpeg:
        return {"ok": False, "backend": "none", "plates": [], "detail": "empty frame"}
    if not fastalpr_installed():
        return {
            "ok": False,
            "backend": "none",
            "plates": [],
            "detail": "FastALPR is not installed — not substituting simulated plates",
        }
    folder = settings.media_dir / "alpr"
    folder.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in camera_label)[:80] or "frame"
    image = folder / f"{safe}-{uuid.uuid4().hex}.jpg"
    try:
        bgr = decode_alpr_image(jpeg)
        from PIL import Image
        Image.fromarray(bgr[:, :, ::-1]).save(image, quality=92)
    except Exception:
        image.write_bytes(jpeg)
        try:
            bgr = decode_alpr_image(image.read_bytes())
        except Exception:
            return {
                "ok": False,
                "backend": "fastalpr",
                "plates": [],
                "detail": "could not decode that photo",
            }
    hits, meta = recognize_bgr(bgr, crop_source=str(image))
    plates = [hit.as_dict() for hit in hits]
    best = max(hits, key=lambda h: h.plate_confidence) if hits else None
    annotated = annotate_image(str(image), hits, dest_name=f"{safe}.jpg")
    return {
        "ok": bool(hits) or bool(meta.get("ok")),
        "backend": meta.get("backend"),
        "plates": plates,
        "count": len(plates),
        "best": best.as_dict() if best else None,
        "latency_ms": meta.get("latency_ms"),
        "detail": meta.get("error") or (f"{len(plates)} plate(s)" if plates else "no plate in frame"),
        "image_path": str(image.relative_to(settings.media_dir)),
        "image_url": f"/media/{image.relative_to(settings.media_dir)}",
        "annotated_path": annotated,
        "annotated_url": f"/media/{annotated}" if annotated else None,
    }
