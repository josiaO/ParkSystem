"""Corrections and model packs for the active plate engine.

A correction is one operator fix: the JPEG reference, what the engine read,
and the plate that was actually on the car. Those rows are the training set.

A model pack is a folder another machine trained. Applying it copies the
weights into the engine directory and unloads the current reader so the next
car uses the new files. The parking code does not change.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings
from app.services import alpr


def corrections_path() -> Path:
    folder = settings.media_dir / "recognition"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "corrections.jsonl"


def record_correction(
    *,
    image_ref: str = "",
    predicted: str = "",
    corrected: str = "",
    engine_id: str = "fastalpr",
    country: str = "",
) -> dict[str, Any]:
    row = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "engine_id": engine_id,
        "country": country or settings.alpr_country or "",
        "image_ref": str(image_ref or ""),
        "predicted": str(predicted or ""),
        "corrected": str(corrected or ""),
    }
    path = corrections_path()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def correction_count() -> int:
    path = corrections_path()
    if not path.is_file():
        return 0
    count = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def training_status(*, engine_id: str = "fastalpr") -> dict[str, Any]:
    path = corrections_path()
    return {
        "engine_id": engine_id,
        "corrections": correction_count(),
        "corrections_file": str(path),
        "retrain": (
            "Export this JSONL with the JPEG each image_ref points at. "
            "Fine-tune the detector (YOLO license-plate ONNX) and the OCR model "
            "(fast-plate-ocr CCT ONNX + yaml). Save them under the filenames in "
            "a model-pack manifest, then apply that folder."
        ),
    }


def install_model_dir() -> Path:
    """Directory the next FastALPR load will read from."""
    import os

    extra = os.environ.get("SMARTPARK_ALPR_MODEL_DIR")
    if extra:
        path = Path(extra)
    else:
        home = os.environ.get("SMARTPARK_HOME")
        if home:
            path = Path(home) / "models" / "fastalpr"
        else:
            path = Path(__file__).resolve().parents[4] / "models" / "fastalpr"
    path.mkdir(parents=True, exist_ok=True)
    return path


def apply_model_pack(directory: str, *, engine_id: str = "fastalpr") -> dict[str, Any]:
    """Copy a trained pack into the engine model directory and drop the loaded reader."""
    source = Path(directory).expanduser()
    if not source.is_dir():
        raise FileNotFoundError(f"Model pack folder not found: {source}")
    manifest_path = source / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("Model pack needs manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pack_engine = str(manifest.get("engine_id") or engine_id).strip().lower()
    if pack_engine != engine_id:
        raise ValueError(f"This pack is for {pack_engine}, not {engine_id}")
    names = {
        "detector": str(manifest.get("detector_onnx") or alpr.DETECTOR_ONNX),
        "ocr": str(manifest.get("ocr_onnx") or alpr.OCR_ONNX),
        "config": str(manifest.get("ocr_config") or alpr.OCR_CONFIG),
    }
    copied: list[str] = []
    dest_root = install_model_dir()
    for key, name in names.items():
        src = source / name
        if not src.is_file():
            raise FileNotFoundError(f"Model pack is missing {name} ({key})")
        dest = dest_root / src.name
        dest.write_bytes(src.read_bytes())
        copied.append(str(dest))
    (dest_root / "manifest.json").write_text(
        json.dumps({**manifest, "engine_id": engine_id, "applied_from": str(source)}, indent=2),
        encoding="utf-8",
    )
    alpr.unload_engine()
    return {
        "ok": True,
        "engine_id": engine_id,
        "installed_to": str(dest_root),
        "files": copied,
        "country": manifest.get("country") or settings.alpr_country,
    }
