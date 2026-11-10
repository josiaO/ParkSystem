from __future__ import annotations

"""Save each car event: zone snapshot, plate crop, extracted characters.

Works for native camera callbacks and FastALPR (or a future in-house engine).
Does not change barrier, fee, or SDK login.

Snapshots are the configured recognition-zone view of vehicle events. The
source frame remains available in memory for coordinate mapping and OCR, while
empty scenes and non-car OCR (signs, walls) must not create VehicleCapture rows.
"""

import re

import time

import logging

import hashlib

from io import BytesIO

from pathlib import Path

from sqlalchemy import func, or_, select

from sqlalchemy.exc import IntegrityError

from sqlalchemy.orm import Session

from app.config import settings

from app.core.plate import is_empty_scene_ocr, normalize_plate

from app.models import Camera, VehicleCapture, as_utc, utcnow

from app.services.camera_lpr import bbox_from_lp_box, native_from_sdk_capture

log = logging.getLogger("smartpark")

_MEDIA_HASH_INDEX: dict[str, dict[tuple[int, str], str]] = {}

def _media_signature(data: bytes) -> tuple[int, str]:
    return len(data), hashlib.sha256(data).hexdigest()

_PLATE_DENYLIST = frozenset({
    "STATION", "POLICE", "TAXI", "STOP", "ENTRY", "EXIT", "OPEN", "CLOSE",
    "DANGER", "PARKING", "WELCOME", "THANKYOU", "THANK", "PLEASE", "SLOW",
    "SPEED", "CAMERA", "SMARTPARK", "DAHUA", "HIKVISION",
})

_TZ_PLATE_RE = re.compile(r"^T\d{3}[A-Z]{2,3}$")

MIN_PLATE_LEN = 5

MAX_PLATE_LEN = 10

MIN_FASTALPR_CONF = 0.35

MIN_FASTALPR_CONF_TZ = 0.22

MIN_PLATE_ASPECT = 1.4  # plate boxes are wider than tall

MAX_PLATE_ASPECT = 8.0

PLATE_CROP_PAD = 0.24

DETECTION_DISPLAY_DEDUPE_SECONDS = 8.0
