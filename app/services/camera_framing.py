"""Per-camera recognition decode width, and the camera's own plate region.

The old ZIRP detection zone, detection zoom and site-wide capture distance
(plate width) were removed: they cropped the picture before the detector and
used one capture distance for every camera, which did not work across
cameras mounted at different heights, angles and focal lengths. Per-camera
capture conditions now live in ``app.services.capture_calibration``.

``framing_from_profiles`` keeps its shape for callers, but always reports the
whole picture (``detect_roi='off'``, zoom 1). Stored zone values are ignored
here and cleared by migration ``0020_clear_legacy_capture_zones``.
"""

from __future__ import annotations

import math

FRAMING_KEY = "FRAMING"
MIN_ZOOM = 1.0
MAX_ZOOM = 4.0

# Width the recognition worker decodes the DETECT stream to. The display
# stream is never affected. 960 is the measured default; wider costs CPU.
DETECT_WIDTHS = (960, 1280, 1600, 1920)


def parse_detect_zoom(value) -> float:
    """Kept for the detector's argument parsing; zoom is no longer configurable."""
    if value in (None, ""):
        return MIN_ZOOM
    try:
        zoom = float(value)
    except (TypeError, ValueError):
        return MIN_ZOOM
    if not math.isfinite(zoom):
        return MIN_ZOOM
    return max(MIN_ZOOM, min(MAX_ZOOM, zoom))


def parse_detect_width(value) -> int:
    from app.config import settings

    default = int(getattr(settings, "recognition_detect_width", 960) or 960)
    try:
        width = int(value)
    except (TypeError, ValueError):
        return default
    return width if width in DETECT_WIDTHS else default


def apply_detect_width(profiles: dict | None, detect_width: int) -> dict:
    """Store the recognition decode width; the only per-camera value left here."""
    if int(detect_width) not in DETECT_WIDTHS:
        raise ValueError(f"Recognition decode width must be one of {', '.join(map(str, DETECT_WIDTHS))} pixels.")
    out = dict(profiles or {})
    out[FRAMING_KEY] = {"detect_width": int(detect_width)}
    return out


def framing_from_profiles(profiles: dict | None) -> dict:
    profiles = profiles or {}
    row = profiles.get(FRAMING_KEY) or {}
    if not isinstance(row, dict):
        row = {}
    return {
        "detect_roi": "off",
        "detect_zoom": MIN_ZOOM,
        "detect_width": parse_detect_width(row.get("detect_width")),
    }


def native_plate_region_to_roi(
    region: list | tuple | None,
    *,
    image_width: int = 0,
    image_height: int = 0,
    padding: float = 0.08,
) -> str:
    """Convert OcxConfig's camera polygon into FastALPR's normalized ROI.

    This is the camera's own (vendor-side) plate region, read-only. It is not
    a ZIRP setting.
    """
    try:
        width = int(image_width or 0)
        height = int(image_height or 0)
    except (TypeError, ValueError):
        return ""
    if width < 32 or height < 32 or not isinstance(region, (list, tuple)):
        return ""
    points: list[tuple[float, float]] = []
    for point in region:
        if not isinstance(point, dict):
            continue
        try:
            x = float(point.get("x"))
            y = float(point.get("y"))
        except (TypeError, ValueError):
            continue
        if math.isfinite(x) and math.isfinite(y):
            points.append((x, y))
    if len(points) < 3:
        return ""
    x1 = max(0.0, min(x for x, _ in points) / width - float(padding))
    y1 = max(0.0, min(y for _, y in points) / height - float(padding))
    x2 = min(1.0, max(x for x, _ in points) / width + float(padding))
    y2 = min(1.0, max(y for _, y in points) / height + float(padding))
    if x2 - x1 < 0.08 or y2 - y1 < 0.08:
        return ""
    return ",".join(f"{value:.4f}" for value in (x1, y1, x2, y2))


def box_in_detection_zone(box: dict | None, detect_roi: str | None = None) -> bool:
    """Whether a detector box's centre is inside an explicit ROI string.

    Used only for the camera's own native region or an explicit per-call ROI;
    ``None``/``off`` means the whole picture.
    """
    if not isinstance(box, dict):
        return False
    from app.services.alpr import parse_detect_roi

    if detect_roi is None or str(detect_roi).strip().lower() in {"", "off", "none", "full"}:
        return True
    roi = parse_detect_roi(detect_roi)
    if roi is None:
        return True
    try:
        width = float(box.get("image_width") or 0)
        height = float(box.get("image_height") or 0)
        x1, y1 = float(box["x1"]), float(box["y1"])
        x2, y2 = float(box["x2"]), float(box["y2"])
    except (KeyError, TypeError, ValueError):
        return False
    if width <= 0 or height <= 0 or x2 <= x1 or y2 <= y1:
        return False
    cx = ((x1 + x2) / 2.0) / width
    cy = ((y1 + y2) / 2.0) / height
    return roi[0] <= cx <= roi[2] and roi[1] <= cy <= roi[3]
