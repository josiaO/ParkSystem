"""Per-camera detection zone and digital zoom.

Works for the site's HVX/OcxConfig cameras and for any other adapter
(RTSP, ONVIF, Hikvision, Dahua). The zone says where the car should be.
Zoom tightens the search on the center of that zone. Recognition watches
the zone with the detector, and OCRs only after the plate holds still.
"""

from __future__ import annotations

import math

FRAMING_KEY = "FRAMING"
MIN_ZOOM = 1.0
MAX_ZOOM = 4.0

_gates: dict[int, "ArrivalGate"] = {}


def parse_detect_zoom(value) -> float:
    if value in (None, ""):
        return MIN_ZOOM
    try:
        zoom = float(value)
    except (TypeError, ValueError):
        return MIN_ZOOM
    if not math.isfinite(zoom):
        return MIN_ZOOM
    if zoom < MIN_ZOOM:
        return MIN_ZOOM
    if zoom > MAX_ZOOM:
        return MAX_ZOOM
    return zoom


def framing_from_profiles(profiles: dict | None) -> dict:
    profiles = profiles or {}
    row = profiles.get(FRAMING_KEY) or profiles.get("framing") or {}
    if not isinstance(row, dict):
        row = {}
    roi = row.get("detect_roi")
    if not isinstance(roi, str) or not roi.strip():
        legacy = profiles.get("detect_roi") or profiles.get("alpr_detect_roi") or ""
        roi = legacy if isinstance(legacy, str) else ""
    # An empty FRAMING value means "use the site default", not "search the
    # whole picture". Keep the effective zone consistent in the API/UI,
    # worker, and legacy recognition paths.
    if not str(roi or "").strip():
        from app.config import settings

        roi = str(getattr(settings, "alpr_detect_roi", "off") or "off").strip()
    zoom_raw = row.get("detect_zoom")
    if zoom_raw in (None, ""):
        zoom_raw = profiles.get("detect_zoom")
    return {"detect_roi": str(roi or "").strip(), "detect_zoom": parse_detect_zoom(zoom_raw)}


def apply_framing(profiles: dict | None, *, detect_roi: str, detect_zoom: float) -> dict:
    from app.services.alpr import parse_detect_roi

    raw = str(detect_roi or "").strip()
    if raw.lower() in {"off", "none", "full"}:
        stored = "off"
    elif raw.lower() in {"", "site"}:
        stored = ""
    else:
        parsed = parse_detect_roi(raw)
        if parsed is None:
            raise ValueError(
                "Detection zone must be x1,y1,x2,y2 between 0 and 1, "
                "and at least 8% of the picture wide and tall."
            )
        stored = ",".join(f"{part:.4f}" for part in parsed)
    out = dict(profiles or {})
    out[FRAMING_KEY] = {
        "detect_roi": stored,
        "detect_zoom": round(parse_detect_zoom(detect_zoom), 3),
    }
    return out


def native_plate_region_to_roi(
    region: list | tuple | None,
    *,
    image_width: int = 0,
    image_height: int = 0,
    padding: float = 0.08,
) -> str:
    """Convert OcxConfig's camera polygon into FastALPR's normalized ROI.

    OcxConfig/ParkWatch stores the plate detection zone as four pixel points.
    FastALPR accepts a normalized rectangle.  The conversion is deliberately
    read-only and conservative: an invalid or missing native zone returns an
    empty string, allowing the configured/site-wide ROI to remain in control.
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
    """Return whether a detector box's center is inside the admission zone."""
    if not isinstance(box, dict):
        return False
    from app.services.alpr import parse_detect_roi

    roi = parse_detect_roi(detect_roi) if detect_roi is not None else parse_detect_roi()
    if roi is None:  # explicit "off" / full-frame mode
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


def best_arrival_box(boxes: list[dict] | None, detect_roi: str | None = None) -> dict | None:
    """Choose the closest credible plate for the lane gate.

    Detector confidence order can change between frames when a second car or
    a reflection is present. Area-first selection keeps the gate attached to
    the nearest plate, which is also the plate with the most readable pixels.
    """
    candidates = [
        item for item in (boxes or [])
        if isinstance(item, dict) and box_in_detection_zone(item, detect_roi)
    ]
    if not candidates:
        return None

    def key(item: dict) -> tuple[float, float]:
        try:
            area = max(0.0, float(item.get("x2", 0)) - float(item.get("x1", 0))) * max(
                0.0, float(item.get("y2", 0)) - float(item.get("y1", 0))
            )
            confidence = float(item.get("confidence") or 0.0)
        except (TypeError, ValueError):
            return 0.0, 0.0
        return area, confidence

    return max(candidates, key=key)


def gate_for(camera_id: int) -> "ArrivalGate":
    camera_id = int(camera_id)
    gate = _gates.get(camera_id)
    if gate is None:
        from app.config import settings

        gate = ArrivalGate(
            min_plate_width_px=int(getattr(settings, "alpr_min_capture_plate_width_px", 64) or 0),
            far_fallback_seconds=float(getattr(settings, "alpr_capture_far_fallback_seconds", 1.5) or 0),
        )
        _gates[camera_id] = gate
    return gate


class ArrivalGate:
    """Detector watches the zone. OCR runs once the plate box holds still.

    A moving plate returns ``moving`` and must not be read. ``ready`` is
    raised once per settle. ``held`` means this visit was already read, so
    the same stopped car cannot open another session. An empty zone for
    ``absence_seconds`` starts the next visit.
    """

    def __init__(
        self,
        *,
        stable_seconds: float = 0.25,
        move_ratio: float = 0.05,
        absence_seconds: float = 0.6,
        max_ocr: int = 2,
        min_plate_width_px: int = 0,
        far_fallback_seconds: float = 0.0,
    ) -> None:
        self.stable_seconds = float(stable_seconds)
        self.move_ratio = float(move_ratio)
        self.absence_seconds = float(absence_seconds)
        self.max_ocr = int(max_ocr)
        self.min_plate_width_px = max(0, int(min_plate_width_px or 0))
        self.far_fallback_seconds = max(0.0, float(far_fallback_seconds or 0.0))
        self.reset()

    def reset(self) -> None:
        self._last: tuple[float, ...] | None = None
        self._seen_since: float | None = None
        self._stable_since: float | None = None
        self._absent_since: float | None = None
        self._announced = False
        self._held = False
        self._ocr_count = 0
        self._retry_at = None
        self.prepared = None

    def observe(self, box: dict | None, now: float) -> str:
        now = float(now)
        if self._held:
            if box is None:
                if self._absent_since is None or now < self._absent_since:
                    self._absent_since = now
                if now - self._absent_since >= self.absence_seconds:
                    self.reset()
                    return "absent"
                return "held"
            self._absent_since = None
            return "held"
        if not box:
            # Detector output is not guaranteed on every decoded frame.  A
            # single night-time glare/compression miss must not erase the
            # arrival state, otherwise the next box starts a fresh settle
            # window and a stopped car can remain permanently unread.  Keep
            # the last valid box only for the same short absence window used
            # for departure detection; a genuinely empty lane still resets.
            if self._last is not None:
                if self._absent_since is None or now < self._absent_since:
                    self._absent_since = now
                if now - self._absent_since < self.absence_seconds:
                    return "missing"
            self._last = None
            self._seen_since = None
            self._stable_since = None
            self._absent_since = None
            self._announced = False
            return "absent"
        if self._retry_at is not None:
            if now < self._retry_at:
                return "cooldown"
            self._retry_at = None
            self._ocr_count = 0
            self._announced = False
            self._stable_since = None
        self._observed_at = now
        center = _box_center(box)
        if center is None:
            if self._last is not None:
                if self._absent_since is None or now < self._absent_since:
                    self._absent_since = now
                if now - self._absent_since < self.absence_seconds:
                    return "missing"
            self._last = None
            self._seen_since = None
            self._stable_since = None
            self._absent_since = None
            self._announced = False
            return "absent"
        self._absent_since = None
        if self._seen_since is None:
            self._seen_since = now
        moved = self._last is None or _moved(self._last, center, self.move_ratio)
        if moved:
            had_previous = self._last is not None
            self._last = center
            self._stable_since = now
            self._announced = False
            # A moving box is detector-only. OCR admission requires the plate
            # to hold still inside the zone, preventing a distant or passing
            # car from being read before it reaches the stop point.
            return "moving"
        if self._stable_since is None:
            self._stable_since = now
            self._announced = False
            return "moving"
        if now - self._stable_since < self.stable_seconds:
            return "moving"
        # Plate pixel width is a useful distance proxy. Upscaling cannot
        # recover characters that were not sampled by the camera. A far plate
        # remains detector-only until it reaches the readable part of the zone.
        if self.min_plate_width_px > 0:
            try:
                plate_width = float(box["x2"]) - float(box["x1"])
            except (KeyError, TypeError, ValueError):
                plate_width = 0.0
            if plate_width < self.min_plate_width_px:
                return "far"
        if self._announced:
            return "moving"
        if self._ocr_count >= self.max_ocr:
            self._held = True
            return "held"
        self._announced = True
        return "ready"

    def _near_enough(self, box: dict) -> bool:
        if self.min_plate_width_px <= 0:
            return False
        try:
            return float(box["x2"]) - float(box["x1"]) >= self.min_plate_width_px
        except (KeyError, TypeError, ValueError):
            return False

    def note_ocr(self, *, published: bool) -> None:
        self._ocr_count += 1
        if published:
            self._held = True
            self._absent_since = None
            return
        if self._ocr_count >= self.max_ocr:
            self._retry_at = getattr(self, "_observed_at", 0) + 1.0
        self._announced = False

    def rearm(self) -> None:
        """The ready frame was not read. Allow the next check to try again."""
        if not self._held:
            self._announced = False


def _box_center(box: dict) -> tuple[float, ...] | None:
    try:
        width = float(box.get("image_width") or 0)
        height = float(box.get("image_height") or 0)
        x1, y1 = float(box["x1"]), float(box["y1"])
        x2, y2 = float(box["x2"]), float(box["y2"])
    except (TypeError, ValueError, KeyError):
        return None
    if width <= 0 or height <= 0 or x2 <= x1 or y2 <= y1:
        return None
    return ((x1 + x2) / 2.0) / width, ((y1 + y2) / 2.0) / height, (x2-x1)/width, (y2-y1)/height


def _moved(previous: tuple[float, float], current: tuple[float, float], ratio: float) -> bool:
    return any(abs(a-b) > ratio for a,b in zip(previous, current))
