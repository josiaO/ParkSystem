"""QY/HVX camera ANPR contract used by SmartPark Edge.

Site cameras are DVCAM_QY. Native plates arrive on Net_RegImageRecvEx after
SDK login on port 30000. FastALPR is the local JPEG OCR for simulation and
as a second read on a live frame. Never invent plates when both are missing.
"""

from __future__ import annotations

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
    """Map HVX Net_RegImageRecvEx last capture to a plate hit."""
    capture = capture or {}
    raw = str(capture.get("plate") or "").strip()
    box = capture.get("plate_box") or capture.get("bbox")
    return {
        "plate": normalize_plate(raw),
        "plate_raw": raw,
        "confidence": native_confidence(capture.get("score") if "score" in capture else capture.get("confidence")),
        "bbox": bbox_from_lp_box(box) if not isinstance(box, dict) else box,
        "source": "qy_Net_RegImageRecvEx",
        "image_id": capture.get("image_id"),
        "image_width": int(capture.get("image_width") or 0),
        "image_height": int(capture.get("image_height") or 0),
        "jpeg_bytes": capture.get("jpeg_bytes") or 0,
        "crop_bytes": capture.get("crop_bytes") or 0,
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
        "official_config": {
            "ui": "OcxConfig/OcxConfig.ocx",
            "client": "OcxConfig/OcxConfigClient.exe",
            "progid": "OCXCONFIG.OcxConfigCtrl.1",
            "register": "regsvr32 OcxConfig.ocx",
            "connect": "Net_AddCamera then Net_ConnCamera(handle, 30000, 5)",
            "autologin": "Net_ConnCameraEx(handle, port, 3, user, pass)",
            "native_plates": "Net_RegImageRecvEx2",
        },
        "native_engine": {
            "api": "Net_RegImageRecvEx / Net_RegImageRecvEx2",
            "plate_field": "CAM_PlateInfo.szPlateText / T_ImageUserInfo.szLprResult",
            "confidence": "0-100 (ucScore / nConfidence)",
            "trigger": "CAM_Capture / Net_ImageSnap",
        },
        "local_engine": {
            "name": "fastalpr",
            "country": ALPR_COUNTRY,
            "csf": ALPR_CSF,
            "confidence": "0-1",
        },
        "relay": {
            "open": CAMCMD_OPEN_RELAY,
            "close": CAMCMD_CLOSE_RELAY,
            "pulse": CAMCMD_PULSE_RELAY,
            "pulse_default_ms": CAMCMD_PULSE_DEFAULT_MS,
            "index": 0,
        },
        "note": "QY cameras use SDK port 30000. Camera HTTP UI is port 80. FastALPR reads plates from a JPEG when the camera callback is not used.",
    }
