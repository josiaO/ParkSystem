"""ClickPesa settings can be read and changed from the desktop, secrets stay write-only."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api.payment_settings import payment_settings_view, save_payment_settings
from app.config import settings
from app.env_tool import read_env

KEYS = ("payments_mobile_provider", "clickpesa_client_id", "clickpesa_api_key", "clickpesa_checksum_key",
        "clickpesa_base_url", "clickpesa_live_enabled", "payments_live_provider_confirmed")


@pytest.fixture(autouse=True)
def restore_settings():
    saved = {key: getattr(settings, key) for key in KEYS}
    yield
    for key, value in saved.items():
        setattr(settings, key, value)


def test_save_writes_env_and_applies_without_restart(tmp_path):
    env = tmp_path / ".env"
    env.write_text("SMARTPARK_SITE_NAME=Test\n", encoding="utf-8")
    view = save_payment_settings({
        "payments_mobile_provider": "clickpesa",
        "clickpesa_client_id": "ID-123456",
        "clickpesa_api_key": "secret-key-value",
        "clickpesa_checksum_key": "checksum-value",
        "clickpesa_live_enabled": False,
    }, env_path=env)
    stored = read_env(env)
    assert stored["SMARTPARK_SITE_NAME"] == "Test"            # other settings kept
    assert stored["SMARTPARK_CLICKPESA_API_KEY"] == "secret-key-value"
    assert stored["SMARTPARK_PAYMENTS_MOBILE_PROVIDER"] == "clickpesa"
    assert settings.clickpesa_client_id == "ID-123456"         # live at once
    assert view["clickpesa_api_key_set"] is True
    assert "secret-key-value" not in repr(view)                # never echoed back
    assert "checksum-value" not in repr(view)


def test_empty_secret_keeps_the_stored_one(tmp_path):
    env = tmp_path / ".env"
    save_payment_settings({"clickpesa_api_key": "first-key"}, env_path=env)
    save_payment_settings({"clickpesa_api_key": "", "clickpesa_client_id": "X"}, env_path=env)
    assert read_env(env)["SMARTPARK_CLICKPESA_API_KEY"] == "first-key"
    assert settings.clickpesa_api_key == "first-key"


def test_rejects_unknown_provider_and_bad_address(tmp_path):
    with pytest.raises(ValueError):
        save_payment_settings({"payments_mobile_provider": "flutterwave"}, env_path=tmp_path / ".env")
    with pytest.raises(ValueError):
        save_payment_settings({"clickpesa_base_url": "api.clickpesa.com"}, env_path=tmp_path / ".env")


def test_view_reports_mode_without_secrets():
    settings.clickpesa_api_key = "do-not-show"
    view = payment_settings_view()
    assert "do-not-show" not in repr(view)
    assert view["mobile_providers"] == ["simulated", "clickpesa"]


def test_endpoint_requires_settings_manage():
    from fastapi.testclient import TestClient

    from app.api_main import app

    client = TestClient(app)
    assert client.get("/settings/payments").status_code == 401
