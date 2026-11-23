"""Settings -> Recognition replaces zirp.env lines an administrator had to edit by hand."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api_main import app, ensure_roles
from app.config import settings
from app.db import Base, get_db
from app.models import Role, User, UserRole
from app.security import hash_password
from app.services import read_budget, receipt_privacy, runtime_settings


@pytest.fixture()
def site(monkeypatch):
    monkeypatch.setattr(runtime_settings, "_read_stored", runtime_settings._read_stored_from_db)
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
        admin = db.scalar(select(Role).where(Role.name == "Admin"))
        user = User(username="admin", full_name="Admin", password_hash=hash_password("correct-horse"))
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_id=admin.id))
        db.commit()
    runtime_settings.invalidate()
    with patch("app.db.SessionLocal", Session), TestClient(app) as client:
        token = client.post("/auth/login", json={"username": "admin", "password": "correct-horse"}).json()["token"]
        yield client, {"Authorization": f"Bearer {token}"}
    app.dependency_overrides.pop(get_db, None)
    runtime_settings.invalidate()
    engine.dispose()


def test_values_come_from_zirp_env_until_saved_on_screen(site, monkeypatch):
    client, headers = site
    monkeypatch.setattr(settings, "capture_trigger", "external")
    body = client.get("/settings/recognition", headers=headers).json()
    assert body["capture_trigger"] == "external"
    assert body["saved_on_screen"] == []
    assert body["read_budget_confident"] == pytest.approx(0.90)


def test_saving_on_screen_applies_without_restart(site):
    client, headers = site
    saved = client.patch("/settings/recognition", headers=headers, json={
        "capture_trigger": "both", "read_budget_confident": 0.95,
        "read_budget_quiet_seconds": 6, "public_receipt_photo": "blurred",
    })
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["capture_trigger"] == "both"
    assert "read_budget_confident" in body["saved_on_screen"]
    # The lanes use the new values straight away.
    assert runtime_settings.get("capture_trigger") == "both"
    assert read_budget._confident_at() == pytest.approx(0.95)
    assert read_budget._quiet() == pytest.approx(6.0)
    assert receipt_privacy.public_photo_mode() == "blurred"
    # 0.93 is no longer final, so one more read is allowed.
    read_budget.record(5, "T776DYB", 0.93, now=100.0)
    assert read_budget.allow(5, now=100.5)


@pytest.mark.parametrize("payload", [
    {"capture_trigger": "sometimes"},
    {"read_budget_confident": 1.5},
    {"read_budget_quiet_seconds": 0},
    {"read_budget_quiet_seconds": 30, "read_budget_max_seconds": 10},
    {"public_receipt_photo": "huge"},
])
def test_bad_values_are_refused_with_a_reason(site, payload):
    client, headers = site
    response = client.patch("/settings/recognition", headers=headers, json=payload)
    assert response.status_code == 422
    assert response.json()["detail"]


def test_plate_country_follows_site_plate_validation(site):
    client, headers = site
    from app.services.alpr import _country_name

    with patch.object(settings, "alpr_country", ""):
        client.patch("/settings/site", headers=headers, json={"plate_validation": "TZ"})
        runtime_settings.invalidate()
        assert _country_name() == "tanzania"
        client.patch("/settings/site", headers=headers, json={"plate_validation": "NONE"})
        runtime_settings.invalidate()
        assert _country_name() == ""


def test_a_database_outage_keeps_the_last_values(monkeypatch):
    monkeypatch.setattr(runtime_settings, "_read_stored", runtime_settings._read_stored_from_db)
    runtime_settings.invalidate()
    with patch("app.db.SessionLocal", side_effect=RuntimeError("database down")):
        assert runtime_settings.get("read_budget_enabled") is settings.read_budget_enabled
