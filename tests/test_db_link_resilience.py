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
