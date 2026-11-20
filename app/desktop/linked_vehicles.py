"""Desktop dialogs: linked vehicle groups, company fleets, visitor passes, manual exit.

The Site Service decides everything (app/services/vehicle_groups.py); these
dialogs only show its answer and send the operator's choice with a reason.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QRadioButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from app.desktop.api import api
from app.desktop.common import run_task
from app.desktop.presentation import configure_table

STATE_TEXT = {
    "ACTIVE": "Inside",
    "EXIT_UNCONFIRMED": "Exit not confirmed",
    "RECONCILIATION": "Needs supervisor",
    "RELEASED": "Left",
}
RELEASE_TEXT = {
    "EXIT_LANE": "Exit camera + barrier (default)",
    "PASSAGE_CONFIRMED": "Passage sensor or guard only (strict)",
}


def _fill(table: QTableWidget, rows: list[list]) -> None:
    table.setRowCount(len(rows))
    for r, values in enumerate(rows):
        for c, value in enumerate(values):
            table.setItem(r, c, QTableWidgetItem(str(value)))


# ----------------------------------------------------------------- groups

class GroupEditDialog(QDialog):
    def __init__(self, parent=None, group: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Edit linked group" if group else "New linked group")
        form = QFormLayout(self)
        self.kind = QComboBox()
        self.kind.addItem("Private owner — one car inside at a time", "PRIVATE")
        self.kind.addItem("Company fleet — own limit", "FLEET")
        self.name = QLineEdit()
        self.company = QLineEdit(); self.company.setPlaceholderText("Shown at the gate: Company: …")
        self.owner = QLineEdit()
        self.phone = QLineEdit()
        self.limit = QSpinBox(); self.limit.setRange(0, 500); self.limit.setSpecialValueText("No limit")
        self.release = QComboBox()
        for key, text in RELEASE_TEXT.items():
            self.release.addItem(text, key)
        self.enabled = QCheckBox("Enabled"); self.enabled.setChecked(True)
        self.notes = QLineEdit()
        if group:
            self.kind.setCurrentIndex(max(0, self.kind.findData(group.get("kind"))))
            self.name.setText(group.get("name") or "")
            self.company.setText(group.get("company_name") or "")
            self.owner.setText(group.get("owner_name") or "")
            self.phone.setText(group.get("contact_phone") or "")
            self.limit.setValue(int(group.get("max_active_sessions") or 0))
            self.release.setCurrentIndex(max(0, self.release.findData(group.get("exit_release"))))
            self.enabled.setChecked(bool(group.get("enabled", True)))
            self.notes.setText(group.get("notes") or "")
        else:
            self.limit.setValue(1)
        form.addRow("Type", self.kind)
        form.addRow("Group name", self.name)
        form.addRow("Company", self.company)
        form.addRow("Owner / contact", self.owner)
        form.addRow("Phone", self.phone)
        form.addRow("Cars inside at once", self.limit)
        form.addRow("Exit releases the group", self.release)
        form.addRow("", self.enabled)
        form.addRow("Notes", self.notes)
        help_text = QLabel(
            "Private owner: only one of the linked cars may be inside. If a car stays overnight, the others "
            "stay blocked until it has left. Company fleet: set how many may be inside (0 = no limit)."
        )
        help_text.setWordWrap(True)
        form.addRow(help_text)
        save = QPushButton("Save"); save.clicked.connect(self.accept); form.addRow(save)
        self.kind.currentIndexChanged.connect(self._kind_changed)
        self._kind_changed()

    def _kind_changed(self):
        private = self.kind.currentData() == "PRIVATE"
        self.limit.setEnabled(not private)
        if private:
            self.limit.setValue(1)

    def payload(self) -> dict:
        return {
            "kind": self.kind.currentData(),
            "name": self.name.text().strip(),
            "company_name": self.company.text().strip(),
            "owner_name": self.owner.text().strip(),
            "contact_phone": self.phone.text().strip(),
            "max_active_sessions": self.limit.value(),
            "exit_release": self.release.currentData(),
            "enabled": self.enabled.isChecked(),
            "notes": self.notes.text().strip(),
        }


class MembersDialog(QDialog):
    """Tick the registered vehicles that belong to this group."""

    def __init__(self, parent, group: dict, vehicles: list[dict]):
        super().__init__(parent)
        self.setWindowTitle(f"Vehicles of {group.get('name')}")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("A vehicle belongs to one group at most. Ticking it here moves it from any other group."))
        self.list = QListWidget()
        for vehicle in vehicles:
            other = vehicle.get("group_id") and vehicle.get("group_id") != group.get("id")
            label = vehicle["plate"] + (f"  ({vehicle.get('owner_name')})" if vehicle.get("owner_name") else "")
            if other:
                label += f"  — now in {vehicle.get('group_name')}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, vehicle["id"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if vehicle.get("group_id") == group.get("id") else Qt.CheckState.Unchecked)
            self.list.addItem(item)
        layout.addWidget(self.list, 1)
        save = QPushButton("Save"); save.clicked.connect(self.accept); layout.addWidget(save)

    def vehicle_ids(self) -> list[int]:
        out = []
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                out.append(int(item.data(Qt.ItemDataRole.UserRole)))
        return out


class GroupsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Linked vehicles and company fleets")
        self.resize(900, 460)
        layout = QVBoxLayout(self)
        note = QLabel("Cars of one private owner share one parking place. Company cars show their company at the gate.")
        note.setWordWrap(True); layout.addWidget(note)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Group", "Belongs to", "Type", "Inside at once", "Cars", "Inside now", "Status"])
        configure_table(self.table); layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        manage = api.can("subscribers.manage")
        self.new_btn = QPushButton("New group…"); self.new_btn.clicked.connect(self.new); self.new_btn.setVisible(manage)
        self.edit_btn = QPushButton("Edit…"); self.edit_btn.clicked.connect(self.edit); self.edit_btn.setVisible(manage)
        self.members_btn = QPushButton("Vehicles…"); self.members_btn.clicked.connect(self.members); self.members_btn.setVisible(manage)
        refresh = QPushButton("Refresh"); refresh.clicked.connect(self.refresh)
        for b in (self.new_btn, self.edit_btn, self.members_btn, refresh):
            row.addWidget(b)
        row.addStretch(); layout.addLayout(row)
        self.rows: list[dict] = []
        self.refresh()

    def refresh(self):
        run_task(self, lambda: api.get("/vehicle-groups"), self._show, title="Linked vehicles")

    def _show(self, rows):
        self.rows = rows or []
        _fill(self.table, [[
            g.get("name"), g.get("display_name"), "Company fleet" if g.get("kind") == "FLEET" else "Private owner",
            g.get("max_active_sessions") or "No limit",
            ", ".join(m["plate"] for m in g.get("members") or []) or "—",
            ", ".join(f"{o['plate']} ({STATE_TEXT.get(o['state'], o['state'])})" for o in g.get("inside") or []) or "—",
            ("Full" if g.get("locked") else "Free") if g.get("enabled") else "Disabled",
        ] for g in self.rows])

    def _selected(self):
        r = self.table.currentRow()
        return self.rows[r] if 0 <= r < len(self.rows) else None

    def new(self):
        d = GroupEditDialog(self)
        if d.exec():
            payload = d.payload()
            run_task(self, lambda: api.post("/vehicle-groups", payload), lambda _r: self.refresh(),
                     buttons=self.new_btn, busy_text="Saving…", title="New group")

    def edit(self):
        g = self._selected()
        if not g:
            QMessageBox.information(self, "Edit", "Select a group first."); return
        d = GroupEditDialog(self, g)
        if d.exec():
            payload = d.payload(); gid = g["id"]
            run_task(self, lambda: api.patch(f"/vehicle-groups/{gid}", payload), lambda _r: self.refresh(),
                     buttons=self.edit_btn, busy_text="Saving…", title="Edit group")

    def members(self):
        g = self._selected()
        if not g:
            QMessageBox.information(self, "Vehicles", "Select a group first."); return

        def loaded(vehicles):
            d = MembersDialog(self, g, vehicles or [])
            if d.exec():
                ids = d.vehicle_ids(); gid = g["id"]
                run_task(self, lambda: api.put(f"/vehicle-groups/{gid}/members", {"vehicle_ids": ids}),
                         lambda _r: self.refresh(), buttons=self.members_btn, busy_text="Saving…", title="Vehicles")
        run_task(self, lambda: api.get("/vehicles"), loaded, buttons=self.members_btn, busy_text="Loading…", title="Vehicles")


# ----------------------------------------------------------------- visitors

class VisitorsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Visitor passes")
        self.resize(860, 440)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("A visitor pass lets one plate in without registering the vehicle. It ends by itself."))
        form = QFormLayout()
        self.plate = QLineEdit(); self.name = QLineEdit(); self.host = QComboBox(); self.host_name = QLineEdit()
        self.hours = QDoubleSpinBox(); self.hours.setRange(0.5, 744); self.hours.setValue(8); self.hours.setSuffix(" h")
        self.entries = QSpinBox(); self.entries.setRange(0, 1000); self.entries.setValue(1); self.entries.setSpecialValueText("Any number")
        self.purpose = QLineEdit()
        form.addRow("Plate", self.plate); form.addRow("Visitor", self.name)
        form.addRow("Visiting company / group", self.host); form.addRow("Host person", self.host_name)
        form.addRow("Valid for", self.hours); form.addRow("Entries", self.entries); form.addRow("Purpose", self.purpose)
        layout.addLayout(form)
        row = QHBoxLayout()
        self.add_btn = QPushButton("Create pass"); self.add_btn.clicked.connect(self.create)
        self.revoke_btn = QPushButton("Revoke selected"); self.revoke_btn.clicked.connect(self.revoke)
        row.addWidget(self.add_btn); row.addWidget(self.revoke_btn); row.addStretch(); layout.addLayout(row)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Plate", "Visitor", "Visiting", "Until", "Entries", "State", "Purpose"])
        configure_table(self.table); layout.addWidget(self.table, 1)
        self.rows: list[dict] = []
        self.host.addItem("—", None)
        run_task(self, lambda: api.get("/vehicle-groups"), self._hosts, on_error=lambda _m, _e: None)
        self.refresh()

    def _hosts(self, groups):
        for g in groups or []:
            self.host.addItem(g.get("display_name") or g.get("name"), g.get("id"))

    def refresh(self):
        run_task(self, lambda: api.get("/visitor-passes"), self._show, title="Visitor passes")

    def _show(self, rows):
        self.rows = rows or []
        _fill(self.table, [[
            v["plate"], v.get("visitor_name") or "—", v.get("host_name") or v.get("belongs_to") or "—",
            (v.get("valid_until") or "")[:16].replace("T", " "),
            f"{v.get('entries_used')}/{v.get('max_entries') or '∞'}", v.get("state"), v.get("purpose") or "",
        ] for v in self.rows])

    def create(self):
        if not self.plate.text().strip():
            QMessageBox.information(self, "Visitor pass", "Enter the plate."); return
        payload = {
            "plate": self.plate.text().strip(), "visitor_name": self.name.text().strip(),
            "host_group_id": self.host.currentData(), "host_name": self.host_name.text().strip(),
            "hours": float(self.hours.value()), "max_entries": int(self.entries.value()),
            "purpose": self.purpose.text().strip(),
        }

        def done(_r):
            self.plate.clear(); self.name.clear(); self.purpose.clear(); self.refresh()
        run_task(self, lambda: api.post("/visitor-passes", payload), done, buttons=self.add_btn,
                 busy_text="Creating…", title="Visitor pass")

    def revoke(self):
        r = self.table.currentRow()
        if not (0 <= r < len(self.rows)):
            QMessageBox.information(self, "Revoke", "Select a pass first."); return
        pid = self.rows[r]["id"]
        run_task(self, lambda: api.post(f"/visitor-passes/{pid}/revoke", {"reason": "revoked at desk"}),
                 lambda _r: self.refresh(), buttons=self.revoke_btn, busy_text="Revoking…", title="Revoke")


# ----------------------------------------------------------------- manual exit

class ManualExitDialog(QDialog):
    """Guard confirms a car left. Opening the boom by hand is not enough on its own."""

    def __init__(self, parent, view: dict):
        super().__init__(parent)
        self.view = view
        self.result_data = None
        self.setWindowTitle(f"Confirm exit — {view.get('plate')}")
        layout = QHBoxLayout(self)
        self.photo = QLabel("Loading entry photo…"); self.photo.setMinimumSize(320, 200)
        self.photo.setAlignment(Qt.AlignmentFlag.AlignCenter); self.photo.setObjectName("video")
        self.photo.setAccessibleName("Entry photograph of this visit")
        layout.addWidget(self.photo, 1)
        right = QVBoxLayout(); layout.addLayout(right, 1)
        plate = QLabel(view.get("plate") or "—"); plate.setStyleSheet("font-size:28px;font-weight:700;letter-spacing:2px")
        right.addWidget(plate)
        occ = view.get("occupancy") or {}
        lines = [
            view.get("belongs_to") or (f"Owner: {view['owner_name']}" if view.get("owner_name") else "Not a linked vehicle"),
            f"Visit #{view.get('session_id')} · {view.get('parker_kind')} · {view.get('status')}",
            f"Entered {(view.get('entry_time') or '')[:16].replace('T', ' ')} · {(view.get('stay') or {}).get('duration_label') or ''}",
        ]
        if occ:
            lines.append(f"Group place: {STATE_TEXT.get(occ.get('state'), occ.get('state'))}")
        info = QLabel("\n".join(lines)); info.setWordWrap(True); right.addWidget(info)
        note = QLabel(view.get("image_note") or ""); note.setWordWrap(True); right.addWidget(note)
        self.left = QRadioButton("The vehicle has left — close the visit and free its place")
        self.unsure = QRadioButton("I am not sure it left — send to a supervisor")
        group = QButtonGroup(self); group.addButton(self.left); group.addButton(self.unsure)
        if view.get("needs_supervisor"):
            self.left.setEnabled(False); self.unsure.setChecked(True)
            warn = QLabel("A supervisor must decide this exit (Exits waiting → Reconcile).")
            warn.setStyleSheet("font-weight:700"); right.addWidget(warn)
        else:
            self.left.setChecked(True)
        right.addWidget(self.left); right.addWidget(self.unsure)
        self.reason = QLineEdit(); self.reason.setPlaceholderText("Reason (required): what you saw")
        right.addWidget(self.reason)
        self.ok_btn = QPushButton("Record"); self.ok_btn.clicked.connect(self.submit)
        self.ok_btn.setEnabled(bool(view.get("can_confirm") or view.get("occupancy")))
        right.addWidget(self.ok_btn); right.addStretch()
        if view.get("snapshot_url"):
            run_task(self, lambda: api.get_bytes(view["snapshot_url"], timeout=12), self._photo,
                     on_error=lambda _m, _e: self.photo.setText("Entry photo not available."))
        else:
            self.photo.setText("No entry photo stored for this visit.")

    def _photo(self, data):
        pix = QPixmap(); pix.loadFromData(data or b"")
        if pix.isNull():
            self.photo.setText("Entry photo not available."); return
        self.photo.setPixmap(pix.scaled(420, 260, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def submit(self):
        reason = self.reason.text().strip()
        if len(reason) < 3:
            QMessageBox.warning(self, "Confirm exit", "Enter a reason (at least 3 characters)."); return
        payload = {"session_id": self.view["session_id"], "outcome": "LEFT" if self.left.isChecked() else "UNCERTAIN",
                   "reason": reason, "identified_by": self.view.get("identified_by") or "SESSION"}

        def done(result):
            self.result_data = result
            self.accept()
        run_task(self, lambda: api.post("/exits/confirm", payload, timeout=20), done, buttons=self.ok_btn,
                 busy_text="Recording…", title="Confirm exit")


def open_manual_exit(parent, query: str, on_done=None) -> None:
    """Look the visit up (session number, receipt QR or plate) and open the confirmation."""
    from urllib.parse import quote

    def loaded(rows):
        rows = rows or []
        if not rows:
            QMessageBox.information(parent, "Confirm exit", "No visit found."); return
        view = rows[0]
        if len(rows) > 1:
            from PySide6.QtWidgets import QInputDialog
            labels = [f"#{r['session_id']} {r['plate']} — {r.get('status')}" for r in rows]
            choice, ok = QInputDialog.getItem(parent, "Confirm exit", "Which visit?", labels, 0, False)
            if not ok:
                return
            view = rows[labels.index(choice)]
        d = ManualExitDialog(parent, view)
        if d.exec() and on_done is not None:
            on_done(d.result_data)
    run_task(parent, lambda: api.get(f"/exits/lookup?q={quote(query, safe='')}", timeout=15), loaded, title="Confirm exit")


class PendingExitsDialog(QDialog):
    """Linked cars inside, exits not confirmed, and cases waiting for a supervisor."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Linked vehicles inside and exits waiting")
        self.resize(900, 420)
        layout = QVBoxLayout(self)
        self.only_waiting = QCheckBox("Only exits waiting for a decision"); self.only_waiting.toggled.connect(self.refresh)
        layout.addWidget(self.only_waiting)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Plate", "Belongs to", "State", "Since", "Visit", "Visit open"])
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        configure_table(self.table); layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.confirm_btn = QPushButton("Confirm exit…"); self.confirm_btn.clicked.connect(self.confirm)
        self.reconcile_btn = QPushButton("Reconcile (supervisor)…"); self.reconcile_btn.clicked.connect(self.reconcile)
        self.reconcile_btn.setVisible(api.can("exits.reconcile"))
        refresh = QPushButton("Refresh"); refresh.clicked.connect(self.refresh)
        row.addWidget(self.confirm_btn); row.addWidget(self.reconcile_btn); row.addWidget(refresh); row.addStretch()
        layout.addLayout(row)
        self.rows: list[dict] = []
        self.refresh()

    def refresh(self):
        include = "false" if self.only_waiting.isChecked() else "true"
        run_task(self, lambda: api.get(f"/exits/pending?include_active={include}"), self._show, title="Exits")

    def _show(self, rows):
        self.rows = rows or []
        _fill(self.table, [[
            o["plate"], o.get("belongs_to") or o.get("group_name"), STATE_TEXT.get(o["state"], o["state"]),
            (o.get("claimed_at") or "")[:16].replace("T", " "), f"#{o.get('session_id')}",
            "Yes" if o.get("session_open") else "No",
        ] for o in self.rows])

    def _selected(self):
        r = self.table.currentRow()
        if not (0 <= r < len(self.rows)):
            QMessageBox.information(self, "Exits", "Select a vehicle first."); return None
        return self.rows[r]

    def confirm(self):
        o = self._selected()
        if o:
            open_manual_exit(self, f"#{o['session_id']}", on_done=lambda _r: self.refresh())

    def reconcile(self):
        o = self._selected()
        if not o:
            return
        from PySide6.QtWidgets import QInputDialog

        choices = ["The vehicle has left — release the group", "The vehicle is still inside — keep the group locked"]
        choice, ok = QInputDialog.getItem(self, "Reconcile", f"{o['plate']} ({o.get('belongs_to')}):", choices, 0, False)
        if not ok:
            return
        reason, ok = QInputDialog.getText(self, "Reconcile", "Reason and evidence checked (required):")
        if not ok or len((reason or "").strip()) < 3:
            return
        payload = {"occupancy_id": o["id"], "decision": "RELEASE" if choice == choices[0] else "KEEP_INSIDE",
                   "reason": reason.strip()}
        run_task(self, lambda: api.post("/exits/reconcile", payload), lambda _r: self.refresh(),
                 buttons=self.reconcile_btn, busy_text="Saving…", title="Reconcile")
