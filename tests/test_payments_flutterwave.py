"""Flutterwave provider + public payment-intent flow.

Provider HTTP is faked; the tests assert the ledger invariants from the
Phase 2 Codex §8: signature required, webhook is never proof, server-side
verify decides, duplicates never double-credit, wrong amount/currency/ref
rejected, reconciliation credits exactly once, provider outage leaves cash
and local parking working.
"""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import hmac
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api_main import app, ensure_roles
from app.config import settings
from app.db import Base, get_db
from app.infrastructure.payments import PROVIDERS, is_external_provider, list_payment_providers
from app.infrastructure.payments.common import ProviderError, normalize_msisdn, redact, to_minor_units
from app.infrastructure.payments.flutterwave import FlutterwavePaymentProvider
from app.models import ParkingSession, PaymentIntent, PaymentTransaction, Role, User, UserRole
from app.security import hash_password
from app.services import mobile_payments

SECRET_KEY = "FLWSECK_TEST-0123456789abcdef0123456789abcdef-X"
SECRET_HASH = "smartpark-webhook-hash-1234"


class FakeHTTP:
    """Scripted responses keyed by (method, url-substring)."""

    def __init__(self):
        self.calls: list[tuple[str, str, dict | None]] = []
        self.routes: list[tuple[str, str, int, dict]] = []
        self.fail_with: ProviderError | None = None

        class _Breaker:
            def snapshot(self):
                return {"state": "CLOSED"}

        self.breaker = _Breaker()

    def on(self, method: str, url_part: str, status: int, body: dict):
        self.routes.append((method, url_part, status, body))
        return self

    async def request(self, method, url, *, headers=None, json=None):
        self.calls.append((method, url, json))
        assert headers and headers.get("Authorization", "").startswith("Bearer FLWSECK_TEST-")
        if self.fail_with is not None:
            raise self.fail_with
        for m, part, status, body in self.routes:
            if m == method and part in url:
                return status, body
        return 404, {"status": "error", "message": "no route"}


def charge_ok(tx_ref: str, flw_id: int = 4321):
    return {"status": "success", "message": "Charge initiated",
            "data": {"id": flw_id, "tx_ref": tx_ref, "flw_ref": "FLW-MOCK-1", "status": "pending",
                     "amount": 1500, "currency": "TZS", "auth_model": "MOBILEMONEY"}}


def verify_ok(tx_ref: str, *, amount=1500, currency="TZS", status="successful", flw_id: int = 4321):
    return {"status": "success", "message": "Transaction fetched successfully",
            "data": {"id": flw_id, "tx_ref": tx_ref, "flw_ref": "FLW-MOCK-1", "status": status,
                     "amount": amount, "charged_amount": amount, "currency": currency}}


def signed_headers(body: bytes, *, mode: str = "verif-hash") -> dict[str, str]:
    if mode == "verif-hash":
        return {"verif-hash": SECRET_HASH}
    sig = base64.b64encode(hmac.new(SECRET_HASH.encode(), body, hashlib.sha256).digest()).decode()
    return {"flutterwave-signature": sig}


class CommonHelpersTests(unittest.TestCase):
    def test_e164_normalisation(self):
        self.assertEqual(normalize_msisdn("0712 345 678"), "+255712345678")
        self.assertEqual(normalize_msisdn("+255712345678"), "+255712345678")
        self.assertEqual(normalize_msisdn("255712345678"), "+255712345678")
        self.assertEqual(normalize_msisdn("712345678"), "+255712345678")
        self.assertEqual(normalize_msisdn("+254700111222"), "+254700111222")
        with self.assertRaises(ValueError):
            normalize_msisdn("12")

    def test_minor_units_use_decimal(self):
        self.assertEqual(to_minor_units("1500", "TZS"), 1500)
        self.assertEqual(to_minor_units("15.50", "USD"), 1550)
        self.assertEqual(to_minor_units(Decimal("0.1") + Decimal("0.2"), "USD"), 30)

    def test_redaction_masks_secrets_and_phones(self):
        out = redact({"secret_key": "FLWSECK_TEST-abc", "phone_number": "255712345678",
                      "nested": {"Authorization": "Bearer x", "amount": 10}})
        self.assertEqual(out["secret_key"], "***")
        self.assertTrue(out["phone_number"].endswith("678"))
        self.assertNotIn("255712345", out["phone_number"])
        self.assertEqual(out["nested"]["Authorization"], "***")
        self.assertEqual(out["nested"]["amount"], 10)


class FlutterwaveProviderTests(unittest.TestCase):
    def setUp(self):
        self.http = FakeHTTP()
        self.provider = FlutterwavePaymentProvider(http=self.http)
        self._patches = [
            patch.object(settings, "flutterwave_secret_key", SECRET_KEY),
            patch.object(settings, "flutterwave_secret_hash", SECRET_HASH),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def test_registered_as_external_provider(self):
        self.assertIn("flutterwave", list_payment_providers())
        self.assertTrue(is_external_provider("flutterwave"))
        self.assertFalse(is_external_provider("kiosk_manual"))

    def test_test_mode_is_default_and_live_key_blocked(self):
        self.assertEqual(self.provider.mode(), "TEST")
        self.assertTrue(self.provider.availability()[0])
        with patch.object(settings, "flutterwave_secret_key", "FLWSECK-liveliveliveliveliveliveliv-X"):
            self.assertEqual(self.provider.mode(), "LIVE")
            ok, reason = self.provider.availability()
            self.assertFalse(ok)
            self.assertIn("LIVE_PROVIDER_CONFIRMATION_REQUIRED", reason)
            out = asyncio.run(self.provider.initiate_collection({"tx_ref": "T1", "amount": "1500", "currency": "TZS",
                                                                 "phone": "+255712345678"}))
            self.assertEqual(out["status"], "BLOCKED")
            self.assertEqual(self.http.calls, [])

    def test_charge_uses_tanzania_mobile_money_and_returns_pending(self):
        self.http.on("POST", "/charges?type=mobile_money_tanzania", 200, charge_ok("SPFW-1"))
        intent = asyncio.run(self.provider.create_intent({"amount": "1500", "currency": "TZS", "phone": "0712345678",
                                                          "network": "airtel", "session_id": 7}))
        self.assertEqual(intent["phone"], "+255712345678")
        self.assertEqual(intent["network"], "Airtel")
        out = asyncio.run(self.provider.initiate_collection({**intent, "tx_ref": "SPFW-1"}))
        self.assertEqual(out["status"], "PENDING")
        self.assertEqual(out["provider_transaction_id"], "4321")
        method, url, body = self.http.calls[0]
        self.assertEqual(body["tx_ref"], "SPFW-1")
        self.assertEqual(body["amount"], "1500")
        self.assertEqual(body["currency"], "TZS")
        self.assertEqual(body["phone_number"], "0712345678")
        self.assertEqual(body["network"], "Airtel")

    def test_webhook_signature_required_both_header_styles(self):
        body = json.dumps({"event": "charge.completed", "data": {"id": 4321, "tx_ref": "SPFW-1", "status": "successful",
                                                                  "amount": 1500, "currency": "TZS"}}).encode()
        bad = asyncio.run(self.provider.verify_callback({"raw_body": body, "headers": {"verif-hash": "nope"}}))
        self.assertFalse(bad["verified"])
        none = asyncio.run(self.provider.verify_callback({"raw_body": body, "headers": {}}))
        self.assertFalse(none["verified"])
        ok1 = asyncio.run(self.provider.verify_callback({"raw_body": body, "headers": signed_headers(body)}))
        self.assertTrue(ok1["verified"])
        self.assertEqual(ok1["tx_ref"], "SPFW-1")
        ok2 = asyncio.run(self.provider.verify_callback({"raw_body": body,
                                                         "headers": signed_headers(body, mode="signature")}))
        self.assertTrue(ok2["verified"])
        tampered = asyncio.run(self.provider.verify_callback({"raw_body": body + b" ",
                                                              "headers": signed_headers(body, mode="signature")}))
        self.assertFalse(tampered["verified"])

    def test_query_status_by_id_and_reference(self):
        self.http.on("GET", "/transactions/4321/verify", 200, verify_ok("SPFW-1"))
        self.http.on("GET", "/transactions/verify_by_reference?tx_ref=SPFW-1", 200, verify_ok("SPFW-1"))
        by_id = asyncio.run(self.provider.query_status("4321"))
        by_ref = asyncio.run(self.provider.query_status("SPFW-1"))
        for out in (by_id, by_ref):
            self.assertEqual(out["status"], "SUCCEEDED")
            self.assertEqual(out["tx_ref"], "SPFW-1")
            self.assertEqual(out["amount"], "1500")
            self.assertEqual(out["currency"], "TZS")

    def test_provider_outage_is_reported_not_raised(self):
        self.http.fail_with = ProviderError("flutterwave unreachable: ConnectTimeout", code="unreachable", retryable=True)
        out = asyncio.run(self.provider.initiate_collection({"tx_ref": "T1", "amount": "1500", "currency": "TZS",
                                                             "phone": "+255712345678"}))
        self.assertEqual(out["status"], "FAILED")
        self.assertTrue(out["retryable"])
        status = asyncio.run(self.provider.query_status("T1"))
        self.assertEqual(status["status"], "UNKNOWN")

    def test_health_never_leaks_secrets(self):
        body = json.dumps(self.provider.health())
        self.assertNotIn(SECRET_KEY, body)
        self.assertNotIn(SECRET_HASH, body)
        self.assertIn('"mode": "TEST"', body)


class FlutterwaveApiFlowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

        def override_get_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        with self.Session() as db:
            ensure_roles(db)
            from app.services.modules import apply_profile
            apply_profile(db, "PARKING_PRO")
            admin_role = db.scalar(select(Role).where(Role.name == "Admin"))
            user = User(username="admin", full_name="Test Admin", password_hash=hash_password("correct-horse"))
            db.add(user)
            db.flush()
            db.add(UserRole(user_id=user.id, role_id=admin_role.id))
            row = ParkingSession(plate="T123ABC", status="CLOSED", currency="TZS", amount_due=1500, amount_paid=0,
                                 public_token="tok-flw-1", entry_time=datetime.now(timezone.utc) - timedelta(hours=2))
            db.add(row)
            db.commit()
            self.session_id = row.id
        self.http = FakeHTTP()
        self.provider = PROVIDERS["flutterwave"]
        self._saved_http = self.provider._http
        self.provider._http = self.http
        self._patches = [
            patch.object(settings, "flutterwave_secret_key", SECRET_KEY),
            patch.object(settings, "flutterwave_secret_hash", SECRET_HASH),
            patch.object(settings, "payments_mobile_provider", "flutterwave"),
        ]
        for p in self._patches:
            p.start()
        mobile_payments.reset_stats()
        self.client = TestClient(app)
        token = self.client.post("/auth/login", json={"username": "admin", "password": "correct-horse"}).json()["token"]
        self.headers = {"Authorization": f"Bearer {token}"}

    def tearDown(self):
        self.client.close()
        for p in self._patches:
            p.stop()
        self.provider._http = self._saved_http
        app.dependency_overrides.clear()
        self.engine.dispose()

    # -- helpers ---------------------------------------------------------
    def _start(self, phone="0712345678", **extra):
        res = self.client.post("/api/public/payment-intents", json={"token": "tok-flw-1", "phone": phone, **extra})
        return res

    def _tx_ref(self) -> str:
        with self.Session() as db:
            intent = db.scalar(select(PaymentIntent).where(PaymentIntent.provider_id == "flutterwave"))
            return intent.idempotency_key

    def _webhook(self, tx_ref: str, *, status="successful", amount=1500, currency="TZS", headers=None):
        body = json.dumps({"event": "charge.completed",
                           "data": {"id": 4321, "tx_ref": tx_ref, "flw_ref": "FLW-MOCK-1", "status": status,
                                    "amount": amount, "currency": currency}}).encode()
        return self.client.post("/api/webhooks/flutterwave", content=body,
                                headers=headers if headers is not None else signed_headers(body))

    def _ledger(self):
        with self.Session() as db:
            txns = db.scalars(select(PaymentTransaction)).all()
            row = db.get(ParkingSession, self.session_id)
            return txns, float(row.amount_paid or 0), row.status

    # -- tests -----------------------------------------------------------
    def test_intent_is_pending_and_nothing_is_paid_until_verified(self):
        self.http.on("POST", "/charges", 200, charge_ok("ANY"))
        res = self._start()
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["intent"]["status"], "PENDING")
        self.assertEqual(body["intent"]["amount"], 1500.0)
        self.assertTrue(body["intent"]["phone"].endswith("678"))
        self.assertNotIn("255712345678", res.text)
        txns, paid, status = self._ledger()
        self.assertEqual(txns, [])
        self.assertEqual(paid, 0.0)
        self.assertNotEqual(status, "PAID")
        # The instant simulated path is closed while a real provider is active.
        sim = self.client.post("/p/tok-flw-1/pay", json={"method": "MOBILE_SIMULATED"})
        self.assertEqual(sim.status_code, 409)
        # Status endpoint exposes the pending intent, still unpaid.
        st = self.client.get("/api/public/payment-status/tok-flw-1")
        self.assertEqual(st.status_code, 200)
        self.assertFalse(st.json()["paid"])
        self.assertEqual(st.json()["intent"]["status"], "PENDING")
        self.assertEqual(st.json()["mobile_provider"], "flutterwave")

    def test_webhook_with_invalid_signature_is_rejected(self):
        self.http.on("POST", "/charges", 200, charge_ok("ANY"))
        self._start()
        tx_ref = self._tx_ref()
        res = self._webhook(tx_ref, headers={"verif-hash": "wrong"})
        self.assertEqual(res.status_code, 401)
        txns, paid, _ = self._ledger()
        self.assertEqual(txns, [])
        self.assertEqual(paid, 0.0)
        self.assertEqual(mobile_payments.stats()["webhooks_rejected"], 1)

    def test_signed_webhook_still_requires_server_side_verification(self):
        self.http.on("POST", "/charges", 200, charge_ok("ANY"))
        self._start()
        tx_ref = self._tx_ref()
        # Provider verify says still pending -> genuine webhook must NOT credit.
        self.http.on("GET", "/transactions/4321/verify", 200, verify_ok(tx_ref, status="pending"))
        res = self._webhook(tx_ref)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertFalse(res.json()["credited"])
        txns, paid, _ = self._ledger()
        self.assertEqual(txns, [])
        self.assertEqual(paid, 0.0)
        self.assertTrue(any("/transactions/4321/verify" in url for _, url, _ in self.http.calls))

    def test_verified_webhook_credits_once_and_duplicates_are_idempotent(self):
        self.http.on("POST", "/charges", 200, charge_ok("ANY"))
        self._start()
        tx_ref = self._tx_ref()
        self.http.on("GET", "/transactions/4321/verify", 200, verify_ok(tx_ref))
        first = self._webhook(tx_ref)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertTrue(first.json()["credited"])
        for _ in range(3):
            again = self._webhook(tx_ref)
            self.assertEqual(again.status_code, 200)
            self.assertFalse(again.json()["credited"])
            self.assertTrue(again.json()["duplicate"])
        txns, paid, status = self._ledger()
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0].status, "SUCCEEDED")
        self.assertEqual(txns[0].provider_id, "flutterwave")
        self.assertEqual(txns[0].provider_transaction_id, "flutterwave:4321")
        self.assertEqual(paid, 1500.0)
        self.assertEqual(status, "PAID")
        with self.Session() as db:
            intent = db.scalar(select(PaymentIntent).where(PaymentIntent.idempotency_key == tx_ref))
            self.assertEqual(intent.status, "SUCCEEDED")
            self.assertEqual(txns[0].intent_id, intent.id)
        st = self.client.get("/api/public/payment-status/tok-flw-1").json()
        self.assertTrue(st["paid"])

    def test_wrong_amount_currency_or_reference_never_credits(self):
        self.http.on("POST", "/charges", 200, charge_ok("ANY"))
        self._start()
        tx_ref = self._tx_ref()
        cases = [
            verify_ok(tx_ref, amount=1000),                 # short payment
            verify_ok(tx_ref, currency="USD"),              # wrong currency
            verify_ok("SOMEONE-ELSE", amount=1500),         # foreign reference
        ]
        for verify_body in cases:
            with self.subTest(case=verify_body["data"]):
                with self.Session() as db:
                    intent = db.scalar(select(PaymentIntent).where(PaymentIntent.idempotency_key == tx_ref))
                    intent.status = "PENDING"
                    db.commit()
                self.http.routes = [r for r in self.http.routes if "/verify" not in r[1]]
                self.http.on("GET", "/transactions/4321/verify", 200, verify_body)
                res = self._webhook(tx_ref)
                self.assertEqual(res.status_code, 200, res.text)
                self.assertFalse(res.json()["credited"])
                self.assertEqual(res.json()["status"], "MISMATCH")
                txns, paid, _ = self._ledger()
                self.assertEqual(txns, [])
                self.assertEqual(paid, 0.0)
        self.assertEqual(mobile_payments.stats()["mismatches"], 3)

    def test_unknown_reference_webhook_is_acknowledged_but_ignored(self):
        body = json.dumps({"event": "charge.completed", "data": {"id": 1, "tx_ref": "NOPE", "status": "successful",
                                                                  "amount": 1500, "currency": "TZS"}}).encode()
        res = self.client.post("/api/webhooks/flutterwave", content=body, headers=signed_headers(body))
        self.assertEqual(res.status_code, 202)
        self.assertTrue(res.json()["ignored"])
        self.assertEqual(self._ledger()[0], [])

    def test_reconciliation_converts_pending_to_succeeded_exactly_once(self):
        self.http.on("POST", "/charges", 200, charge_ok("ANY"))
        self._start()
        tx_ref = self._tx_ref()
        with self.Session() as db:  # old enough for the reconciler to pick up
            intent = db.scalar(select(PaymentIntent).where(PaymentIntent.idempotency_key == tx_ref))
            intent.created_at = datetime.now(timezone.utc) - timedelta(minutes=2)
            db.commit()
        self.http.on("GET", "/transactions/4321/verify", 200, verify_ok(tx_ref))
        first = asyncio.run(mobile_payments.reconcile_pending(self.Session))
        self.assertEqual(first["checked"], 1)
        self.assertEqual(first["credited"], 1)
        second = asyncio.run(mobile_payments.reconcile_pending(self.Session))
        self.assertEqual(second["checked"], 0)
        txns, paid, status = self._ledger()
        self.assertEqual(len(txns), 1)
        self.assertEqual(paid, 1500.0)
        self.assertEqual(status, "PAID")
        # Operator endpoint shares the same code path and is idempotent too.
        res = self.client.post("/payments/reconcile", headers=self.headers)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["credited"], 0)

    def test_reconciliation_expires_stale_pending_without_crediting(self):
        self.http.on("POST", "/charges", 200, charge_ok("ANY"))
        self._start()
        tx_ref = self._tx_ref()
        with self.Session() as db:
            intent = db.scalar(select(PaymentIntent).where(PaymentIntent.idempotency_key == tx_ref))
            intent.created_at = datetime.now(timezone.utc) - timedelta(hours=3)
            db.commit()
        self.http.on("GET", "/transactions/4321/verify", 200, verify_ok(tx_ref, status="pending"))
        out = asyncio.run(mobile_payments.reconcile_pending(self.Session))
        self.assertEqual(out["expired"], 1)
        self.assertEqual(self._ledger()[0], [])

    def test_provider_unavailable_leaves_cash_and_local_parking_working(self):
        self.http.fail_with = ProviderError("flutterwave unreachable: ConnectTimeout", code="unreachable", retryable=True)
        res = self._start()
        self.assertEqual(res.status_code, 503, res.text)
        self.assertFalse(res.json()["ok"])
        self.assertEqual(res.json()["intent"]["status"], "FAILED")
        self.assertNotIn(SECRET_KEY, res.text)
        # Cash at the kiosk is a local ledger write and keeps working.
        cash = self.client.post("/p/tok-flw-1/kiosk-pay", headers=self.headers, json={"method": "KIOSK_CASH"})
        self.assertEqual(cash.status_code, 200, cash.text)
        self.assertTrue(cash.json()["paid"])
        txns, paid, status = self._ledger()
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0].provider_id, "kiosk_manual")
        self.assertEqual(status, "PAID")
        # Health still answers and reports the provider truthfully.
        health = self.client.get("/payments/health", headers=self.headers)
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["providers"]["flutterwave"]["mode"], "TEST")
        self.assertNotIn(SECRET_KEY, health.text)
        self.assertNotIn(SECRET_HASH, health.text)

    def test_repeat_start_reuses_fresh_pending_intent(self):
        self.http.on("POST", "/charges", 200, charge_ok("ANY"))
        first = self._start().json()
        second = self._start().json()
        self.assertTrue(second.get("reused"))
        self.assertEqual(first["intent"]["reference"], second["intent"]["reference"])
        self.assertEqual(sum(1 for m, url, _ in self.http.calls if "/charges" in url), 1)

    def test_receipt_page_uses_intent_flow_when_provider_is_external(self):
        page = self.client.get("/p/tok-flw-1")
        self.assertEqual(page.status_code, 200)
        self.assertIn("/api/public/payment-intents", page.text)
        self.assertIn('id="phone"', page.text)
        self.assertIn("const externalPay = true", page.text)
        status = self.client.get("/p/tok-flw-1/status").json()
        self.assertEqual(status["pay_endpoint"], "/api/public/payment-intents")
        self.assertEqual(status["pay_methods"], ["MOBILE_MONEY", "KIOSK_CASH"])

    def test_bad_phone_is_a_400_and_creates_nothing(self):
        res = self._start(phone="12")
        self.assertEqual(res.status_code, 400)
        with self.Session() as db:
            self.assertEqual(db.scalars(select(PaymentIntent)).all(), [])

    def test_public_routes_are_module_gated(self):
        with self.Session() as db:
            from app.services.modules import apply_profile, is_enabled
            apply_profile(db, "LPR_ONLY")
            db.commit()
            self.assertFalse(is_enabled("payments.core", db))
        res = self._start()
        self.assertEqual(res.status_code, 404)
        hook = self.client.post("/api/webhooks/flutterwave", content=b"{}", headers={"verif-hash": SECRET_HASH})
        self.assertEqual(hook.status_code, 404)


if __name__ == "__main__":
    unittest.main()
