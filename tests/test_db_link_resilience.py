"""Phase 5: a dead or slow central database link fails fast instead of hanging a lane."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

from app.db import engine_kwargs

PG = "postgresql+psycopg://u:p@site-server/smartpark"


def test_postgres_connections_fail_fast_and_detect_dead_links():
    kwargs = engine_kwargs(PG)
    args = kwargs["connect_args"]
    assert args["connect_timeout"] <= 5
    assert args["keepalives"] == 1 and args["keepalives_idle"] <= 15 and args["keepalives_count"] >= 2
    assert "statement_timeout=15000" in args["options"]
    assert "idle_in_transaction_session_timeout=60000" in args["options"]
    assert args["application_name"].startswith("smartpark")
    assert kwargs["pool_timeout"] <= 5
    assert kwargs["pool_pre_ping"] is True
    assert "sslmode" not in args  # psycopg default unless configured


def test_sslmode_and_timeouts_are_configurable():
    from app.config import settings

    with patch.object(settings, "db_sslmode", "require"), \
         patch.object(settings, "db_statement_timeout_ms", 0), \
         patch.object(settings, "db_connect_timeout_seconds", 3):
        args = engine_kwargs(PG)["connect_args"]
    assert args["sslmode"] == "require"
    assert args["connect_timeout"] == 3
    assert "statement_timeout" not in args["options"]  # 0 disables it


def test_sqlite_is_unchanged():
    kwargs = engine_kwargs("sqlite:///tmp/x.db")
    assert "keepalives" not in kwargs["connect_args"]


def test_migrations_lift_the_statement_timeout():
    from app.migrations import runner

    executed = []

    class Conn:
        dialect = type("D", (), {"name": "postgresql"})()

        def exec_driver_sql(self, sql):
            executed.append(sql)

    class Engine:
        dialect = Conn.dialect

        @contextmanager
        def begin(self):
            yield Conn()

    with patch.object(runner, "alembic_config", return_value=type("C", (), {"attributes": {}})()):
        runner._run(Engine(), lambda cfg: None)
    assert executed == ["SET LOCAL statement_timeout = 0"]


# Link state and the recognition outbox ------------------------------------

def _operational_error():
    from sqlalchemy.exc import OperationalError

    return OperationalError("SELECT 1", {}, Exception("could not connect to server: Connection refused"))


def test_link_errors_are_recognised():
    from sqlalchemy.exc import IntegrityError, TimeoutError as PoolTimeout

    from app.services import db_link

    assert db_link.is_link_error(_operational_error())
    assert db_link.is_link_error(PoolTimeout("QueuePool limit reached"))
    assert not db_link.is_link_error(IntegrityError("x", {}, Exception("dup")))
    assert not db_link.is_link_error(ValueError("bad payload"))
    from sqlalchemy.exc import OperationalError

    assert not db_link.is_link_error(OperationalError("x", {}, Exception("no such table: cameras")))
    assert not db_link.is_link_error(OperationalError("x", {}, Exception("database is locked")))
    assert db_link.is_link_error(OperationalError("x", {}, Exception("canceling statement due to statement timeout")))


def test_link_state_goes_down_and_recovers():
    from app.services import db_link

    monitor = db_link.LinkMonitor(slow_ms=800)
    assert monitor.snapshot()["state"] == "UNKNOWN"
    monitor.note_ok(12.0)
    assert monitor.snapshot()["state"] == "UP"
    monitor.note_failure(_operational_error())
    snap = monitor.snapshot()
    assert snap["state"] == "DOWN" and "Connection refused" in snap["last_error"]
    assert "QR" in snap["operator_message"]
    monitor.note_ok(1500.0)
    assert monitor.snapshot()["state"] == "SLOW"
    monitor.note_ok(20.0)
    assert monitor.snapshot()["state"] == "UP"


def test_outbox_keeps_events_during_a_link_outage(tmp_path):
    from app.services.queues import SQLiteOutbox
    from app.services import db_link

    box = SQLiteOutbox(tmp_path / "outbox.sqlite3")
    box.enqueue("plate-event", {"camera_id": 1, "plate": "T1"})
    item = box.pending()[0]
    for _ in range(SQLiteOutbox.MAX_ATTEMPTS + 3):
        assert db_link.handle_outbox_failure(box, item, _operational_error()) == "link-down"
    assert [row["id"] for row in box.pending()] == [item["id"]]   # not dead-lettered
    assert box.dead_letter_depth() == 0


def test_outbox_still_dead_letters_a_poison_event(tmp_path):
    from app.services.queues import SQLiteOutbox
    from app.services import db_link

    box = SQLiteOutbox(tmp_path / "outbox.sqlite3")
    box.enqueue("plate-event", {"camera_id": 1, "plate": "T1"})
    item = box.pending()[0]
    results = [db_link.handle_outbox_failure(box, item, ValueError("bad payload")) for _ in range(SQLiteOutbox.MAX_ATTEMPTS)]
    assert results[-1] == "dead-lettered" and box.dead_letter_depth() == 1


def test_database_link_errors_return_503_with_a_fallback_message():
    from fastapi.testclient import TestClient

    from app.api_main import app
    from app.db import get_db

    def broken_db():
        raise _operational_error()
        yield  # pragma: no cover

    app.dependency_overrides[get_db] = broken_db
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/gates", headers={"Authorization": "Bearer x"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503
    body = response.json()
    assert body["link"] == "DOWN" and "QR" in body["detail"]


def test_health_live_reports_the_link_without_touching_the_database():
    from app.services import db_link
    from app.services.health import live

    db_link.monitor().note_failure(_operational_error())
    try:
        assert live()["db_link"]["state"] == "DOWN"
    finally:
        db_link.monitor().note_ok(5.0)


def test_desktop_banner_tells_the_operator_what_to_do():
    from app.desktop.desk import link_banner

    assert link_banner({"db_link": {"state": "UP"}}) == ("", "")
    level, text = link_banner({"db_link": {"state": "DOWN", "seconds_in_state": 42,
                                           "operator_message": "Server link down: use the receipt QR."}})
    assert level == "down" and "receipt QR" in text and "42 s" in text
    level, text = link_banner(None, "Connection refused")
    assert level == "down" and "Site Service is not responding" in text and "QR" in text
    assert link_banner({"db_link": {"state": "SLOW", "latency_ms": 1800}})[0] == "slow"


def test_main_window_banner_shows_link_down(monkeypatch):
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    import app.desktop.main as desktop

    global _APP
    _APP = QApplication.instance() or QApplication([])
    shown = []
    page = type("P", (), {})()
    page.link_banner = desktop.QLabel()
    page.statusBar = lambda: type("S", (), {"showMessage": lambda self, text: shown.append(text)})()
    desktop.MainWindow._show_link(page, {"db_link": {"state": "DOWN", "seconds_in_state": 3,
                                                     "operator_message": "Server link down: use the receipt QR."}}, None)
    assert "receipt QR" in page.link_banner.text() and shown
    desktop.MainWindow._show_link(page, {"db_link": {"state": "UP"}}, None)
    assert page.link_banner.text() == ""
