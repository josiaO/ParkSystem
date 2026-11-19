"""The site's payment_exit_grace_seconds decides how long a paid car may take to reach the exit."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import Base
from app.infrastructure.payments.ledger import DEFAULT_EXIT_GRACE_SECONDS, record_succeeded_payment
from app.models import ParkingSession, SiteSetting


def _aware(value):
    return value if value is None or value.tzinfo else value.replace(tzinfo=timezone.utc)


class PaymentExitGraceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

    def tearDown(self):
        self.engine.dispose()

    def _pay(self, grace_setting=None):
        with self.Session() as db:
            if grace_setting is not None:
                db.add(SiteSetting(key="parking", value={"payment_exit_grace_seconds": grace_setting}))
            row = ParkingSession(plate="T123ABC", status="CLOSED", currency="TZS", amount_due=1000, amount_paid=0,
                                 public_token="tok-grace", entry_time=datetime.now(timezone.utc) - timedelta(hours=1))
            db.add(row)
            db.commit()
            out = record_succeeded_payment(db, row, amount=1000, operator_id=None, idempotency_key="grace-1")
            row = out["session"]
            return _aware(row.paid_at), _aware(row.payment_exit_grace_until)

    def test_configured_grace_is_used(self):
        paid_at, until = self._pay(120)
        self.assertEqual(until - paid_at, timedelta(seconds=120))

    def test_zero_means_no_grace(self):
        _, until = self._pay(0)
        self.assertIsNone(until)

    def test_default_when_not_configured(self):
        paid_at, until = self._pay()
        self.assertEqual(until - paid_at, timedelta(seconds=DEFAULT_EXIT_GRACE_SECONDS))


if __name__ == "__main__":
    unittest.main()
