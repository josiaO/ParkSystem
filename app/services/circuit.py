"""Circuit breakers and capped reconnect backoff with jitter.

Cameras must not reconnect in the same millisecond. Vendor SDK calls that keep
failing move CLOSED -> OPEN -> HALF_OPEN instead of spinning.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

BACKOFF_STEPS = (2.0, 5.0, 10.0, 20.0, 30.0, 30.0)


@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 5
    reset_seconds: float = 30.0
    failures: int = 0
    opened_at: float = 0.0
    state: str = "CLOSED"

    def allow(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if (time.monotonic() - self.opened_at) >= self.reset_seconds:
                self.state = "HALF_OPEN"
                return True
            return False
        return True  # HALF_OPEN: one probe

    def success(self) -> None:
        self.failures = 0
        self.state = "CLOSED"
        self.opened_at = 0.0

    def failure(self) -> None:
        self.failures += 1
        if self.state == "HALF_OPEN" or self.failures >= self.failure_threshold:
            self.state = "OPEN"
            self.opened_at = time.monotonic()

    def snapshot(self) -> dict:
        return {
            "name": self.name,
            "state": self.state,
            "failures": self.failures,
            "reset_seconds": self.reset_seconds,
        }


@dataclass
class ReconnectPolicy:
    """Per-camera reconnect with capped exponential backoff plus jitter."""

    attempts: int = 0
    next_at: float = 0.0
    last_error: str = ""
    stagger: float = field(default_factory=lambda: random.uniform(0.0, 1.5))

    def ready(self) -> bool:
        return time.monotonic() >= self.next_at

    def record_failure(self, error: str = "") -> float:
        delay = BACKOFF_STEPS[min(self.attempts, len(BACKOFF_STEPS) - 1)]
        self.attempts += 1
        jitter = random.uniform(0.0, 0.4 * delay)
        wait = delay + jitter + self.stagger
        self.next_at = time.monotonic() + wait
        self.last_error = (error or "")[:300]
        return wait

    def record_success(self) -> None:
        self.attempts = 0
        self.next_at = 0.0
        self.last_error = ""

    def snapshot(self) -> dict:
        remaining = max(0.0, round(self.next_at - time.monotonic(), 1)) if self.next_at else 0.0
        return {
            "attempts": self.attempts,
            "retry_in_seconds": remaining,
            "last_error": self.last_error,
        }


_breakers: dict[str, CircuitBreaker] = {}
_reconnects: dict[int, ReconnectPolicy] = {}


def breaker(name: str) -> CircuitBreaker:
    row = _breakers.get(name)
    if row is None:
        row = CircuitBreaker(name=name)
        _breakers[name] = row
    return row


def reconnect_for(camera_id: int) -> ReconnectPolicy:
    row = _reconnects.get(camera_id)
    if row is None:
        row = ReconnectPolicy()
        _reconnects[camera_id] = row
    return row


def all_breakers() -> list[dict]:
    return [row.snapshot() for row in _breakers.values()]
