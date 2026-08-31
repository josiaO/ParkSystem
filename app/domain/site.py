"""Site identity and locale. Product defaults are not Tanzania-specific."""

from __future__ import annotations

from typing import Any


DEFAULT_SITE_ID = 1

DEFAULT_SITE_POLICY: dict[str, Any] = {
    "site_id": DEFAULT_SITE_ID,
    "name": "Parking Site",
    "timezone": "UTC",
    "locale": "en",
    "language": "en",
    "currency": "USD",
    "currency_precision": 2,
    "date_format": "YYYY-MM-DD",
    "time_format": "HH:mm:ss",
    "distance_units": "metric",
    "plate_normalization": "ALNUM_UPPER",
    "plate_validation": "NONE",
    "tax_behavior": "NONE",
    "branding": "",
    "support_contacts": "",
    "public_base_url": "",
}

# Named validators a site may opt into. NONE is the product default.
PLATE_VALIDATION_POLICIES = ("NONE", "TZ", "KE", "ZA", "AE", "CUSTOM")
PLATE_NORMALIZATION_POLICIES = ("ALNUM_UPPER", "UPPER_STRIP", "AS_READ")
SUPPORTED_LANGUAGES = ("en", "sw", "ar", "fr", "pt")
