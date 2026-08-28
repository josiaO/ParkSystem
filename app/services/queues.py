"""Bounded queues. Video drops stale frames; parking events never silently drop."""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BoundedQueue:
    name: str
    maxsize: int
    overflow: str = "drop_oldest"  # drop_oldest | drop_newest | block | reject
    _items: deque = field(default_factory=deque, repr=False)
    dropped: int = 0
    enqueued: int = 0
    alert_threshold: float = 0.8
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def put(self, item: Any) -> bool:
        with self._lock:
            self.enqueued += 1
            if len(self._items) < self.maxsize:
                self._items.append(item)
                return True
            self.dropped += 1
            if self.overflow == "drop_oldest":
                if self._items:
                    self._items.popleft()
                self._items.append(item)
                return True
            if self.overflow == "drop_newest":
                return False
            if self.overflow == "reject":
                return False
            self._items.append(item)
            return True

    def get(self) -> Any | None:
        with self._lock:
            if not self._items:
                return None
            return self._items.popleft()

    def depth(self) -> int:
        with self._lock:
            return len(self._items)

    def snapshot(self) -> dict:
        depth = self.depth()
        return {
            "name": self.name,
            "depth": depth,
            "maxsize": self.maxsize,
            "overflow": self.overflow,
            "dropped": self.dropped,
            "enqueued": self.enqueued,
            "alert": depth >= int(self.maxsize * self.alert_threshold),
        }


class DurableOutbox:
    """JSONL outbox so plate/payment work survives a process restart."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.acked = 0
        self.failed = 0

    def enqueue(self, kind: str, payload: dict) -> str:
        item = {
            "id": uuid.uuid4().hex,
            "kind": kind,
            "payload": payload,
            "ts": time.time(),
        }
        line = json.dumps(item, default=str) + "\n"
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line)
        return item["id"]

    def pending(self, limit: int = 50) -> list[dict]:
        if not self.path.is_file():
            return []
        rows: list[dict] = []
        with self._lock:
            text = self.path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(rows) >= limit:
                break
        return rows

    def ack(self, item_id: str) -> None:
        with self._lock:
            if not self.path.is_file():
                return
            kept = []
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("id") == item_id:
                    self.acked += 1
                    continue
                kept.append(line)
            self.path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")

    def note_failure(self) -> None:
        self.failed += 1

    def depth(self) -> int:
        return len(self.pending(limit=10_000))

    def snapshot(self) -> dict:
        return {
            "name": "outbox",
            "depth": self.depth(),
            "acked": self.acked,
            "failed": self.failed,
            "path": str(self.path),
        }


VIDEO_FRAMES = BoundedQueue("video-frames", maxsize=1, overflow="drop_oldest")
PARKING_EVENTS = BoundedQueue("parking-events", maxsize=200, overflow="reject")
GATE_COMMANDS = BoundedQueue("gate-commands", maxsize=50, overflow="reject")

_outbox: DurableOutbox | None = None


def parking_outbox() -> DurableOutbox:
    global _outbox
    if _outbox is None:
        from app.config import settings
        _outbox = DurableOutbox(settings.data_dir / "outbox" / "parking-events.jsonl")
    return _outbox


def queue_snapshots() -> list[dict]:
    rows = [VIDEO_FRAMES.snapshot(), PARKING_EVENTS.snapshot(), GATE_COMMANDS.snapshot()]
    try:
        rows.append(parking_outbox().snapshot())
    except Exception:
        pass
    return rows
