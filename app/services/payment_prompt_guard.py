"""Limits on mobile-money payment prompts (USSD pushes).

Anyone holding a receipt QR can ask the site to push a payment prompt to a
phone number. Without limits that is a free way to spam arbitrary numbers.

- Per phone number: at most one prompt per ``phone_interval_seconds`` and
  ``phone_max_per_hour`` per hour, whichever receipt asked for it.
- Per parking session: at most ``session_max_per_hour`` prompts, so one
  receipt cannot cycle through many numbers.

Re-using a fresh pending intent (no new prompt) is not counted. Phone numbers
are kept only as a salted hash. Process-local: the Site Service runs a single
worker, and a restart only resets the budget.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque
from typing import Callable

from app.infrastructure.payments.common import normalize_msisdn


class PaymentPromptCooldown(Exception):
    def __init__(self, message: str, retry_after: float) -> None:
        super().__init__(message)
        self.retry_after = max(1.0, float(retry_after))


class PaymentPromptGuard:
    phone_interval_seconds = 60.0
    phone_max_per_hour = 5
    session_max_per_hour = 6
    hour = 3600.0
    max_keys = 20_000

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._salt = secrets.token_bytes(16)
        self._phones: dict[str, deque[float]] = defaultdict(deque)
        self._sessions: dict[int, deque[float]] = defaultdict(deque)

    def _phone_key(self, phone: str) -> str:
        e164 = normalize_msisdn(phone)  # raises ValueError for junk input
        return hashlib.sha256(self._salt + e164.encode("ascii")).hexdigest()

    def _prune(self, bucket: deque[float], now: float) -> None:
        while bucket and bucket[0] <= now - self.hour:
            bucket.popleft()

    def claim(self, phone: str, *, session_id: int) -> None:
        """Reserve one prompt, or raise PaymentPromptCooldown with a retry time."""
        key = self._phone_key(phone)
        now = self._clock()
        with self._lock:
            phone_hits = self._phones[key]
            session_hits = self._sessions[int(session_id)]
            self._prune(phone_hits, now)
            self._prune(session_hits, now)
            if phone_hits and now - phone_hits[-1] < self.phone_interval_seconds:
                raise PaymentPromptCooldown(
                    "A payment prompt was just sent to this number. Check the phone, or try again shortly.",
                    self.phone_interval_seconds - (now - phone_hits[-1]),
                )
            if len(phone_hits) >= self.phone_max_per_hour:
                raise PaymentPromptCooldown(
                    "Too many payment prompts to this number. Try again later or pay at the kiosk.",
                    phone_hits[0] + self.hour - now,
                )
            if len(session_hits) >= self.session_max_per_hour:
                raise PaymentPromptCooldown(
                    "Too many payment prompts for this receipt. Try again later or pay at the kiosk.",
                    session_hits[0] + self.hour - now,
                )
            phone_hits.append(now)
            session_hits.append(now)
            if len(self._phones) + len(self._sessions) > self.max_keys:
                for store in (self._phones, self._sessions):
                    for stale in [k for k, v in store.items() if not v or v[-1] <= now - self.hour]:
                        store.pop(stale, None)

    def reset(self) -> None:
        with self._lock:
            self._phones.clear()
            self._sessions.clear()


_guard = PaymentPromptGuard()


def guard() -> PaymentPromptGuard:
    return _guard


def reset() -> None:
    _guard.reset()
