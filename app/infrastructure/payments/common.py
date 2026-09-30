"""Shared helpers for external payment providers.

Money is handled as Decimal (or integer minor units); phone numbers are
normalised to E.164; secrets are never echoed back in responses or logs.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
import secrets
import time
from typing import Any

ZERO_DECIMAL_CURRENCIES = {"TZS", "UGX", "RWF", "XAF", "XOF", "JPY", "KRW"}
_SECRET_KEY_HINTS = ("secret", "key", "token", "hash", "authorization", "password", "pin", "signature", "checksum")
_PHONE_KEY_HINTS = ("phone", "msisdn", "mobile")


def to_decimal(value: Any, default: Decimal | None = None) -> Decimal:
    """Parse provider/user input into Decimal without going through float."""
    if isinstance(value, Decimal):
        return value
    if value is None or value == "":
        if default is not None:
            return default
        raise ValueError("amount is required")
    if isinstance(value, bool):
        raise ValueError("amount must be numeric")
    if isinstance(value, float):
        value = repr(value)
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid amount: {value!r}") from exc


def quantize_amount(amount: Decimal, currency: str) -> Decimal:
    places = Decimal("1") if (currency or "").upper() in ZERO_DECIMAL_CURRENCIES else Decimal("0.01")
    return amount.quantize(places, rounding=ROUND_HALF_UP)


def to_minor_units(amount: Any, currency: str) -> int:
    amt = quantize_amount(to_decimal(amount), currency)
    scale = 1 if (currency or "").upper() in ZERO_DECIMAL_CURRENCIES else 100
    return int(amt * scale)


def amount_string(amount: Any, currency: str) -> str:
    """Provider-facing amount string: '1500' for TZS, '15.50' for cent currencies."""
    amt = quantize_amount(to_decimal(amount), currency)
    return format(amt, "f")


def normalize_msisdn(raw: str, *, default_country: str = "255") -> str:
    """Return E.164 ('+2557XXXXXXXX') or raise ValueError.

    Accepts 07XXXXXXXX, 7XXXXXXXX, 2557XXXXXXXX, +2557XXXXXXXX and common
    separators. Country-neutral: the default country only applies to local
    numbers (leading 0 or bare subscriber digits).
    """
    digits = re.sub(r"[^\d+]", "", raw or "")
    if not digits:
        raise ValueError("phone number is required")
    if digits.startswith("+"):
        digits = digits[1:]
        if not digits.isdigit():
            raise ValueError("invalid phone number")
    elif digits.startswith("00"):
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = default_country + digits[1:]
    elif len(digits) == 9:
        digits = default_country + digits
    if not digits.isdigit() or not (10 <= len(digits) <= 15):
        raise ValueError("invalid phone number")
    return "+" + digits


def msisdn_digits(e164: str) -> str:
    """'+255712345678' -> '255712345678' (ClickPesa/Flutterwave wire format)."""
    return e164.lstrip("+")


def msisdn_local(e164: str, *, country: str = "255") -> str:
    """'+255712345678' -> '0712345678' when the number is in *country*."""
    digits = msisdn_digits(e164)
    if digits.startswith(country):
        return "0" + digits[len(country):]
    return digits


def mask_msisdn(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) <= 4:
        return "***"
    return f"{'*' * (len(digits) - 3)}{digits[-3:]}"


def new_reference(prefix: str = "SP") -> str:
    """Provider-facing unique reference (tx_ref / orderReference). <= 40 chars."""
    return f"{prefix}-{int(time.time())}-{secrets.token_hex(6).upper()}"


def redact(value: Any, *, _depth: int = 0) -> Any:
    """Deep-copy *value* masking secrets and phone numbers. Safe for API/logs."""
    if _depth > 8:
        return "…"
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            k = str(key)
            kl = k.lower()
            if any(h in kl for h in _SECRET_KEY_HINTS):
                out[k] = "***" if item not in (None, "") else item
            elif any(h in kl for h in _PHONE_KEY_HINTS) and isinstance(item, (str, int)):
                out[k] = mask_msisdn(str(item))
            else:
                out[k] = redact(item, _depth=_depth + 1)
        return out
    if isinstance(value, list):
        return [redact(v, _depth=_depth + 1) for v in value[:50]]
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes>"
    return value


def scrub_text(text: str, *secrets_: str) -> str:
    """Remove known secret material from free text (exceptions, error bodies)."""
    out = text or ""
    for s in secrets_:
        if s and len(s) >= 6:
            out = out.replace(s, "***")
    return out[:600]


class ProviderError(RuntimeError):
    """Raised by provider adapters; message is already redacted."""

    def __init__(self, message: str, *, code: str = "provider_error", retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class ProviderHTTP:
    """Small async JSON client with timeout + circuit breaker.

    Kept deliberately thin so tests can replace ``request`` with a fake.
    """

    def __init__(self, name: str, *, timeout: float = 8.0, secrets_: tuple[str, ...] = ()):
        self.name = name
        self.timeout = float(timeout)
        self._secrets = tuple(s for s in secrets_ if s)
        from app.services.circuit import breaker

        self.breaker = breaker(f"payments-{name}")

    async def request(self, method: str, url: str, *, headers: dict | None = None, json: Any = None) -> tuple[int, Any]:
        if not self.breaker.allow():
            raise ProviderError(f"{self.name} circuit open", code="circuit_open", retryable=True)
        try:
            import httpx

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.request(method, url, headers=headers, json=json)
        except Exception as exc:  # network / timeout
            self.breaker.failure()
            raise ProviderError(
                scrub_text(f"{self.name} unreachable: {type(exc).__name__}", *self._secrets),
                code="unreachable",
                retryable=True,
            ) from exc
        try:
            body = res.json()
        except Exception:
            body = {"raw": scrub_text(res.text, *self._secrets)}
        if res.status_code >= 500:
            self.breaker.failure()
        else:
            self.breaker.success()
        return res.status_code, body
