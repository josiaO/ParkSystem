"""Phase 2.6: clock skew between gate PCs and the site's time authority."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services import clock_skew


class _FakeDb:
    def __init__(self, server_time, dialect="postgresql"):
        self.server_time = server_time
        self.bind = type("B", (), {"dialect": type("D", (), {"name": dialect})()})()

    def get_bind(self):
        return self.bind

    def scalar(self, _statement):
        return self.server_time


def test_skew_against_the_database_clock_is_measured_and_flagged():
    ahead = datetime.now(timezone.utc) - timedelta(seconds=5)  # this PC runs 5 s ahead
    result = clock_skew.measure_database_skew(_FakeDb(ahead))
    assert result["source"] == "database"
    assert 4.5 < result["skew_seconds"] < 5.5
    assert result["ok"] is False and "5" in result["warning"]


def test_small_skew_is_ok():
    result = clock_skew.measure_database_skew(_FakeDb(datetime.now(timezone.utc)))
    assert result["ok"] is True and result["warning"] == ""


def test_naive_server_time_is_treated_as_utc():
    naive = datetime.now(timezone.utc).replace(tzinfo=None)
    assert clock_skew.measure_database_skew(_FakeDb(naive))["ok"] is True


def test_local_sqlite_shares_this_computers_clock():
    result = clock_skew.measure_database_skew(_FakeDb(None, dialect="sqlite"))
    assert result["source"] == "local-database" and result["ok"] is True


def test_workstation_skew_against_the_site_server():
    server = (datetime.now(timezone.utc) + timedelta(seconds=3)).isoformat()
    result = clock_skew.skew_from_server_time(server, round_trip_seconds=0.1)
    assert -3.5 < result["skew_seconds"] < -2.5  # this PC is behind
    assert result["ok"] is False


def test_desktop_health_sentence_mentions_clock_problems():
    from app.desktop.desk import health_sentences

    text = health_sentences({"status": "ok", "clock": {"ok": False, "warning": "Clock is 5.0 s ahead of the database server."}})
    assert "5.0 s ahead" in text


def test_desktop_system_health_shows_both_clocks():
    import os
    from types import MethodType, SimpleNamespace
    from unittest.mock import patch

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QLabel, QPlainTextEdit

    import app.desktop.main as desktop

    global _APP
    _APP = QApplication.instance() or QApplication([])
    server_now = (datetime.now(timezone.utc) + timedelta(seconds=4)).isoformat()

    class Api:
        def get(self, path, timeout=8):
            if path == "/health/live":
                return {"state": "READY"}
            if path == "/settings/clock":
                return {"server_time_utc": server_now}
            return {"status": "ok", "clock": {"source": "database", "skew_seconds": 0.4, "ok": True, "warning": ""}}

    page = SimpleNamespace(state=QLabel(), summary=QLabel(), clock=QLabel(), info=QPlainTextEdit())
    page._workstation_clock = MethodType(desktop.SystemHealth._workstation_clock, page)
    page._show = MethodType(desktop.SystemHealth._show, page)
    import app.desktop.common as desktop_common
    # The page loads on a worker thread in the app; run it inline here.
    with patch.object(desktop, "api", Api()), patch.object(desktop_common, "TASKS_INLINE", True):
        desktop.SystemHealth.refresh(page)
    assert "Gate PC vs database: +0.4 s (OK)" in page.clock.text()
    assert "This computer vs Site Server: -4" in page.clock.text() and "CHECK" in page.clock.text()
    assert "behind the Site Server" in page.summary.text()
