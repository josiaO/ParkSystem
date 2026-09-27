"""Offline file backup and a scheduled cloud copy of the local database."""

from __future__ import annotations

import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import SiteSetting

BACKUP_KEY = "backup"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def default_backup_settings() -> dict[str, Any]:
    return {
        "reminder_days": 7,
        "last_offline_at": None,
        "snooze_until": None,
        "cloud_enabled": False,
        "cloud_url": "",
        "cloud_interval_hours": 24,
        "last_cloud_at": None,
        "last_cloud_ok": None,
        "last_cloud_error": "",
    }


def backup_settings(db: Session) -> dict[str, Any]:
    row = db.get(SiteSetting, BACKUP_KEY)
    current = default_backup_settings()
    stored = row.value if row is not None and isinstance(row.value, dict) else {}
    current.update({k: v for k, v in stored.items() if k in current or k == "cloud_token"})
    if "cloud_token" not in current:
        current["cloud_token"] = str(stored.get("cloud_token") or "")
    return current


def save_backup_settings(db: Session, updates: dict[str, Any]) -> dict[str, Any]:
    current = backup_settings(db)
    for key in ("reminder_days", "cloud_interval_hours"):
        if updates.get(key) is None:
            continue
        number = int(updates[key])
        if number < 1:
            raise ValueError(f"{key.replace('_', ' ')} must be at least 1")
        current[key] = number
    if updates.get("cloud_enabled") is not None:
        current["cloud_enabled"] = bool(updates["cloud_enabled"])
    if updates.get("cloud_url") is not None:
        url = str(updates["cloud_url"] or "").strip()
        if url and not (url.startswith("https://") or url.startswith("http://")):
            raise ValueError("Cloud backup address must start with http:// or https://")
        current["cloud_url"] = url
    if updates.get("cloud_token") is not None:
        current["cloud_token"] = str(updates["cloud_token"])
    if updates.get("snooze_until") is not None:
        current["snooze_until"] = updates["snooze_until"]
    row = db.get(SiteSetting, BACKUP_KEY)
    if row is None:
        db.add(SiteSetting(key=BACKUP_KEY, value=current))
    else:
        row.value = current
    db.commit()
    return current


def public_backup_status(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    cfg = backup_settings(db)
    moment = now or _now()
    last_off = _parse(cfg.get("last_offline_at"))
    snooze = _parse(cfg.get("snooze_until"))
    reminder_days = int(cfg.get("reminder_days") or 7)
    due_at = (last_off + timedelta(days=reminder_days)) if last_off else moment
    snoozed = bool(snooze and snooze > moment)
    offline_due = (not snoozed) and (last_off is None or moment >= due_at)
    if last_off is None:
        offline_message = "No offline backup has been saved on this computer yet."
    elif offline_due:
        offline_message = f"The last offline backup was {last_off.date().isoformat()}. Save a new copy."
    else:
        offline_message = f"Offline backup is up to date (last saved {last_off.date().isoformat()})."

    last_cloud = _parse(cfg.get("last_cloud_at"))
    interval = int(cfg.get("cloud_interval_hours") or 24)
    cloud_due = bool(cfg.get("cloud_enabled") and cfg.get("cloud_url")) and (
        last_cloud is None or moment >= last_cloud + timedelta(hours=interval)
    )
    return {
        "reminder_days": reminder_days,
        "last_offline_at": cfg.get("last_offline_at"),
        "offline_due": offline_due,
        "offline_message": offline_message,
        "cloud_enabled": bool(cfg.get("cloud_enabled")),
        "cloud_url": cfg.get("cloud_url") or "",
        "cloud_token_set": bool(cfg.get("cloud_token")),
        "cloud_interval_hours": interval,
        "last_cloud_at": cfg.get("last_cloud_at"),
        "last_cloud_ok": cfg.get("last_cloud_ok"),
        "last_cloud_error": cfg.get("last_cloud_error") or "",
        "cloud_due": cloud_due,
        "cloud_message": (
            "Cloud backup is due." if cloud_due
            else ("Cloud backup is scheduled." if cfg.get("cloud_enabled") and cfg.get("cloud_url")
                  else "Cloud backup is off until you add an address.")
        ),
    }


def mark_offline_saved(db: Session) -> dict[str, Any]:
    save_backup_settings(db, {"snooze_until": None})
    cfg = backup_settings(db)
    cfg["last_offline_at"] = _iso(_now())
    cfg["snooze_until"] = None
    row = db.get(SiteSetting, BACKUP_KEY)
    if row is None:
        db.add(SiteSetting(key=BACKUP_KEY, value=cfg))
    else:
        row.value = cfg
    db.commit()
    return public_backup_status(db)


def snooze_offline_reminder(db: Session, *, hours: int = 24) -> dict[str, Any]:
    until = _iso(_now() + timedelta(hours=max(1, hours)))
    save_backup_settings(db, {"snooze_until": until})
    return public_backup_status(db)


def dump_sql(db: Session) -> bytes:
    conn = db.connection().connection
    raw = getattr(conn, "driver_connection", None) or getattr(conn, "dbapi_connection", None) or conn
    if not hasattr(raw, "iterdump"):
        raise RuntimeError("This database cannot be exported as a SQL file")
    text = "\n".join(raw.iterdump())
    return text.encode("utf-8")


def push_cloud_backup(db: Session) -> dict[str, Any]:
    cfg = backup_settings(db)
    url = str(cfg.get("cloud_url") or "").strip()
    if not cfg.get("cloud_enabled") or not url:
        raise ValueError("Turn on cloud backup and set an address first")
    body = dump_sql(db)
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/sql")
    token = str(cfg.get("cloud_token") or "")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    error = ""
    ok = False
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            ok = 200 <= int(response.status) < 300
            if not ok:
                error = f"Cloud backup returned {response.status}"
    except urllib.error.HTTPError as exc:
        error = f"Cloud backup returned {exc.code}"
    except Exception as exc:
        error = str(exc) or "Cloud backup failed"
    cfg["last_cloud_at"] = _iso(_now())
    cfg["last_cloud_ok"] = ok
    cfg["last_cloud_error"] = "" if ok else error
    row = db.get(SiteSetting, BACKUP_KEY)
    if row is None:
        db.add(SiteSetting(key=BACKUP_KEY, value=cfg))
    else:
        row.value = cfg
    db.commit()
    status = public_backup_status(db)
    status["ok"] = ok
    if not ok:
        raise RuntimeError(error or "Cloud backup failed")
    return status


def backup_filename(now: datetime | None = None) -> str:
    stamp = (now or _now()).strftime("%Y%m%d-%H%M")
    return f"smartpark-backup-{stamp}.sql"
