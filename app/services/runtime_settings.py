"""Site settings an administrator changes on screen instead of in zirp.env.

These used to be ``SMARTPARK_*`` lines in ``zirp.env``, which meant opening a
file on the server and restarting services. They now live in the site
database (``site_settings`` row ``recognition``) and are edited under
Settings -> Recognition. The ``zirp.env`` value, when there is one, is only
the install default used until someone saves the screen.

Every Zirp process (Site Service, Recognition Worker) reads the same row, and
re-reads it every few seconds, so a change applies without a restart.

Secrets (ClickPesa keys, database password) are not here: they stay in the
protected settings and secret store, edited on their own screens.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from app.config import settings

KEY = "recognition"
_REFRESH_SECONDS = 5.0

CAPTURE_TRIGGERS = ("external", "zirp", "both")
RECEIPT_PHOTOS = ("off", "blurred", "full")

# name -> (zirp.env attribute, kind, bounds or choices)
FIELDS: dict[str, tuple[str, str, Any]] = {
    "capture_trigger": ("capture_trigger", "choice", CAPTURE_TRIGGERS),
    "public_receipt_photo": ("public_receipt_photo", "choice", RECEIPT_PHOTOS),
    "read_budget_enabled": ("read_budget_enabled", "bool", None),
    "read_budget_confident": ("read_budget_confident", "float", (0.50, 0.99)),
    "read_budget_quiet_seconds": ("read_budget_quiet_seconds", "float", (1.0, 30.0)),
    "read_budget_max_seconds": ("read_budget_max_seconds", "float", (5.0, 120.0)),
}

_lock = threading.Lock()
_cache: dict[str, Any] = {"at": 0.0, "stored": {}, "plate_validation": None}


def _env_default(name: str) -> Any:
    attr = FIELDS[name][0]
    return getattr(settings, attr, None)


def clean(name: str, value: Any) -> Any:
    """Validate one value; raises ValueError with a message for the screen."""
    if name not in FIELDS:
        raise ValueError(f"Unknown setting {name!r}")
    _, kind, rule = FIELDS[name]
    if kind == "choice":
        text = str(value or "").strip().lower()
        if text not in rule:
            raise ValueError(f"{name} must be one of: {', '.join(rule)}")
        return text
    if kind == "bool":
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number") from None
    low, high = rule
    if not low <= number <= high:
        raise ValueError(f"{name} must be between {low:g} and {high:g}")
    return number


def _read_stored() -> tuple[dict[str, Any], str | None]:
    from app.db import SessionLocal
    from app.models import SiteSetting
    from app.services.site_policy import site_policy

    with SessionLocal() as db:
        row = db.get(SiteSetting, KEY)
        stored = dict(row.value) if row is not None and isinstance(row.value, dict) else {}
        validation = str(site_policy(db).get("plate_validation") or "")
    return stored, validation


_read_stored_from_db = _read_stored        # kept for tests that stub _read_stored


def _refresh(force: bool = False) -> None:
    now = time.monotonic()
    if not force and now - float(_cache["at"]) < _REFRESH_SECONDS and _cache["at"]:
        return
    with _lock:
        if not force and now - float(_cache["at"]) < _REFRESH_SECONDS and _cache["at"]:
            return
        try:
            stored, validation = _read_stored()
        except Exception:
            # Database briefly unavailable: keep the last values (or the
            # zirp.env defaults). A lane never stops over a settings read.
            _cache["at"] = now
            return
        _cache.update(at=now, stored=stored, plate_validation=validation)


def invalidate() -> None:
    _cache["at"] = 0.0


def get(name: str) -> Any:
    """Effective value: the saved screen value, else the zirp.env default."""
    _refresh()
    stored = _cache["stored"] or {}
    if name in stored:
        try:
            return clean(name, stored[name])
        except ValueError:
            pass
    return _env_default(name)


def all_values() -> dict[str, Any]:
    _refresh(force=True)
    stored = _cache["stored"] or {}
    body = {name: get(name) for name in FIELDS}
    body["saved_on_screen"] = sorted(name for name in FIELDS if name in stored)
    body["choices"] = {"capture_trigger": list(CAPTURE_TRIGGERS), "public_receipt_photo": list(RECEIPT_PHOTOS)}
    body["limits"] = {name: list(rule) for name, (_, kind, rule) in FIELDS.items() if kind == "float"}
    return body


def save(db, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and store the given fields. Caller commits."""
    from app.models import SiteSetting

    changes = {name: clean(name, value) for name, value in payload.items() if name in FIELDS and value is not None}
    row = db.get(SiteSetting, KEY)
    current = dict(row.value) if row is not None and isinstance(row.value, dict) else {}
    current.update(changes)
    quiet = float(current.get("read_budget_quiet_seconds", _env_default("read_budget_quiet_seconds")) or 4.0)
    longest = float(current.get("read_budget_max_seconds", _env_default("read_budget_max_seconds")) or 20.0)
    if longest < quiet:
        raise ValueError("The longest time for one car can't be shorter than the quiet time.")
    if row is None:
        db.add(SiteSetting(key=KEY, value=current))
    else:
        row.value = current
    db.flush()
    invalidate()
    return changes


def site_plate_validation() -> str:
    """The site's plate rule (Settings -> Site -> Plate validation)."""
    _refresh()
    return str(_cache.get("plate_validation") or getattr(settings, "plate_validation", "") or "").upper()
