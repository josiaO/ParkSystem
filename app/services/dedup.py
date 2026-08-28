"""Camera-event and gate-command idempotency windows."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.core.plate import normalize_plate


@dataclass
class EventDeduper:
    window_seconds: float = 2.0
    _seen: dict[str, float] = field(default_factory=dict)

    def key(self, *, camera_id: int, plate: str = "", image_id: int = 0) -> str:
        plate = normalize_plate(plate)
        if image_id:
            return f"{camera_id}:{image_id}"
        return f"{camera_id}:{plate}"

    def seen(self, *, camera_id: int, plate: str = "", image_id: int = 0) -> bool:
        token = self.key(camera_id=camera_id, plate=plate, image_id=image_id)
        now = time.monotonic()
        expires = self._seen.get(token)
        self._prune(now)
        if expires is not None and expires > now:
            return True
        self._seen[token] = now + self.window_seconds
        return False

    def _prune(self, now: float) -> None:
        if len(self._seen) < 64:
            return
        self._seen = {k: v for k, v in self._seen.items() if v > now}


camera_events = EventDeduper(window_seconds=2.0)
gate_commands = EventDeduper(window_seconds=1.5)
