"""Phase 5: configurable tariff and local cash settlement without internet."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import Base
from app.domain.tariff_engine import quote_stay
from app.infrastructure.payments.ledger import (
    FAILED,
    PAYMENT_STATUSES,
    SUCCEEDED,
    paid_total,
    record_succeeded_payment,
)
from app.models import PaymentTransaction, Site
from app.services.parking_sessions import start_entry
from app.services.simulation import mark_paid, quote_session


RULES = {
    "currency": "TZS",
    "day_start": "00:00:00",
    "day_end": "23:59:59",
    "free_day_seconds": 2700,
    "free_night_seconds": 2700,
    "day_block_seconds": 2700,
    "night_block_seconds": 2700,
    "day_block_fee": 1000,
    "night_block_fee": 1000,
    "day_max": 22000,
    "night_max": 14000,
    "daily_wrap_fee": 34000,
    "over_1000_subtract": 1000,
}


class TariffQuoteTests(unittest.TestCase):
    def test_under_grace_is_zero(self):
        start = datetime(2026, 9, 30, 10, 0, tzinfo=timezone.utc)
        quote = quote_stay(start, start + timedelta(minutes=45), RULES)
        self.assertEqual(quote.due_minor, 0)
        self.assertTrue(quote.in_grace)

    def test_first_charge_block(self):
        start = datetime(2026, 9, 30, 10, 0, tzinfo=timezone.utc)
        quote = quote_stay(start, start + timedelta(seconds=2701), RULES)
        self.assertEqual(quote.due_minor, 1000)

    def test_multiple_blocks_from_configuration(self):
        rules = dict(RULES)
        rules["over_1000_subtract"] = 0
        start = datetime(2026, 9, 30, 10, 0, tzinfo=timezone.utc)
        one = quote_stay(start, start + timedelta(seconds=2701), rules)
        two = quote_stay(start, start + timedelta(seconds=5401), rules)
        self.assertGreater(two.due_minor, one.due_minor)
        self.assertEqual(one.currency, "TZS")

    def test_rules_are_required(self):
        start = datetime(2026, 9, 30, 10, 0, tzinfo=timezone.utc)
        with self.assertRaises(ValueError):
            quote_stay(start, start + timedelta(minutes=10), {})

    def test_ledger_status_set_is_complete(self):
        self.assertIn(FAILED, PAYMENT_STATUSES)
        self.assertIn(SUCCEEDED, PAYMENT_STATUSES)


class LocalCashTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        with self.Session() as db:
            db.add(Site(id=1, name="Site"))
            db.commit()

    def tearDown(self):
        self.engine.dispose()

    def _stale_session(self, db, plate="T100PAY"):
        row, _ = start_entry(db, plate=plate, event_id=f"in-{plate}")
        row.entry_time = datetime.now(timezone.utc) - timedelta(hours=2)
        db.commit()
        quote_session(db, row)
        db.refresh(row)
        return row

    def test_cash_payment_and_paid_total(self):
        with self.Session() as db:
            row = self._stale_session(db)
            self.assertGreater(float(row.amount_due or 0), 0)
            paid = mark_paid(db, row, method="KIOSK_CASH")
            self.assertEqual(paid.status, "PAID")
            self.assertEqual(float(paid.amount_paid), float(paid.amount_due))
            self.assertEqual(paid_total(db, paid.id), float(paid.amount_due))
            self.assertEqual(paid.payment_status, SUCCEEDED)
            self.assertIsNotNone(paid.paid_at)
            self.assertIsNotNone(paid.payment_exit_grace_until)
            self.assertGreater(paid.payment_exit_grace_until, paid.paid_at)

    def test_duplicate_cash_submit_is_idempotent(self):
        with self.Session() as db:
            row = self._stale_session(db, "T200DUP")
            first = mark_paid(db, row, method="KIOSK_CASH")
            with self.assertRaises(ValueError):
                mark_paid(db, first, method="KIOSK_CASH")
            count = db.scalar(
                select(func.count()).select_from(PaymentTransaction).where(
                    PaymentTransaction.session_id == first.id,
                    PaymentTransaction.status == SUCCEEDED,
                )
            )
            self.assertEqual(count, 1)

    def test_partial_payment_then_settle(self):
        with self.Session() as db:
            row = self._stale_session(db, "T300PAR")
            due = float(row.amount_due or 0)
            self.assertGreater(due, 1)
            record_succeeded_payment(
                db, row, amount=due / 2, method="KIOSK_CASH",
                idempotency_key=f"session:{row.id}:half",
            )
            db.refresh(row)
            self.assertLess(float(row.amount_paid or 0), due)
            self.assertNotEqual(row.status, "PAID")
            settled = mark_paid(db, row, method="KIOSK_CASH")
            self.assertEqual(settled.status, "PAID")
            self.assertAlmostEqual(float(settled.amount_paid), due, places=2)

    def test_cash_works_with_network_down(self):
        with self.Session() as db:
            row = self._stale_session(db, "T400OFF")
            with patch("httpx.Client") as client:
                client.side_effect = OSError("network unreachable")
                paid = mark_paid(db, row, method="KIOSK_CASH")
            self.assertEqual(paid.status, "PAID")
            self.assertEqual(paid.payment_status, SUCCEEDED)
