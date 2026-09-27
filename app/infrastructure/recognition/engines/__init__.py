"""Isolated plate engines. Parking imports `recognize_frame` and nothing else."""

from app.infrastructure.recognition.engines.registry import (
    active_engine,
    active_engine_id,
    engine_for,
    list_engines,
    recognize_frame,
    register_engine,
)

__all__ = [
    "active_engine",
    "active_engine_id",
    "engine_for",
    "list_engines",
    "recognize_frame",
    "register_engine",
]
