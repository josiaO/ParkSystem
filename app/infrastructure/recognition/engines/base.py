"""Plate-engine contract.

ParkWatch read every lane JPEG through one helper (`LPRHelper.Recognize` /
`RecognizeAll`) and could point that helper at a different library. SmartPark
keeps the same split: the camera supplies the picture, a `PlateEngine` returns
the plate. Parking never imports a vendor SDK.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class PlateEngine(Protocol):
    """One swappable reader. Implementations live in this package only."""

    id: str
    display_name: str
    version: str

    def describe(self) -> dict[str, Any]:
        """Identity, country, model files, and whether a new pack can replace them."""

    def recognize_bytes(self, jpeg: bytes, *, camera_label: str = "frame") -> dict[str, Any]:
        """Read one JPEG. Return the FastALPR-shaped dict (`ok`, `plates`, `best`)."""


def engine_catalog_row(engine: PlateEngine) -> dict[str, Any]:
    described = engine.describe()
    return {
        "id": engine.id,
        "display_name": described.get("display_name") or engine.display_name,
        "version": described.get("version") or engine.version,
        "active": bool(described.get("active")),
        "installed": bool(described.get("installed")),
        "retrainable": bool(described.get("retrainable")),
        "replaceable": bool(described.get("replaceable")),
    }
