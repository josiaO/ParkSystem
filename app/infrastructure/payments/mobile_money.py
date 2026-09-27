"""Mobile-money provider seam. SUCCEEDED is only written after a verified webhook."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from app.config import settings


class MobileMoneyPaymentProvider:
    """Placeholder aggregator (Selcom/M-Pesa style). Never trust a redirect URL."""

    id = "mobile_money"

    async def create_intent(self, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "CREATED",
            "provider_id": self.id,
            "checkout_url": str(request.get("checkout_url") or ""),
            "provider_ref": str(request.get("provider_ref") or request.get("idempotency_key") or ""),
            **{k: v for k, v in request.items() if k != "checkout_url"},
        }

    async def initiate_collection(self, intent: dict[str, Any]) -> dict[str, Any]:
        return {"status": "PENDING", "provider_id": self.id, "verified": False, **intent}

    def _secret(self) -> bytes:
        return str(getattr(settings, "mobile_money_webhook_secret", "") or "").encode("utf-8")

    def signature_for(self, body: bytes | str) -> str:
        payload = body if isinstance(body, bytes) else str(body).encode("utf-8")
        secret = self._secret()
        if not secret:
            return ""
        return hmac.new(secret, payload, hashlib.sha256).hexdigest()

    async def verify_callback(self, request: dict[str, Any]) -> dict[str, Any]:
        secret = self._secret()
        provided = str(request.get("signature") or request.get("x_signature") or "").strip()
        body = request.get("raw_body")
        if isinstance(body, bytes):
            payload = body
        else:
            payload = str(body or request.get("payload") or "").encode("utf-8")
        if not secret:
            return {"status": "FAILED", "provider_id": self.id, "verified": False, "error": "webhook secret is not set"}
        expected = hmac.new(secret, payload, hashlib.sha256).hexdigest()
        if not provided or not hmac.compare_digest(expected, provided):
            return {"status": "FAILED", "provider_id": self.id, "verified": False, "error": "invalid webhook signature"}
        return {
            "status": "SUCCEEDED",
            "provider_id": self.id,
            "verified": True,
            "session_id": request.get("session_id"),
            "amount": request.get("amount"),
            "provider_ref": request.get("provider_ref") or "",
        }

    async def query_status(self, provider_ref: str) -> dict[str, Any]:
        return {"status": "PENDING", "provider_id": self.id, "provider_ref": provider_ref, "verified": False}
