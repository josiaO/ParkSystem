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



class OverstayAfterGraceTests(unittest.TestCase):
    """A paid car still inside after its exit grace owes the rest of its stay."""

    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        from app.services.fee_engine import normalize_tariff_rules

        # Car1 defaults: 45/35-minute blocks, so 50 min and 90 min price differently.
        self.rules = normalize_tariff_rules(None, car_type="Car1")

    def tearDown(self):
        self.engine.dispose()

    def _paid_visit(self, db, *, paid_minutes_ago: int, stayed_minutes: int):
        from app.services.simulation import quote_session

        now = datetime.now(timezone.utc)
        paid_at = now - timedelta(minutes=paid_minutes_ago)
        row = ParkingSession(plate="T555OVR", status="ACTIVE", currency="TZS", amount_due=0, amount_paid=0,
                             public_token="tok-over", tariff_rules=self.rules,
                             entry_time=paid_at - timedelta(minutes=stayed_minutes))
        db.add(row)
        db.commit()
        quote_session(db, row, at=paid_at)
        record_succeeded_payment(db, row, amount=float(row.amount_due), idempotency_key="over-1")
        row.paid_at = paid_at
        row.payment_exit_grace_until = paid_at + timedelta(minutes=15)
        db.commit()
        return row

    def test_inside_grace_nothing_changes(self):
        from app.infrastructure.payments.ledger import reopen_after_grace

        with self.Session() as db:
            row = self._paid_visit(db, paid_minutes_ago=5, stayed_minutes=50)
            self.assertFalse(reopen_after_grace(db, row))
            self.assertEqual(row.status, "PAID")

    def test_after_grace_more_is_due_and_a_new_payment_gets_a_new_grace(self):
        from app.infrastructure.payments.ledger import reopen_expired_graces
        from app.services.public_pay import public_session_payload

        with self.Session() as db:
            row = self._paid_visit(db, paid_minutes_ago=40, stayed_minutes=50)   # 1h30 inside, paid for 50 min
            paid_before = float(row.amount_paid)
            self.assertEqual(reopen_expired_graces(db), 1)
            db.refresh(row)
            self.assertEqual(row.status, "ACTIVE")
            self.assertIsNone(row.payment_exit_grace_until)
            self.assertGreater(float(row.amount_due), paid_before)
            body = public_session_payload(db, row)
            self.assertFalse(body["paid"])
            self.assertTrue(body["payable"])
            self.assertAlmostEqual(body["amount_remaining"], float(row.amount_due) - paid_before)
            out = record_succeeded_payment(db, row, amount=body["amount_remaining"], idempotency_key="over-2")
            row = out["session"]
            self.assertEqual(row.status, "PAID")
            self.assertGreater(_aware(row.payment_exit_grace_until), datetime.now(timezone.utc))

    def test_phone_page_shows_the_overstay_before_the_sweep_runs(self):
        from app.services.public_pay import public_session_payload

        with self.Session() as db:
            row = self._paid_visit(db, paid_minutes_ago=40, stayed_minutes=50)
            body = public_session_payload(db, row)
            self.assertTrue(body["payable"])
            self.assertFalse(body["paid"])

    def test_car_that_left_is_not_reopened(self):
        from app.infrastructure.payments.ledger import reopen_expired_graces

        with self.Session() as db:
            row = self._paid_visit(db, paid_minutes_ago=40, stayed_minutes=50)
            row.exit_time = datetime.now(timezone.utc) - timedelta(minutes=30)
            db.commit()
            self.assertEqual(reopen_expired_graces(db), 0)


if __name__ == "__main__":
    unittest.main()
