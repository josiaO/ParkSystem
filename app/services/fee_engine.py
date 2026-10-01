"""Car1 tariff, run locally on SQLite (PostgreSQL later).

Numbers follow the live Car1 day/night blocks: ``1 + seconds//block`` then
``if result > 1000: result -= 1000``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.domain.site import DEFAULT_SITE_ID
from app.models import Tariff

# Car1 constants (seconds / integer amounts).
CAR1_RULES: dict[str, Any] = {
    "source": "Car1",
    "currency": "TZS",
    "day_start": "05:05:00",
    "day_end": "23:05:00",
    "free_day_seconds": 2700,
    "free_night_seconds": 2100,
    "day_block_seconds": 2700,
    "night_block_seconds": 2100,
    "day_block_fee": 1000,
    "night_block_fee": 1000,
    "day_max": 22000,
    "night_max": 14000,
    "daily_wrap_fee": 34000,
    "over_1000_subtract": 1000,
}


@dataclass
class FeeResult:
    duration_seconds: int
    due: int
    currency: str
    car_type: str
    breakdown: list[str]


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_hms(value: str) -> time:
    parts = [int(p) for p in str(value).split(":")[:3]]
    while len(parts) < 3:
        parts.append(0)
    return time(parts[0], parts[1], parts[2])


def is_daytime(when: datetime, rules: dict[str, Any] | None = None) -> bool:
    rules = rules or CAR1_RULES
    dt = _aware(when)
    tz_name = str(rules.get("timezone") or "")
    if tz_name:
        try:
            from zoneinfo import ZoneInfo
            dt = dt.astimezone(ZoneInfo(tz_name))
        except Exception:
            pass
    start = _parse_hms(str(rules["day_start"]))
    end = _parse_hms(str(rules["day_end"]))
    clock = dt.timetz().replace(tzinfo=None)
    return start <= clock < end


def _blocks(seconds: int, block: int) -> int:
    if seconds <= 0 or block <= 0:
        return 0
    return 1 + (int(seconds) // int(block))


def _next_boundary(when: datetime, rules: dict[str, Any]) -> datetime:
    dt = _aware(when)
    start = datetime.combine(dt.date(), _parse_hms(str(rules["day_start"])), dt.tzinfo)
    end = datetime.combine(dt.date(), _parse_hms(str(rules["day_end"])), dt.tzinfo)
    if dt < start:
        return start
    if dt < end:
        return end
    return start + timedelta(days=1)


def _charge_span(start: datetime, end: datetime, rules: dict[str, Any]) -> tuple[int, list[str]]:
    notes: list[str] = []
    total = 0
    cursor = _aware(start)
    finish = _aware(end)
    while cursor < finish:
        boundary = _next_boundary(cursor, rules)
        chunk_end = min(finish, boundary)
        seconds = int((chunk_end - cursor).total_seconds())
        if seconds > 0:
            if is_daytime(cursor, rules):
                blocks = _blocks(seconds, int(rules["day_block_seconds"]))
                part = blocks * int(rules["day_block_fee"])
                notes.append(f"day:{seconds}s/{blocks}blk={part}")
            else:
                blocks = _blocks(seconds, int(rules["night_block_seconds"]))
                part = blocks * int(rules["night_block_fee"])
                notes.append(f"night:{seconds}s/{blocks}blk={part}")
            total += part
        cursor = chunk_end
    return total, notes


def calculate_car1_fee(
    entry_time: datetime,
    exit_time: datetime,
    rules: dict[str, Any] | None = None,
) -> FeeResult:
    rules = dict(CAR1_RULES if rules is None else {**CAR1_RULES, **_class_overlay(rules)})
    start = _aware(entry_time)
    end = _aware(exit_time)
    if end < start:
        start, end = end, start
    duration = int((end - start).total_seconds())
    currency = str(rules.get("currency") or settings.fee_currency)
    notes = [f"duration:{duration}s"]
    free = int(rules["free_day_seconds"] if is_daytime(end, rules) else rules["free_night_seconds"])
    notes.append(f"free:{free}s")
    if duration <= free:
        return FeeResult(duration, 0, currency, "Car1", notes + ["grace"])

    full_days = duration // 86400
    remainder_start = start + timedelta(days=full_days)
    due = full_days * int(rules["daily_wrap_fee"])
    if full_days:
        notes.append(f"days:{full_days}*{rules['daily_wrap_fee']}")
    span, span_notes = _charge_span(remainder_start, end, rules)
    due += span
    notes.extend(span_notes)
    subtract = int(rules.get("over_1000_subtract") or 0)
    if subtract and due > subtract:
        due -= subtract
        notes.append(f"minus:{subtract}")
    car_type = str(rules.get("car_type") or "Car1")
    return FeeResult(duration, int(due), currency, car_type, notes)


def _class_overlay(rules: dict[str, Any]) -> dict[str, Any]:
    """Apply optional vehicle_classes[car_type] onto the Car1 JSON without a new API."""
    merged = dict(rules or {})
    classes = merged.get("vehicle_classes")
    car_type = str(merged.get("car_type") or settings.fee_car_type or "Car1")
    if isinstance(classes, dict) and car_type in classes and isinstance(classes[car_type], dict):
        overlay = dict(classes[car_type])
        overlay.pop("vehicle_classes", None)
        merged.update(overlay)
    merged["car_type"] = car_type
    return merged


def default_tariff_payload() -> dict[str, Any]:
    rules = dict(CAR1_RULES)
    rules["currency"] = settings.fee_currency
    return {
        "name": "Car1",
        "car_type": "Car1",
        "currency": settings.fee_currency,
        "source": CAR1_RULES["source"],
        "rules": rules,
        "active": True,
    }


def ensure_car1_tariff(db: Session, *, site_id: int = DEFAULT_SITE_ID) -> Tariff:
    row = db.scalar(select(Tariff).where(Tariff.site_id == site_id, Tariff.name == "Car1"))
    payload = default_tariff_payload()
    if row is None:
        row = Tariff(site_id=site_id, **payload)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    existing = row.rules if isinstance(row.rules, dict) else {}
    merged = dict(payload["rules"])
    # Keep rates an operator already saved. Defaults fill only missing keys.
    for key, value in existing.items():
        if value is not None:
            merged[key] = value
    if not row.currency:
        row.currency = payload["currency"]
    if not row.source:
        row.source = payload["source"]
    row.rules = merged
    if row.active is None:
        row.active = True
    db.commit()
    db.refresh(row)
    return row


def _minutes(seconds: Any) -> float:
    return round(int(seconds or 0) / 60, 2)


def tariff_editor(row: Tariff) -> dict[str, Any]:
    """Plain fields for the tariff screen. Times stay as clock values; fees stay as money."""
    rules = row.rules if isinstance(row.rules, dict) else {}
    return {
        "id": row.id,
        "name": row.name,
        "car_type": row.car_type,
        "currency": row.currency or str(rules.get("currency") or "TZS"),
        "active": bool(row.active),
        "day_start": str(rules.get("day_start") or CAR1_RULES["day_start"])[:5],
        "day_end": str(rules.get("day_end") or CAR1_RULES["day_end"])[:5],
        "free_day_minutes": _minutes(rules.get("free_day_seconds")),
        "free_night_minutes": _minutes(rules.get("free_night_seconds")),
        "day_block_minutes": _minutes(rules.get("day_block_seconds")),
        "night_block_minutes": _minutes(rules.get("night_block_seconds")),
        "day_block_fee": int(rules.get("day_block_fee") or 0),
        "night_block_fee": int(rules.get("night_block_fee") or 0),
        "day_max": int(rules.get("day_max") or 0),
        "night_max": int(rules.get("night_max") or 0),
        "daily_wrap_fee": int(rules.get("daily_wrap_fee") or 0),
    }


def _clock(value: str, fallback: str) -> str:
    text = (value or "").strip() or fallback
    parts = text.split(":")
    if len(parts) < 2:
        raise ValueError("Enter a time like 05:05")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("Enter a time like 05:05")
    second = int(parts[2]) if len(parts) > 2 else 0
    return f"{hour:02d}:{minute:02d}:{second:02d}"


def apply_tariff_editor(db: Session, updates: dict[str, Any]) -> Tariff:
    """Save the tariff form. Minutes on screen become the seconds the fee engine uses."""
    row = ensure_car1_tariff(db)
    rules = dict(row.rules or {})
    if updates.get("currency"):
        row.currency = str(updates["currency"]).strip().upper()[:8]
        rules["currency"] = row.currency
    if updates.get("day_start"):
        rules["day_start"] = _clock(str(updates["day_start"]), str(rules.get("day_start")))
    if updates.get("day_end"):
        rules["day_end"] = _clock(str(updates["day_end"]), str(rules.get("day_end")))
    minute_keys = {
        "free_day_minutes": "free_day_seconds",
        "free_night_minutes": "free_night_seconds",
        "day_block_minutes": "day_block_seconds",
        "night_block_minutes": "night_block_seconds",
    }
    for form_key, rule_key in minute_keys.items():
        if updates.get(form_key) is None:
            continue
        minutes = float(updates[form_key])
        if minutes < 0:
            raise ValueError("Minutes cannot be negative")
        rules[rule_key] = int(round(minutes * 60))
    for key in ("day_block_fee", "night_block_fee", "day_max", "night_max", "daily_wrap_fee"):
        if updates.get(key) is None:
            continue
        amount = int(updates[key])
        if amount < 0:
            raise ValueError("Fees cannot be negative")
        rules[key] = amount
    if updates.get("active") is not None:
        row.active = bool(updates["active"])
    row.rules = rules
    db.commit()
    db.refresh(row)
    return row


def load_active_rules(db: Session, car_type: str = "Car1", *, site_id: int = DEFAULT_SITE_ID) -> dict[str, Any]:
    wanted = car_type or "Car1"
    row = db.scalar(select(Tariff).where(
        Tariff.site_id == site_id,
        Tariff.car_type == wanted,
        Tariff.active.is_(True),
    ).order_by(Tariff.id.desc()))
    if row is None and wanted != "Car1":
        row = db.scalar(select(Tariff).where(
            Tariff.site_id == site_id,
            Tariff.car_type == "Car1",
            Tariff.active.is_(True),
        ).order_by(Tariff.id.desc()))
    if row and isinstance(row.rules, dict):
        rules = dict(CAR1_RULES)
        rules.update(row.rules)
        rules["currency"] = row.currency or rules.get("currency")
        rules["car_type"] = wanted
        return _class_overlay(rules)
    return _class_overlay({**CAR1_RULES, "car_type": wanted})
