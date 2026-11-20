"""Mobile money end to end: Zirp's real ClickPesa adapter and webhook route
against the bundled mock ClickPesa (``app.mock_services.clickpesa``).

Only the network is replaced (in-process ASGI). Every scenario asserts the
ledger: what the driver paid is credited exactly once, and nothing else is.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api_main import app, ensure_roles
from app.config import settings
from app.db import Base, get_db
from app.infrastructure.payments import PROVIDERS
from app.infrastructure.payments.clickpesa import is_mock_host
from app.mock_services.clickpesa import MockClickPesa, create_app
from app.models import ParkingSession, PaymentIntent, PaymentTransaction
from app.services import mobile_payments

CLIENT_ID, API_KEY, CHECKSUM_KEY = "mock-client", "mock-api-key", "mock-checksum-key"
BASE_URL = "http://clickpesa.test/third-parties"


class ASGIProviderHTTP:
    """ProviderHTTP over an in-process ASGI app (same contract as the real one)."""

    def __init__(self, asgi_app):
        self.asgi_app = asgi_app

        class _Breaker:
            def snapshot(self):
                return {"state": "CLOSED"}

        self.breaker = _Breaker()

        # "lost": the push reaches the provider, the answer never comes back.
        # "refused": the connection fails before the push is sent.
        self.initiate_fault: str | None = None

    async def request(self, method, url, *, headers=None, json=None):
        from app.infrastructure.payments.common import ProviderError

        if self.initiate_fault == "refused" and "initiate-ussd-push-request" in url:
            raise ProviderError("clickpesa unreachable: ConnectError", code="connect_failed", retryable=True)
        transport = httpx.ASGITransport(app=self.asgi_app)
        async with httpx.AsyncClient(transport=transport) as client:
            res = await client.request(method, url, headers=headers, json=json)
        if self.initiate_fault == "lost" and "initiate-ussd-push-request" in url:
            raise ProviderError("clickpesa unreachable: ReadTimeout", code="unreachable", retryable=True)
        try:
            return res.status_code, res.json()
        except ValueError:
            return res.status_code, {"raw": res.text}


class MockClickPesaFlowTests(unittest.TestCase):
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
            row = ParkingSession(plate="T422BCR", status="CLOSED", currency="TZS", amount_due=1500, amount_paid=0,
                                 public_token="tok-mock-1", entry_time=datetime.now(timezone.utc) - timedelta(hours=2))
            db.add(row)
            db.commit()
            self.session_id = row.id
        self._patches = [
            patch.object(settings, "payments_mobile_provider", "clickpesa"),
            patch.object(settings, "clickpesa_base_url", BASE_URL),
            patch.object(settings, "clickpesa_client_id", CLIENT_ID),
            patch.object(settings, "clickpesa_api_key", API_KEY),
            patch.object(settings, "clickpesa_checksum_key", CHECKSUM_KEY),
            patch.object(settings, "clickpesa_live_enabled", False),
            patch.object(settings, "payments_live_provider_confirmed", False),
        ]
        for p in self._patches:
            p.start()
        self.client = TestClient(app)

        async def post_to_zirp(payload: dict) -> str:
            res = self.client.post("/api/webhooks/clickpesa", content=json.dumps(payload).encode(),
                                   headers={"content-type": "application/json"})
            return f"HTTP {res.status_code} {res.text[:160]}"

        self.mock = MockClickPesa(webhook_url="http://zirp/api/webhooks/clickpesa", client_id=CLIENT_ID,
                                  api_key=API_KEY, checksum_key=CHECKSUM_KEY,
                                  webhook_poster=post_to_zirp, sync_webhooks=True)
        self.mock_app = create_app(self.mock)
        self.provider = PROVIDERS["clickpesa"]
        self._saved_http, self._saved_token = self.provider._http, self.provider._token
        self.provider._http, self.provider._token = ASGIProviderHTTP(self.mock_app), ""
        mobile_payments.reset_stats()
        from app.services.payment_prompt_guard import reset as reset_prompt_guard

        reset_prompt_guard()

    def tearDown(self):
        self.client.close()
        for p in self._patches:
            p.stop()
        self.provider._http, self.provider._token = self._saved_http, self._saved_token
        app.dependency_overrides.clear()
        self.engine.dispose()

    # -- helpers ---------------------------------------------------------
    def start(self, phone="0712345678"):
        return self.client.post("/api/public/payment-intents", json={"token": "tok-mock-1", "phone": phone})

    def ref(self) -> str:
        with self.Session() as db:
            return db.scalar(select(PaymentIntent).order_by(PaymentIntent.id.desc())).idempotency_key

    def phone(self, action: str, ref: str | None = None):
        return asyncio.run(self.mock.resolve(ref or self.ref(), action))

    def ledger(self):
        with self.Session() as db:
            txns = db.scalars(select(PaymentTransaction)).all()
            row = db.get(ParkingSession, self.session_id)
            intent = db.scalar(select(PaymentIntent).order_by(PaymentIntent.id.desc()))
            return txns, float(row.amount_paid or 0), intent

    def reconcile(self):
        return asyncio.run(mobile_payments.reconcile_pending(db_factory=self.Session))

    def age_intent(self, minutes: int):
        with self.Session() as db:
            intent = db.scalar(select(PaymentIntent).order_by(PaymentIntent.id.desc()))
            intent.created_at = datetime.now(timezone.utc) - timedelta(minutes=minutes)
            db.commit()

    # -- mode --------------------------------------------------------------
    def test_private_hosts_are_mock_and_real_hosts_need_the_live_flags(self):
        for url in (BASE_URL, "http://127.0.0.1:9100/third-parties", "http://192.168.10.240:9100/x",
                    "http://mockpay:9100", "http://zirp.local:9100"):
            self.assertTrue(is_mock_host(url), url)
        for url in ("https://api.clickpesa.com/third-parties", "https://evil.clickpesa.com",
                    "https://proxy.example.com/clickpesa", "http://8.8.8.8/x"):
            self.assertFalse(is_mock_host(url), url)
        self.assertEqual(self.provider.mode(), "MOCK")
        self.assertEqual(self.provider.availability(), (True, ""))
        self.assertFalse(self.provider.health()["real_money"])
        with patch.object(settings, "clickpesa_base_url", "https://api.clickpesa.com/third-parties"):
            self.assertEqual(self.provider.mode(), "LIVE_DISABLED")
            self.assertFalse(self.provider.availability()[0])
        with patch.object(settings, "clickpesa_checksum_key", ""):
            self.assertFalse(self.provider.availability()[0])     # unsigned webhooks are never OK

    # -- driver outcomes ---------------------------------------------------
    def test_approved_on_the_phone_is_credited_once(self):
        res = self.start()
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["intent"]["status"], "PENDING")
        self.assertEqual(self.ledger()[1], 0.0)                  # nothing paid before the phone says yes
        status = self.client.get("/api/public/payment-status/tok-mock-1").json()
        self.assertEqual(status["payment_mode"], "MOCK")
        self.phone("approve")
        txns, paid, intent = self.ledger()
        self.assertEqual((len(txns), paid, intent.status), (1, 1500.0, "SUCCEEDED"))
        self.assertEqual(self.client.get("/api/public/payment-status/tok-mock-1").json()["paid"], True)

    def test_declined_on_the_phone_pays_nothing(self):
        self.start()
        self.phone("decline")
        txns, paid, intent = self.ledger()
        self.assertEqual((txns, paid, intent.status), ([], 0.0, "FAILED"))

    def test_unanswered_pin_prompt_closes_like_a_real_phone(self):
        """The USSD PIN prompt does not wait for ever: the provider reports a failure."""
        from app.mock_services.clickpesa import Faults

        self.assertGreater(Faults().pin_timeout_seconds, 0)
        self.start()
        payment = self.phone("timeout")
        self.assertEqual(payment.status, "FAILED")
        txns, paid, intent = self.ledger()
        self.assertEqual((txns, paid, intent.status), ([], 0.0, "FAILED"))
        # A prompt already answered is not closed by a late timer.
        self.assertEqual(self.phone("timeout").status, "FAILED")

    def test_ignored_prompt_expires_without_payment(self):
        self.start()
        self.age_intent(minutes=int(settings.payments_intent_expiry_minutes) + 1)
        self.assertEqual(self.reconcile()["expired"], 1)
        txns, paid, intent = self.ledger()
        self.assertEqual((txns, paid, intent.status), ([], 0.0, "EXPIRED"))

    # -- provider faults ---------------------------------------------------
    def test_dropped_webhook_is_settled_by_reconciliation(self):
        self.start()
        self.mock.faults.drop_webhook = True
        self.phone("approve")
        self.assertEqual(self.ledger()[1], 0.0)
        self.age_intent(minutes=1)                               # reconciliation skips brand-new intents
        self.assertEqual(self.reconcile()["credited"], 1)
        self.assertEqual(self.reconcile()["checked"], 0)          # settled: not checked again
        txns, paid, intent = self.ledger()
        self.assertEqual((len(txns), paid, intent.status), (1, 1500.0, "SUCCEEDED"))

    def test_duplicate_webhook_credits_once(self):
        self.start()
        self.mock.faults.duplicate_webhook = True
        payment = self.phone("approve")
        self.assertEqual(len(payment.webhooks), 2)
        txns, paid, _ = self.ledger()
        self.assertEqual((len(txns), paid), (1, 1500.0))

    def test_underpayment_is_not_credited(self):
        self.start()
        self.mock.faults.underpay_by = 500
        self.phone("approve")
        txns, paid, intent = self.ledger()
        self.assertEqual((txns, paid, intent.status), ([], 0.0, "MISMATCH"))
        self.assertIn("amount mismatch", intent.extra.get("verification_error", ""))

    def test_forged_webhook_is_rejected(self):
        self.start()
        self.mock.faults.bad_checksum = True
        payment = self.phone("approve")
        self.assertIn("HTTP 401", payment.webhooks[-1]["result"])
        self.assertEqual(self.ledger()[1], 0.0)

    def test_provider_outage_fails_cleanly_and_recovers(self):
        self.mock.faults.provider_down = True
        res = self.start("0712000001")
        self.assertEqual(res.status_code, 503, res.text)
        self.assertFalse(res.json()["ok"])
        self.mock.faults.provider_down = False
        self.provider.http.breaker.success() if hasattr(self.provider.http.breaker, "success") else None
        res = self.start("0712000002")
        self.assertEqual(res.status_code, 200, res.text)
        self.phone("approve")
        self.assertEqual(self.ledger()[1], 1500.0)

    # -- money that arrives late or goes back --------------------------------
    def test_success_after_local_expiry_is_still_credited(self):
        self.start()
        self.age_intent(minutes=int(settings.payments_intent_expiry_minutes) + 1)
        self.reconcile()
        self.assertEqual(self.ledger()[2].status, "EXPIRED")
        self.phone("approve")                                      # driver approves late; money is taken
        txns, paid, intent = self.ledger()
        self.assertEqual((len(txns), paid, intent.status), (1, 1500.0, "SUCCEEDED"))
        self.assertTrue(intent.extra.get("late_success"))
        self.assertEqual(mobile_payments.stats()["late_credited"], 1)

    # -- push request whose answer never came back --------------------------
    def test_lost_push_response_stays_pending_and_approval_is_credited(self):
        self.provider.http.initiate_fault = "lost"
        res = self.start()
        self.assertEqual(res.status_code, 200, res.text)
        _, paid, intent = self.ledger()
        self.assertEqual((paid, intent.status), (0.0, "PENDING"))       # not FAILED: the prompt may be on the phone
        self.assertTrue(intent.extra.get("outcome_unknown"))
        self.phone("approve")
        txns, paid, intent = self.ledger()
        self.assertEqual((len(txns), paid, intent.status), (1, 1500.0, "SUCCEEDED"))

    def test_lost_push_response_with_dropped_webhook_is_settled_by_reconciliation(self):
        self.provider.http.initiate_fault = "lost"
        self.start()
        self.mock.faults.drop_webhook = True
        self.phone("approve")
        self.age_intent(minutes=1)
        self.assertEqual(self.reconcile()["credited"], 1)
        txns, paid, intent = self.ledger()
        self.assertEqual((len(txns), paid, intent.status), (1, 1500.0, "SUCCEEDED"))

    def test_lost_push_the_provider_never_recorded_expires_without_payment(self):
        self.provider.http.initiate_fault = "lost"
        self.start()
        self.mock.payments.pop(self.ref())                          # the provider has no record of the push
        self.age_intent(minutes=int(settings.payments_intent_expiry_minutes) + 1)
        self.assertEqual(self.reconcile()["expired"], 1)
        txns, paid, intent = self.ledger()
        self.assertEqual((txns, paid, intent.status), ([], 0.0, "EXPIRED"))

    def test_refused_connection_fails_at_once(self):
        self.provider.http.initiate_fault = "refused"
        res = self.start()
        self.assertFalse(res.json()["ok"])
        txns, paid, intent = self.ledger()
        self.assertEqual((txns, paid, intent.status), ([], 0.0, "FAILED"))
        self.assertFalse(intent.extra.get("outcome_unknown"))

    def test_success_webhook_after_local_failure_is_credited(self):
        self.start()
        with self.Session() as db:                                  # e.g. recorded FAILED by an older build
            intent = db.scalar(select(PaymentIntent).order_by(PaymentIntent.id.desc()))
            intent.status = "FAILED"
            db.commit()
        self.phone("approve")                                       # the driver approved; money is taken
        txns, paid, intent = self.ledger()
        self.assertEqual((len(txns), paid, intent.status), (1, 1500.0, "SUCCEEDED"))
        self.assertEqual(intent.extra.get("late_success_after"), "FAILED")

    def test_reversal_after_success_is_flagged_not_hidden(self):
        self.start()
        self.phone("approve")
        self.phone("reverse")
        txns, paid, intent = self.ledger()
        self.assertEqual((len(txns), paid, intent.status), (1, 1500.0, "SUCCEEDED"))   # never silently re-written
        self.assertEqual(intent.extra.get("reversal_status"), "REVERSED")
        self.assertEqual(mobile_payments.stats()["reversals"], 1)


if __name__ == "__main__":
    unittest.main()
