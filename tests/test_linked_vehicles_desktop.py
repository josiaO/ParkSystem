"""Desktop dialogs for linked vehicles render and send what the Site Service expects (offscreen Qt)."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

_APP = QApplication.instance() or QApplication([])

from app.desktop import linked_vehicles as lv  # noqa: E402


class LinkedVehicleDialogTests(unittest.TestCase):
    def test_private_group_is_locked_to_one_car(self):
        d = lv.GroupEditDialog()
        d.name.setText("Obeid cars")
        self.assertEqual(d.payload()["kind"], "PRIVATE")
        self.assertFalse(d.limit.isEnabled())
        self.assertEqual(d.payload()["max_active_sessions"], 1)
        d.kind.setCurrentIndex(d.kind.findData("FLEET"))
        self.assertTrue(d.limit.isEnabled())
        d.limit.setValue(4)
        d.company.setText("ACME Logistics Ltd")
        self.assertEqual(d.payload()["max_active_sessions"], 4)
        self.assertEqual(d.payload()["company_name"], "ACME Logistics Ltd")

    def test_uncertain_exit_cannot_be_confirmed_by_guard(self):
        view = {"session_id": 7, "plate": "T777XYZ", "status": "ACTIVE", "parker_kind": "MONTHLY",
                "belongs_to": "Private: J. Obeid", "occupancy": {"id": 3, "state": "RECONCILIATION"},
                "needs_supervisor": True, "can_confirm": False, "snapshot_url": None}
        d = lv.ManualExitDialog(None, view)
        self.assertFalse(d.left.isEnabled())
        self.assertTrue(d.unsure.isChecked())

    def test_vehicle_dialog_sends_group(self):
        import app.desktop.main as main

        d = main.VehicleDialog(plans=[{"id": 1, "name": "Monthly"}],
                               groups=[{"id": 9, "name": "ACME fleet", "display_name": "Company: ACME Logistics Ltd"}])
        d.plate.setText("T301FLT")
        d.group.setCurrentIndex(d.group.findData(9))
        self.assertEqual(d.payload()["group_id"], 9)
        self.assertEqual(d.group.currentText(), "Company: ACME Logistics Ltd")


if __name__ == "__main__":
    unittest.main()
