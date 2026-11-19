"""ClickPesa USSD-PUSH collection provider (Tanzania).

Official API shape (docs.clickpesa.com):

* token:    POST {base}/generate-token  headers: client-id, api-key
            -> {"success": true, "token": "Bearer eyJ..."} (valid ~1 h)
* preview:  POST {base}/payments/preview-ussd-push-request
* initiate: POST {base}/payments/initiate-ussd-push-request
            body: amount (string), currency "TZS", orderReference, phoneNumber
            ("2557XXXXXXXX", no '+'), checksum (when enabled on the app)
* status:   GET  {base}/payments/{orderReference} -> list of payments with
            status in SUCCESS | SETTLED | PROCESSING | PENDING | FAILED
* webhook:  {"event": "PAYMENT RECEIVED"|"PAYMENT FAILED", "data": {...},
             "checksum": hex, "checksumMethod": "..."}; checksum is
            HMAC-SHA256(hex) over the compact JSON of the recursively
            key-sorted payload *without* checksum/checksumMethod.

ClickPesa has **no sandbox**: every USSD push moves real money. Collection is
therefore refused unless the operator sets ``clickpesa_live_enabled`` AND
(when ``payments_live_provider_confirmation_required``)
``payments_live_provider_confirmed``. Webhook verification and status queries
stay available so a partially configured site can still be diagnosed.

**MOCK mode.** When ``clickpesa_base_url`` points at a private test host
(loopback, a private LAN address, or a ``.test``/``.local``/``.localhost``/
``.internal``/single-label name), the provider runs in MOCK mode: it may
collect without the live flags, because no real money can move. Credentials
and webhook checksums are still required, exactly as in production. Any
other host, including ``*.clickpesa.com`` and unknown public hosts, keeps
the live gate, so "LIVE" always means real money. The bundled mock server is
``tools/mock_clickpesa``.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import time
from urllib.parse import urlparse
from typing import Any

from app.config import settings
from app.infrastructure.payments.common import (
    initiate_outcome_unknown,
    outcome_unknown,
    ProviderError,
    ProviderHTTP,
    amount_string,
    msisdn_digits,
    new_reference,
    normalize_msisdn,
    redact,
    scrub_text,
    to_decimal,
)

SUCCESS_STATES = {"SUCCESS", "SETTLED"}
FAILED_STATES = {"FAILED", "CANCELLED", "REVERSED", "REFUNDED"}
TOKEN_TTL_SECONDS = 50 * 60
MOCK_HOST_SUFFIXES = (".test", ".local", ".localhost", ".internal", ".lan", ".home.arpa")


def is_mock_host(base_url: str) -> bool:
    """True for a base URL that cannot be the real ClickPesa service.

    Loopback, private/link-local addresses and reserved test names only. An
    unknown public host is *not* a mock: it might proxy the real API.
    """
    host = (urlparse(str(base_url or "")).hostname or "").strip().lower().rstrip(".")
    if not host or host == "clickpesa.com" or host.endswith(".clickpesa.com"):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host == "localhost" or "." not in host or host.endswith(MOCK_HOST_SUFFIXES)
    return address.is_loopback or address.is_private or address.is_link_local


def canonicalize(obj: Any) -> Any:
    if isinstance(obj, list):
        return [canonicalize(item) for item in obj]
    if isinstance(obj, dict):
        return {key: canonicalize(obj[key]) for key in sorted(obj.keys())}
    return obj


def payload_checksum(checksum_key: str, payload: dict[str, Any]) -> str:
    """HMAC-SHA256 hex over the compact JSON of the canonical payload."""
    body = {k: v for k, v in payload.items() if k not in ("checksum", "checksumMethod")}
    serialized = json.dumps(canonicalize(body), separators=(",", ":"), ensure_ascii=False)
    return hmac.new(checksum_key.encode("utf-8"), serialized.encode("utf-8"), hashlib.sha256).hexdigest()


class ClickPesaPaymentProvider:
    id = "clickpesa"
    method = "MOBILE_MONEY"

    def __init__(self, http: ProviderHTTP | None = None):
        self._http = http
        self._token: str = ""
        self._token_at: float = 0.0

    # ------------------------------------------------------------ config --
    @property
    def client_id(self) -> str:
        return (settings.clickpesa_client_id or "").strip()

    @property
    def api_key(self) -> str:
        return (settings.clickpesa_api_key or "").strip()

    @property
    def checksum_key(self) -> str:
        return (settings.clickpesa_checksum_key or "").strip()

    @property
    def base_url(self) -> str:
        return (settings.clickpesa_base_url or "https://api.clickpesa.com/third-parties").rstrip("/")

    def configured(self) -> bool:
        return bool(self.client_id and self.api_key)

    def is_mock(self) -> bool:
        return is_mock_host(self.base_url)

    def live_confirmed(self) -> bool:
        if self.is_mock():
            return False          # a mock never counts as live money
        if not settings.clickpesa_live_enabled:
            return False
        if settings.payments_live_provider_confirmation_required and not settings.payments_live_provider_confirmed:
            return False
        return True

    def mode(self) -> str:
        if not self.configured():
            return "UNCONFIGURED"
        if self.is_mock():
            return "MOCK"
        return "LIVE" if self.live_confirmed() else "LIVE_DISABLED"

    def availability(self) -> tuple[bool, str]:
        if not self.configured():
            return False, "SMARTPARK_CLICKPESA_CLIENT_ID / SMARTPARK_CLICKPESA_API_KEY are not set"
        if self.is_mock():
            if not self.checksum_key:
                return False, "MOCK mode still needs SMARTPARK_CLICKPESA_CHECKSUM_KEY (webhooks must be signed)"
            return True, ""
        if not self.live_confirmed():
            return False, ("LIVE_PROVIDER_CONFIRMATION_REQUIRED: ClickPesa has no sandbox; set "
                           "SMARTPARK_CLICKPESA_LIVE_ENABLED=1 and SMARTPARK_PAYMENTS_LIVE_PROVIDER_CONFIRMED=1 "
                           "to collect real money")
        return True, ""

    def health(self) -> dict[str, Any]:
        ok, reason = self.availability()
        return {
            "provider_id": self.id,
            "mode": self.mode(),
            "real_money": self.mode() == "LIVE",
            "configured": self.configured(),
            "available": ok,
            "reason": reason,
            "checksum_configured": bool(self.checksum_key),
            "base_url": self.base_url,
            "token_cached": bool(self._token and (time.monotonic() - self._token_at) < TOKEN_TTL_SECONDS),
            "breaker": self.http.breaker.snapshot(),
        }

    @property
    def http(self) -> ProviderHTTP:
        if self._http is None:
            self._http = ProviderHTTP(
                "clickpesa",
                timeout=settings.payments_http_timeout_seconds,
                secrets_=(self.api_key, self.checksum_key, self._token),
            )
        return self._http

    async def _bearer(self) -> str:
        if self._token and (time.monotonic() - self._token_at) < TOKEN_TTL_SECONDS:
            return self._token
        code, res = await self.http.request(
            "POST", f"{self.base_url}/generate-token",
            headers={"client-id": self.client_id, "api-key": self.api_key},
        )
        token = (res or {}).get("token") if isinstance(res, dict) else None
        if code >= 400 or not token:
            raise ProviderError(scrub_text(str((res or {}).get("message") or f"token HTTP {code}"), self.api_key),
                                code="auth_failed")
        token = str(token)
        if not token.lower().startswith("bearer "):
            token = f"Bearer {token}"
        self._token, self._token_at = token, time.monotonic()
        return token

    async def _authed(self) -> dict[str, str]:
        return {"Authorization": await self._bearer(), "Content-Type": "application/json"}

    def _signed(self, body: dict[str, Any]) -> dict[str, Any]:
        if self.checksum_key:
            return {**body, "checksum": payload_checksum(self.checksum_key, body)}
        return body

    # --------------------------------------------------------- protocol --
    async def create_intent(self, request: dict[str, Any]) -> dict[str, Any]:
        currency = (request.get("currency") or "TZS").upper()
        amount = to_decimal(request.get("amount"))
        if amount <= 0:
            raise ValueError("amount must be positive")
        phone = normalize_msisdn(str(request.get("phone") or request.get("phone_number") or ""))
        return {
            "status": "CREATED",
            "provider_id": self.id,
            "method": self.method,
            "tx_ref": request.get("tx_ref") or new_reference("SPCP").replace("-", ""),
            "amount": amount_string(amount, currency),
            "currency": currency,
            "phone": phone,
            "session_id": request.get("session_id"),
            "token": request.get("token"),
        }

    async def initiate_collection(self, intent: dict[str, Any]) -> dict[str, Any]:
        ok, reason = self.availability()
        if not ok:
            return {"status": "BLOCKED", "provider_id": self.id, "error": reason, "tx_ref": intent.get("tx_ref")}
        currency = (intent.get("currency") or "TZS").upper()
        body = self._signed({
            "amount": amount_string(intent["amount"], currency),
            "currency": currency,
            "orderReference": intent["tx_ref"],
            "phoneNumber": msisdn_digits(intent["phone"]),
        })
        try:
            headers = await self._authed()
            code, preview = await self.http.request(
                "POST", f"{self.base_url}/payments/preview-ussd-push-request", headers=headers, json=body
            )
            if code >= 400:
                message = scrub_text(str((preview or {}).get("message") or f"preview HTTP {code}"), self.api_key)
                return {"status": "FAILED", "provider_id": self.id, "error": message, "tx_ref": intent["tx_ref"],
                        "raw": redact(preview)}
        except ProviderError as exc:
            # Token or preview failed: the push request was never sent.
            return {"status": "FAILED", "provider_id": self.id, "error": str(exc), "retryable": exc.retryable,
                    "tx_ref": intent["tx_ref"]}
        try:
            code, res = await self.http.request(
                "POST", f"{self.base_url}/payments/initiate-ussd-push-request", headers=headers, json=body
            )
        except ProviderError as exc:
            if outcome_unknown(exc):
                return initiate_outcome_unknown(self.id, intent["tx_ref"], str(exc))
            return {"status": "FAILED", "provider_id": self.id, "error": str(exc), "retryable": exc.retryable,
                    "tx_ref": intent["tx_ref"]}
        res = res if isinstance(res, dict) else {}
        if code >= 500:
            # A server error after the push request arrived does not prove
            # the prompt was not sent to the phone.
            return initiate_outcome_unknown(self.id, intent["tx_ref"], f"initiate HTTP {code}")
        if code >= 400:
            message = scrub_text(str(res.get("message") or f"HTTP {code}"), self.api_key)
            return {"status": "FAILED", "provider_id": self.id, "error": message, "tx_ref": intent["tx_ref"],
                    "raw": redact(res)}
        provider_status = str(res.get("status") or "").upper()
        status = "FAILED" if provider_status in FAILED_STATES else "PENDING"
        return {
            "status": status,
            "provider_id": self.id,
            "tx_ref": intent["tx_ref"],
            "provider_transaction_id": str(res.get("id") or "") or None,
            "provider_ref": res.get("paymentReference"),
            "provider_status": provider_status,
            "message": scrub_text(str(res.get("message") or ""), self.api_key),
            "raw": redact(res),
        }

    async def verify_callback(self, request: dict[str, Any]) -> dict[str, Any]:
        raw: bytes = request.get("raw_body") or b""
        if not self.checksum_key:
            return {"verified": False, "error": "ClickPesa checksum key not configured; webhook cannot be authenticated"}
        try:
            payload = json.loads(raw.decode("utf-8") or "{}") if raw else {}
        except Exception:
            return {"verified": False, "error": "malformed webhook body"}
        if not isinstance(payload, dict):
            return {"verified": False, "error": "malformed webhook body"}
        provided = str(payload.get("checksum") or "")
        if not provided:
            return {"verified": False, "error": "webhook missing checksum"}
        expected = payload_checksum(self.checksum_key, payload)
        if not hmac.compare_digest(provided.lower().encode("utf-8"), expected.encode("utf-8")):
            return {"verified": False, "error": "invalid webhook checksum"}
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        return {
            "verified": True,
            "provider_id": self.id,
            "event": str(payload.get("event") or ""),
            "tx_ref": data.get("orderReference") or "",
            "provider_transaction_id": str(data.get("id") or "") or None,
            "provider_ref": data.get("paymentReference"),
            "provider_status": str(data.get("status") or "").upper(),
            "amount": data.get("collectedAmount"),
            "currency": data.get("collectedCurrency"),
            "raw": redact(payload),
        }

    async def query_status(self, provider_ref: str) -> dict[str, Any]:
        if not self.configured():
            return {"status": "UNKNOWN", "provider_id": self.id, "error": "ClickPesa credentials not configured"}
        ref = str(provider_ref or "").strip()
        if not ref:
            return {"status": "UNKNOWN", "provider_id": self.id, "error": "missing reference"}
        try:
            headers = await self._authed()
            code, res = await self.http.request("GET", f"{self.base_url}/payments/{ref}", headers=headers)
        except ProviderError as exc:
            return {"status": "UNKNOWN", "provider_id": self.id, "error": str(exc), "retryable": exc.retryable}
        if code == 404:
            return {"status": "PENDING", "provider_id": self.id, "tx_ref": ref, "error": "not found yet"}
        rows = res if isinstance(res, list) else ([res] if isinstance(res, dict) and res.get("status") else [])
        if code >= 400 or not rows:
            message = scrub_text(str((res or {}).get("message") if isinstance(res, dict) else f"HTTP {code}"), self.api_key)
            return {"status": "UNKNOWN", "provider_id": self.id, "tx_ref": ref, "error": message}
        # Prefer a successful row; otherwise the latest.
        chosen = next((r for r in rows if str(r.get("status", "")).upper() in SUCCESS_STATES), rows[-1])
        provider_status = str(chosen.get("status") or "").upper()
        if provider_status in SUCCESS_STATES:
            status = "SUCCEEDED"
        elif provider_status in FAILED_STATES:
            status = "FAILED"
        else:
            status = "PENDING"
        amount = chosen.get("collectedAmount")
        try:
            amount_s = str(to_decimal(amount)) if amount not in (None, "") else None
        except ValueError:
            amount_s = None
        return {
            "status": status,
            "provider_id": self.id,
            "provider_status": provider_status,
            "tx_ref": chosen.get("orderReference") or ref,
            "provider_transaction_id": str(chosen.get("id") or "") or None,
            "provider_ref": chosen.get("paymentReference"),
            "amount": amount_s,
            "currency": (chosen.get("collectedCurrency") or "").upper() or None,
            "raw": redact(chosen),
        }

    async def refund(self, provider_transaction_id: str, *, amount: Any = None) -> dict[str, Any]:
        return {"ok": False, "status": "UNSUPPORTED", "provider_id": self.id,
                "error": "Refunds are operator-initiated in the ClickPesa dashboard for this release"}
