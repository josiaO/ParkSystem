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
    read_budget.record(5, "T669DYB", 0.93, now=100.0)
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


def test_camera_region_search_is_off_until_switched_on_screen(site):
    client, headers = site
    body = client.get("/settings/recognition", headers=headers).json()
    assert body["camera_region_search"] is False
    saved = client.patch("/settings/recognition", headers=headers, json={"camera_region_search": True})
    assert saved.status_code == 200, saved.text
    assert saved.json()["camera_region_search"] is True
    assert runtime_settings.get("camera_region_search") is True
    saved = client.patch("/settings/recognition", headers=headers, json={"camera_region_search": False})
    assert runtime_settings.get("camera_region_search") is False


@pytest.fixture()
def blank_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield Session
    engine.dispose()


def test_zirp_env_settings_move_into_the_site_settings(blank_db, tmp_path):
    """A zirp.env line for an on-screen setting is moved, then removed from the file."""
    from app.models import SiteSetting

    env = tmp_path / "zirp.env"
    env.write_text("SMARTPARK_PAYMENTS_MOBILE_PROVIDER=clickpesa\n"
                   "SMARTPARK_CAPTURE_TRIGGER=external\n"
                   "SMARTPARK_PUBLIC_RECEIPT_PHOTO=blurred\n"
                   "SMARTPARK_ALPR_COUNTRY=tanzania\n", encoding="utf-8")
    with blank_db() as db:
        moved = runtime_settings.adopt_env_file(db, env_path=env)
        assert moved["adopted"] == {"capture_trigger": "external", "public_receipt_photo": "blurred",
                                    "plate_validation": "TZ"}
        assert db.get(SiteSetting, "recognition").value["capture_trigger"] == "external"
        assert db.get(SiteSetting, "site").value["plate_validation"] == "TZ"
    text = env.read_text(encoding="utf-8")
    assert "CAPTURE_TRIGGER" not in text and "ALPR_COUNTRY" not in text and "RECEIPT_PHOTO" not in text
    assert "SMARTPARK_PAYMENTS_MOBILE_PROVIDER=clickpesa" in text       # other lines are kept
    assert (tmp_path / "zirp.env.bak").exists()


def test_a_value_saved_on_screen_is_not_replaced_by_zirp_env(blank_db, tmp_path):
    from app.models import SiteSetting

    env = tmp_path / "zirp.env"
    env.write_text("SMARTPARK_CAPTURE_TRIGGER=external\nSMARTPARK_ALPR_COUNTRY=tanzania\n", encoding="utf-8")
    with blank_db() as db:
        db.add(SiteSetting(key="recognition", value={"capture_trigger": "zirp"}))
        db.add(SiteSetting(key="site", value={"plate_validation": "NONE"}))
        db.commit()
        moved = runtime_settings.adopt_env_file(db, env_path=env)
        assert moved["adopted"] == {}
        assert db.get(SiteSetting, "recognition").value["capture_trigger"] == "zirp"
        assert db.get(SiteSetting, "site").value["plate_validation"] == "NONE"
    assert "CAPTURE_TRIGGER" not in env.read_text(encoding="utf-8")


def test_site_plate_rule_wins_over_zirp_env_country(monkeypatch):
    from app.services import alpr

    monkeypatch.setattr(settings, "alpr_country", "tanzania")
    monkeypatch.setattr(runtime_settings, "site_plate_validation", lambda: "NONE")
    assert alpr._country_name() == ""
    monkeypatch.setattr(runtime_settings, "site_plate_validation", lambda: "TZ")
    monkeypatch.setattr(settings, "alpr_country", "")
    assert alpr._country_name() == "tanzania"


def test_ocr_acceptance_uses_the_site_plate_rule(monkeypatch):
    """The screen's plate rule is what accepts or holds a read, not zirp.env."""
    from app.services import alpr

    seen = []
    import app.services.alpr as module
    real = module.accept_ocr_plate.__globals__["assess_plate"]
    monkeypatch.setitem(module.accept_ocr_plate.__globals__, "assess_plate",
                        lambda plate, rule, **kw: seen.append(rule) or real(plate, rule, **kw))
    monkeypatch.setattr(settings, "plate_validation", "NONE")
    monkeypatch.setattr(runtime_settings, "site_plate_validation", lambda: "TZ")
    alpr.accept_ocr_plate("T123ABC", 0.95)
    assert seen == ["TZ"]
