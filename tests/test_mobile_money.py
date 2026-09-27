from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api_main import app, ensure_roles
from app.db import Base, get_db
from app.infrastructure.payments import list_payment_providers, payment_provider_for
from app.infrastructure.payments.mobile_money import MobileMoneyPaymentProvider
from app.models import Role, User, UserRole
from app.security import hash_password


class MobileMoneyProviderTests(unittest.TestCase):
    def test_provider_is_registered(self):
        self.assertIn("mobile_money", list_payment_providers())
        self.assertIsInstance(payment_provider_for("mobile_money"), MobileMoneyPaymentProvider)

    def test_verify_callback_rejects_bad_signature(self):
        provider = MobileMoneyPaymentProvider()
        with patch("app.infrastructure.payments.mobile_money.settings") as cfg:
            cfg.mobile_money_webhook_secret = "test-secret"
            result = asyncio.run(provider.verify_callback({
                "raw_body": b'{"session_id":1}',
                "signature": "deadbeef",
            }))
        self.assertFalse(result["verified"])

    def test_verify_callback_accepts_hmac(self):
        provider = MobileMoneyPaymentProvider()
        body = b'{"session_id":1,"amount":1000}'
        sig = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
        with patch("app.infrastructure.payments.mobile_money.settings") as cfg:
            cfg.mobile_money_webhook_secret = "test-secret"
            result = asyncio.run(provider.verify_callback({
                "raw_body": body,
                "signature": sig,
                "session_id": 1,
                "amount": 1000,
            }))
        self.assertTrue(result["verified"])
        self.assertEqual(result["status"], "SUCCEEDED")


class MobileMoneyWebhookApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
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
            admin_role = db.scalar(select(Role).where(Role.name == "Admin"))
            user = User(username="admin", full_name="Test Admin", password_hash=hash_password("correct-horse"))
            db.add(user)
            db.flush()
            db.add(UserRole(user_id=user.id, role_id=admin_role.id))
            db.commit()
        self.client = TestClient(app)
        token = self.client.post("/auth/login", json={"username": "admin", "password": "correct-horse"}).json()["token"]
        self.headers = {"Authorization": f"Bearer {token}"}

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_unverified_webhook_does_not_mark_paid(self):
        body = json.dumps({"session_id": 1, "amount": 1000}).encode()
        res = self.client.post("/payments/mobile-money/webhook", content=body, headers={"x-signature": "nope"})
        self.assertEqual(res.status_code, 400)


if __name__ == "__main__":
    unittest.main()
