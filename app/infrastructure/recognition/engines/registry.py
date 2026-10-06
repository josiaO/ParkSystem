"""Which plate engine is active.

Register another class here, set SMARTPARK_ALPR_ENGINE to its id, and lane
photos go through that reader. FastALPR stays the default.
"""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.infrastructure.recognition.engines.base import PlateEngine, engine_catalog_row
from app.infrastructure.recognition.engines.fastalpr import FastALPRPlateEngine

_ENGINES: dict[str, PlateEngine] = {
    "fastalpr": FastALPRPlateEngine(),
}


def register_engine(engine: PlateEngine) -> None:
    key = str(engine.id or "").strip().lower()
    if not key:
        raise ValueError("Plate engine id is required")
    _ENGINES[key] = engine


def list_engines() -> list[dict[str, Any]]:
    active = active_engine_id()
    rows = []
    for engine in _ENGINES.values():
        row = engine_catalog_row(engine)
        row["active"] = row["id"] == active
        rows.append(row)
    return rows


def active_engine_id() -> str:
    chosen = str(getattr(settings, "alpr_engine", "") or "fastalpr").strip().lower()
    if chosen in _ENGINES:
        return chosen
    return "fastalpr"


def active_engine() -> PlateEngine:
    return _ENGINES[active_engine_id()]


def engine_for(engine_id: str | None) -> PlateEngine:
    key = str(engine_id or "").strip().lower()
    if key not in _ENGINES:
        known = ", ".join(sorted(_ENGINES))
        raise KeyError(f"Unknown plate engine {engine_id!r}. Known: {known}")
    return _ENGINES[key]


def recognize_frame(jpeg: bytes, *, camera_label: str = "frame", detect_roi: str | None = None) -> dict[str, Any]:
    """ParkWatch RecognizeAll equivalent: one JPEG in, plate candidates out."""
    engine = active_engine()
    if detect_roi:
        return engine.recognize_bytes(jpeg, camera_label=camera_label, detect_roi=detect_roi)
    return engine.recognize_bytes(jpeg, camera_label=camera_label)
