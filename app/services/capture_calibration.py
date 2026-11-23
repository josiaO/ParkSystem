"""Per-camera capture-zone and plate-size calibration.

A camera may detect a plate from far away; the final snapshot and OCR happen
only when the plate is *eligible*:

* its centre is inside the camera's capture zone (polygon, normalised 0..1),
* it is past the camera's trigger line (when one is set),
* the plate box is at least the camera's minimum width / height in pixels,
* the detector confidence meets the camera's minimum,
* the plate crop passes basic sharpness and exposure checks,
* and this passage has not already produced a completed event.

Eligible frames are collected for a short window and the best one (plate
size, sharpness, exposure, detector confidence) is handed to the existing
crop + OCR step. Nothing here decodes video or runs a recognition model: it
judges the detector's boxes on frames the existing pipeline already has.

Every camera has its own record (``site_settings`` key
``capture_calibration:{camera_id}``) carrying camera, site, gate, lane and
direction, the geometry, thresholds and a configuration version. A camera
without a record is *uncalibrated*: whole picture, no size or quality gate,
best-frame selection still on. No values are shared between cameras.

Plate pixel sizes are a relative distance cue only; they are not metres.
"""

from __future__ import annotations

import io
import math
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

KEY_PREFIX = "capture_calibration:"
TEST_PREFIX = "capture_calibration_test:"
TEST_MODE_MAX_MINUTES = 240

DEFAULTS: dict[str, Any] = {
    "enabled": False,                 # False = uncalibrated: whole picture, no size/quality gate
    "zone": [],                       # [[x, y], ...] normalised; empty = whole picture
    "trigger_line": None,             # start line: {"y": 0..1, "side": "below"|"above"} or None
    "end_line": None,                 # end line: reading stops once the plate is past it
    "min_plate_width_px": 0,
    "min_plate_height_px": 0,
    "min_detection_confidence": 0.0,
    "min_ocr_confidence": 0.0,        # a read below this is not accepted as the passage's plate
    "min_sharpness": 0.0,             # variance of the Laplacian on the plate crop
    "min_brightness": 0.0,            # mean grey level of the plate crop (0-255)
    "max_brightness": 255.0,
    "max_clipped_fraction": 1.0,      # share of crop pixels burnt white or crushed black
    "candidate_frames": 3,            # best of up to N eligible frames ...
    "candidate_seconds": 0.8,         # ... or what arrived within this window
    "reference_width": 0,             # width of the picture the sizes were set on (0 = any)
}

# Each rule can refuse a read (on) or only help choose the best picture (off).
# A rule that is off still shows on screen and still ranks frames, but a car
# is never left unstored because of it.
RULES: dict[str, str] = {
    "zone": "Capture zone",
    "start_line": "Start line",
    "end_line": "End line",
    "plate_size": "Minimum plate size",
    "detector": "Detector confidence",
    "picture_quality": "Sharpness, brightness and glare",
    "recognition": "Recognition confidence",
}
DEFAULT_ENFORCE: dict[str, bool] = {
    "zone": True,
    "start_line": False,
    "end_line": False,
    "plate_size": True,
    "detector": True,
    "picture_quality": True,
    "recognition": True,
}
DEFAULTS["enforce"] = dict(DEFAULT_ENFORCE)


def enforce_of(config: dict[str, Any]) -> dict[str, bool]:
    """Which rules refuse a read for this configuration (missing = default)."""
    stored = config.get("enforce") if isinstance(config.get("enforce"), dict) else {}
    return {name: bool(stored.get(name, default)) for name, default in DEFAULT_ENFORCE.items()}


def enforced(config: dict[str, Any], rule: str) -> bool:
    return enforce_of(config).get(rule, True)

LIMITS = {
    "min_plate_width_px": (0, 1000),
    "min_plate_height_px": (0, 600),
    "min_detection_confidence": (0.0, 1.0),
    "min_ocr_confidence": (0.0, 1.0),
    "min_sharpness": (0.0, 5000.0),
    "min_brightness": (0.0, 255.0),
    "max_brightness": (0.0, 255.0),
    "max_clipped_fraction": (0.0, 1.0),
    "candidate_frames": (1, 10),
    "candidate_seconds": (0.1, 5.0),
    "reference_width": (0, 8000),
}

# Values beyond these would refuse most or all cars (night headlights make
# plates bright; a 0-255 "brightness to" of 2 refused every car on 2# Entry).
# Saving them is refused; such values already saved are ignored and reported.
SAFE = {
    "max_brightness": (150.0, 255.0, "Brightness to must be at least 150 (0-255); lower refuses plates lit by headlights."),
    "min_brightness": (0.0, 100.0, "Brightness from must be 100 or less (0-255); higher refuses plates at night."),
    "max_clipped_fraction": (0.2, 1.0, "Most glare/black allowed must be at least 0.20; lower refuses ordinary plates."),
    "min_detection_confidence": (0.0, 0.9, "Minimum detector confidence must be 0.90 or less; higher refuses most plates."),
    "min_ocr_confidence": (0.0, 0.9, "Minimum recognition confidence must be 0.90 or less; higher refuses most reads."),
    "min_plate_height_px": (0, 40, "Minimum plate height must be 40 px or less on the live picture; plates are rarely taller."),
    "min_plate_width_px": (0, 160, "Minimum plate width must be 160 px or less on the live picture; plates are rarely wider."),
}
MIN_BAND = 0.08   # start and end line at least 8% of the picture apart


# --------------------------------------------------------------- storage --

def _key(camera_id: int) -> str:
    return f"{KEY_PREFIX}{int(camera_id)}"


def identity(camera) -> dict[str, Any]:
    from app.domain.site import DEFAULT_SITE_ID

    return {
        "camera_id": int(camera.id),
        "camera_name": str(getattr(camera, "name", "") or ""),
        "site_id": getattr(camera, "site_id", None) or DEFAULT_SITE_ID,
        "gate_id": getattr(camera, "gate_id", None),
        "lane_id": getattr(camera, "lane_id", None),
        "direction": str(getattr(camera, "lane_direction", "") or "ENTRY").upper(),
    }


def validate(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a clean calibration from operator input, or raise ValueError."""
    out = dict(DEFAULTS)
    data = payload or {}
    out["enabled"] = bool(data.get("enabled", False))
    zone = data.get("zone") or []
    if not isinstance(zone, list):
        raise ValueError("Capture zone must be a list of points.")
    points: list[list[float]] = []
    for point in zone:
        try:
            x, y = float(point[0]), float(point[1])
        except (TypeError, ValueError, IndexError, KeyError):
            raise ValueError("Each capture-zone point needs x and y.") from None
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0) or not (math.isfinite(x) and math.isfinite(y)):
            raise ValueError("Capture-zone points must be inside the picture (0 to 1).")
        points.append([round(x, 4), round(y, 4)])
    if points and len(points) < 3:
        raise ValueError("A capture zone needs at least 3 corners.")
    if len(points) > 16:
        raise ValueError("A capture zone can have at most 16 corners.")
    if points and polygon_area(points) < 0.01:
        raise ValueError("The capture zone is too small (under 1% of the picture).")
    out["zone"] = points
    line = data.get("trigger_line")
    if line not in (None, "", {}):
        try:
            y = float(line.get("y"))
        except (AttributeError, TypeError, ValueError):
            raise ValueError("Trigger line needs a y position between 0 and 1.") from None
        side = str(line.get("side") or "below").lower()
        if not 0.0 <= y <= 1.0 or side not in {"below", "above"}:
            raise ValueError("Trigger line y must be 0-1 and side 'below' or 'above'.")
        out["trigger_line"] = {"y": round(y, 4), "side": side}
    end = data.get("end_line")
    if end not in (None, "", {}):
        try:
            end_y = float(end.get("y"))
        except (AttributeError, TypeError, ValueError):
            raise ValueError("End line needs a y position between 0 and 1.") from None
        if not 0.0 <= end_y <= 1.0:
            raise ValueError("End line y must be between 0 and 1.")
        start = out.get("trigger_line")
        if start:
            # The plate travels from the start line towards the end line.
            if start["side"] == "below" and end_y <= start["y"]:
                raise ValueError("The end line must be below the start (trigger) line.")
            if start["side"] == "above" and end_y >= start["y"]:
                raise ValueError("The end line must be above the start (trigger) line.")
        out["end_line"] = {"y": round(end_y, 4)}
    for name, (low, high) in LIMITS.items():
        if name not in data or data[name] in (None, ""):
            continue
        try:
            value = float(data[name])
        except (TypeError, ValueError):
            raise ValueError(f"{name.replace('_', ' ')} must be a number.") from None
        if not low <= value <= high:
            raise ValueError(f"{name.replace('_', ' ')} must be between {low:g} and {high:g}.")
        out[name] = int(value) if isinstance(DEFAULTS[name], int) and not isinstance(DEFAULTS[name], bool) else value
    if out["min_brightness"] > out["max_brightness"]:
        raise ValueError("Minimum brightness cannot be above maximum brightness.")
    rules = data.get("enforce")
    if rules not in (None, ""):
        if not isinstance(rules, dict) or any(name not in RULES for name in rules):
            raise ValueError("Rules must be a list of on/off switches: " + ", ".join(RULES) + ".")
    out["enforce"] = enforce_of({"enforce": rules or {}})
    for name, (low, high, message) in SAFE.items():
        if not low <= float(out[name]) <= high:
            raise ValueError(message)
    if out.get("trigger_line") and out.get("end_line"):
        if abs(float(out["end_line"]["y"]) - float(out["trigger_line"]["y"])) < MIN_BAND:
            raise ValueError("Leave at least 8% of the picture between the start and end lines, "
                             "or cars will pass between two snapshots without being read.")
    return out


def load(db, camera) -> dict[str, Any]:
    """The camera's calibration, merged over defaults, with identity fields."""
    from app.models import SiteSetting

    row = db.get(SiteSetting, _key(camera.id))
    stored = row.value if row is not None and isinstance(row.value, dict) else {}
    config = dict(DEFAULTS)
    for name in DEFAULTS:
        if name in stored:
            config[name] = stored[name]
    config["version"] = int(stored.get("version") or 0)
    config["updated_at"] = stored.get("updated_at") or None
    config["updated_by"] = stored.get("updated_by") or None
    config["calibrated"] = bool(stored) and bool(config["enabled"])
    # A saved value that would refuse every car (from before these limits)
    # is not applied; the calibration window and Live Gates say so.
    ignored = []
    for name, (low, high, message) in SAFE.items():
        try:
            value = float(config.get(name))
        except (TypeError, ValueError):
            continue
        if not low <= value <= high:
            config[name] = DEFAULTS[name]
            ignored.append(message)
    config["ignored"] = ignored
    config["enforce"] = enforce_of(config)
    config.update(identity(camera))
    return config


def save(db, camera, payload: dict[str, Any], *, user: str = "") -> dict[str, Any]:
    from app.models import SiteSetting

    clean = validate(payload)
    row = db.get(SiteSetting, _key(camera.id))
    previous = row.value if row is not None and isinstance(row.value, dict) else {}
    expected = payload.get("version")
    if expected not in (None, "") and int(expected) != int(previous.get("version") or 0):
        raise ConflictError("This camera's calibration was changed by someone else. Reload and try again.")
    record = {
        **clean,
        **identity(camera),
        "version": int(previous.get("version") or 0) + 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": str(user or ""),
    }
    if row is None:
        db.add(SiteSetting(key=_key(camera.id), value=record))
    else:
        row.value = record
    db.commit()
    invalidate(camera.id)
    return load(db, camera)


def remove(db, camera_id: int) -> None:
    from app.models import SiteSetting

    row = db.get(SiteSetting, _key(camera_id))
    if row is not None:
        db.delete(row)
        db.commit()
    invalidate(camera_id)


class ConflictError(ValueError):
    pass


# Short cache so the frame loop does not query the database for every frame,
# while a saved change (here or from another process) applies within seconds.
_cache: dict[int, tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()
CACHE_SECONDS = 3.0


def invalidate(camera_id: int | None = None) -> None:
    with _cache_lock:
        if camera_id is None:
            _cache.clear()
        else:
            _cache.pop(int(camera_id), None)
            _test_cache.pop(int(camera_id), None)


def for_camera(camera_id: int, camera=None) -> dict[str, Any]:
    """Cached calibration for the recognition loop."""
    camera_id = int(camera_id)
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(camera_id)
        if hit and (hit[0] == float("inf") or now - hit[0] < CACHE_SECONDS):
            return hit[1]
    try:
        from app.db import short_session
        from app.models import Camera

        with short_session() as db:
            row = camera if camera is not None else db.get(Camera, camera_id)
            if row is None:
                config = {**DEFAULTS, "version": 0, "calibrated": False, "camera_id": camera_id}
            else:
                config = load(db, row)
    except Exception:
        config = hit[1] if hit else {**DEFAULTS, "version": 0, "calibrated": False, "camera_id": camera_id}
    with _cache_lock:
        _cache[camera_id] = (now, config)
    return config


def override(camera_id: int, config: dict[str, Any] | None) -> None:
    """Pin a calibration in this process without the database (replay tools, tests).

    ``None`` removes the pin.
    """
    with _cache_lock:
        if config is None:
            _cache.pop(int(camera_id), None)
        else:
            _cache[int(camera_id)] = (float("inf"), {**DEFAULTS, **config, "camera_id": int(camera_id)})


# -------------------------------------------------------------- test mode --

_test_cache: dict[int, tuple[float, bool]] = {}


def set_test_mode(db, camera_id: int, *, enabled: bool, minutes: float = 30) -> dict[str, Any]:
    """Calibration test mode: reads are shown, never stored; no session, no barrier.

    It switches itself off after ``minutes`` so a forgotten test cannot leave
    a lane without parking sessions.
    """
    from app.models import SiteSetting

    key = f"{TEST_PREFIX}{int(camera_id)}"
    row = db.get(SiteSetting, key)
    if enabled:
        minutes = max(1.0, min(float(minutes or 30), float(TEST_MODE_MAX_MINUTES)))
        until = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()
        if row is None:
            db.add(SiteSetting(key=key, value={"until": until}))
        else:
            row.value = {"until": until}
    elif row is not None:
        db.delete(row)
    db.commit()
    invalidate(camera_id)
    return test_mode_status(db, camera_id)


def test_mode_status(db, camera_id: int) -> dict[str, Any]:
    from app.models import SiteSetting

    row = db.get(SiteSetting, f"{TEST_PREFIX}{int(camera_id)}")
    until = (row.value or {}).get("until") if row is not None and isinstance(row.value, dict) else None
    active = False
    if until:
        try:
            active = datetime.fromisoformat(str(until)) > datetime.now(timezone.utc)
        except ValueError:
            active = False
    return {"enabled": active, "until": until if active else None}


def in_test_mode(camera_id: int) -> bool:
    camera_id = int(camera_id)
    now = time.monotonic()
    with _cache_lock:
        hit = _test_cache.get(camera_id)
        if hit and now - hit[0] < 2.0:
            return hit[1]
    try:
        from app.db import short_session

        with short_session() as db:
            active = bool(test_mode_status(db, camera_id)["enabled"])
    except Exception:
        active = hit[1] if hit else False
    with _cache_lock:
        _test_cache[camera_id] = (now, active)
    return active


# --------------------------------------------------------------- geometry --

def polygon_area(points) -> float:
    total = 0.0
    for i in range(len(points)):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % len(points)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def point_in_polygon(x: float, y: float, points) -> bool:
    inside = False
    n = len(points)
    j = n - 1
    for i in range(n):
        xi, yi = points[i]
        xj, yj = points[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def _side_of_zone(x: float, y: float, points) -> str:
    """Where a point outside the zone lies: "above", "below" or "side".

    "above"/"below" means the zone is straight up or down from the point (the
    car is in its lane but hasn't reached the zone, or has passed it).
    """
    hits: list[float] = []
    n = len(points or [])
    for i in range(n):
        (x1, y1), (x2, y2) = points[i], points[(i + 1) % n]
        if x1 == x2:
            if abs(x - x1) < 1e-9:
                hits.extend([y1, y2])
            continue
        if min(x1, x2) <= x <= max(x1, x2):
            hits.append(y1 + (y2 - y1) * (x - x1) / (x2 - x1))
    if not hits:
        return "side"
    if y < min(hits):
        return "above"
    if y > max(hits):
        return "below"
    return "side"


def _box_numbers(box: dict) -> tuple[float, float, float, float, float, float] | None:
    try:
        x1, y1, x2, y2 = (float(box[k]) for k in ("x1", "y1", "x2", "y2"))
        width = float(box.get("image_width") or 0)
        height = float(box.get("image_height") or 0)
    except (KeyError, TypeError, ValueError):
        return None
    if x2 <= x1 or y2 <= y1 or width <= 0 or height <= 0:
        return None
    return x1, y1, x2, y2, width, height


# ---------------------------------------------------------------- quality --

def measure_quality(gray_crop) -> dict[str, float]:
    """Sharpness (Laplacian variance), mean brightness, clipped share of a grey crop.

    ``gray_crop`` is a 2-D numpy array (uint8). Small crops are measured as
    they are: upscaling cannot add detail.
    """
    import numpy as np

    a = np.asarray(gray_crop, dtype=np.float32)
    if a.ndim != 2 or a.shape[0] < 3 or a.shape[1] < 3:
        return {"sharpness": 0.0, "brightness": 0.0, "clipped": 1.0, "contrast": 0.0}
    lap = (a[1:-1, :-2] + a[1:-1, 2:] + a[:-2, 1:-1] + a[2:, 1:-1] - 4.0 * a[1:-1, 1:-1])
    clipped = float(((a >= 250) | (a <= 5)).mean())
    return {
        "sharpness": round(float(lap.var()), 1),
        "brightness": round(float(a.mean()), 1),
        "clipped": round(clipped, 3),
        "contrast": round(float(a.std()), 1),
    }


def _gray(jpeg: bytes, scale: float = 1.0):
    """Grey picture, at ``scale`` of its size (sharpness is judged at the calibrated size)."""
    from PIL import Image
    import numpy as np

    image = Image.open(io.BytesIO(jpeg))
    if scale < 0.999:
        width, height = image.size
        target = (max(1, int(width * scale)), max(1, int(height * scale)))
        image.draft("L", target)            # decode at 1/2, 1/4… directly: cheap on big snapshots
        image = image.convert("L")
        if image.size != target:
            image = image.resize(target, Image.Resampling.BILINEAR)
        return np.asarray(image)
    image.load()
    return np.asarray(image.convert("L"))


@dataclass
class Candidate:
    box: dict
    eligible: bool
    reasons: list[str]
    width_px: float
    height_px: float
    area_px: float
    relative_width: float
    in_zone: bool
    past_line: bool
    confidence: float
    quality: dict[str, float] = field(default_factory=dict)
    score: float = 0.0
    advisory: list[str] = field(default_factory=list)   # failed rules that are switched off

    def as_dict(self) -> dict[str, Any]:
        return {
            "box": {k: self.box.get(k) for k in ("x1", "y1", "x2", "y2", "image_width", "image_height")},
            "eligible": self.eligible,
            "reasons": list(self.reasons),
            "advisory": list(self.advisory),
            "plate_width_px": round(self.width_px, 1),
            "plate_height_px": round(self.height_px, 1),
            "plate_area_px": round(self.area_px, 1),
            "relative_plate_width": round(self.relative_width, 4),
            "in_zone": self.in_zone,
            "past_trigger_line": self.past_line,
            "detection_confidence": round(self.confidence, 3),
            "quality": dict(self.quality),
            "score": round(self.score, 4),
        }


def evaluate_frame(jpeg: bytes, boxes: list[dict] | None, config: dict[str, Any]) -> list[Candidate]:
    """Judge every plate box on one frame against this camera's calibration.

    Geometry first (cheap); the crop is decoded and measured only for boxes
    that pass it, so far-away plates cost nothing beyond the detector.
    """
    calibrated = bool(config.get("enabled"))
    zone = config.get("zone") or []
    line = config.get("trigger_line") if calibrated else None
    out: list[Candidate] = []
    gray = None
    for box in boxes or []:
        if not isinstance(box, dict):
            continue
        numbers = _box_numbers(box)
        if numbers is None:
            continue
        x1, y1, x2, y2, fw, fh = numbers
        # Sizes are judged in pixels of the picture the camera was calibrated
        # on (its live view); a larger camera snapshot is scaled down to it.
        reference = float(config.get("reference_width") or 0)
        scale = reference / fw if reference > 0 else 1.0
        width, height = (x2 - x1) * scale, (y2 - y1) * scale
        cx, cy = (x1 + x2) / 2.0 / fw, (y1 + y2) / 2.0 / fh
        rules = enforce_of(config)
        reasons: list[str] = []
        advisory: list[str] = []

        def fail(rule: str, text: str) -> None:
            (reasons if rules.get(rule, True) else advisory).append(text)

        in_zone = True if not (calibrated and zone) else point_in_polygon(cx, cy, zone)
        end = config.get("end_line") if calibrated else None
        travel_down = (line or {}).get("side", "below") == "below"
        past_line = True
        if line:
            past_line = cy >= float(line["y"]) if travel_down else cy <= float(line["y"])
        beyond = bool(end) and (cy > float(end["y"]) if travel_down else cy < float(end["y"]))
        if not in_zone:
            # Outside the zone only because the car hasn't reached it yet (or
            # has already driven through it) is a start/end-line question, so
            # those switches decide. Before this, "store reads before the
            # start line" did nothing: the zone's top edge sits just above the
            # start line, and every early read was refused as outside the zone.
            # Off to the side (another lane, a parked car) stays a zone refusal.
            side = _side_of_zone(cx, cy, zone)
            approach, departed = ("above", "below") if travel_down else ("below", "above")
            if side == approach and line:
                if past_line:
                    fail("start_line", "before the capture zone")
            elif side == departed and end:
                if not beyond:
                    fail("end_line", "past the capture zone")
            else:
                fail("zone", "outside capture zone")
        if line and not past_line:
            fail("start_line", "not past trigger line")
        if beyond:
            # Reading ends here: a car moving out past the end line is not read again.
            fail("end_line", "past end line")
        if calibrated:
            if width < float(config.get("min_plate_width_px") or 0):
                fail("plate_size", f"plate {width:.0f}px wide < {float(config['min_plate_width_px']):.0f}px")
            if height < float(config.get("min_plate_height_px") or 0):
                fail("plate_size", f"plate {height:.0f}px tall < {float(config['min_plate_height_px']):.0f}px")
        try:
            confidence = float(box.get("confidence") or box.get("detection_confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        if calibrated and confidence < float(config.get("min_detection_confidence") or 0.0):
            fail("detector", f"detector {confidence:.2f} < {float(config['min_detection_confidence']):.2f}")
        quality: dict[str, float] = {}
        if not reasons and jpeg[:2] == b"\xff\xd8":
            try:
                if gray is None:
                    gray = _gray(jpeg, scale)
                gh, gw = gray.shape[:2]
                sx, sy = gw / fw, gh / fh
                crop = gray[max(0, int(y1 * sy)):min(gh, int(math.ceil(y2 * sy))),
                            max(0, int(x1 * sx)):min(gw, int(math.ceil(x2 * sx)))]
                quality = measure_quality(crop)
            except Exception:
                quality = {}
            if calibrated and quality:
                if quality["sharpness"] < float(config.get("min_sharpness") or 0):
                    fail("picture_quality", f"blurred (sharpness {quality['sharpness']:.0f} < {float(config['min_sharpness']):.0f})")
                if quality["brightness"] < float(config.get("min_brightness") or 0):
                    fail("picture_quality", "too dark")
                if quality["brightness"] > float(config.get("max_brightness") or 255):
                    fail("picture_quality", "too bright")
                if quality["clipped"] > float(config.get("max_clipped_fraction") or 1.0):
                    fail("picture_quality", "glare or crushed shadows")
        candidate = Candidate(
            box=box, eligible=not reasons, reasons=reasons,
            width_px=width, height_px=height, area_px=width * height, relative_width=(x2 - x1) / fw,
            in_zone=in_zone, past_line=past_line, confidence=confidence, quality=quality, advisory=advisory,
        )
        candidate.score = frame_score(candidate)
        out.append(candidate)
    return out


def plates_to_read(camera_id: int, jpeg: bytes, boxes: list[dict] | None) -> tuple[list[dict], list[Candidate]]:
    """The plate boxes on this picture that this camera may read, best first.

    Called before OCR. A plate outside the calibration (another lane, a parked
    car) is never read: reading the most confident plate anywhere on the
    picture and checking the zone afterwards read the wrong car and then
    refused it, so the car inside the zone was never read at all.
    Uncalibrated cameras get every box back unchanged.
    """
    config = for_camera(camera_id)
    if not config.get("enabled") or not boxes:
        return list(boxes or []), []
    candidates = evaluate_frame(jpeg, list(boxes), config)
    kept = sorted((c for c in candidates if c.eligible), key=lambda c: c.score, reverse=True)
    refused = [c for c in candidates if not c.eligible]
    return [c.box for c in kept], refused


def check_capture(camera_id: int, box: dict | None, jpeg: bytes = b"", *, plate: str = "",
                  plate_confidence: float | None = None) -> Candidate | None:
    """Last check before any read becomes a capture (and so a session or a barrier).

    Every path (the camera's own trigger, ZIRP's video gate, the Recognition
    Worker) ends in ``persist_event``, which calls this. ``None`` means the
    camera is uncalibrated (nothing to enforce). Otherwise the returned
    candidate says whether this read's plate box meets the camera's
    calibration; a read without a usable plate box cannot be checked and is
    not eligible.

    Camera snapshots can be larger than the live picture the calibration was
    drawn on; sizes and sharpness are measured on the snapshot scaled to that
    picture's width, so every limit means the same thing on every path. The
    camera's own plate rectangle has no detector score and is judged on
    position, size and quality.
    """
    config = for_camera(camera_id)
    if not config.get("enabled"):
        return None
    box = dict(box or {})
    rules = enforce_of(config)
    if not all(k in box for k in ("x1", "y1", "x2", "y2")):
        # Nothing to place on the picture: refuse only if a position or size rule is on.
        place_rules = any(rules[name] for name in ("zone", "start_line", "end_line", "plate_size"))
        return Candidate(box=box, eligible=not place_rules,
                         reasons=["no plate box to check against the calibration"] if place_rules else [],
                         advisory=[] if place_rules else ["no plate box to check against the calibration"],
                         width_px=0, height_px=0, area_px=0, relative_width=0, in_zone=False, past_line=False,
                         confidence=0)
    if not box.get("image_width") or not box.get("image_height"):
        size = _jpeg_size(jpeg)
        if size:
            box["image_width"], box["image_height"] = size
    if box.get("confidence") in (None, "") and box.get("detection_confidence") in (None, ""):
        # A camera's own plate rectangle carries no detector score; it is
        # judged on position and size.
        box["confidence"] = 1.0
    # Every limit applies at every picture size: plate sizes and sharpness
    # are measured on the snapshot scaled to the live picture the camera was
    # calibrated on.
    candidates = evaluate_frame(jpeg, [box], config)
    if not candidates:
        return Candidate(box=box, eligible=False, reasons=["plate box could not be read"],
                         width_px=0, height_px=0, area_px=0, relative_width=0, in_zone=False, past_line=False,
                         confidence=0)
    verdict = candidates[0]
    if plate_confidence is not None and plate and float(plate_confidence) < float(config.get("min_ocr_confidence") or 0.0):
        text = f"recognition {float(plate_confidence):.2f} < {float(config['min_ocr_confidence']):.2f}"
        if rules["recognition"]:
            verdict.reasons.append(text)
            verdict.eligible = False
        else:
            verdict.advisory.append(text)
    if verdict.eligible and quality_required(config) and not verdict.quality and jpeg[:2] == b"\xff\xd8":
        verdict.reasons.append("picture could not be checked for sharpness/brightness")
        verdict.eligible = False
    return verdict


def quality_required(config: dict[str, Any]) -> bool:
    return enforced(config, "picture_quality") and bool(float(config.get("min_sharpness") or 0) > 0 or float(config.get("min_brightness") or 0) > 0
                or float(config.get("max_brightness") if config.get("max_brightness") is not None else 255) < 255
                or float(config.get("max_clipped_fraction") if config.get("max_clipped_fraction") is not None else 1) < 1)


def _jpeg_size(jpeg: bytes) -> tuple[int, int] | None:
    if not jpeg or jpeg[:2] != b"\xff\xd8":
        return None
    try:
        from PIL import Image

        with Image.open(io.BytesIO(jpeg)) as image:
            return int(image.width), int(image.height)
    except Exception:
        return None


def frame_score(candidate: Candidate) -> float:
    """Higher is a better OCR frame: plate size, sharpness, exposure, confidence."""
    if not candidate.eligible:
        return 0.0
    q = candidate.quality or {}
    size = min(1.0, candidate.relative_width / 0.25)            # plate width share of the frame
    sharp = min(1.0, float(q.get("sharpness") or 0.0) / 400.0) if q else 0.5
    exposure = max(0.0, 1.0 - float(q.get("clipped") or 0.0)) if q else 0.5
    confidence = max(0.05, candidate.confidence or 0.05)
    # A frame that breaks a rule which is switched off is still usable, but a
    # frame that keeps every rule is preferred.
    penalty = 0.5 ** len(candidate.advisory or [])
    return round((0.15 + size) * (0.25 + sharp) * (0.5 + exposure) * confidence * penalty, 6)


# ------------------------------------------------------------------- gate --

@dataclass
class Selected:
    jpeg: bytes
    box: dict
    boxes: list[dict]
    candidate: Candidate
    frames_considered: int
    selected_at: float


class CaptureGate:
    """Detection runs on every sampled frame; OCR runs once per passage on the best eligible frame.

    ``observe(candidates, boxes, jpeg, now)`` returns a phase:

    * ``absent``     lane empty (after ``absence_seconds``), state reset
    * ``missing``    a short detector gap; nothing changes
    * ``far``        a plate is seen but not eligible yet (early detection)
    * ``collecting`` eligible frames are being gathered for best-frame choice
    * ``ready``      ``selected`` holds the best frame: crop + OCR it now
    * ``held``       this passage already produced its event
    * ``new_vehicle`` a different car replaced the held one without a gap
    """

    def __init__(self, *, absence_seconds: float = 0.6, max_ocr: int = 2, new_vehicle_ratio: float = 0.5) -> None:
        self.absence_seconds = float(absence_seconds)
        self.max_ocr = int(max_ocr)
        self.new_vehicle_ratio = float(new_vehicle_ratio)
        self.config: dict[str, Any] = dict(DEFAULTS)
        self.prepared = None
        self.last: dict[str, Any] = {}
        self.reset()

    def configure(self, config: dict[str, Any]) -> None:
        self.config = dict(config or DEFAULTS)

    def reset(self) -> None:
        self._held = False
        self._fired = False            # a frame was handed to OCR; waiting for its outcome
        self._seen_any = False
        self._absent_since: float | None = None
        self._window: list[Selected] = []
        self._window_started: float | None = None
        self._ocr_count = 0
        self._fired_width = 0.0
        self.selected: Selected | None = None
        self.best_width = 0.0

    # -- the decision -------------------------------------------------
    def observe(self, candidates: list[Candidate], boxes: list[dict], jpeg: bytes, now: float) -> str:
        now = float(now)
        seen = [c for c in candidates or []]
        eligible = [c for c in seen if c.eligible]
        if not seen:
            if not self._seen_any:
                self.reset()
                return "absent"                         # nothing was ever here
            if self._absent_since is None or now < self._absent_since:
                self._absent_since = now
            if self._window and not self._held and not self._fired:
                return self._fire(now)                  # car left mid-window: use the best we have
            if now - self._absent_since >= self.absence_seconds:
                self.reset()
                return "absent"
            return "missing"
        self._absent_since = None
        self._seen_any = True
        widest = max(c.width_px for c in seen)
        self.best_width = max(self.best_width, widest)
        if self._held or self._fired:
            # Fired: one frame of this car is with OCR (or a camera snapshot
            # was commanded). Do not fire again until told the read failed.
            # Queued cars: the read car pulled away and a smaller (farther)
            # plate is now the nearest one, without an empty frame between.
            if eligible and self._fired_width and max(c.width_px for c in eligible) < self._fired_width * self.new_vehicle_ratio:
                self.reset()
                return "new_vehicle"
            return "held"
        if not eligible:
            if self._window:
                return self._fire(now)                  # left the eligible area: best of the window
            return "far"
        best = max(eligible, key=lambda c: c.score)
        if self._window_started is None:
            self._window_started = now
        self._window.append(Selected(jpeg=jpeg, box=best.box, boxes=list(boxes or []), candidate=best,
                                     frames_considered=0, selected_at=now))
        frames = int(self.config.get("candidate_frames") or DEFAULTS["candidate_frames"])
        seconds = float(self.config.get("candidate_seconds") or DEFAULTS["candidate_seconds"])
        if len(self._window) >= frames or now - self._window_started >= seconds:
            return self._fire(now)
        return "collecting"

    def _fire(self, now: float) -> str:
        if self._ocr_count >= self.max_ocr:
            self._held = True
            self._window = []
            self._window_started = None
            return "held"
        best = max(self._window, key=lambda s: s.candidate.score)
        best.frames_considered = len(self._window)
        best.selected_at = now
        self.selected = best
        self._fired_width = best.candidate.width_px
        self._fired = True
        self._window = []
        self._window_started = None
        return "ready"

    # -- feedback from the OCR step -----------------------------------
    def note_ocr(self, *, published: bool) -> None:
        self._ocr_count += 1
        self._fired = False
        if published or self._ocr_count >= self.max_ocr:
            self._held = True

    def rearm(self) -> None:
        """The selected frame was not read (engine busy/failed): collect again."""
        self._fired = False
        if not self._held:
            self._window = []
            self._window_started = None

    def hold(self) -> None:
        self._held = True


_gates: dict[int, CaptureGate] = {}


def gate_for(camera_id: int) -> CaptureGate:
    camera_id = int(camera_id)
    gate = _gates.get(camera_id)
    if gate is None:
        gate = CaptureGate()
        _gates[camera_id] = gate
    return gate


# ------------------------------------------------------------ live view --

_live: dict[int, dict[str, Any]] = {}
_snapshots: dict[int, bytes] = {}


def note_frame(camera_id: int, candidates: list[Candidate], phase: str, config: dict[str, Any]) -> None:
    """What the calibration window shows: boxes, sizes, eligibility, phase."""
    row = _live.setdefault(int(camera_id), {})
    row.update({
        "at": time.time(),
        "phase": phase,
        "calibrated": bool(config.get("enabled")),
        "config_version": int(config.get("version") or 0),
        "plates": [c.as_dict() for c in candidates],
        "eligible": any(c.eligible for c in candidates),
    })


def note_selected(camera_id: int, selected: Selected | None) -> None:
    if selected is None:
        return
    _snapshots[int(camera_id)] = selected.jpeg
    row = _live.setdefault(int(camera_id), {})
    row["selected"] = {
        "at": time.time(),
        "frames_considered": selected.frames_considered,
        "candidate": selected.candidate.as_dict(),
    }


def note_read(camera_id: int, *, plate: str, confidence: float, source: str, test_mode: bool,
              accepted: bool | None = None, jpeg: bytes = b"") -> None:
    row = _live.setdefault(int(camera_id), {})
    min_conf = float(for_camera(camera_id).get("min_ocr_confidence") or 0.0)
    row["last_read"] = {
        "at": time.time(),
        "plate": str(plate or ""),
        "confidence": round(float(confidence or 0.0), 3),
        "source": str(source or ""),
        "test_mode": bool(test_mode),
        "meets_min_confidence": float(confidence or 0.0) >= min_conf,
        "accepted": accepted,
    }
    if jpeg[:2] == b"\xff\xd8" and int(camera_id) not in _snapshots:
        _snapshots[int(camera_id)] = jpeg


def note_rejected(camera_id: int, *, plate: str, reasons: list[str], candidate: Candidate | None = None,
                  jpeg: bytes = b"") -> None:
    """A read that did not meet the calibration and so was not stored."""
    import logging

    now = time.time()
    row = _live.setdefault(int(camera_id), {})
    row["last_rejected"] = {
        "at": now,
        "plate": str(plate or ""),
        "reasons": list(reasons or []),
        "candidate": candidate.as_dict() if candidate is not None else None,
        "has_image": bool(jpeg[:2] == b"\xff\xd8"),
    }
    row["rejected_count"] = int(row.get("rejected_count") or 0) + 1
    recent = [item for item in row.get("recent_rejections", []) if now - item[0] <= WARN_WINDOW_SECONDS]
    recent.append((now, list(reasons or [])))
    row["recent_rejections"] = recent[-50:]
    if jpeg[:2] == b"\xff\xd8":
        _rejected_images[int(camera_id)] = (jpeg, dict(candidate.box) if candidate is not None else {})
    logging.getLogger("smartpark").info(
        "camera=%s read not stored: outside capture calibration plate=%s reasons=%s",
        camera_id, plate or "-", "; ".join(reasons or []),
    )


WARN_WINDOW_SECONDS = 600.0
WARN_MIN_REFUSED = 3
_rejected_images: dict[int, tuple[bytes, dict]] = {}


def note_stored(camera_id: int) -> None:
    """A read for this camera became a capture (it met the calibration)."""
    _live.setdefault(int(camera_id), {})["last_stored_at"] = time.time()


def lane_warning(camera_id: int) -> str:
    """Plain warning when the calibration keeps refusing cars and stores none."""
    row = _live.get(int(camera_id)) or {}
    now = time.time()
    stored_at = float(row.get("last_stored_at") or 0)
    recent = [item for item in row.get("recent_rejections", [])
              if now - item[0] <= WARN_WINDOW_SECONDS and item[0] > stored_at]
    if len(recent) < WARN_MIN_REFUSED:
        return ""
    import collections

    reasons = collections.Counter(
        reason.split(" (")[0].split(" <")[0] for _, items in recent for reason in items[:1]
    )
    top = ", ".join(f"{reason} ({count})" for reason, count in reasons.most_common(2))
    minutes = int(min(WARN_WINDOW_SECONDS, now - recent[0][0]) // 60) + 1
    return (f"{len(recent)} cars not stored in the last {minutes} min and none stored since: {top}. "
            "Check this camera's calibration in Settings.")


def live_state(camera_id: int) -> dict[str, Any]:
    row = dict(_live.get(int(camera_id)) or {})
    row.pop("recent_rejections", None)
    row["warning"] = lane_warning(camera_id)
    return row


def rejected_image(camera_id: int, part: str = "snapshot") -> bytes:
    """The last refused read's picture (or its plate crop), for the live view."""
    item = _rejected_images.get(int(camera_id))
    if not item:
        return b""
    jpeg, box = item
    if part != "crop" or not box:
        return jpeg
    try:
        from app.services.captures import _crop_from_bbox

        return _crop_from_bbox(jpeg, box) or b""
    except Exception:
        return b""


def selected_snapshot(camera_id: int) -> bytes:
    return _snapshots.get(int(camera_id), b"")


def ocr_confidence_ok(camera_id: int, confidence: float) -> bool:
    config = for_camera(camera_id)
    if not enforced(config, "recognition"):
        return True
    return float(confidence or 0.0) >= float(config.get("min_ocr_confidence") or 0.0)
