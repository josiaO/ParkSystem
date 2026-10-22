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


def gate_for(camera_id: int) -> "ArrivalGate":
    camera_id = int(camera_id)
    gate = _gates.get(camera_id)
    if gate is None:
        gate = ArrivalGate()
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
        stable_seconds: float = 0.35,
        move_ratio: float = 0.025,
        absence_seconds: float = 0.6,
        max_ocr: int = 2,
    ) -> None:
        self.stable_seconds = float(stable_seconds)
        self.move_ratio = float(move_ratio)
        self.absence_seconds = float(absence_seconds)
        self.max_ocr = int(max_ocr)
        self.reset()

    def reset(self) -> None:
        self._last: tuple[float, ...] | None = None
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
            self._last = None
            self._stable_since = None
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
            return "absent"
        if self._last is None or _moved(self._last, center, self.move_ratio):
            self._last = center
            self._stable_since = now
            self._announced = False
            return "moving"
        if self._stable_since is None:
            self._stable_since = now
            self._announced = False
            return "moving"
        if now - self._stable_since < self.stable_seconds:
            return "moving"
        if self._announced:
            return "moving"
        if self._ocr_count >= self.max_ocr:
            self._held = True
            return "held"
        self._announced = True
        return "ready"

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
