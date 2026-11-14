"""Brute-force protection for password sign-in (``/auth/login``, ``/auth/token``).

Failures are counted per client IP and per username (case-insensitive) in a
sliding window. After a few free failures each further failure doubles the
wait, capped at a short lockout, so a mistyped password costs seconds and an
online guessing attack costs hours. While a key is blocked the password is not
checked at all, so the response does not reveal whether a guess was right.

A successful sign-in clears that account's counter but not the client's: one
valid account must not reset the budget for spraying other accounts.

Process-local by design: the Site Service runs one Uvicorn worker. The client
IP is the TCP peer, never X-Forwarded-For (which a client could rotate);
login is not reachable through the public payments ingress.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class _Entry:
    failures: deque[float] = field(default_factory=deque)
    blocked_until: float = 0.0


class LoginThrottle:
    window_seconds = 15 * 60.0
    user_free_failures = 5
    ip_free_failures = 20
    base_delay_seconds = 2.0
    max_lockout_seconds = 5 * 60.0
    max_keys = 10_000

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: dict[str, _Entry] = {}

    @staticmethod
    def _keys(ip: str, username: str) -> tuple[str, str]:
        return f"ip:{(ip or 'unknown').strip()}", f"user:{(username or '').strip().lower()}"

    def _prune(self, entry: _Entry, now: float) -> None:
        cutoff = now - self.window_seconds
        while entry.failures and entry.failures[0] <= cutoff:
            entry.failures.popleft()

    def check(self, ip: str, username: str) -> float:
        """Seconds the caller must wait before a password may be checked (0 = go)."""
        now = self._clock()
        with self._lock:
            waits = [
                entry.blocked_until - now
                for key in self._keys(ip, username)
                if (entry := self._entries.get(key)) is not None
            ]
        return max([0.0, *waits])

    def record_failure(self, ip: str, username: str) -> None:
        now = self._clock()
        ip_key, user_key = self._keys(ip, username)
        with self._lock:
            for key, free in ((ip_key, self.ip_free_failures), (user_key, self.user_free_failures)):
                entry = self._entries.setdefault(key, _Entry())
                if entry.blocked_until > now:
                    continue  # attempts while blocked never reached the password check
                self._prune(entry, now)
                entry.failures.append(now)
                excess = len(entry.failures) - free
                if excess >= 0:
                    delay = min(self.max_lockout_seconds, self.base_delay_seconds * (2 ** excess))
                    entry.blocked_until = now + delay
            self._bound(now)

    def record_success(self, ip: str, username: str) -> None:
        _ip_key, user_key = self._keys(ip, username)
        with self._lock:
            self._entries.pop(user_key, None)

    def _bound(self, now: float) -> None:
        if len(self._entries) <= self.max_keys:
            return
        for key in [k for k, e in self._entries.items() if e.blocked_until <= now and not e.failures]:
            self._entries.pop(key, None)
        if len(self._entries) > self.max_keys:
            oldest = sorted(self._entries.items(), key=lambda item: item[1].failures[-1] if item[1].failures else 0.0)
            for key, _ in oldest[: len(self._entries) - self.max_keys]:
                self._entries.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._entries.clear()


_throttle = LoginThrottle()


def throttle() -> LoginThrottle:
    return _throttle


def reset() -> None:
    """Clear all counters (tests, or an operator unlocking after an incident)."""
    _throttle.reset()
