"""Bounded latest-frame-wins buffers. Real-time video keeps the newest frame."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FrameSample:
    jpeg: bytes
    seq: int
    received_at: float
    source: str = ""
    url: str = ""
    decode_at: float = 0.0
    source_ts: float | None = None

    def age_ms(self, now: float | None = None) -> float:
        stamp = self.received_at or 0.0
        if stamp <= 0:
            return 0.0
        return round(((now if now is not None else time.monotonic()) - stamp) * 1000.0, 1)


@dataclass
class LatestFrameBuffer:
    """Keep 1–3 frames. A slow consumer drops old frames and reads the newest."""

    name: str
    maxsize: int = 1
    _items: deque[FrameSample] = field(default_factory=deque, repr=False)
    dropped: int = 0
    received: int = 0
    seq: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self) -> None:
        self.maxsize = max(1, min(int(self.maxsize or 1), 3))

    def put(self, jpeg: bytes, *, source: str = "", url: str = "", source_ts: float | None = None) -> FrameSample:
        now = time.monotonic()
        with self._lock:
            self.received += 1
            self.seq += 1
            sample = FrameSample(
                jpeg=jpeg,
                seq=self.seq,
                received_at=now,
                source=source,
                url=url,
                decode_at=now,
                source_ts=source_ts,
            )
            self._items.append(sample)
            while len(self._items) > self.maxsize:
                self._items.popleft()
                self.dropped += 1
            return sample

    def latest(self) -> FrameSample | None:
        with self._lock:
            return self._items[-1] if self._items else None

    def take(self) -> FrameSample | None:
        with self._lock:
            if not self._items:
                return None
            return self._items.pop()

    def depth(self) -> int:
        with self._lock:
            return len(self._items)

    def snapshot(self) -> dict[str, Any]:
        latest = self.latest()
        now = time.monotonic()
        return {
            "name": self.name,
            "depth": self.depth(),
            "maxsize": self.maxsize,
            "dropped": self.dropped,
            "received": self.received,
            "seq": latest.seq if latest else 0,
            "age_ms": latest.age_ms(now) if latest else None,
            "source": latest.source if latest else "",
        }
