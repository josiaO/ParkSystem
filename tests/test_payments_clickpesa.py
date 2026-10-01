"""ClickPesa provider: live-disabled by default, official checksum, verified webhook."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings
from app.infrastructure.payments import is_external_provider, list_payment_providers
from app.infrastructure.payments.clickpesa import ClickPesaPaymentProvider, canonicalize, payload_checksum

CHECKSUM_KEY = "clickpesa-checksum-key-1234"


class FakeHTTP:
    def __init__(self):
        self.calls: list[tuple[str, str, dict | None, dict | None]] = []
        self.routes: list[tuple[str, str, int, object]] = []

        class _Breaker:
            def snapshot(self):
                return {"state": "CLOSED"}

        self.breaker = _Breaker()

    def on(self, method, part, status, body):
        self.routes.append((method, part, status, body))
        return self

    async def request(self, method, url, *, headers=None, json=None):
        self.calls.append((method, url, json, headers))
        for m, part, status, body in self.routes:
            if m == method and part in url:
                return status, body
        return 404, {"message": "no route"}


def live_settings(**overrides):
    values = {
        "clickpesa_client_id": "IDTEST1234",
        "clickpesa_api_key": "SKTESTapikeyapikeyapikey",
        "clickpesa_checksum_key": CHECKSUM_KEY,
        "clickpesa_live_enabled": False,
        "payments_live_provider_confirmation_required": True,
        "payments_live_provider_confirmed": False,
    }
    values.update(overrides)
    return [patch.object(settings, k, v) for k, v in values.items()]


class ChecksumTests(unittest.TestCase):
    def test_matches_official_reference_algorithm(self):
        payload = {
            "currency": "USD", "amount": 100, "reference": "TX123",
            "customer": {"phone": "+255123456789", "name": "John Doe", "email": "john@example.com"},
            "exchange": {"toCurrency": "TZS", "fromCurrency": "TZS", "rate": "1", "amount": "1000"},
        }
        # Reference implementation from docs.clickpesa.com/home/checksum
        canonical = json.dumps(canonicalize(payload), separators=(",", ":"), sort_keys=False)
        expected = hmac.new(b"secret-key", canonical.encode(), hashlib.sha256).hexdigest()
        self.assertEqual(payload_checksum("secret-key", payload), expected)
        reordered = {"reference": "TX123", "amount": 100, "currency": "USD",
                     "exchange": payload["exchange"], "customer": payload["customer"]}
        self.assertEqual(payload_checksum("secret-key", reordered), expected)
        # checksum / checksumMethod fields are excluded from the computation
        self.assertEqual(payload_checksum("secret-key", {**payload, "checksum": "x", "checksumMethod": "HMAC"}), expected)


class ClickPesaProviderTests(unittest.TestCase):
    def setUp(self):
        self.http = FakeHTTP()
        self.provider = ClickPesaPaymentProvider(http=self.http)

    def _with(self, patches):
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])

    def test_registered_and_external(self):
        self.assertIn("clickpesa", list_payment_providers())
        self.assertTrue(is_external_provider("clickpesa"))

    def test_live_disabled_by_default_even_when_configured(self):
        self._with(live_settings())
        self.assertEqual(self.provider.mode(), "LIVE_DISABLED")
        ok, reason = self.provider.availability()
        self.assertFalse(ok)
        self.assertIn("LIVE_PROVIDER_CONFIRMATION_REQUIRED", reason)
        out = asyncio.run(self.provider.initiate_collection({"tx_ref": "SP1", "amount": "1500", "currency": "TZS",
                                                             "phone": "+255712345678"}))
        self.assertEqual(out["status"], "BLOCKED")
        self.assertEqual(self.http.calls, [], "no network call may happen while live is disabled")

    def test_live_enabled_flag_alone_is_not_enough(self):
        self._with(live_settings(clickpesa_live_enabled=True))
        self.assertFalse(self.provider.availability()[0])
        out = asyncio.run(self.provider.initiate_collection({"tx_ref": "SP1", "amount": "1500", "currency": "TZS",
                                                             "phone": "+255712345678"}))
        self.assertEqual(out["status"], "BLOCKED")

    def test_confirmed_live_uses_token_preview_initiate_with_checksum(self):
        self._with(live_settings(clickpesa_live_enabled=True, payments_live_provider_confirmed=True))
        self.http.on("POST", "/generate-token", 200, {"success": True, "token": "Bearer eyJ.fake"})
        self.http.on("POST", "/payments/preview-ussd-push-request", 200, {"activeFees": [], "availableMethods": [{"name": "MPESA", "status": "AVAILABLE"}]})
        self.http.on("POST", "/payments/initiate-ussd-push-request", 200,
                     {"id": "ORD1LCP1", "status": "PROCESSING", "orderReference": "SP1", "paymentReference": "PR1"})
        intent = asyncio.run(self.provider.create_intent({"amount": "1500", "currency": "TZS", "phone": "0712345678"}))
        out = asyncio.run(self.provider.initiate_collection({**intent, "tx_ref": "SP1"}))
        self.assertEqual(out["status"], "PENDING")
        self.assertEqual(out["provider_transaction_id"], "ORD1LCP1")
        urls = [u for _, u, _, _ in self.http.calls]
        self.assertTrue(urls[0].endswith("/generate-token"))
        self.assertIn("preview-ussd-push-request", urls[1])
        self.assertIn("initiate-ussd-push-request", urls[2])
        token_headers = self.http.calls[0][3]
        self.assertEqual(token_headers["client-id"], "IDTEST1234")
        body = self.http.calls[2][2]
        self.assertEqual(body["amount"], "1500")
        self.assertEqual(body["currency"], "TZS")
        self.assertEqual(body["orderReference"], "SP1")
        self.assertEqual(body["phoneNumber"], "255712345678")
        self.assertEqual(body["checksum"], payload_checksum(CHECKSUM_KEY, {k: v for k, v in body.items() if k != "checksum"}))
        self.assertEqual(self.http.calls[2][3]["Authorization"], "Bearer eyJ.fake")

    def test_webhook_requires_valid_checksum(self):
        self._with(live_settings())
        data = {"id": "ORD1LCP1", "status": "SUCCESS", "paymentReference": "PR1", "orderReference": "SP1",
                "collectedAmount": "1500", "collectedCurrency": "TZS", "message": "success", "channel": "MPESA"}
        payload = {"event": "PAYMENT RECEIVED", "data": data}
        good = {**payload, "checksum": payload_checksum(CHECKSUM_KEY, payload), "checksumMethod": "HMAC-SHA256"}
        ok = asyncio.run(self.provider.verify_callback({"raw_body": json.dumps(good).encode(), "headers": {}}))
        self.assertTrue(ok["verified"])
        self.assertEqual(ok["tx_ref"], "SP1")
        self.assertEqual(ok["amount"], "1500")
        bad = {**payload, "checksum": "0" * 64}
        rejected = asyncio.run(self.provider.verify_callback({"raw_body": json.dumps(bad).encode(), "headers": {}}))
        self.assertFalse(rejected["verified"])
        missing = asyncio.run(self.provider.verify_callback({"raw_body": json.dumps(payload).encode(), "headers": {}}))
        self.assertFalse(missing["verified"])
        tampered = {**good, "data": {**data, "collectedAmount": "99999"}}
        self.assertFalse(asyncio.run(self.provider.verify_callback({"raw_body": json.dumps(tampered).encode(),
                                                                    "headers": {}}))["verified"])

    def test_webhook_unverifiable_without_checksum_key(self):
        self._with(live_settings(clickpesa_checksum_key=""))
        out = asyncio.run(self.provider.verify_callback({"raw_body": b'{"event":"PAYMENT RECEIVED"}', "headers": {}}))
        self.assertFalse(out["verified"])

    def test_query_status_normalises_states(self):
        self._with(live_settings())
        self.http.on("POST", "/generate-token", 200, {"success": True, "token": "Bearer eyJ.fake"})
        self.http.on("GET", "/payments/SP1", 200, [
            {"id": "A", "status": "PENDING", "orderReference": "SP1"},
            {"id": "B", "status": "SUCCESS", "orderReference": "SP1", "collectedAmount": 1500, "collectedCurrency": "TZS"},
        ])
        self.http.on("GET", "/payments/SP2", 200, [{"id": "C", "status": "FAILED", "orderReference": "SP2"}])
        self.http.on("GET", "/payments/SP3", 404, {"message": "Invalid or missing payment: SP3"})
        ok = asyncio.run(self.provider.query_status("SP1"))
        self.assertEqual((ok["status"], ok["provider_transaction_id"], ok["amount"], ok["currency"]),
                         ("SUCCEEDED", "B", "1500", "TZS"))
        self.assertEqual(asyncio.run(self.provider.query_status("SP2"))["status"], "FAILED")
        self.assertEqual(asyncio.run(self.provider.query_status("SP3"))["status"], "PENDING")
        # Token is cached across calls.
        self.assertEqual(sum(1 for _, u, _, _ in self.http.calls if u.endswith("/generate-token")), 1)

    def test_health_never_leaks_credentials(self):
        self._with(live_settings())
        text = json.dumps(self.provider.health())
        self.assertNotIn("SKTESTapikey", text)
        self.assertNotIn(CHECKSUM_KEY, text)
        self.assertIn("LIVE_DISABLED", text)


if __name__ == "__main__":
    unittest.main()
