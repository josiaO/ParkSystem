"""Unattended kiosks cannot record cash; staff accounts are unaffected."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

import app.api_main as runtime


def _user(name):
    return SimpleNamespace(username=name, id=1)


@pytest.mark.parametrize("cash_enabled, username, refused", [
    (False, "kiosk-device:kiosk-68c1decb98a0", True),
    (True, "kiosk-device:kiosk-68c1decb98a0", False),
    (False, "cashier", False),
    (False, "admin", False),
])
def test_unattended_kiosk_cash_guard(cash_enabled, username, refused):
    with patch.object(runtime, "parking_settings", return_value={"kiosk_cash_enabled": cash_enabled}):
        if refused:
            with pytest.raises(HTTPException) as err:
                runtime._refuse_cash_on_unattended_kiosk(None, _user(username))
            assert err.value.status_code == 403 and "mobile money" in err.value.detail
        else:
            runtime._refuse_cash_on_unattended_kiosk(None, _user(username))


def test_kiosk_cash_is_allowed_by_default():
    from app.services.simulation import DEFAULT_PARKING_SETTINGS

    assert DEFAULT_PARKING_SETTINGS["kiosk_cash_enabled"] is True


def test_kiosk_mobile_button_uses_the_real_intent_flow():
    from pathlib import Path

    root = Path(runtime.__file__).resolve().parents[1]
    js = (root / "web" / "assets" / "pages" / "30_kiosk.js").read_text(encoding="utf-8")
    desktop = (root / "desktop" / "main" / "30_parking.py").read_text(encoding="utf-8")
    for source in (js, desktop):
        assert "/api/public/payment-intents" in source and "/api/public/payment-status/" in source
    assert "MOBILE_SIMULATED" not in js.split('getElementById("kiosk-mobile")', 1)[1].split("});", 1)[0]
