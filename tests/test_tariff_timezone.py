"""Phase 2.2: tariff day/night boundaries are site-local, not UTC."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import Base
from app.services.fee_engine import CAR1_RULES, calculate_car1_fee, is_daytime, load_active_rules

DAR = {**CAR1_RULES, "timezone": "Africa/Dar_es_Salaam"}  # UTC+3, day 05:05-23:05 local


def _utc(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, 14, hour, minute, tzinfo=timezone.utc)


def test_new_installs_default_to_tanzania_time():
    assert Settings().site_timezone == "Africa/Dar_es_Salaam"


def test_day_and_night_follow_local_time():
    assert is_daytime(_utc(2, 10), DAR)        # 05:10 local
    assert not is_daytime(_utc(2, 0), DAR)     # 05:00 local
    assert is_daytime(_utc(20, 0), DAR)        # 23:00 local
    assert not is_daytime(_utc(20, 10), DAR)   # 23:10 local (UTC would still say day)


def test_evening_stay_splits_at_local_23_05():
    # 22:30 -> 00:00 local: 35 min day, then 55 min night.
    fee = calculate_car1_fee(_utc(19, 30), _utc(21, 0), DAR)
    assert "day:2100s/1blk=1000" in fee.breakdown, fee.breakdown
    assert "night:3300s/2blk=2000" in fee.breakdown, fee.breakdown
    assert fee.due == 2000


def test_early_morning_stay_splits_at_local_05_05():
    # 04:00 -> 06:00 local: 65 min night, then 55 min day.
    fee = calculate_car1_fee(_utc(1, 0), _utc(3, 0), DAR)
    assert "night:3900s/2blk=2000" in fee.breakdown, fee.breakdown
    assert "day:3300s/2blk=2000" in fee.breakdown, fee.breakdown


def test_free_period_uses_local_night_length():
    # Leaves at 23:30 local after 40 min: night free period is 35 min.
    fee = calculate_car1_fee(_utc(19, 50), _utc(20, 30), DAR)
    assert "free:2100s" in fee.breakdown
    assert fee.due > 0


def test_tariff_without_timezone_gets_the_site_timezone():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with sessionmaker(bind=engine)() as db:
            assert load_active_rules(db)["timezone"] == "Africa/Dar_es_Salaam"
    finally:
        engine.dispose()
