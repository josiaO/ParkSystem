"""A slow database call in one request must not stall the event loop.

``async def`` routes share one loop with live MJPEG streams, kiosk payments
and gate decisions. Their database work runs in the threadpool (``run_db``),
so a lock wait or slow disk in one request leaves every other request
answering. These tests make a route's database step block for seconds and
check that ``/health/live`` still answers promptly meanwhile.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import patch

import anyio.from_thread
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api_main import app, ensure_roles
from app.db import Base, get_db, run_db
from app.models import Role, User, UserRole
from app.security import hash_password

SLOW_SECONDS = 3.0
PROMPT_SECONDS = 1.0


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with Session() as db:
        ensure_roles(db)
        admin_role = db.scalar(select(Role).where(Role.name == "Admin"))
        user = User(username="admin", full_name="Test Admin", password_hash=hash_password("correct-horse"))
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_id=admin_role.id))
        db.commit()
    test_client = TestClient(app)
    # One event loop for every request, as in production (uvicorn). Without a
    # shared portal TestClient starts a fresh loop per request, and a blocked
    # loop could never delay another request. The app lifespan is not run.
    portal_cm = anyio.from_thread.start_blocking_portal()
    test_client.portal = portal_cm.__enter__()
    token = test_client.post("/auth/login", json={"username": "admin", "password": "correct-horse"}).json()["token"]
    test_client.headers["Authorization"] = f"Bearer {token}"
    try:
        yield test_client
    finally:
        test_client.portal = None
        portal_cm.__exit__(None, None, None)
        test_client.close()
        app.dependency_overrides.clear()
        engine.dispose()


def _slow_db_step(result=None, *, raises: Exception | None = None):
    """A stand-in for a query stuck behind a lock: blocks its thread."""
    started = threading.Event()

    def step(*_args, **_kwargs):
        started.set()
        time.sleep(SLOW_SECONDS)
        if raises is not None:
            raise raises
        return result

    return step, started


def _health_answers_while(client: TestClient, method: str, path: str, started: threading.Event, **kwargs):
    outcome: dict = {}

    def slow_request():
        outcome["response"] = client.request(method, path, **kwargs)

    worker = threading.Thread(target=slow_request, daemon=True)
    worker.start()
    try:
        assert started.wait(5.0), f"{path} never reached its database step"
        t0 = time.monotonic()
        live = client.get("/health/live")
        elapsed = time.monotonic() - t0
        assert live.status_code == 200
        assert elapsed < PROMPT_SECONDS, (
            f"/health/live took {elapsed:.2f}s while {path} waited on the database: "
            "the database work is blocking the event loop"
        )
    finally:
        worker.join(SLOW_SECONDS + 10)
    assert "response" in outcome, f"{path} did not finish"
    return outcome["response"]


def test_slow_settings_query_in_printer_status_does_not_block_loop(client):
    step, started = _slow_db_step({"printer_adapter": "simulated", "printer_name": ""})
    with patch("app.api_main.parking_settings", step):
        response = _health_answers_while(client, "GET", "/printers/status", started)
    assert response.status_code == 200
    assert response.json()["adapter_id"] == "simulated"


def test_slow_gate_lookup_in_gate_open_does_not_block_loop(client):
    step, started = _slow_db_step(raises=HTTPException(404, "Gate not found"))
    with patch("app.api_main._gate_for_node", step):
        response = _health_answers_while(
            client, "POST", "/gates/1/open", started,
            json={"reason": "operator test", "dry_run": True},
        )
    assert response.status_code == 404


def test_run_db_runs_off_the_event_loop_thread():
    import asyncio

    async def main():
        loop_thread = threading.get_ident()
        worker_thread = await run_db(threading.get_ident)
        return loop_thread, worker_thread

    loop_thread, worker_thread = asyncio.run(main())
    assert worker_thread != loop_thread
