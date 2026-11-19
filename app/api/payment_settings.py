"""Mobile-money (ClickPesa) configuration over HTTP, for the desktop Settings page.

ClickPesa is configured through ``SMARTPARK_*`` settings that live in the
install's ``.env`` file. Before this endpoint a technician had to edit that
file by hand on the Site Server. The desktop now reads and changes it here:

- secrets (API key, checksum key) are write-only: GET reports only whether
  they are set; an empty value in PATCH keeps the stored secret;
- changes are written to ``.env`` (so they survive a restart) and applied to
  the running Site Service at once;
- real-money collection still needs both explicit switches (ClickPesa has no
  sandbox), exactly as before.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import User
from app.security import require

MOBILE_PROVIDERS = ("simulated", "clickpesa")


class PaymentSettingsUpdate(BaseModel):
    payments_mobile_provider: str | None = None
    clickpesa_client_id: str | None = Field(default=None, max_length=200)
    clickpesa_api_key: str | None = Field(default=None, max_length=400)
    clickpesa_checksum_key: str | None = Field(default=None, max_length=400)
    clickpesa_base_url: str | None = Field(default=None, max_length=300)
    clickpesa_live_enabled: bool | None = None
    payments_live_provider_confirmed: bool | None = None


def _mask(value: str) -> str:
    value = str(value or "")
    if len(value) <= 6:
        return "•" * len(value)
    return value[:3] + "•" * (len(value) - 6) + value[-3:]


def payment_settings_view() -> dict[str, Any]:
    from app.infrastructure.payments import payment_provider_for

    provider = payment_provider_for("clickpesa")
    health = provider.health() if hasattr(provider, "health") else {}
    return {
        "payments_mobile_provider": str(settings.payments_mobile_provider or "simulated"),
        "mobile_providers": list(MOBILE_PROVIDERS),
        "clickpesa_client_id": str(settings.clickpesa_client_id or ""),
        "clickpesa_client_id_masked": _mask(settings.clickpesa_client_id),
        "clickpesa_api_key_set": bool((settings.clickpesa_api_key or "").strip()),
        "clickpesa_checksum_key_set": bool((settings.clickpesa_checksum_key or "").strip()),
        "clickpesa_base_url": str(settings.clickpesa_base_url or ""),
        "clickpesa_live_enabled": bool(settings.clickpesa_live_enabled),
        "payments_live_provider_confirmed": bool(settings.payments_live_provider_confirmed),
        "mode": health.get("mode"),
        "available": health.get("available"),
        "reason": health.get("reason") or "",
        # A value set in the Site Server's own process environment wins over
        # .env after a restart; the desktop warns about these.
        "overridden_by_environment": _environment_overrides(),
    }


def _environment_overrides() -> list[str]:
    import os

    from app.env_tool import env_key

    keys = ("payments_mobile_provider", "clickpesa_client_id", "clickpesa_api_key", "clickpesa_checksum_key",
            "clickpesa_base_url", "clickpesa_live_enabled", "payments_live_provider_confirmed")
    return [key for key in keys if env_key(key) in os.environ]


def _env_value(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def save_payment_settings(data: dict[str, Any], *, env_path=None) -> dict[str, Any]:
    from app.env_tool import env_file_path, env_key, write_env

    updates: dict[str, Any] = {}
    provider = data.get("payments_mobile_provider")
    if provider is not None:
        provider = str(provider).strip().lower()
        if provider not in MOBILE_PROVIDERS:
            raise ValueError(f"Mobile money provider must be one of: {', '.join(MOBILE_PROVIDERS)}")
        updates["payments_mobile_provider"] = provider
    for key in ("clickpesa_client_id", "clickpesa_base_url"):
        if data.get(key) is not None:
            updates[key] = str(data[key]).strip()
    base_url = updates.get("clickpesa_base_url")
    if base_url is not None and base_url and not base_url.startswith(("http://", "https://")):
        raise ValueError("ClickPesa address must start with https://")
    # Secrets: empty means "keep what is stored".
    for key in ("clickpesa_api_key", "clickpesa_checksum_key"):
        value = data.get(key)
        if value is not None and str(value).strip():
            updates[key] = str(value).strip()
    for key in ("clickpesa_live_enabled", "payments_live_provider_confirmed"):
        if data.get(key) is not None:
            updates[key] = bool(data[key])
    if not updates:
        return payment_settings_view()
    write_env(env_file_path(env_path), {env_key(key): _env_value(value) for key, value in updates.items()})
    for key, value in updates.items():
        setattr(settings, key, value)
    # New credentials: drop any cached ClickPesa access token.
    try:
        from app.infrastructure.payments import payment_provider_for

        provider_obj = payment_provider_for("clickpesa")
        if hasattr(provider_obj, "_token"):
            provider_obj._token = ""
            provider_obj._token_at = 0.0
    except Exception:
        pass
    return payment_settings_view()


def register() -> APIRouter:
    router = APIRouter()

    @router.get("/settings/payments")
    def get_payment_settings(_: User = Depends(require("settings.manage"))):
        return payment_settings_view()

    @router.patch("/settings/payments")
    def patch_payment_settings(
        payload: PaymentSettingsUpdate,
        db: Session = Depends(get_db),
        user: User = Depends(require("settings.manage")),
    ):
        from app.services.audit import write_audit

        data = payload.model_dump(exclude_unset=True)
        try:
            saved = save_payment_settings(data)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        changed = sorted(k for k in data if k not in {"clickpesa_api_key", "clickpesa_checksum_key"} or str(data[k] or "").strip())
        # Never write secret values to the audit log; names only.
        write_audit(db, user, "settings.payments", "site", "payments", ", ".join(changed))
        db.commit()
        return saved

    return router
