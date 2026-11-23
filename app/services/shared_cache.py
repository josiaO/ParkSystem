"""Shared fast cache: a local Redis service when there is one, memory otherwise.

The Site Service and the Recognition Worker are separate processes. Some
short-lived lane facts (how often the car at a camera has been read, the plate
it settled on) have to be the same in both, or each process makes its own
decision about the same car. A Redis service on 127.0.0.1, installed with
Zirp, holds those facts.

Nothing here is a record. PostgreSQL stays the source of truth; every key has
a short expiry, and if Redis is missing, stopped or slow the cache silently
falls back to this process's memory and tries Redis again a few seconds later.
A lane never waits on Redis for more than a fraction of a second.

The client speaks the Redis protocol directly (GET/SET/DEL and a lock), so it
needs no extra package in the installer.
"""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from contextlib import contextmanager
from urllib.parse import unquote, urlparse

log = logging.getLogger(__name__)

PREFIX = "zirp:"
_TIMEOUT = 0.25          # seconds per Redis call; the lane must never wait long
_RETRY_AFTER = 5.0       # after a failure, use memory this long before retrying


class RedisError(Exception):
    pass


class _RespClient:
    """Minimal synchronous Redis (RESP2) client for a handful of commands."""

    def __init__(self, url: str, timeout: float = _TIMEOUT) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"redis", ""}:
            raise ValueError(f"unsupported cache URL scheme {parsed.scheme!r}")
        self.host = parsed.hostname or "127.0.0.1"
        self.port = int(parsed.port or 6379)
        self.password = unquote(parsed.password) if parsed.password else ""
        self.username = unquote(parsed.username) if parsed.username else ""
        path = (parsed.path or "").strip("/")
        self.db = int(path) if path.isdigit() else 0
        self.timeout = float(timeout)
        self._sock: socket.socket | None = None
        self._buf = b""

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        self._sock = None
        self._buf = b""

    def _connect(self) -> None:
        sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        sock.settimeout(self.timeout)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._sock = sock
        self._buf = b""
        if self.password:
            args = ("AUTH", self.username, self.password) if self.username else ("AUTH", self.password)
            self._call(*args)
        if self.db:
            self._call("SELECT", str(self.db))

    def command(self, *args):
        if self._sock is None:
            self._connect()
        try:
            return self._call(*args)
        except (OSError, RedisError):
            self.close()
            raise

    def _call(self, *args):
        parts = [b"*%d\r\n" % len(args)]
        for arg in args:
            data = arg if isinstance(arg, bytes) else str(arg).encode("utf-8")
            parts.append(b"$%d\r\n%s\r\n" % (len(data), data))
        assert self._sock is not None
        self._sock.sendall(b"".join(parts))
        return self._reply()

    def _line(self) -> bytes:
        while b"\r\n" not in self._buf:
            chunk = self._sock.recv(65536) if self._sock else b""
            if not chunk:
                raise RedisError("connection closed")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\r\n", 1)
        return line

    def _exact(self, n: int) -> bytes:
        while len(self._buf) < n + 2:
            chunk = self._sock.recv(65536) if self._sock else b""
            if not chunk:
                raise RedisError("connection closed")
            self._buf += chunk
        data, self._buf = self._buf[:n], self._buf[n + 2:]
        return data

    def _reply(self):
        line = self._line()
        kind, rest = line[:1], line[1:]
        if kind == b"+":
            return rest.decode()
        if kind == b"-":
            raise RedisError(rest.decode(errors="replace"))
        if kind == b":":
            return int(rest)
        if kind == b"$":
            size = int(rest)
            return None if size < 0 else self._exact(size)
        if kind == b"*":
            size = int(rest)
            return None if size < 0 else [self._reply() for _ in range(size)]
        raise RedisError(f"unexpected reply {line[:20]!r}")


class SharedCache:
    """Short-lived shared values with a memory fallback."""

    def __init__(self, url: str | None = None) -> None:
        self._url = url
        self._client: _RespClient | None = None
        self._client_url = ""
        self._io = threading.Lock()
        self._memory: dict[str, tuple[float, str]] = {}
        self._mem_lock = threading.Lock()
        self._local_locks: dict[str, threading.Lock] = {}
        self._down_until = 0.0
        self.last_error = ""

    # -- backend selection -------------------------------------------------
    def _configured_url(self) -> str:
        if self._url is not None:
            return self._url
        try:
            from app.config import settings

            return str(getattr(settings, "redis_url", "") or "").strip()
        except Exception:
            return ""

    def _redis(self, *args):
        """Run one Redis command, or raise LookupError to use memory."""
        url = self._configured_url()
        if not url:
            raise LookupError("no shared cache configured")
        if time.monotonic() < self._down_until:
            raise LookupError("shared cache unavailable")
        with self._io:
            try:
                if self._client is None or self._client_url != url:
                    if self._client is not None:
                        self._client.close()
                    self._client = _RespClient(url)
                    self._client_url = url
                return self._client.command(*args)
            except (OSError, RedisError, ValueError) as exc:
                if self._client is not None:
                    self._client.close()
                self._down_until = time.monotonic() + _RETRY_AFTER
                if self.last_error != str(exc):
                    log.warning("shared cache unavailable, using memory: %s", exc)
                self.last_error = str(exc)
                raise LookupError(str(exc)) from exc

    def backend(self) -> str:
        """``redis`` when Redis answers now, else ``memory``."""
        try:
            return "redis" if self._redis("PING") in {"PONG", b"PONG"} else "memory"
        except LookupError:
            return "memory"

    # -- values -------------------------------------------------------------
    def get(self, key: str) -> str | None:
        key = PREFIX + key
        try:
            value = self._redis("GET", key)
            return value.decode("utf-8") if isinstance(value, bytes) else value
        except LookupError:
            pass
        with self._mem_lock:
            item = self._memory.get(key)
            if item is None:
                return None
            if item[0] and item[0] < time.monotonic():
                self._memory.pop(key, None)
                return None
            return item[1]

    def set(self, key: str, value: str, *, ttl: float) -> None:
        key = PREFIX + key
        ttl_ms = max(1, int(float(ttl) * 1000))
        try:
            self._redis("SET", key, value, "PX", str(ttl_ms))
            return
        except LookupError:
            pass
        with self._mem_lock:
            self._memory[key] = (time.monotonic() + ttl_ms / 1000.0, value)
            if len(self._memory) > 5000:
                now = time.monotonic()
                for stale in [k for k, (exp, _) in self._memory.items() if exp and exp < now]:
                    self._memory.pop(stale, None)

    def delete(self, key: str) -> None:
        key = PREFIX + key
        try:
            self._redis("DEL", key)
        except LookupError:
            pass
        with self._mem_lock:
            self._memory.pop(key, None)

    def get_json(self, key: str):
        raw = self.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            return None

    def set_json(self, key: str, value, *, ttl: float) -> None:
        self.set(key, json.dumps(value, separators=(",", ":")), ttl=ttl)

    # -- locking ------------------------------------------------------------
    @contextmanager
    def lock(self, key: str, *, ttl: float = 1.0, wait: float = 0.3):
        """Short cross-process lock. Never blocks a lane longer than ``wait``.

        If the lock can't be had in time the body still runs: a rare double
        decision is better than a lane that stops reading.
        """
        local = self._local_locks.setdefault(key, threading.Lock())
        got_local = local.acquire(timeout=wait)
        token = f"{id(self)}:{time.monotonic_ns()}"
        full = PREFIX + key + ":lock"
        held_remote = False
        try:
            deadline = time.monotonic() + wait
            while True:
                try:
                    if self._redis("SET", full, token, "NX", "PX", str(max(1, int(ttl * 1000)))) is not None:
                        held_remote = True
                        break
                except LookupError:
                    break
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.005)
            yield
        finally:
            if held_remote:
                try:
                    if self._redis("GET", full) in {token, token.encode()}:
                        self._redis("DEL", full)
                except LookupError:
                    pass
            if got_local:
                local.release()

    def clear_memory(self) -> None:
        with self._mem_lock:
            self._memory.clear()


cache = SharedCache()
