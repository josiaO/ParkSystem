"""FastALPR plate engine.

This is the reader that replaces ParkWatch SimpleLPR. The camera still snaps
the JPEG. This engine finds the plate, crops it, and reads the characters.

Swap or retrain by dropping a model pack (detector ONNX + OCR ONNX + OCR
config) into the model directory. See docs/PLATE-ENGINE.md.
"""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.services import alpr


ENGINE_VERSION = "fastalpr-1"


class FastALPRPlateEngine:
    id = "fastalpr"
    display_name = "FastALPR"
    version = ENGINE_VERSION

    def describe(self) -> dict[str, Any]:
        info = alpr.status()
        models = info.get("models") or {}
        return {
            "id": self.id,
            "display_name": self.display_name,
            "version": self.version,
            "active": True,
            "installed": bool(info.get("installed")),
            "loaded": bool(info.get("loaded")),
            "retrainable": True,
            "replaceable": True,
            "country": settings.alpr_country or "Tanzania",
            "contrast_sensitivity": float(settings.alpr_csf or 0.918),
            "pipeline": "detect_crop_ocr",
            "flow": [
                "Camera snaps a JPEG (HVX/QY image callback or coil snapshot).",
                "This engine detects the plate on that JPEG.",
                "OCR runs on the padded plate crop only.",
                "Parking receives one normalized plate event.",
            ],
            "models": {
                "detector": alpr.DETECTOR_MODEL,
                "detector_file": alpr.DETECTOR_ONNX,
                "ocr": alpr.OCR_MODEL,
                "ocr_file": alpr.OCR_ONNX,
                "ocr_config": alpr.OCR_CONFIG,
                "bundled_dir": models.get("bundled_dir"),
                "detector_ready": bool(models.get("detector")),
                "ocr_ready": bool(models.get("ocr")),
            },
            "how_to_replace": (
                "Put a manifest.json plus the ONNX files in a folder and apply that "
                "folder as a model pack. The next read loads the new weights. "
                "A different library implements PlateEngine and is selected by id."
            ),
        }

    def recognize_bytes(self, jpeg: bytes, *, camera_label: str = "frame") -> dict[str, Any]:
        result = alpr.recognize_bytes(jpeg, camera_label=camera_label)
        result["engine_id"] = self.id
        result["engine_version"] = self.version
        return result
