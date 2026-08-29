"""Site locale, timezone, currency, and plate policy. Stored in site_settings."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.config import settings
from app.domain.site import DEFAULT_SITE_POLICY, PLATE_NORMALIZATION_POLICIES, PLATE_VALIDATION_POLICIES, SUPPORTED_LANGUAGES
from app.models import SiteSetting


def _bundled_defaults() -> dict[str, Any]:
    """Install defaults. This site may still ship TZS; the product does not require it."""
    body = dict(DEFAULT_SITE_POLICY)
    body["name"] = settings.site_name
    currency = str(getattr(settings, "fee_currency", "") or "").strip().upper()
    if currency:
        body["currency"] = currency
        body["currency_precision"] = 0 if currency in {"TZS", "KES", "UGX", "RWF"} else 2
    tz = str(getattr(settings, "site_timezone", "") or "").strip()
    if tz:
        body["timezone"] = tz
    locale = str(getattr(settings, "site_locale", "") or "").strip()
    if locale:
        body["locale"] = locale
        body["language"] = locale.split("-", 1)[0].lower()
    language = str(getattr(settings, "site_language", "") or "").strip().lower()
    if language:
        body["language"] = language
    plate_n = str(getattr(settings, "plate_normalization", "") or "").strip().upper()
    if plate_n in PLATE_NORMALIZATION_POLICIES:
        body["plate_normalization"] = plate_n
    plate_v = str(getattr(settings, "plate_validation", "") or "").strip().upper()
    if plate_v in PLATE_VALIDATION_POLICIES:
        body["plate_validation"] = plate_v
    return body


def site_policy(db: Session | None = None) -> dict[str, Any]:
    merged = _bundled_defaults()
    if db is None:
        return merged
    row = db.get(SiteSetting, "site")
    if row and isinstance(row.value, dict):
        for key, value in row.value.items():
            if key in DEFAULT_SITE_POLICY and value not in (None, ""):
                merged[key] = value
    lang = str(merged.get("language") or "en").split("-", 1)[0].lower()
    merged["language"] = lang if lang in SUPPORTED_LANGUAGES else "en"
    merged["currency"] = str(merged.get("currency") or "USD").upper()[:8]
    return merged


def save_site_policy(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    current = site_policy(db)
    for key in DEFAULT_SITE_POLICY:
        if key in payload and payload[key] not in (None,):
            current[key] = payload[key]
    if current.get("language"):
        lang = str(current["language"]).split("-", 1)[0].lower()
        current["language"] = lang if lang in SUPPORTED_LANGUAGES else "en"
    if current.get("plate_normalization"):
        value = str(current["plate_normalization"]).upper()
        current["plate_normalization"] = value if value in PLATE_NORMALIZATION_POLICIES else "ALNUM_UPPER"
    if current.get("plate_validation"):
        value = str(current["plate_validation"]).upper()
        current["plate_validation"] = value if value in PLATE_VALIDATION_POLICIES else "NONE"
    current["currency"] = str(current.get("currency") or "USD").upper()[:8]
    row = db.get(SiteSetting, "site")
    if row is None:
        db.add(SiteSetting(key="site", value=current))
    else:
        row.value = current
    db.commit()
    return site_policy(db)


def site_zoneinfo(policy: dict[str, Any] | None = None) -> ZoneInfo:
    name = str((policy or {}).get("timezone") or "UTC")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, Exception):
        return ZoneInfo("UTC")


def as_site_local(when: datetime, policy: dict[str, Any] | None = None) -> datetime:
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(site_zoneinfo(policy))


def format_money(amount, policy: dict[str, Any] | None = None) -> str:
    cfg = policy or DEFAULT_SITE_POLICY
    currency = str(cfg.get("currency") or "USD")
    precision = int(cfg.get("currency_precision") or 0)
    try:
        value = float(amount or 0)
    except (TypeError, ValueError):
        value = 0.0
    if precision <= 0:
        return f"{currency} {int(round(value)):,}"
    return f"{currency} {value:,.{precision}f}"
