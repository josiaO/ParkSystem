"""Flutterwave v3 mobile-money (Tanzania) provider.

Behaviour follows the official v3 docs:

* charge:   POST {base}/charges?type=mobile_money_tanzania
            body: tx_ref, amount, currency=TZS, email, phone_number, network?
            -> data.status == "pending", data.id, data.flw_ref
* verify:   GET  {base}/transactions/{id}/verify
            GET  {base}/transactions/verify_by_reference?tx_ref=...
            -> data.status == "successful", data.tx_ref, data.amount, data.currency
* webhook:  v3 docs send the configured secret hash verbatim in ``verif-hash``;
            newer docs send ``flutterwave-signature`` = base64(HMAC-SHA256(raw body,
            secret hash)). Both are accepted with constant-time comparison.

A webhook is only a *hint*. Money is credited exclusively after
``query_status`` confirms status/tx_ref/amount/currency server-side.

TEST mode is the default: the secret key must start with ``FLWSECK_TEST-``
unless ``flutterwave_allow_live_keys`` is set explicitly.
"""

from __future__ import annotations

import base64
from decimal import Decimal
import hashlib
import hmac
import json
from typing import Any

from app.config import settings
from app.infrastructure.payments.common import (
    ProviderError,
    ProviderHTTP,
    amount_string,
    msisdn_local,
    new_reference,
    normalize_msisdn,
    redact,
    scrub_text,
    to_decimal,
)

TEST_KEY_PREFIX = "FLWSECK_TEST-"
LIVE_KEY_PREFIX = "FLWSECK-"
SUCCESS_STATES = {"successful"}
FAILED_STATES = {"failed", "cancelled", "canceled", "error", "abandoned", "voided", "reversed"}
NETWORKS = {"airtel": "Airtel", "tigo": "Tigo", "halopesa": "Halopesa", "vodacom": "Vodafone", "vodafone": "Vodafone"}


def _flutterwave_signature(raw_body: bytes, secret_hash: str) -> str:
    digest = hmac.new(secret_hash.encode("utf-8"), raw_body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


class FlutterwavePaymentProvider:
    id = "flutterwave"
    method = "MOBILE_MONEY"

    def __init__(self, http: ProviderHTTP | None = None):
        self._http = http

    # ------------------------------------------------------------ config --
    @property
    def secret_key(self) -> str:
        return (settings.flutterwave_secret_key or "").strip()

    @property
    def secret_hash(self) -> str:
        return (settings.flutterwave_secret_hash or "").strip()

    @property
    def base_url(self) -> str:
        return (settings.flutterwave_base_url or "https://api.flutterwave.com/v3").rstrip("/")

    def mode(self) -> str:
        key = self.secret_key
        if not key:
            return "UNCONFIGURED"
        if key.startswith(TEST_KEY_PREFIX):
            return "TEST"
        if key.startswith(LIVE_KEY_PREFIX):
            return "LIVE"
        return "INVALID"

    def configured(self) -> bool:
        return self.mode() in {"TEST", "LIVE"}

    def live_allowed(self) -> bool:
        return bool(settings.flutterwave_allow_live_keys) and (
            not settings.payments_live_provider_confirmation_required or settings.payments_live_provider_confirmed
        )

    def availability(self) -> tuple[bool, str]:
        mode = self.mode()
        if mode == "UNCONFIGURED":
            return False, "SMARTPARK_FLUTTERWAVE_SECRET_KEY is not set"
        if mode == "INVALID":
            return False, "Flutterwave secret key must start with FLWSECK_TEST- (or FLWSECK- when live keys are allowed)"
        if mode == "LIVE" and not self.live_allowed():
            return False, "LIVE_PROVIDER_CONFIRMATION_REQUIRED: live Flutterwave key present but live use not confirmed"
        if not self.secret_hash:
            return False, "SMARTPARK_FLUTTERWAVE_SECRET_HASH (webhook secret) is not set"
        return True, ""

    def health(self) -> dict[str, Any]:
        ok, reason = self.availability()
        body = {
            "provider_id": self.id,
            "mode": self.mode(),
            "configured": self.configured(),
            "available": ok,
            "reason": reason,
            "webhook_secret_configured": bool(self.secret_hash),
            "base_url": self.base_url,
            "breaker": self.http.breaker.snapshot(),
        }
        return body

    @property
    def http(self) -> ProviderHTTP:
        if self._http is None:
            self._http = ProviderHTTP(
                "flutterwave",
                timeout=settings.payments_http_timeout_seconds,
                secrets_=(self.secret_key, self.secret_hash),
            )
        return self._http

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.secret_key}", "Content-Type": "application/json"}

    # --------------------------------------------------------- protocol --
    async def create_intent(self, request: dict[str, Any]) -> dict[str, Any]:
        currency = (request.get("currency") or "TZS").upper()
        amount = to_decimal(request.get("amount"))
        if amount <= 0:
            raise ValueError("amount must be positive")
        phone = normalize_msisdn(str(request.get("phone") or request.get("phone_number") or ""))
        network = str(request.get("network") or settings.flutterwave_default_network or "").strip().lower()
        if network and network not in NETWORKS:
            raise ValueError(f"unknown mobile network: {network}")
        return {
            "status": "CREATED",
            "provider_id": self.id,
            "method": self.method,
            "tx_ref": request.get("tx_ref") or new_reference("SPFW"),
            "amount": amount_string(amount, currency),
            "currency": currency,
            "phone": phone,
            "network": NETWORKS.get(network, ""),
            "session_id": request.get("session_id"),
            "token": request.get("token"),
        }

    async def initiate_collection(self, intent: dict[str, Any]) -> dict[str, Any]:
        ok, reason = self.availability()
        if not ok:
            return {"status": "BLOCKED", "provider_id": self.id, "error": reason, "tx_ref": intent.get("tx_ref")}
        currency = (intent.get("currency") or "TZS").upper()
        body: dict[str, Any] = {
            "tx_ref": intent["tx_ref"],
            "amount": amount_string(intent["amount"], currency),
            "currency": currency,
            "email": settings.flutterwave_customer_email or "payments@smartpark.local",
            "phone_number": msisdn_local(intent["phone"]),
            "meta": {"session_id": intent.get("session_id"), "source": "smartpark-edge"},
        }
        if intent.get("network"):
            body["network"] = intent["network"]
        try:
            code, res = await self.http.request(
                "POST", f"{self.base_url}/charges?type=mobile_money_tanzania", headers=self._headers(), json=body
            )
        except ProviderError as exc:
            return {"status": "FAILED", "provider_id": self.id, "error": str(exc), "retryable": exc.retryable,
                    "tx_ref": intent["tx_ref"]}
        data = res.get("data") if isinstance(res, dict) else None
        data = data if isinstance(data, dict) else {}
        if code >= 400 or (isinstance(res, dict) and res.get("status") == "error"):
            message = scrub_text(str((res or {}).get("message") or f"HTTP {code}"), self.secret_key)
            return {"status": "FAILED", "provider_id": self.id, "error": message, "tx_ref": intent["tx_ref"],
                    "raw": redact(res)}
        provider_status = str(data.get("status") or "").lower()
        status = "SUCCEEDED" if provider_status in SUCCESS_STATES else "FAILED" if provider_status in FAILED_STATES else "PENDING"
        if status == "SUCCEEDED":
            # Never trust the charge response for money; verification decides.
            status = "PENDING"
        return {
            "status": status,
            "provider_id": self.id,
            "tx_ref": intent["tx_ref"],
            "provider_transaction_id": str(data.get("id") or "") or None,
            "provider_ref": data.get("flw_ref"),
            "provider_status": provider_status,
            "message": scrub_text(str(res.get("message") or data.get("processor_response") or ""), self.secret_key),
            "raw": redact(data),
        }

    async def verify_callback(self, request: dict[str, Any]) -> dict[str, Any]:
        """Authenticate a webhook. Returns verified=True only for a genuine signature.

        This does *not* mean money moved: the caller must still run query_status.
        """
        raw: bytes = request.get("raw_body") or b""
        headers = {str(k).lower(): str(v) for k, v in (request.get("headers") or {}).items()}
        secret = self.secret_hash
        if not secret:
            return {"verified": False, "error": "webhook secret not configured"}
        verif_hash = headers.get("verif-hash", "")
        signature = headers.get("flutterwave-signature", "")
        genuine = False
        if verif_hash:
            genuine = hmac.compare_digest(verif_hash.encode("utf-8"), secret.encode("utf-8"))
        if not genuine and signature:
            genuine = hmac.compare_digest(signature.encode("utf-8"), _flutterwave_signature(raw, secret).encode("utf-8"))
        if not genuine:
            return {"verified": False, "error": "invalid webhook signature"}
        try:
            payload = json.loads(raw.decode("utf-8") or "{}") if raw else {}
        except Exception:
            return {"verified": False, "error": "malformed webhook body"}
        if not isinstance(payload, dict):
            return {"verified": False, "error": "malformed webhook body"}
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        return {
            "verified": True,
            "provider_id": self.id,
            "event": payload.get("event") or payload.get("event.type") or "",
            "tx_ref": data.get("tx_ref") or data.get("txRef") or "",
            "provider_transaction_id": str(data.get("id") or "") or None,
            "provider_ref": data.get("flw_ref") or data.get("flwRef"),
            "provider_status": str(data.get("status") or "").lower(),
            "amount": data.get("amount"),
            "currency": data.get("currency"),
            "raw": redact(payload),
        }

    async def query_status(self, provider_ref: str) -> dict[str, Any]:
        """Server-side truth. ``provider_ref`` is a Flutterwave id or our tx_ref."""
        ok, reason = self.availability()
        if not ok:
            return {"status": "UNKNOWN", "provider_id": self.id, "error": reason}
        ref = str(provider_ref or "").strip()
        if not ref:
            return {"status": "UNKNOWN", "provider_id": self.id, "error": "missing reference"}
        if ref.isdigit():
            url = f"{self.base_url}/transactions/{ref}/verify"
        else:
            url = f"{self.base_url}/transactions/verify_by_reference?tx_ref={ref}"
        try:
            code, res = await self.http.request("GET", url, headers=self._headers())
        except ProviderError as exc:
            return {"status": "UNKNOWN", "provider_id": self.id, "error": str(exc), "retryable": exc.retryable}
        data = res.get("data") if isinstance(res, dict) else None
        if code == 404 or not isinstance(data, dict):
            message = scrub_text(str((res or {}).get("message") or f"HTTP {code}"), self.secret_key)
            status = "PENDING" if code == 404 else "UNKNOWN"
            return {"status": status, "provider_id": self.id, "error": message}
        provider_status = str(data.get("status") or "").lower()
        if provider_status in SUCCESS_STATES:
            status = "SUCCEEDED"
        elif provider_status in FAILED_STATES:
            status = "FAILED"
        else:
            status = "PENDING"
        amount: Decimal | None
        try:
            amount = to_decimal(data.get("amount")) if data.get("amount") is not None else None
        except ValueError:
            amount = None
        return {
            "status": status,
            "provider_id": self.id,
            "provider_status": provider_status,
            "tx_ref": data.get("tx_ref") or "",
            "provider_transaction_id": str(data.get("id") or "") or None,
            "provider_ref": data.get("flw_ref"),
            "amount": str(amount) if amount is not None else None,
            "currency": (data.get("currency") or "").upper() or None,
            "raw": redact(data),
        }

    async def refund(self, provider_transaction_id: str, *, amount: Any = None) -> dict[str, Any]:
        return {"ok": False, "status": "UNSUPPORTED", "provider_id": self.id,
                "error": "Refunds are operator-initiated in the Flutterwave dashboard for this release"}
