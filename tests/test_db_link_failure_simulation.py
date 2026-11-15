"""Phase 5.3: an Edge Node with a dropped or slow database link stays responsive.

There is no PostgreSQL server in CI, so the link is simulated at the DBAPI
level: an engine whose connections fail ("could not connect to server") or
take seconds to open. The Site Service's own behaviour is real: FastAPI
routing, auth, the 503 handler, the link probe and /health/live.
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
import time

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from app.api_main import app
from app.db import get_db
from app.services import db_link


def _engine(*, delay: float, fail: bool):
    def creator():
        time.sleep(delay)
        if fail:
            raise sqlite3.OperationalError("could not connect to server: Connection refused")
        return sqlite3.connect(":memory:", check_same_thread=False)

    return create_engine("sqlite://", creator=creator, poolclass=QueuePool, pool_size=1, max_overflow=0, pool_timeout=1)


def _use(engine):
    Session = sessionmaker(bind=engine)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override


def _probe_with(engine):
    def probe():
        started = time.perf_counter()
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return (time.perf_counter() - started) * 1000

    return probe


def test_dropped_link_answers_fast_with_fallback_and_reports_down():
    engine = _engine(delay=0.2, fail=True)
    _use(engine)
    try:
        client = TestClient(app, raise_server_exceptions=False)
        started = time.perf_counter()
        response = client.get("/lanes/1/view", headers={"Authorization": "Bearer operator-token"})
        elapsed = time.perf_counter() - started
        assert response.status_code == 503, response.text
        assert "QR" in response.json()["detail"]
        assert elapsed < 2.0
        snap = asyncio.run(db_link.probe_once(timeout_seconds=2, probe=_probe_with(engine)))
        assert snap["state"] == "DOWN"
        live = client.get("/health/live")
        assert live.status_code == 200 and live.json()["db_link"]["state"] == "DOWN"
    finally:
        app.dependency_overrides.clear()
        db_link.monitor().note_ok(5.0)
        engine.dispose()


def test_slow_link_does_not_freeze_the_service():
    engine = _engine(delay=3.0, fail=False)
    _use(engine)
    client = TestClient(app, raise_server_exceptions=False)
    stuck = threading.Thread(target=lambda: client.get("/lanes/1/view", headers={"Authorization": "Bearer t"}))
    try:
        stuck.start()
        time.sleep(0.2)  # the lane request is now waiting on a 3 s connect
        started = time.perf_counter()
        live = client.get("/health/live")
        assert live.status_code == 200
        assert time.perf_counter() - started < 0.5   # health and the event loop stay responsive
        snap = asyncio.run(db_link.probe_once(timeout_seconds=1, probe=_probe_with(engine)))
        assert snap["state"] == "DOWN" and "did not answer within 1 s" in snap["last_error"]
    finally:
        stuck.join(10)
        app.dependency_overrides.clear()
        db_link.monitor().note_ok(5.0)
        engine.dispose()
