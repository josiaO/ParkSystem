"""One redaction implementation for API responses, logs, exceptions and diagnostics.

Two layers:

* **Pattern** redaction – URL credentials (``rtsp://user:pass@``), ``key=value``
  pairs for password/secret/token-like keys, and well-known key formats
  (Flutterwave ``FLWSECK-…``, Google ``AIza…``, generic ``sk-…``).
* **Known-value** redaction – every configured secret (provider keys, webhook
  hashes, camera passwords resolved at runtime) is registered and replaced
  wherever it appears verbatim.

Use ``redact_text`` for strings, ``redact_obj`` for JSON-like structures,
``RedactingFilter`` on log handlers, and the FastAPI exception handlers in
``api_main`` for error bodies.
"""

from __future__ import annotations

import logging
import re
import threading
from typing import Any

MASK = "***"
_MIN_SECRET_LEN = 6
_COMMON_VALUES = {"admin", "password", "changeme", "secret", "123456", "12345678"}

_URL_CRED = re.compile(r"(\b[a-z][a-z0-9+.-]*://[^/\s:@]+):([^@\s/]+)@", re.IGNORECASE)
_KV = re.compile(
    r"(?i)\b(password|passwd|pwd|secret(?:_?key|_?hash)?|api[_-]?key|access[_-]?token|token|verif[_-]?hash|"
    r"checksum(?:_?key)?|client[_-]?secret|authorization)\b(\s*[=:]\s*)(\"?)([^&\s,;\"']+)"
)
_KEY_FORMATS = re.compile(
    r"\b(FLWSECK(?:_TEST)?-[A-Za-z0-9-]{8,}|FLWPUBK(?:_TEST)?-[A-Za-z0-9-]{8,}|AIza[0-9A-Za-z_-]{20,}|"
    r"sk-[A-Za-z0-9_-]{16,}|Bearer\s+[A-Za-z0-9._-]{16,})"
)
_SECRET_KEY_HINTS = ("secret", "password", "passwd", "apikey", "authorization", "signature")
_SECRET_KEY_PARTS = {"token", "hash", "pin", "checksum", "credential", "credentials", "apikey", "passphrase"}
_PHONE_KEYS = {"phone", "msisdn", "mobile", "phone_number", "phonenumber", "mobile_number", "customer_phone",
               "payer_phone", "phone_e164"}
_PASSTHROUGH_KEYS = {"token_cached", "webhook_secret_configured", "checksum_configured", "public_token",
                     "credentials_ref", "secret_store", "secrets_backend", "hash_algorithm", "tokens"}

_lock = threading.Lock()
_registered: set[str] = set()


def register_secret(value: str | None) -> None:
    """Remember a runtime secret (camera password, provider key) for verbatim masking."""
    text = (value or "").strip()
    if len(text) < _MIN_SECRET_LEN or text.lower() in _COMMON_VALUES:
        return
    with _lock:
        _registered.add(text)


def forget_all_secrets() -> None:
    """Tests only."""
    with _lock:
        _registered.clear()


def _settings_secrets() -> list[str]:
    try:
        from app.config import settings
    except Exception:  # pragma: no cover - config import failure is fatal elsewhere
        return []
    names = (
        "flutterwave_secret_key", "flutterwave_secret_hash", "clickpesa_api_key", "clickpesa_checksum_key",
        "clickpesa_client_id", "mobile_money_webhook_secret", "gemini_api_key", "bootstrap_password",
        "hvx_host_token", "api_secret",
    )
    out = []
    for name in names:
        value = getattr(settings, name, "")
        if isinstance(value, str) and len(value.strip()) >= _MIN_SECRET_LEN and value.lower() not in _COMMON_VALUES:
            out.append(value.strip())
    return out


def known_secrets() -> list[str]:
    with _lock:
        values = set(_registered)
    values.update(_settings_secrets())
    # longest first so a key does not get partially masked by a shorter secret
    return sorted(values, key=len, reverse=True)


def mask_msisdn(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) <= 4:
        return MASK
    return f"{'*' * (len(digits) - 3)}{digits[-3:]}"


def redact_text(text: Any, *, extra: tuple[str, ...] = ()) -> str:
    """Mask secrets in free text. Safe to call on non-strings (they are str()-ed)."""
    if text is None:
        return ""
    out = text if isinstance(text, str) else str(text)
    if not out:
        return out
    for value in known_secrets() + [v for v in extra if v and len(v) >= _MIN_SECRET_LEN]:
        if value in out:
            out = out.replace(value, MASK)
    out = _URL_CRED.sub(rf"\1:{MASK}@", out)
    out = _KV.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}{MASK}", out)
    out = _KEY_FORMATS.sub(lambda m: m.group(1).split(" ")[0] + " " + MASK if m.group(1).startswith("Bearer") else MASK, out)
    return out


def _is_secret_key(key: str) -> bool:
    kl = key.lower()
    if kl in _PASSTHROUGH_KEYS or kl.endswith(("_redacted", "_configured", "_present", "_cached", "_masked")):
        return False
    if any(h in kl for h in _SECRET_KEY_HINTS):
        return True
    parts = [p for p in re.split(r"[_\-\s.]+", kl) if p]
    if any(p in _SECRET_KEY_PARTS for p in parts):
        return True
    # "api_key", "secret_key", "private_key", "access_key" but not "idempotency_key"
    return "key" in parts and any(p in ("api", "secret", "private", "access", "client", "webhook", "checksum") for p in parts)


def _is_phone_key(kl: str) -> bool:
    if kl.endswith("_masked") or kl.endswith("_redacted"):
        return False
    return kl in _PHONE_KEYS or kl.endswith("_phone") or kl.endswith("_msisdn")


def redact_obj(value: Any, *, _depth: int = 0) -> Any:
    """Deep copy of *value* with secret-like keys masked and strings pattern-redacted."""
    if _depth > 10:
        return "…"
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            k = str(key)
            kl = k.lower()
            if _is_secret_key(k):
                out[k] = MASK if item not in (None, "", False) else item
            elif _is_phone_key(kl) and isinstance(item, (str, int)):
                out[k] = mask_msisdn(str(item))
            else:
                out[k] = redact_obj(item, _depth=_depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [redact_obj(v, _depth=_depth + 1) for v in list(value)[:200]]
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes>"
    if isinstance(value, str):
        return redact_text(value)
    return value


class RedactingFilter(logging.Filter):
    """Masks secrets in log records before any handler formats them."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = redact_text(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {k: redact_text(v) if isinstance(v, str) else v for k, v in record.args.items()}
                else:
                    record.args = tuple(redact_text(a) if isinstance(a, str) else a for a in record.args)
            if record.exc_text:
                record.exc_text = redact_text(record.exc_text)
        except Exception:  # never let redaction break logging
            pass
        return True


def install_logging_redaction(*loggers: logging.Logger) -> None:
    filt = RedactingFilter()
    for log in loggers or (logging.getLogger(),):
        if not any(isinstance(f, RedactingFilter) for f in log.filters):
            log.addFilter(filt)
        for handler in log.handlers:
            if not any(isinstance(f, RedactingFilter) for f in handler.filters):
                handler.addFilter(filt)
