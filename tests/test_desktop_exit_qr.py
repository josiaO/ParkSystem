"""Phase 2.4 desktop: QR exit fallback shows a camera/receipt plate mismatch."""

from __future__ import annotations

import os
from types import MethodType, SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

import app.desktop.main as desktop  # noqa: E402

# Keep a reference for the whole module: a freed QApplication crashes Qt.
_APP = QApplication.instance() or QApplication([])


class _FakeApi:
    def __init__(self, result):
        self.result = result
        self.posted = []

    def get(self, path, timeout=8):
        assert path == "/gates"
        return [{"id": 2, "name": "Gate B", "enabled": True, "cameras": [
            {"id": 20, "name": "B exit", "lane_direction": "EXIT"},
            {"id": 21, "name": "B entry", "lane_direction": "ENTRY"},
        ]}]

    def post(self, path, payload=None, timeout=15):
        self.posted.append((path, payload))
        return self.result


def _page(visit):
    page = SimpleNamespace(visit=visit, refreshed=False)
    page.refresh = lambda: setattr(page, "refreshed", True)
    for name in ("_exit_lanes", "_report_exit", "exit_with_receipt"):
        setattr(page, name, MethodType(getattr(desktop.Sessions, name), page))
    return page


def test_exit_with_receipt_posts_the_token_and_warns_on_mismatch():
    fake = _FakeApi({"ok": True, "barrier_opened": True, "message": "Exit authorized.",
                     "plate_mismatch": {"camera_plate": "T999ZZZ", "session_plate": "T500AAA"}})
    page = _page({"token": "tok-1", "plate": "T500AAA", "still_inside": True})
    with patch.object(desktop, "api", fake), \
         patch.object(desktop.QInputDialog, "getItem", return_value=("Gate B — B exit", True)) as chooser, \
         patch.object(desktop.QMessageBox, "warning") as warning, \
         patch.object(desktop.QMessageBox, "information") as info:
        page.exit_with_receipt()
    assert chooser.call_args.args[3] == ["Gate B — B exit"]  # exit lanes only
    assert fake.posted == [("/exit/qr-scan", {"gate_id": 2, "camera_id": 20, "raw_scan": "tok-1"})]
    assert "T999ZZZ" in warning.call_args.args[2] and "T500AAA" in warning.call_args.args[2]
    info.assert_not_called()
    assert page.refreshed


def test_exit_with_receipt_reports_payment_needed():
    fake = _FakeApi({"ok": False, "pay_required": True, "message": "Pay TZS 2,000 first."})
    page = _page({"token": "tok-2", "plate": "T1", "still_inside": True})
    with patch.object(desktop, "api", fake), \
         patch.object(desktop.QInputDialog, "getItem", return_value=("Gate B — B exit", True)), \
         patch.object(desktop.QMessageBox, "information") as info:
        page.exit_with_receipt()
    assert "Payment needed" in info.call_args.args[2]
