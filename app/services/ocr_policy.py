"""Native ALPR first. FastALPR runs only when the camera score is weak or local-only."""

from __future__ import annotations

NATIVE_ONLY = "NATIVE_ONLY"
NATIVE_WITH_LOCAL_VERIFY = "NATIVE_WITH_LOCAL_VERIFY"
LOCAL_ONLY = "LOCAL_ONLY"
MODES = {NATIVE_ONLY, NATIVE_WITH_LOCAL_VERIFY, LOCAL_ONLY}

VERIFY_MIN = 0.70


def alpr_mode() -> str:
    from app.config import settings
    value = str(getattr(settings, "alpr_mode", NATIVE_ONLY) or NATIVE_ONLY).upper()
    return value if value in MODES else NATIVE_ONLY


def fusion_mode() -> str:
    mode = alpr_mode()
    if mode == LOCAL_ONLY:
        return "LOCAL_ONLY"
    if mode == NATIVE_ONLY:
        return "NATIVE_ONLY"
    return "HYBRID"


def should_run_local(*, native_plate: str = "", native_confidence: float = 0.0, explicit: bool = False) -> bool:
    """Live cameras: skip FastALPR unless the operator asked or native is missing/weak."""
    if explicit:
        return True
    mode = alpr_mode()
    if mode == LOCAL_ONLY:
        return True
    if mode == NATIVE_ONLY:
        return False
    if not native_plate:
        return True
    return float(native_confidence or 0) < VERIFY_MIN
