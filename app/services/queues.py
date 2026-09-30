"""Bounded queues. Video drops stale frames; parking events never silently drop."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from collections import deque
from contextlib import contextmanager
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


class SQLiteOutbox:
    """Process-safe durable queue. Acknowledgements delete only their own row.

    The Site Service is the sole consumer; any process may enqueue events.
    Legacy JSONL is imported once transactionally and retained for rollback.
    """

    PROCESSED_RETENTION_SECONDS = 7 * 24 * 3600.0

    def __init__(self, path: Path, *, legacy_path: Path | None = None):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.acked = 0
        self.failed = 0
        self.duplicates = 0
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE, kind TEXT NOT NULL, payload TEXT NOT NULL, ts REAL NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            # Business-event idempotency that survives a crash between "processed"
            # and "acknowledged": the ack and the processed mark commit together.
            db.execute("CREATE TABLE IF NOT EXISTS processed (key TEXT PRIMARY KEY, ts REAL NOT NULL)")
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM metadata WHERE key = 'legacy_imported'").fetchone():
                if legacy_path is not None and legacy_path.is_file():
                    for line in legacy_path.read_text(encoding="utf-8").splitlines():
                        if not line.strip():
                            continue
                        row = json.loads(line)
                        db.execute("INSERT OR IGNORE INTO events (id, kind, payload, ts) VALUES (?, ?, ?, ?)",
                                   (row["id"], row["kind"], json.dumps(row["payload"]), float(row["ts"])))
                db.execute("INSERT INTO metadata (key, value) VALUES ('legacy_imported', '1')")

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=5.0)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def enqueue(self, kind: str, payload: dict) -> str:
        item_id = uuid.uuid4().hex
        with self._connect() as db:
            db.execute("INSERT INTO events (id, kind, payload, ts) VALUES (?, ?, ?, ?)",
                       (item_id, kind, json.dumps(payload, default=str), time.time()))
        return item_id

    def pending(self, limit: int = 50) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("SELECT id, kind, payload, ts FROM events ORDER BY sequence LIMIT ?", (max(0, int(limit)),)).fetchall()
        return [{"id": row[0], "kind": row[1], "payload": json.loads(row[2]), "ts": row[3]} for row in rows]

    def ack(self, item_id: str, *, processed_key: str | None = None) -> None:
        """Delete the row and, atomically, remember ``processed_key`` as done."""
        with self._connect() as db:
            cursor = db.execute("DELETE FROM events WHERE id = ?", (item_id,))
            self.acked += cursor.rowcount
            if processed_key:
                now = time.time()
                db.execute("INSERT OR REPLACE INTO processed (key, ts) VALUES (?, ?)", (str(processed_key), now))
                db.execute("DELETE FROM processed WHERE ts < ?", (now - self.PROCESSED_RETENTION_SECONDS,))

    def was_processed(self, key: str | None) -> bool:
        if not key:
            return False
        with self._connect() as db:
            hit = db.execute("SELECT 1 FROM processed WHERE key = ?", (str(key),)).fetchone()
        if hit:
            self.duplicates += 1
        return bool(hit)

    def note_failure(self) -> None:
        self.failed += 1

    def depth(self) -> int:
        with self._connect() as db:
            return db.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    def snapshot(self) -> dict:
        return {"name": "outbox", "backend": "sqlite", "depth": self.depth(),
                "acked": self.acked, "failed": self.failed, "duplicates": self.duplicates, "path": str(self.path)}


VIDEO_FRAMES = BoundedQueue("video-frames", maxsize=1, overflow="drop_oldest")
AI_FRAMES = BoundedQueue("ai-frames", maxsize=1, overflow="drop_oldest")
PARKING_EVENTS = BoundedQueue("parking-events", maxsize=200, overflow="reject")
GATE_COMMANDS = BoundedQueue("gate-commands", maxsize=50, overflow="reject")

_outbox: SQLiteOutbox | None = None


def parking_outbox() -> SQLiteOutbox:
    global _outbox
    if _outbox is None:
        from app.config import settings
        folder = settings.data_dir / "outbox"
        _outbox = SQLiteOutbox(folder / "parking-events.sqlite3", legacy_path=folder / "parking-events.jsonl")
    return _outbox


def queue_snapshots() -> list[dict]:
    rows = [VIDEO_FRAMES.snapshot(), AI_FRAMES.snapshot(), PARKING_EVENTS.snapshot(), GATE_COMMANDS.snapshot()]
    try:
        rows.append(parking_outbox().snapshot())
    except Exception:
        pass
    return rows
