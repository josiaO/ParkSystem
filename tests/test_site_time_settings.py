from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import ParkingSession, Site
from app.services.session_presentation import session_presentation
from app.services.site_policy import as_site_local, as_site_utc, save_site_policy, site_clock, site_policy


def _session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'site.db'}")
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def test_site_timezone_is_validated_and_synced_to_site_row(tmp_path):
    engine, factory = _session(tmp_path)
    try:
        with factory() as db:
            db.add(Site(id=1, name="Gate", timezone="UTC", locale="en", currency="USD"))
            db.commit()
            saved = save_site_policy(db, {"timezone": "Africa/Dar_es_Salaam", "currency": "TZS"})
            assert saved["timezone"] == "Africa/Dar_es_Salaam"
            site = db.get(Site, 1)
            assert site.timezone == "Africa/Dar_es_Salaam"
            assert site.currency == "TZS"
            with pytest.raises(ValueError, match="Invalid timezone"):
                save_site_policy(db, {"timezone": "Not/A_Timezone"})
    finally:
        engine.dispose()


def test_session_and_clock_use_site_local_time(tmp_path):
    engine, factory = _session(tmp_path)
    try:
        with factory() as db:
            save_site_policy(db, {"timezone": "Africa/Dar_es_Salaam"})
            row = ParkingSession(
                plate="T123ABC", status="ACTIVE", lane_direction="ENTRY",
                entry_time=datetime(2026, 10, 31, 9, 0, tzinfo=timezone.utc),
            )
            db.add(row)
            db.commit()
            body = session_presentation(db, row)
            assert body["entry_time"].endswith("+03:00")
            assert body["entry_time"].startswith("2026-10-31T12:00:00")
            clock = site_clock(db)
            assert clock["source"] == "site_server_os_utc"
            assert clock["timezone"] == "Africa/Dar_es_Salaam"
            assert as_site_local(datetime.now(timezone.utc), site_policy(db)).utcoffset().total_seconds() == 10800
    finally:
        engine.dispose()


def test_naive_user_input_is_converted_from_site_time_to_utc(tmp_path):
    engine, factory = _session(tmp_path)
    try:
        with factory() as db:
            save_site_policy(db, {"timezone": "Africa/Dar_es_Salaam"})
            converted = as_site_utc(datetime(2026, 10, 31, 12, 0), site_policy(db))
            assert converted == datetime(2026, 10, 31, 9, 0, tzinfo=timezone.utc)
    finally:
        engine.dispose()
