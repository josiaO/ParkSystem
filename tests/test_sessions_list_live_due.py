"""The session list shows what an open visit owes now, without saving anything."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch


def _row(**kw):
    base = dict(exit_time=None, status="ACTIVE", parker_kind="CASUAL", tariff_rules={"x": 1}, car_type="Car1",
                site_id=1, amount_paid=0, amount_due=0, entry_time=datetime.now(timezone.utc) - timedelta(hours=2))
    base.update(kw)
    return SimpleNamespace(**base)


def test_open_visits_get_a_live_amount_and_rows_are_not_changed():
    from app import api_main as api

    rows = [_row(), _row(amount_paid=500), _row(status="PAID"), _row(exit_time=datetime.now(timezone.utc)),
            _row(parker_kind="SUBSCRIBER")]
    out = [{"amount_due": 0} for _ in rows]
    with patch("app.services.fee_engine.normalize_tariff_rules", return_value={}), \
         patch("app.services.fee_engine.calculate_car1_fee", return_value=SimpleNamespace(due=2000.0)):
        api._add_live_due(None, rows, out)
    assert [o["due_now"] for o in out] == [2000.0, 1500.0, None, None, None]
    assert out[0]["amount_due"] == 2000.0
    assert all(r.amount_due == 0 for r in rows)          # read-only: nothing written to the visit
