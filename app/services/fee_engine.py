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
    rules = dict(CAR1_RULES if rules is None else {**CAR1_RULES, **rules})
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
    return FeeResult(duration, int(due), currency, "Car1", notes)


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


def ensure_car1_tariff(db: Session) -> Tariff:
    row = db.scalar(select(Tariff).where(Tariff.name == "Car1"))
    payload = default_tariff_payload()
    if row is None:
        row = Tariff(**payload)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    row.currency = payload["currency"]
    row.source = payload["source"]
    row.rules = payload["rules"]
    row.active = True
    db.commit()
    db.refresh(row)
    return row


def load_active_rules(db: Session, car_type: str = "Car1") -> dict[str, Any]:
    row = db.scalar(select(Tariff).where(Tariff.car_type == car_type, Tariff.active.is_(True)).order_by(Tariff.id.desc()))
    if row and isinstance(row.rules, dict):
        rules = dict(CAR1_RULES)
        rules.update(row.rules)
        rules["currency"] = row.currency or rules.get("currency")
        return rules
    return dict(CAR1_RULES)
