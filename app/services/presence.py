"""Vehicle presence (ground loop / coil / GPIO) for plate reads.

Parking does not need OcxConfig. HVX cameras expose occupancy through
``Net_ReadGPIOState`` and the image callback (``ucHaveVehicle``). Another
vendor, a Board* dry contact, or a future in-house ALPR camera can push the
same rising edge into this helper and the shared plate pipeline.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class CoilEdge:
    camera_id: int
    occupied: bool
    rising: bool
    falling: bool
    source: str
    index: int | None = None
    value: int | None = None
    at: float = field(default_factory=time.monotonic)

    def as_dict(self) -> dict:
        return {
            "camera_id": self.camera_id,
            "occupied": self.occupied,
            "rising": self.rising,
            "falling": self.falling,
            "source": self.source,
            "index": self.index,
            "value": self.value,
        }


class PresenceWatch:
    """Debounce occupancy so one car on the loop fires one detect."""

    def __init__(self, debounce_seconds: float = 0.35, hold_seconds: float = 4.0):
        self.debounce_seconds = debounce_seconds
        self.hold_seconds = hold_seconds
        self._occupied: dict[int, bool] = {}
        self._raw: dict[int, bool] = {}
        self._raw_at: dict[int, float] = {}
        self._fired_at: dict[int, float] = {}
        self._learned: dict[int, int] = {}

    def learned_index(self, camera_id: int) -> int | None:
        return self._learned.get(int(camera_id))

    def _slot(self, camera_id: int, index: int | None):
        return int(camera_id) if index is None else (int(camera_id), int(index))

    def observe(
        self,
        camera_id: int,
        occupied: bool,
        *,
        source: str = "coil",
        index: int | None = None,
        value: int | None = None,
        now: float | None = None,
    ) -> CoilEdge:
        now = time.monotonic() if now is None else now
        slot = self._slot(camera_id, index)
        prev_raw = self._raw.get(slot)
        self._raw[slot] = bool(occupied)
        if prev_raw is None:
            self._raw_at[slot] = now
            self._occupied[slot] = bool(occupied)
            rising = bool(occupied) and index is None
            if rising:
                self._fired_at[camera_id] = now
            if index is None:
                self._occupied[camera_id] = bool(occupied)
            return CoilEdge(
                camera_id=camera_id,
                occupied=bool(self._occupied.get(camera_id, False if index is not None else occupied)),
                rising=rising,
                falling=False,
                source=source,
                index=index,
                value=value,
                at=now,
            )
        if prev_raw != occupied:
            self._raw_at[slot] = now
        stable = (now - self._raw_at.get(slot, now)) >= self.debounce_seconds
        previous = bool(self._occupied.get(slot, False))
        current = previous
        if stable:
            current = bool(occupied)
            self._occupied[slot] = current
        rising = current and not previous
        falling = previous and not current
        if rising:
            self._fired_at[camera_id] = now
            if index is not None:
                self._learned[camera_id] = int(index)
        if index is None or self._learned.get(camera_id) == index:
            self._occupied[camera_id] = current
        return CoilEdge(
            camera_id=camera_id,
            occupied=bool(self._occupied.get(camera_id, current)),
            rising=rising,
            falling=falling,
            source=source,
            index=index,
            value=value,
            at=now,
        )

    def occupied(self, camera_id: int) -> bool:
        return bool(self._occupied.get(camera_id, False))

    def recently_triggered(self, camera_id: int, window: float | None = None) -> bool:
        last = self._fired_at.get(camera_id)
        if last is None:
            return False
        return (time.monotonic() - last) <= float(window if window is not None else self.hold_seconds)

    def mark_triggered(self, camera_id: int) -> None:
        self._fired_at[camera_id] = time.monotonic()


coil_watch = PresenceWatch()
