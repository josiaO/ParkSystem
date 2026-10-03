"""Software plate reading is the default, matching ParkWatch InALPR/OutALPR.

The camera snaps the JPEG. The active PlateEngine (FastALPR) reads that JPEG.
NATIVE_ONLY is still available when a lane should keep the camera's own text.
FASTALPR_ONLY reads every presence frame in software and does not require the
camera's onboard OCR.
"""

from __future__ import annotations

NATIVE_ONLY = "NATIVE_ONLY"
NATIVE_WITH_LOCAL_VERIFY = "NATIVE_WITH_LOCAL_VERIFY"
LOCAL_ONLY = "LOCAL_ONLY"
FASTALPR_ONLY = "FASTALPR_ONLY"
HYBRID = "HYBRID"
MODES = {NATIVE_ONLY, NATIVE_WITH_LOCAL_VERIFY, LOCAL_ONLY, FASTALPR_ONLY, HYBRID}

VERIFY_MIN = 0.70


def _canonical_mode(value: str) -> str:
    chosen = (value or NATIVE_ONLY).upper()
    if chosen in {"FASTALPR_ONLY", "LOCAL", "LOCAL_ONLY", "FASTALPR"}:
        return LOCAL_ONLY
    if chosen in {"HYBRID", "NATIVE_WITH_LOCAL_VERIFY"}:
        return NATIVE_WITH_LOCAL_VERIFY
    if chosen in MODES:
        return chosen
    return NATIVE_ONLY


def alpr_mode() -> str:
    from app.config import settings
    return _canonical_mode(str(getattr(settings, "alpr_mode", "FASTALPR_ONLY") or "FASTALPR_ONLY"))


def camera_recognition_mode(camera=None) -> str:
    raw = str(getattr(camera, "recognition_mode", None) or "").strip()
    if raw:
        return _canonical_mode(raw)
    from app.infrastructure.hardware.cameras import adapter_has_native_plates
    if camera is not None and not adapter_has_native_plates(camera):
        return LOCAL_ONLY
    return alpr_mode()


def fusion_mode(camera=None) -> str:
    mode = camera_recognition_mode(camera) if camera is not None else alpr_mode()
    if mode == LOCAL_ONLY:
        return "LOCAL_ONLY"
    if mode == NATIVE_ONLY:
        return "NATIVE_ONLY"
    return "HYBRID"


def software_ocr_enabled(camera=None) -> bool:
    """ParkWatch InALPR/OutALPR: the PC reads the camera JPEG in FastALPR.

    QY/HVX cameras still supply video and optional native callbacks. They are
    not the plate engine unless the lane is explicitly ``NATIVE_ONLY``.
    """
    return camera_recognition_mode(camera) != NATIVE_ONLY


def should_run_local(
    *,
    native_plate: str = "",
    native_confidence: float = 0.0,
    explicit: bool = False,
    presence: bool = False,
    native_plates: bool = True,
    camera=None,
) -> bool:
    """Run FastALPR on an operator click, LOCAL_ONLY, cameras with no onboard ALPR, weak native, or a car-present frame with no plate."""
    if explicit:
        return True
    if not native_plates:
        return True
    mode = camera_recognition_mode(camera)
    native = str(native_plate or "").strip()
    conf = float(native_confidence or 0)
    if mode == LOCAL_ONLY:
        # Generic IP (native_plates=False) already returned True above.
        # HVX FASTALPR_ONLY reads the capture/coil JPEG, not every idle frame.
        return bool(presence)
    if mode == NATIVE_WITH_LOCAL_VERIFY:
        # ParkWatch-style event verification: when a vehicle-trigger JPEG is
        # available, always run software OCR once and fuse it with native LPR.
        # This is event-driven, not continuous video OCR.
        return bool(presence)
    if mode == NATIVE_ONLY:
        return (not native) and bool(presence)
    if native and conf >= VERIFY_MIN:
        return False
    if not native:
        return True
    return conf < VERIFY_MIN
