"""Camera ANPR contract used by SmartPark Edge.

Parking and FastALPR do not depend on OcxConfig. HVX/QY is the current site
adapter (port 30000, Net_RegImageRecvEx). Another vendor or an in-house ALPR
camera delivers plates into the same event path. FastALPR is the local JPEG
OCR used when the camera has no native engine or the native plate is empty.
Never invent plates when both are missing.
"""

from __future__ import annotations

from app.config import settings
from app.core.plate import normalize_plate

DVCAM_ZS = 1
DVCAM_HX = 2
DVCAM_QY = 3
DVCAM_DH = 6
DVCAM_TVT = 7

CAMAPI_DEFAULT_PORT = 60000
QY_SDK_PORT = 30000
QY_HTTP_PORT = 80
QY_PICTURE_PORT = 40000
OCX_CLIENT_TIMEOUT_SECONDS = 5
OCX_AUTOLOGIN_TIMEOUT_SECONDS = 3

CAMCMD_OPEN_RELAY = 100
CAMCMD_CLOSE_RELAY = 101
CAMCMD_PULSE_RELAY = 102
CAMCMD_PULSE_DEFAULT_MS = 500

ALPR_COUNTRY = "Tanzania"
ALPR_CSF = 0.918
CONTRAST_INI_TO_CSF = 1000.0
NATIVE_SCORE_MAX = 100.0


def csf_from_contrast(contrast: int | float | None) -> float:
    if contrast is None:
        return ALPR_CSF
    value = float(contrast)
    if value > 1.0:
        value = value / CONTRAST_INI_TO_CSF
    if value <= 0.0 or value > 1.0:
        return ALPR_CSF
    return value


def native_confidence(score) -> float:
    """Map camera ucScore (0-100) or already-normalised 0-1 onto 0-1."""
    if score is None:
        return 0.0
    value = float(score)
    if value > 1.0:
        value = value / NATIVE_SCORE_MAX
    return max(0.0, min(value, 1.0))


def bbox_from_lp_box(box) -> dict | None:
    """T_ImageUserInfo.usLpBox: top-left (0,1), bottom-right (2,3)."""
    if not box or len(box) < 4:
        return None
    left, top, right, bottom = (int(box[0]), int(box[1]), int(box[2]), int(box[3]))
    if right <= left or bottom <= top:
        return None
    return {"x1": left, "y1": top, "x2": right, "y2": bottom}


def choose_overlay_box(native: dict | None = None, local: dict | None = None) -> dict | None:
    """Prefer the camera usLpBox overlay; FastALPR box is the fallback."""
    for src in (native or {}, local or {}):
        box = src.get("bbox")
        if not isinstance(box, dict):
            continue
        x1, y1 = int(box.get("x1") or 0), int(box.get("y1") or 0)
        x2, y2 = int(box.get("x2") or 0), int(box.get("y2") or 0)
        if x2 <= x1 or y2 <= y1:
            continue
        return {
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "label": str(src.get("plate") or ""),
            "image_width": int(src.get("image_width") or 0),
            "image_height": int(src.get("image_height") or 0),
            "source": src.get("source") or "",
        }
    return None


def native_from_sdk_capture(capture: dict | None) -> dict:
    """Map a camera capture (HVX callback or vendor-neutral payload) to a plate hit."""
    capture = capture or {}
    raw = str(capture.get("plate") or "").strip()
    box = capture.get("plate_box") or capture.get("bbox")
    source = str(capture.get("source") or "").strip() or "qy_Net_RegImageRecvEx"
    return {
        "plate": normalize_plate(raw),
        "plate_raw": raw,
        "confidence": native_confidence(capture.get("score") if "score" in capture else capture.get("confidence")),
        "bbox": bbox_from_lp_box(box) if not isinstance(box, dict) else box,
        "source": source,
        "image_id": capture.get("image_id"),
        "image_width": int(capture.get("image_width") or 0),
        "image_height": int(capture.get("image_height") or 0),
        "jpeg_bytes": capture.get("jpeg_bytes") or 0,
        "crop_bytes": capture.get("crop_bytes") or 0,
        "have_vehicle": bool(capture.get("have_vehicle")),
        "snap_type": capture.get("snap_type"),
    }


def local_from_fastalpr(result: dict | None) -> dict:
    result = result or {}
    best = result.get("best") or {}
    raw = str(best.get("plate_raw") or best.get("plate") or "")
    return {
        "plate": normalize_plate(best.get("plate_normalized") or raw),
        "plate_raw": raw,
        "confidence": float(best.get("confidence") or 0),
        "bbox": best.get("bbox"),
        "source": "fastalpr",
        "backend": result.get("backend") or "none",
        "ok": bool(result.get("ok")),
    }


def camera_contract() -> dict:
    return {
        "camera_type": DVCAM_QY,
        "camera_type_name": "DVCAM_QY",
        "sdk_port": QY_SDK_PORT,
        "picture_port": QY_PICTURE_PORT,
        "http_ui_port": QY_HTTP_PORT,
        "do_not_use_port": CAMAPI_DEFAULT_PORT,
        "parking_requires_ocxconfig": False,
        "official_config": {
            "ui": "OcxConfig/OcxConfig.ocx",
            "client": "OcxConfig/OcxConfigClient.exe",
            "progid": "OCXCONFIG.OcxConfigCtrl.1",
            "register": "regsvr32 OcxConfig.ocx",
            "connect": "Net_AddCamera then Net_ConnCamera(handle, 30000, 5)",
            "autologin": "Net_ConnCameraEx(handle, port, 3, user, pass)",
            "native_plates": "Net_RegImageRecvEx2",
            "note": "HVX vendor kit only. Not required for FastALPR, parking sessions, or a future camera brand.",
        },
        "native_engine": {
            "api": "Net_RegImageRecvEx / Net_RegImageRecvEx2",
            "optional": True,
            "adapter_id": "hvx",
            "plate_field": "CAM_PlateInfo.szPlateText / T_ImageUserInfo.szLprResult",
            "confidence": "0-100 (ucScore / nConfidence)",
            "trigger": "ground loop / GPIO IN / CAM_Capture / Net_ImageSnap",
        },
        "local_engine": {
            "name": "fastalpr",
            "vendor_independent": True,
            "country": settings.alpr_country or None,
            "csf": ALPR_CSF,
            "confidence": "0-1",
            "trigger": "coil rising edge, native JPEG with no plate, or operator FastALPR",
        },
        "coil": {
            "gpio_api": "Net_ReadGPIOState",
            "default_index": 1,
            "active_value": 1,
            "note": "You do not need the pin number. SmartPark scans GPIO IN 1–7 and learns the loop pin when it changes. If the camera already snaps on the coil, that JPEG is enough without GPIO.",
        },
        "relay": {
            "open": CAMCMD_OPEN_RELAY,
            "close": CAMCMD_CLOSE_RELAY,
            "pulse": CAMCMD_PULSE_RELAY,
            "pulse_default_ms": CAMCMD_PULSE_DEFAULT_MS,
            "index": 0,
        },
        "note": (
            "Parking is adapter + plate-event based. HVX uses NetSDK port 30000; "
            "OcxConfig is only the current vendor DLL kit. FastALPR reads a JPEG when "
            "the camera has no native plate or you ship your own ALPR later."
        ),
    }
