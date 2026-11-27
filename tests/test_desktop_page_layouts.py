"""Page layouts: dashboard, payments, reports, gates and hardware lab."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication, QDateEdit, QWidget  # noqa: E402

from app.desktop import common, desk, main  # noqa: E402

_APP = QApplication.instance() or QApplication([])


class InlineWorker(QObject):
    done = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, function):
        super().__init__()
        self.function = function

    def start(self):
        try:
            self.done.emit(self.function())
        finally:
            self.finished.emit()


class PageApi:
    modules = {"profile": "PARKING_PRO", "enabled": [], "onboarding_completed": True}

    def __init__(self, answers):
        self.answers = answers
        self.requests = []

    def can(self, permission):
        return True

    def get(self, path, **kwargs):
        self.requests.append(path)
        for prefix, answer in self.answers.items():
            if path.startswith(prefix):
                return answer
        return {}

    def runtime_client(self):
        return self


@pytest.fixture()
def page_api(monkeypatch):
    def install(answers):
        api = PageApi(answers)
        for module in (main, desk, common):
            monkeypatch.setattr(module, "api", api)
        monkeypatch.setattr(main, "Worker", InlineWorker)
        monkeypatch.setattr(common, "Worker", InlineWorker)
        return api
    return install


def test_dashboard_words_lane_states_in_its_own_language(page_api):
    page_api({"/dashboard": {
        "vehicles_inside": 5, "entries_today": 9, "exits_today": 4, "revenue_today": 0, "currency": "TZS",
        "unpaid_active": 1, "subscribers_inside": 0, "alerts": [],
        "lanes": [{"label": "1# Entry", "camera": "Imeunganishwa", "live_video": "Imeunganishwa",
                   "plate_recognition": "Tayari", "barrier": "Tayari", "last_plate": "T123ABC",
                   "states": {"camera": "online", "live_video": "degraded", "plate_recognition": "ready",
                              "barrier": "unknown"}}],
    }, "/backup": {}})
    page = main.Dashboard()
    page._apply(main.api.get("/dashboard"))
    row = [page.lanes.item(0, c).text() for c in range(6)]
    assert row == ["1# Entry", "Online", "Degraded", "Ready", "Not set", "T123ABC"]
    # The six figures sit in one row.
    assert {page.grid.getItemPosition(i)[0] for i in range(page.grid.count())} == {0}
    page.close()


def test_dashboard_without_states_shows_the_server_words(page_api):
    page_api({})
    page = main.Dashboard()
    page._apply({"lanes": [{"label": "Old server", "camera": "Online", "live_video": "Online",
                            "plate_recognition": "Ready", "barrier": "Ready"}]})
    assert page.lanes.item(0, 1).text() == "Online"
    page.close()


def test_payments_filter_by_date_method_status_and_total_what_was_paid(page_api):
    api = page_api({"/payments": [
        {"created_at": "2026-11-27T08:00:00", "session_id": 1, "method": "KIOSK_CASH", "amount": 1000,
         "currency": "TZS", "status": "SUCCEEDED"},
        {"created_at": "2026-11-27T09:00:00", "session_id": 2, "method": "MOBILE_MONEY", "amount": 2000,
         "currency": "TZS", "status": "SUCCEEDED"},
        {"created_at": "2026-11-27T10:00:00", "session_id": 3, "method": "MOBILE_MONEY", "amount": 5000,
         "currency": "TZS", "status": "FAILED"},
    ]})
    page = main.Payments()
    page.method.setCurrentIndex(page.method.findData("MOBILE_MONEY"))
    page.pay_status.setCurrentIndex(page.pay_status.findData("SUCCEEDED"))
    page.refresh()
    path = api.requests[-1]
    assert path.startswith("/payments?") and "date_from=" in path and "date_to=" in path
    assert "method=MOBILE_MONEY" in path and "status=SUCCEEDED" in path
    assert page.table.rowCount() == 3
    assert "3,000" in page.total.text() or "3000" in page.total.text()     # the failed 5,000 is not counted
    page.close()


def test_report_dates_are_compact_date_pickers(page_api):
    page_api({"/backup": {}})
    page = desk.ReportsPage()
    assert isinstance(page.start, QDateEdit) and isinstance(page.end, QDateEdit)
    assert len(page.start.text()) == 10 and page.start.text()[4] == "-"     # "yyyy-MM-dd", as before
    page.resize(1400, 700); page.show(); _APP.processEvents()
    assert page.start.width() < 300
    page.close()


def test_gates_keep_setup_in_the_list_and_barrier_commands_apart(page_api, monkeypatch):
    page_api({"/gates": [
        {"id": 1, "name": "1#", "mode": "PRODUCTION", "enabled": True,
         "cameras": [{"lane_direction": "ENTRY", "ip_address": "10.0.0.1"}]},
    ]})
    page = main.Gates()
    page._fill(main.api.get("/gates"))
    assert page.table.columnCount() == 5
    assert page.table.cellWidget(0, 4) is None                       # no buttons in the rows
    assert page.table.currentRow() == 0
    assert page.side_buttons[("ENTRY", "open")].isEnabled()
    assert not page.side_buttons[("EXIT", "open")].isEnabled()       # this lane has no exit camera
    sent = []
    monkeypatch.setattr(page, "command_gate", lambda gid, side, action="open": sent.append((gid, side, action)))
    page.side_buttons[("ENTRY", "close")].click()
    assert sent == [(1, "ENTRY", "close")]
    page.close()


def test_hardware_lab_shows_a_readable_summary_and_folds_the_raw_data(page_api):
    page_api({"/hardware/hvx/info": {"available": True, "startup_error": "",
                                     "connections": [{"handle": 0, "ip": "10.0.0.5", "state": 0},
                                                     {"handle": 1, "ip": "10.0.0.6", "state": 0}],
                                     "files": {"NetSDK.dll": True}}})
    page = main.Hardware()
    page.check()
    rows = {page.summary.item(r, 0).text(): page.summary.item(r, 1).text() for r in range(page.summary.rowCount())}
    assert rows["Available"] == "Yes"
    assert rows["Connections 1"].startswith("handle: 0")
    assert rows["Files › NetSDK.dll"] == "Yes"
    assert page.info.isHidden() and '"available": true' in page.info.toPlainText()
    page.raw_toggle.click()
    assert not page.info.isHidden()
    page.close()


def test_payments_endpoint_filters_by_date_method_and_status():
    from datetime import datetime, timezone

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.db import Base
    from app.infrastructure.payments.ledger import list_transactions
    from app.models import PaymentTransaction

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        for n, (day, method, status) in enumerate([(25, "KIOSK_CASH", "SUCCEEDED"), (26, "MOBILE_MONEY", "SUCCEEDED"),
                                                   (27, "MOBILE_MONEY", "FAILED"), (27, "KIOSK_CASH", "SUCCEEDED")]):
            db.add(PaymentTransaction(method=method, status=status, amount=1000, provider_transaction_id=f"t{n}",
                                      idempotency_key=f"k{n}", created_at=datetime(2026, 11, day, 9, tzinfo=timezone.utc)))
        db.commit()
        start, end = datetime(2026, 11, 26, tzinfo=timezone.utc), datetime(2026, 11, 28, tzinfo=timezone.utc)
        assert len(list_transactions(db)) == 4                                           # unfiltered, as before
        assert len(list_transactions(db, start_at=start, end_at=end)) == 3
        assert [t.method for t in list_transactions(db, start_at=start, end_at=end, method="mobile_money")] == ["MOBILE_MONEY", "MOBILE_MONEY"]
        assert len(list_transactions(db, start_at=start, end_at=end, status="SUCCEEDED")) == 2
    engine.dispose()
