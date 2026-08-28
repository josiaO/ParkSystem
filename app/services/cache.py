"""Short-lived TTL caches for snapshots, health, and dashboard summaries."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable


class TtlCache:
    def __init__(self, ttl_seconds: float = 2.0, maxsize: int = 64):
        self.ttl = float(ttl_seconds)
        self.maxsize = int(maxsize)
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Any | None:
        with self._lock:
            row = self._data.get(key)
            if row is None:
                self.misses += 1
                return None
            expires, value = row
            if expires < time.monotonic():
                self._data.pop(key, None)
                self.misses += 1
                return None
            self.hits += 1
            return value

    def set(self, key: str, value: Any, ttl: float | None = None) -> Any:
        with self._lock:
            if len(self._data) >= self.maxsize:
                oldest = min(self._data, key=lambda k: self._data[k][0])
                self._data.pop(oldest, None)
            self._data[key] = (time.monotonic() + float(ttl if ttl is not None else self.ttl), value)
            return value

    def get_or_set(self, key: str, factory: Callable[[], Any], ttl: float | None = None) -> Any:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = factory()
        return self.set(key, value, ttl)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def snapshot(self) -> dict:
        with self._lock:
            size = len(self._data)
        return {"size": size, "hits": self.hits, "misses": self.misses, "ttl": self.ttl}


dashboard_cache = TtlCache(ttl_seconds=3.0, maxsize=8)
health_cache = TtlCache(ttl_seconds=1.0, maxsize=8)
url_cache = TtlCache(ttl_seconds=60.0, maxsize=32)
