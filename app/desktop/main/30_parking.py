from __future__ import annotations

class GateDialog(QDialog):
    def __init__(self, gate=None):
        super().__init__(); self.setWindowTitle("Edit Gate" if gate else "Add Gate")
        self.setMinimumWidth(320); self.setMaximumWidth(480)
        form=QFormLayout(self)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.name=QLineEdit(); self.mode=QComboBox(); self.mode.addItems(["COMMISSIONING","SHADOW","PRODUCTION","MAINTENANCE"])
        self.enabled=QComboBox(); self.enabled.addItems(["Yes","No"])
        if gate:
            self.name.setText(gate["name"]); self.mode.setCurrentText(gate["mode"]); self.enabled.setCurrentText("Yes" if gate["enabled"] else "No")
        form.addRow("Name", self.name); form.addRow("Mode", self.mode); form.addRow("Enabled", self.enabled)
        save=QPushButton("Save Gate"); save.clicked.connect(self.accept); form.addRow(save)
    def payload(self):
        return {"name":self.name.text().strip(),"mode":self.mode.currentText(),"enabled":self.enabled.currentText()=="Yes"}

class Gates(QWidget):
    def __init__(self):
        super().__init__(); l=QVBoxLayout(self)
        title=QLabel("Gates"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
        # Setup above the list; barrier commands in their own box below, for
        # the selected lane. Each row used to carry four Open/Close buttons
        # beside the setup columns (and Live Gates has them per camera).
        self.table=QTableWidget(0,5); self.table.setHorizontalHeaderLabels(["ID","Lane","Mode","Enabled","Sides (camera / controller / display)"])
        configure_table(self.table)
        self._armed_side=None
        row=QHBoxLayout()
        add=QPushButton(action_label("Add Gate", "Ctrl+N")); add.clicked.connect(self.add_gate); add.setVisible(api.can("gates.manage")); add.setToolTip("Add Gate (Ctrl+N)")
        edit=QPushButton(action_label("Edit", "Ctrl+E")); edit.clicked.connect(self.edit_gate); edit.setVisible(api.can("gates.manage")); edit.setToolTip("Edit (Ctrl+E)")
        delete=QPushButton(action_label("Delete", "Del")); delete.clicked.connect(self.delete_gate); delete.setVisible(api.can("gates.manage")); delete.setToolTip("Delete (Del)")
        led=QPushButton("LED text"); led.clicked.connect(self.write_led)
        self.refresh_btn=QPushButton(action_label("Refresh", "F5")); self.refresh_btn.clicked.connect(self.refresh)
        self.status=QLabel(""); self.status.setWordWrap(True)
        row.addWidget(add); row.addWidget(edit); row.addWidget(delete); row.addWidget(self.refresh_btn); row.addStretch(); l.addLayout(row)
        l.addWidget(self.table, 1)
        control=QGroupBox("Barrier control (selected lane)")
        control_l=QVBoxLayout(control)
        buttons=QHBoxLayout()
        self.side_buttons={}
        for side, action, text in (("ENTRY", "open", "Open entry"), ("ENTRY", "close", "Close entry"),
                                   ("EXIT", "open", "Open exit"), ("EXIT", "close", "Close exit")):
            button=QPushButton(text)
            button.clicked.connect(lambda _=False, s=side, a=action: self._command_selected(s, a))
            buttons.addWidget(button)
            self.side_buttons[(side, action)]=button
        buttons.addWidget(led); buttons.addStretch()
        control_l.addLayout(buttons)
        self.shortcut_hint=QLabel("Manual commands apply to one side only, never both barriers. "
                                  "Select a lane, then 1 = entry, 2 = exit; F8 opens it, F9 closes it.")
        self.shortcut_hint.setWordWrap(True); self.shortcut_hint.setObjectName("muted")
        control_l.addWidget(self.shortcut_hint)
        control.setVisible(api.can("gates.open"))
        self.control_box=control
        l.addWidget(control)
        l.addWidget(self.status); self.rows=[]
        self.table.itemSelectionChanged.connect(self._sync_side_buttons)
        self._sync_side_buttons()
        self._loaded=False
        sc1=QShortcut(QKeySequence("1"), self); sc1.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut); sc1.activated.connect(lambda: self.arm_side("ENTRY"))
        sc2=QShortcut(QKeySequence("2"), self); sc2.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut); sc2.activated.connect(lambda: self.arm_side("EXIT"))
    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded:
            self._loaded=True
            self.refresh()
    def refresh(self):
        self.status.setText("Loading lanes…")
        def failed(message, _exc):
            self.status.setText(message)
        run_task(self, lambda: api.runtime_client().get("/gates"), self._fill,
                 buttons=getattr(self, "refresh_btn", None), busy_text="Loading…", on_error=failed)
    def _fill(self, rows):
        rows=rows or []
        self.status.setText("" if rows else "No lanes yet. Add a gate to start.")
        self.rows=rows
        self.table.setRowCount(len(rows))
        for r,g in enumerate(rows):
            cams=g.get("cameras") or []
            summary="; ".join(
                f'{row.get("side") or row.get("lane_direction")}: cam {row.get("ip_address")} / ctrl {row.get("controller_ip") or "—"} / disp {row.get("display_ip") or "—"}'
                for row in cams
            ) or "—"
            for c,v in enumerate([g["id"],g["name"],g["mode"],"Yes" if g["enabled"] else "No", summary]): self.table.setItem(r,c,QTableWidgetItem(str(v)))
        if rows and self.table.currentRow()<0:
            self.table.selectRow(0)
        self._sync_side_buttons()
    def selected_gate(self):
        row=self.table.currentRow()
        if row<0 or row>=len(self.rows): return None
        return self.rows[row]
    def arm_side(self, side):
        self._armed_side=side
        gate=self.selected_gate()
        name=(gate or {}).get("name") or "this lane"
        label="entry" if side=="ENTRY" else "exit"
        self.shortcut_hint.setText(f"{name} {label} is armed. F8 opens it, F9 closes it.")
    def shortcut_side(self):
        gate=self.selected_gate()
        if not gate:
            return None, None
        sides=[]
        seen=set()
        for cam in (gate.get("cameras") or []):
            s=(cam.get("lane_direction") or cam.get("side") or "").upper()
            if s in {"ENTRY","EXIT"} and s not in seen:
                seen.add(s); sides.append(s)
        if self._armed_side in sides:
            return gate, self._armed_side
        if len(sides)==1:
            return gate, sides[0]
        return gate, None
    def _gate_sides(self, gate):
        sides=set()
        for cam in ((gate or {}).get("cameras") or []):
            side=(cam.get("lane_direction") or cam.get("side") or "").upper()
            if side in {"ENTRY","EXIT"}:
                sides.add(side)
        return sides
    def _sync_side_buttons(self):
        gate=self.selected_gate()
        sides=self._gate_sides(gate)
        for (side, _action), button in getattr(self, "side_buttons", {}).items():
            button.setVisible(side in sides or gate is None)
            button.setEnabled(side in sides)
        if hasattr(self, "control_box"):
            name=(gate or {}).get("name")
            self.control_box.setTitle(f"Barrier control · {name}" if name else "Barrier control (select a lane)")
    def _command_selected(self, side, action):
        gate=self.selected_gate()
        if not gate:
            QMessageBox.information(self, "Barrier control", "Select a lane first."); return
        self._open_and_arm(gate["id"], side, action)
    def _open_and_arm(self, gid, side, action):
        self._armed_side=side
        self.arm_side(side)
        self.command_gate(gid, side, action)
    def add_gate(self):
        d=GateDialog()
        if d.exec():
            payload=d.payload()
            run_task(self, lambda: api.runtime_client().post("/gates",payload),
                     lambda _r: (show_status(self, "Gate added."), self.refresh()), title="Add gate", status="Adding gate…")
    def edit_gate(self):
        gate=self.selected_gate()
        if not gate: QMessageBox.information(self,"Edit gate","Select a gate first."); return
        d=GateDialog(gate)
        if d.exec():
            payload=d.payload(); gid=gate['id']
            run_task(self, lambda: api.runtime_client().patch(f"/gates/{gid}",payload),
                     lambda _r: (show_status(self, "Gate saved."), self.refresh()), title="Edit gate", status="Saving gate…")
    def delete_gate(self):
        gate=self.selected_gate()
        if not gate: QMessageBox.information(self,"Delete gate","Select a gate first."); return
        if QMessageBox.question(self,"Delete gate",f"Delete {gate['name']}?")!=QMessageBox.Yes: return
        gid=gate['id']
        run_task(self, lambda: api.runtime_client().delete(f"/gates/{gid}"),
                 lambda _r: (show_status(self, "Gate deleted."), self.refresh()), title="Delete gate", status="Deleting gate…")
    def open_gate(self,gid,side):
        self.command_gate(gid, side, "open")
    def command_gate(self,gid,side,action="open"):
        verb="close" if action=="close" else "open"
        label="entry" if side=="ENTRY" else "exit"
        title=f"{'Close' if verb=='close' else 'Open'} this side"
        prompt=f"{'Close' if verb=='close' else 'Pulse'} only this lane's {label} barrier (not the other side)?"
        if QMessageBox.question(self,title,prompt)!=QMessageBox.Yes: return
        reason,ok=QInputDialog.getText(self,title,"Reason", text=f"manual {verb}")
        if ok and reason:
            self.status.setText(f"Sending {verb} to the {label} barrier…")
            def done(result):
                result=result or {}
                text=str(result.get("message") or result.get("reason") or (f"Barrier {verb} sent." if result.get("ok", True) else "Barrier did not respond."))
                self.status.setText(text)
                QMessageBox.information(self,"Barrier",text)
            def failed(message, _exc):
                self.status.setText(message)
                QMessageBox.warning(self,"Barrier",message)
            run_task(self, lambda: api.runtime_client().post(f"/gates/{gid}/open",{"reason":reason,"side":side,"action":verb}, timeout=20),
                     done, on_error=failed)
    def write_led(self):
        gate=self.selected_gate()
        if not gate: QMessageBox.information(self,"LED","Select a lane first."); return
        cams=gate.get("cameras") or []
        if not cams: QMessageBox.information(self,"LED","No cameras on this lane."); return
        text,ok=QInputDialog.getText(self,"LED text","Message", text="WELCOME")
        if not ok or not text: return
        cam_id=cams[0]['id']
        def done(result):
            result=result or {}
            QMessageBox.information(self,"LED",str(result.get("message") or ("Text sent to the display." if result.get("ok", True) else "The display did not accept the text.")))
        run_task(self, lambda: api.runtime_client().post(f"/cameras/{cam_id}/led",{"text":text}), done, title="LED", status="Sending text to the display…")

class VehicleDialog(QDialog):
    def __init__(self, vehicle=None, plans=None, groups=None):
        super().__init__(); self.setWindowTitle("Edit vehicle" if vehicle else "Register plate")
        form=QFormLayout(self)
        self.plate=QLineEdit(); self.owner=QLineEdit(); self.plan=QComboBox(); self.enabled=QComboBox(); self.enabled.addItems(["Yes","No"]); self.notes=QLineEdit()
        # Linked vehicles: a private owner's cars (one inside at a time) or a company fleet.
        self.group=QComboBox(); self.group.addItem("— Not linked —", None)
        for g in groups or []: self.group.addItem(g.get("display_name") or g.get("name") or "", g.get("id"))
        self.use_from=QCheckBox("Starts on")
        self.valid_from=QDateEdit(QDate.currentDate()); self.valid_from.setCalendarPopup(True); self.valid_from.setDisplayFormat("yyyy-MM-dd")
        self.use_until=QCheckBox("Ends on")
        self.valid_until=QDateEdit(QDate.currentDate()); self.valid_until.setCalendarPopup(True); self.valid_until.setDisplayFormat("yyyy-MM-dd")
        for p in plans or []: self.plan.addItem(p["name"], p["id"])
        if vehicle:
            self.plate.setText(vehicle.get("plate") or ""); self.owner.setText(vehicle.get("owner_name") or "")
            idx=self.plan.findData(vehicle.get("plan_id"));
            if idx>=0: self.plan.setCurrentIndex(idx)
            gidx=self.group.findData(vehicle.get("group_id"))
            if gidx>=0: self.group.setCurrentIndex(gidx)
            self.enabled.setCurrentText("Yes" if vehicle.get("enabled") else "No")
            self.notes.setText(vehicle.get("notes") or "")
            start=_iso_date(str(vehicle.get("valid_from") or ""))
            finish=_iso_date(str(vehicle.get("valid_until") or ""), end=True)
            if start:
                self.use_from.setChecked(True)
                self.valid_from.setDate(QDate.fromString(start[:10], "yyyy-MM-dd"))
            if finish:
                self.use_until.setChecked(True)
                self.valid_until.setDate(QDate.fromString(finish[:10], "yyyy-MM-dd"))
        form.addRow("Plate", self.plate); form.addRow("Owner", self.owner); form.addRow("Plan", self.plan)
        form.addRow("Belongs to (company / linked cars)", self.group)
        form.addRow("Enabled", self.enabled); form.addRow("Notes", self.notes)
        from_row=QHBoxLayout(); from_row.addWidget(self.use_from); from_row.addWidget(self.valid_from)
        start_today=QPushButton("Start today"); start_today.clicked.connect(lambda: (self.use_from.setChecked(True), self.valid_from.setDate(QDate.currentDate())))
        from_row.addWidget(start_today)
        until_row=QHBoxLayout(); until_row.addWidget(self.use_until); until_row.addWidget(self.valid_until)
        end_today=QPushButton("End today"); end_today.clicked.connect(lambda: (self.use_until.setChecked(True), self.valid_until.setDate(QDate.currentDate())))
        until_row.addWidget(end_today)
        form.addRow("Season start", from_row); form.addRow("Season end", until_row)
        save=QPushButton("Save"); save.clicked.connect(self.accept); form.addRow(save)
    def payload(self):
        return {
            "plate": self.plate.text().strip(), "owner_name": self.owner.text().strip(),
            "plan_id": self.plan.currentData(), "enabled": self.enabled.currentText()=="Yes",
            "group_id": self.group.currentData(),
            "notes": self.notes.text().strip(),
            "valid_from": _iso_date(self.valid_from.date().toString("yyyy-MM-dd")) if self.use_from.isChecked() else None,
            "valid_until": _iso_date(self.valid_until.date().toString("yyyy-MM-dd"), end=True) if self.use_until.isChecked() else None,
        }

def mobile_unconfirmed_message(state: str) -> str:
    """What to tell the cashier when mobile money is neither paid nor refused."""
    if state == "MISMATCH":
        return ("ClickPesa reported a different amount for this payment. Do not take cash: "
                "ask a supervisor to check the payment before the driver pays again.")
    return ("No confirmation from ClickPesa yet. Do not take cash now: the driver may still be "
            "charged, and a late approval is credited automatically. Look this visit up again "
            "in a few minutes; it shows as paid once ClickPesa confirms.")


AUTO_REFRESH_MS=8000


class Sessions(QWidget):
    def __init__(self):
        super().__init__(); l=QVBoxLayout(self)
        title=QLabel("Parking sessions"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
        # The instructions are the find box's hover text: as a paragraph they
        # took a band of the screen above the list every operator scans.
        note_text=("Find a visit by scanning the receipt QR or typing the plate. Compare the photo and the time "
                   "inside before taking money. Payment stays off when nothing is owed.")
        find=QHBoxLayout()
        self.query=QLineEdit(); self.query.setPlaceholderText("Scan QR, paste the receipt link, or type the plate")
        self.query.setToolTip(note_text)
        self.query.returnPressed.connect(self.lookup)
        self.find_btn=QPushButton("Find visit"); self.find_btn.clicked.connect(self.lookup)
        find.addWidget(label_for("&Find visit", self.query)); find.addWidget(self.query, 1); find.addWidget(self.find_btn); l.addLayout(find)
        # Visits list on the left, the selected visit on the right: the list
        # used to sit below the photo card, out of sight on a normal screen.
        # Staff browse visits; a kiosk only sees the visit it looked up, so a
        # kiosk keeps the wide card (photo beside the details).
        self.can_browse=api.can("sessions.view") or api.can("fees.view")
        card=QFrame(); card.setObjectName("card")
        card_l=QVBoxLayout(card) if self.can_browse else QHBoxLayout(card)
        if self.can_browse:
            card.setMinimumWidth(320); card.setMaximumWidth(460)
        photos=QVBoxLayout()
        self.photo=QLabel("No entry photo stored."); self.photo.setMinimumSize(200, 140); self.photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.photo.setMaximumHeight(240)
        self.photo.setObjectName("video"); self.photo.setAccessibleName("Selected visit entry photograph")
        self.crop=QLabel(""); self.crop.setMinimumHeight(80); self.crop.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.crop.setObjectName("video"); self.crop.setAccessibleName("Selected visit plate crop")
        photos.addWidget(self.photo); photos.addWidget(self.crop)
        detail=QVBoxLayout()
        self.kiosk_plate=QLabel("—"); self.kiosk_plate.setStyleSheet("font-size:28px;font-weight:700;letter-spacing:2px")
        self.kiosk_stay=QLabel("Scan a receipt or pick a session.")
        self.kiosk_stay.setWordWrap(True)
        self.kiosk_due=QLabel(""); self.kiosk_due.setStyleSheet("font-size:18px;font-weight:700")
        self.kiosk_due.setWordWrap(True)          # long messages were cut off in the narrow column
        self.kiosk_note=QLabel(""); self.kiosk_note.setWordWrap(True)
        self.correct=QLineEdit(); self.correct.setPlaceholderText("Correct plate")
        actions=QVBoxLayout()
        save_plate=QPushButton("Save corrected plate"); save_plate.clicked.connect(self.correct_plate); self.save_plate_btn=save_plate
        self.pay_btn=QPushButton("Record payment"); self.pay_btn.clicked.connect(self.pay_visit); self.pay_btn.setEnabled(False)
        self.mobile_btn=QPushButton("Pay with mobile on this computer"); self.mobile_btn.clicked.connect(self.pay_mobile); self.mobile_btn.setEnabled(False)
        can_pay=api.can("payments.create") or api.can("kiosk.use")
        self.pay_btn.setVisible(can_pay)
        self.mobile_btn.setVisible(can_pay)
        # QR fallback at the exit (OCR failed or the plate is unreadable): the
        # receipt identifies the visit and the normal exit decision applies.
        self.exit_btn=QPushButton("Let out at exit with this receipt…"); self.exit_btn.clicked.connect(self.exit_with_receipt)
        self.exit_btn.setEnabled(False); self.exit_btn.setVisible(api.can("gates.open"))
        self.exit_btn.setToolTip("Use the scanned receipt as the exit identity. The barrier opens only if the visit is paid or free.")
        actions.addWidget(save_plate); actions.addWidget(self.pay_btn); actions.addWidget(self.mobile_btn); actions.addWidget(self.exit_btn)
        detail.addWidget(self.kiosk_plate); detail.addWidget(self.kiosk_stay); detail.addWidget(self.kiosk_due); detail.addWidget(self.kiosk_note)
        detail.addWidget(label_for("&Correct plate", self.correct)); detail.addWidget(self.correct); detail.addLayout(actions)
        if self.can_browse:
            card_l.addLayout(photos); card_l.addLayout(detail); card_l.addStretch(1)
        else:
            card_l.addLayout(photos, 1); card_l.addLayout(detail, 2)
        self.table=QTableWidget(0,8); self.table.setHorizontalHeaderLabels(["Plate","Kind","Status","Receipt","Entry","Due","Paid","Gate"])
        configure_table(self.table)
        list_side=QWidget(); list_l=QVBoxLayout(list_side); list_l.setContentsMargins(0, 0, 0, 0)
        list_l.addWidget(self.table, 1)
        split=QSplitter(Qt.Orientation.Horizontal); split.setChildrenCollapsible(False)
        split.addWidget(list_side); split.addWidget(card)
        split.setStretchFactor(0, 3); split.setStretchFactor(1, 1)
        l.addWidget(split, 1)
        list_side.setVisible(self.can_browse)
        self.table.setVisible(self.can_browse)
        self.table.itemSelectionChanged.connect(self._on_row)
        row=QHBoxLayout()
        receipt=QPushButton("Show / print receipt"); receipt.clicked.connect(self.print_receipt); self.receipt_btn=receipt
        refresh=QPushButton("Refresh"); refresh.clicked.connect(self.refresh); refresh.setVisible(self.can_browse); self.refresh_btn=refresh
        admit=QPushButton("Admit without receipt…"); admit.clicked.connect(self.admit_without_receipt)
        admit.setVisible(api.can("gates.open"))
        admit.setToolTip("Open the entry barrier for a visit waiting on a receipt. Requires a reason; recorded in the audit log.")
        self.admit_btn=admit
        # A boom opened by hand does not prove the car left: the guard confirms
        # the exit here (photo + reason), or sends it to a supervisor.
        confirm_exit=QPushButton("Confirm vehicle left…"); confirm_exit.clicked.connect(self.confirm_exit)
        confirm_exit.setVisible(api.can("exits.confirm")); self.confirm_exit_btn=confirm_exit
        confirm_exit.setToolTip("The camera missed an exit or the boom was opened by hand: confirm the car left, with a reason.")
        waiting=QPushButton("Linked cars inside / exits waiting…"); waiting.clicked.connect(self.exits_waiting)
        waiting.setVisible(api.can("exits.confirm"))
        row.addWidget(receipt); row.addWidget(admit); row.addWidget(confirm_exit); row.addWidget(waiting); row.addWidget(refresh); row.addStretch()
        list_l.addLayout(row) if self.can_browse else l.addLayout(row)
        self.rows=[]; self.visit=None; self._loaded=False
        # Payments arrive from phones, kiosks and other desks: while this page
        # is on screen it re-reads the list and the shown visit by itself.
        self._auto=QTimer(self); self._auto.setInterval(AUTO_REFRESH_MS); self._auto.timeout.connect(self._auto_refresh)
    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded:
            self._loaded=True
            self.refresh()
        else:
            self._auto_refresh()
        self._auto.start()
    def hideEvent(self, event):
        super().hideEvent(event)
        self._auto.stop()
    def _auto_refresh(self):
        if getattr(self, "_auto_busy", False):
            return
        from urllib.parse import quote
        token=(self.visit or {}).get("token")
        def load():
            rows=api.get("/sessions", timeout=10) if getattr(self, "can_browse", True) else None
            visit=api.get(f"/sessions/lookup?q={quote(str(token), safe='')}", timeout=10) if token else None
            return rows, visit
        def done(result):
            self._auto_busy=False
            rows, visit = result
            if rows is not None:
                self._fill_rows(rows)
            if visit and (self.visit or {}).get("token")==token:
                self._show_visit(visit, quiet=True)
        def failed(_message, _exc):
            self._auto_busy=False   # a missed refresh is retried on the next tick
        self._auto_busy=True
        run_task(self, load, done, on_error=failed)
    def confirm_exit(self):
        from app.desktop.linked_vehicles import open_manual_exit
        s=self.selected() if getattr(self, "can_browse", False) else None
        query=(f"#{s['id']}" if s and s.get("id") else "") or str((self.visit or {}).get("token") or "") or self.query.text().strip()
        if not query:
            QMessageBox.information(self,"Confirm vehicle left","Select a session, scan its receipt or type the plate first."); return
        def done(result):
            confirmation=(result or {}).get("confirmation") or {}
            QMessageBox.information(self,"Confirm vehicle left",
                "Exit recorded." if confirmation.get("action")=="MANUAL_EXIT_CONFIRMED"
                else "Sent to a supervisor. Linked cars stay blocked until it is decided.")
            self.refresh()
        open_manual_exit(self, query, on_done=done)
    def exits_waiting(self):
        from app.desktop.linked_vehicles import PendingExitsDialog
        PendingExitsDialog(self).exec(); self.refresh()
    def admit_without_receipt(self):
        s=self.selected()
        if not s: QMessageBox.information(self,"Admit without receipt","Select a session first."); return
        if str(s.get("status") or "").upper()!="WAITING_RECEIPT":
            QMessageBox.information(self,"Admit without receipt","Only a visit that is waiting for its receipt can be admitted this way."); return
        reason,ok=QInputDialog.getText(self,"Admit without receipt",f"Reason for opening the entry for {s.get('plate') or 'this visit'} without a taken receipt:")
        if not ok: return
        reason=(reason or "").strip()
        if len(reason)<3:
            QMessageBox.warning(self,"Admit without receipt","Enter a reason (at least 3 characters)."); return
        sid=s['id']
        def done(result):
            QMessageBox.information(self,"Admit without receipt",str((result or {}).get("message") or (result or {}).get("reason") or "Done."))
            self.refresh()
        run_task(self, lambda: api.post(f"/sessions/{sid}/admit-without-receipt", {"reason": reason}, timeout=20),
                 done, buttons=getattr(self, "admit_btn", None), busy_text="Opening…", title="Admit without receipt")
    def _pixmap(self, label, path, empty):
        label.setPixmap(QPixmap())
        # Photos load in the background; a reply for a visit that is no
        # longer shown is dropped so a slow photo cannot land on a new visit.
        token=object(); label._photo_request=token
        if not path:
            label.setText(empty); return
        label.setText("Loading photo…")
        def done(data):
            if getattr(label, "_photo_request", None) is not token:
                return
            pix=QPixmap(); pix.loadFromData(data or b"")
            if pix.isNull():
                label.setText(empty); return
            label.setText("")
            label.setPixmap(pix.scaled(320, 180, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        run_task(self, lambda: api.get_bytes(path, timeout=12), done,
                 on_error=lambda _m, _e: label.setText(empty or "Photo not available.") if getattr(label, "_photo_request", None) is token else None)
    def _show_visit(self, data, quiet=False):
        """``quiet``: a background re-read of the same visit; keep photos and typing."""
        self.visit=data or None
        if not data:
            self.kiosk_plate.setText("—")
            self.kiosk_stay.setText("No visit matches that QR code or plate.")
            self.kiosk_due.setText("")
            self.kiosk_note.setText("")
            self.pay_btn.setEnabled(False)
            self.mobile_btn.setEnabled(False)
            self.exit_btn.setEnabled(False)
            self._pixmap(self.photo, None, "No entry photo stored.")
            self._pixmap(self.crop, None, "")
            return
        self.kiosk_plate.setText(data.get("plate") or "—")
        inside="Still inside." if data.get("still_inside") else "Has left."
        entered=(data.get("entry_time") or "").replace("T", " ")[:16]
        self.kiosk_stay.setText(f"Time on site: {data.get('duration_label') or '—'} ({inside}) Entered {entered}.")
        remaining=int(float(data.get("amount_remaining") or 0))
        currency=data.get("currency") or "TZS"
        if data.get("payable"):
            self.kiosk_due.setText(f"To pay: {currency} {remaining:,}")
        else:
            self.kiosk_due.setText(data.get("pay_blocked_reason") or "Nothing to pay.")
        self.kiosk_note.setText(data.get("image_note") or "")
        if not quiet:
            self.correct.setText("" if data.get("image_matches_plate") is False else (data.get("plate") or ""))
        payable=bool(data.get("payable"))
        self.pay_btn.setEnabled(payable)
        self.mobile_btn.setEnabled(payable and bool(data.get("token")))
        self.exit_btn.setEnabled(bool(data.get("token")) and data.get("still_inside") is not False)
        if quiet:
            return
        self._pixmap(self.photo, data.get("snapshot_url"), "No entry photo stored.")
        self._pixmap(self.crop, data.get("crop_url"), "")
    def _exit_lanes(self):
        lanes=[]
        for gate in api.get("/gates") or []:
            if gate.get("enabled") is False:
                continue
            for cam in gate.get("cameras") or []:
                if str(cam.get("lane_direction") or "").upper()=="EXIT":
                    lanes.append((f"{gate.get('name')} — {cam.get('name')}", int(gate["id"]), int(cam["id"])))
        return lanes
    def exit_with_receipt(self):
        visit=self.visit or {}
        token=visit.get("token")
        if not token:
            QMessageBox.information(self,"Exit with receipt","Scan the receipt QR first."); return
        button=getattr(self, "exit_btn", None)
        def lanes_loaded(lanes):
            if not lanes:
                QMessageBox.information(self,"Exit with receipt","No exit lane with an exit camera is configured."); return
            labels=[label for label,_,_ in lanes]
            choice,ok=QInputDialog.getItem(self,"Exit with receipt",f"Which exit is {visit.get('plate') or 'this car'} at?",labels,0,False)
            if not ok: return
            _,gate_id,camera_id=lanes[labels.index(choice)]
            def opened(result):
                self._report_exit(result or {})
                self.refresh()
            run_task(self, lambda: api.post("/exit/qr-scan",{"gate_id":gate_id,"camera_id":camera_id,"raw_scan":token},timeout=20),
                     opened, buttons=button, busy_text="Checking exit…", title="Exit with receipt")
        run_task(self, self._exit_lanes, lanes_loaded, buttons=button, busy_text="Loading exits…", title="Exit with receipt")
    def _report_exit(self, result):
        message=str(result.get("message") or result.get("reason") or "Done.")
        mismatch=result.get("plate_mismatch")
        if mismatch:
            QMessageBox.warning(self,"Exit with receipt — check the car",
                f"The exit camera read {mismatch.get('camera_plate')}, but this receipt is for "
                f"{mismatch.get('session_plate')}.\n\nLook at the car before it leaves; the mismatch is recorded.\n\n{message}")
            return
        if result.get("pay_required"):
            QMessageBox.information(self,"Exit with receipt",f"Payment needed before this car can leave.\n\n{message}")
            return
        QMessageBox.information(self,"Exit with receipt",message)
    def lookup(self):
        from urllib.parse import quote
        q=self.query.text().strip()
        if not q:
            QMessageBox.information(self, "Find visit", "Scan a QR code or type a plate."); return
        self.kiosk_stay.setText("Looking up the visit…")
        def failed(message, exc):
            def not_found():
                self._show_visit(None)
                self.kiosk_stay.setText(message)
            if getattr(exc, "status_code", None)==404 and self._offer_near_match(q, not_found):
                return
            not_found()
        run_task(self, lambda: api.get(f"/sessions/lookup?q={quote(q, safe='')}", timeout=15), self._show_visit,
                 buttons=getattr(self, "find_btn", None), busy_text="Finding…", on_error=failed)
    def _offer_near_match(self, typed, not_found=None):
        """No exact visit: offer open visits with a close plate (OCR 8/B, 0/O…).

        Choosing one only shows that visit. The operator still checks the car
        and the receipt; nothing opens a barrier from a fuzzy match. Returns
        False when ``typed`` is not a plate; otherwise the near-match search
        runs in the background and ``not_found`` is called if nothing fits.
        """
        from urllib.parse import quote
        if "/" in typed or len(typed) > 16:
            return False  # a receipt link or token, not a typed plate
        not_found = not_found or (lambda: None)
        run_task(self, lambda: api.get(f"/sessions/near-matches?plate={quote(typed, safe='')}", timeout=10) or [],
                 lambda matches: self._choose_near_match(typed, matches, not_found),
                 on_error=lambda _m, _e: not_found())
        return True
    def _choose_near_match(self, typed, matches, not_found):
        from urllib.parse import quote
        if not matches:
            not_found(); return
        labels=[f"{m.get('plate')}  (entered {(m.get('entry_time') or '').replace('T',' ')[:16]})" for m in matches]
        choice,ok=QInputDialog.getItem(self,"Did you mean…",
            f"No visit for {typed.upper()}. Did you mean one of these? Check the car and the receipt before acting.",
            labels,0,False)
        if not ok:
            not_found(); return
        picked=matches[labels.index(choice)]
        def shown(data):
            self._show_visit(data)
            self.kiosk_note.setText(f"Shown because you typed {typed.upper()}. Confirm the plate on the car matches {(data or {}).get('plate')}.")
        def failed(message, _exc):
            self._show_visit(None); self.kiosk_stay.setText(message)
        run_task(self, lambda: api.get(f"/sessions/lookup?q={quote(str(picked.get('token') or picked.get('plate')), safe='')}", timeout=15),
                 shown, on_error=failed)
    def _on_row(self):
        if getattr(self, "_filling", False):
            return
        row=self.selected()
        if not row:
            return
        text=row.get("public_token") or row.get("plate") or ""
        if not text:
            return
        self.query.setText(text)
        self.lookup()
    def refresh(self):
        if not getattr(self, "can_browse", True):
            return
        def failed(message, _exc):
            self.statusBar_message(f"Visit list not refreshed: {message}")
        run_task(self, lambda: api.get("/sessions"), self._fill_rows,
                 buttons=getattr(self, "refresh_btn", None), busy_text="Refreshing…", on_error=failed)
    def _fill_rows(self, rows):
        keep=(self.selected() or {}).get("id")
        self.rows=rows or []
        self._filling=True
        self.table.setRowCount(len(self.rows))
        for r,s in enumerate(self.rows):
            vals=[
                s.get("plate") or "",
                s.get("parker_kind") or "CASUAL",
                s.get("status") or "",
                s.get("receipt_status") or "—",
                (s.get("entry_time") or "")[:19].replace("T"," "),
                money_label(s.get("amount_due"), s.get("currency")),
                money_label(s.get("amount_paid"), s.get("currency")),
                s.get("gate_id") or "—",
            ]
            for c,val in enumerate(vals): self.table.setItem(r,c,QTableWidgetItem(str(val)))
            if keep is not None and s.get("id")==keep:
                self.table.selectRow(r)
        self._filling=False
    def selected(self):
        row=self.table.currentRow()
        if row<0 or row>=len(self.rows): return None
        return self.rows[row]
    def print_receipt(self):
        s=self.selected()
        if not s and (self.visit or {}).get("session_id"):
            s={"id": self.visit["session_id"]}
        if not s: QMessageBox.information(self,"Receipt","Find a visit first."); return
        sid=s['id']
        def load():
            issued=api.post(f"/sessions/{sid}/receipt", {}, timeout=15)
            slip=None
            if not (issued or {}).get("receipt"):
                try:
                    slip=api.get(f"/sessions/{sid}/receipt")
                except Exception:
                    slip=None
            return issued, slip
        run_task(self, load, self._show_receipt, buttons=getattr(self, "receipt_btn", None),
                 busy_text="Preparing receipt…", title="Receipt")
    def _show_receipt(self, loaded):
        issued, slip = loaded
        body=(issued or {}).get("receipt") or ""
        printed=(issued or {}).get("print") or {}
        record=(issued or {}).get("receipt_record") or {}
        path=printed.get("path") or (record.get("payload") or {}).get("path") or ""
        qr_url=(issued or {}).get("qr_url") or ""
        if not qr_url and (issued or {}).get("public_token"):
            qr_url=f"/p/{issued['public_token']}/qr.png"
        qr_payload=(issued or {}).get("qr_payload") or (issued or {}).get("public_url") or ""
        if not body and slip:
            body=slip.get("body_text") or ""
            path=(slip.get("payload") or {}).get("path") or path
            qr_payload=qr_payload or slip.get("qr_payload") or ""
            if not qr_url and slip.get("qr_url"):
                qr_url=slip.get("qr_url")
        show_printable_receipt(self, body, path, qr_url=qr_url, qr_payload=qr_payload)
        self.refresh()
    def correct_plate(self):
        visit=self.visit or {}
        session_id=visit.get("session_id")
        plate=self.correct.text().strip()
        if not session_id or not plate:
            QMessageBox.information(self, "Correct plate", "Find the visit and type the plate you can see."); return
        def done(_result):
            self.statusBar_message(f"Plate corrected to {plate}.")
            self.query.setText(plate)
            self.lookup()
            self.refresh()
        run_task(self, lambda: api.post(f"/sessions/{session_id}/correct-plate", {"plate": plate}), done,
                 buttons=getattr(self, "save_plate_btn", None), busy_text="Saving…", title="Correct plate")
    def _settle(self, method):
        visit=self.visit or {}
        if not visit.get("payable"):
            QMessageBox.information(self, "Payment", visit.get("pay_blocked_reason") or "This vehicle does not have a fee to pay.")
            return
        token=visit.get("token")
        session_id=visit.get("session_id")
        plate=visit.get("plate") or ""
        if QMessageBox.question(self, "Record payment", f"Take payment for {plate}?") != QMessageBox.Yes:
            return
        def send():
            if method == "KIOSK_CASH" and token:
                return api.post(f"/p/{token}/kiosk-pay", {"method": "KIOSK_CASH"})
            if method == "KIOSK_CASH" and session_id:
                return api.post(f"/sessions/{session_id}/pay", {"method": "KIOSK_CASH"})
            if token:
                return api.post(f"/p/{token}/pay", {"method": "MOBILE_SIMULATED"})
            raise RuntimeError("This visit has no receipt code for phone payment.")
        def done(result):
            result=result or {}
            if result.get("already_paid"):
                QMessageBox.information(self, "Payment", "Already settled.")
            else:
                QMessageBox.information(self, "Payment", "Payment recorded.")
            if "payable" in result:
                self._show_visit(result)
            self.refresh()
        def failed(message, exc):
            # A timeout is not a refusal: the payment may have been recorded.
            # Say so, so nobody takes the money twice.
            if isinstance(exc, SiteServerUnreachable) and exc.timed_out:
                message += "\n\nLook this visit up again before taking money a second time."
            QMessageBox.critical(self, "Payment", message)
        run_task(self, send, done, buttons=getattr(self, "pay_btn", None), busy_text="Recording payment…", on_error=failed)
    def pay_visit(self):
        self._settle("KIOSK_CASH")
    def pay_mobile(self):
        """Real mobile money: push prompt to the driver's phone, then wait for the provider."""
        visit=self.visit or {}
        if not visit.get("payable"):
            QMessageBox.information(self, "Mobile money", visit.get("pay_blocked_reason") or "This vehicle does not have a fee to pay.")
            return
        token=visit.get("token")
        if not token:
            QMessageBox.information(self, "Mobile money", "Scan the receipt QR first; mobile money needs the receipt code.")
            return
        phone,ok=QInputDialog.getText(self, "Mobile money", f"Driver's mobile number for {visit.get('plate') or 'this visit'}:")
        if not ok or not phone.strip():
            return
        number=phone.strip()
        run_task(self, lambda: api.post("/api/public/payment-intents", {"token": token, "phone": number}, timeout=30),
                 lambda _r: self._start_mobile_wait(token), buttons=getattr(self, "mobile_btn", None),
                 busy_text="Sending prompt…", title="Mobile money")
    def _start_mobile_wait(self, token):
        self._mobile_token=token
        self._mobile_deadline=time.monotonic() + 180
        self.statusBar_message("Payment prompt sent. Ask the driver to approve it on their phone…")
        if getattr(self, "_mobile_timer", None) is None:
            self._mobile_timer=QTimer(self)
            self._mobile_timer.setInterval(3000)
            self._mobile_timer.timeout.connect(self._poll_mobile_payment)
        self._mobile_timer.start()
    def _poll_mobile_payment(self):
        token=getattr(self, "_mobile_token", None)
        if not token:
            self._mobile_timer.stop(); return
        if getattr(self, "_mobile_polling", False):
            return
        self._mobile_polling=True
        def done(status):
            self._mobile_polling=False
            if getattr(self, "_mobile_token", None) == token:
                self._mobile_status(status or {})
        def failed(_message, _exc):
            self._mobile_polling=False  # transient; keep waiting until the deadline
            if getattr(self, "_mobile_token", None) == token and time.monotonic() > getattr(self, "_mobile_deadline", 0):
                self._mobile_status({})
        run_task(self, lambda: api.get(f"/api/public/payment-status/{token}", timeout=5), done, on_error=failed)
    def _mobile_status(self, status):
        intent=(status or {}).get("intent") or {}
        state=str(intent.get("status") or "").upper()
        if not status.get("payable") and str(status.get("status") or "").upper() in {"PAID", "CLOSED"} or state == "SUCCEEDED":
            self._mobile_timer.stop(); self._mobile_token=None
            QMessageBox.information(self, "Mobile money", "Payment confirmed by the provider.")
            self.lookup(); self.refresh(); return
        if state in {"FAILED", "BLOCKED"}:
            # The provider refused or never sent the prompt: nothing was taken.
            self._mobile_timer.stop(); self._mobile_token=None
            QMessageBox.warning(self, "Mobile money", f"Payment not completed ({state}). Try again or take cash.")
            return
        if state in {"MISMATCH", "EXPIRED"} or time.monotonic() > self._mobile_deadline:
            # The driver may still be charged: a late approval is credited
            # automatically. Taking cash now risks charging them twice.
            self._mobile_timer.stop(); self._mobile_token=None
            QMessageBox.warning(self, "Mobile money", mobile_unconfirmed_message(state))
    def statusBar_message(self, text):
        window=self.window()
        bar=getattr(window, "statusBar", None)
        if callable(bar):
            bar().showMessage(text, 10000)
    def pay(self):
        s=self.selected()
        if not s:
            self.pay_visit(); return
        q=s.get("public_token") or s.get("plate") or ""
        self.query.setText(q)
        from urllib.parse import quote
        def fallback():
            self.visit={"session_id": s.get("id"), "plate": s.get("plate"), "token": s.get("public_token"), "payable": float(s.get("amount_due") or 0) > float(s.get("amount_paid") or 0)}
            self.pay_visit()
        def found(data):
            self._show_visit(data)
            if not (self.visit or {}).get("session_id"):
                fallback(); return
            self.pay_visit()
        run_task(self, lambda: api.get(f"/sessions/lookup?q={quote(q, safe='')}", timeout=15), found,
                 on_error=lambda _m, _e: fallback())

class Payments(QWidget):
    def __init__(self):
        super().__init__(); l=QVBoxLayout(self)
        title=QLabel("Payments"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
        # Filters on top and the total of what was paid: the page used to be
        # the newest 100 payments with neither.
        filters=QHBoxLayout()
        today=QDate.currentDate()
        self.date_from=QDateEdit(today.addDays(-6)); self.date_from.setCalendarPopup(True); self.date_from.setDisplayFormat("yyyy-MM-dd")
        self.date_to=QDateEdit(today); self.date_to.setCalendarPopup(True); self.date_to.setDisplayFormat("yyyy-MM-dd")
        for field in (self.date_from, self.date_to):
            field.setMinimumWidth(field.fontMetrics().horizontalAdvance("2026-12-31") + 48)
        self.method=QComboBox(); self.method.addItem("All methods", "")
        # The method codes the ledger records (simulated ones on test sites).
        for code, label in (("KIOSK_CASH", "Cash"), ("MOBILE_MONEY", "Mobile Money"),
                            ("MOBILE_SIMULATED", "Mobile (simulated)"), ("CARD_SIMULATED", "Card (simulated)")):
            self.method.addItem(label, code)
        self.pay_status=QComboBox(); self.pay_status.addItem("All statuses", "")
        for code, label in (("SUCCEEDED", "Succeeded"), ("PENDING", "Pending"), ("FAILED", "Failed"), ("CANCELLED", "Cancelled")):
            self.pay_status.addItem(label, code)
        for label, field in (("From", self.date_from), ("To", self.date_to), ("Method", self.method), ("Status", self.pay_status)):
            filters.addWidget(label_for(label, field)); filters.addWidget(field)
        self.refresh_btn=QPushButton("Show"); self.refresh_btn.clicked.connect(self.refresh)
        filters.addWidget(self.refresh_btn); filters.addStretch()
        l.addLayout(filters)
        self.table=QTableWidget(0,6); self.table.setHorizontalHeaderLabels(["When","Session","Method","Amount","Status","Provider"])
        self.table.setToolTip("Kiosk and mobile payments share one ledger. A phone success screen is not paid "
                              "until a verified transaction exists.")
        configure_table(self.table); l.addWidget(self.table, 1)
        self.total=QLabel(""); self.total.setStyleSheet("font-weight:700")
        self.status=QLabel(""); self.status.setWordWrap(True)
        row=QHBoxLayout(); row.addWidget(self.total); row.addWidget(self.status, 1); l.addLayout(row)
        self._loaded=False
    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded:
            self._loaded=True
            self.refresh()
    def refresh(self):
        self.status.setText("Loading payments…")
        from urllib.parse import urlencode
        query={"date_from": self.date_from.date().toString("yyyy-MM-dd"),
               "date_to": self.date_to.date().toString("yyyy-MM-dd"), "limit": 1000}
        if self.method.currentData():
            query["method"]=self.method.currentData()
        if self.pay_status.currentData():
            query["status"]=self.pay_status.currentData()
        path="/payments?"+urlencode(query)
        run_task(self, lambda: api.get(path), self._fill, buttons=self.refresh_btn, busy_text="Loading…",
                 on_error=lambda message, _e: self.status.setText(message))
    def _fill(self, rows):
        rows=rows or []
        self.status.setText(f"{len(rows)} payments." if rows else "No payments in this range.")
        totals={}
        for p in rows:
            if str(p.get("status") or "").upper()=="SUCCEEDED":
                currency=p.get("currency") or ""
                totals[currency]=totals.get(currency, 0)+float(p.get("amount") or 0)
        self.total.setText("Paid: " + ", ".join(money_label(v, c) for c, v in sorted(totals.items())) if totals else "Paid: 0")
        self.table.setRowCount(len(rows))
        for r,p in enumerate(rows):
            vals=[
                (p.get("confirmed_at") or p.get("created_at") or "")[:19].replace("T"," "),
                p.get("session_id") or "—",
                method_label(p.get("method")),
                money_label(p.get("amount"), p.get("currency")),
                p.get("status") or "",
                p.get("provider_id") or "",
            ]
            for c,val in enumerate(vals): self.table.setItem(r,c,QTableWidgetItem(str(val)))
        self.table.setColumnHidden(5, not is_technician())

class Vehicles(QWidget):
    def __init__(self):
        super().__init__(); l=QVBoxLayout(self)
        title=QLabel("Registered vehicles"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
        note=QLabel("Registered vehicles and access plans. A matching plate can be allowed through when gate access is enabled.")
        note.setWordWrap(True); l.addWidget(note)
        self.table=QTableWidget(0,8); self.table.setHorizontalHeaderLabels(["Plate","Owner","Belongs to","Plan","Auto-open","Enabled","From","Until"])
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        configure_table(self.table)
        # Buttons above the list (they were cut off at the right below it),
        # and the bulk box folded behind "Register many…" until needed.
        self.bulk_box=QWidget(); bulk_l=QVBoxLayout(self.bulk_box); bulk_l.setContentsMargins(0, 0, 0, 0)
        bulk_note=QLabel("Register many, one plate per line: plate, owner, start date, end date")
        bulk_l.addWidget(bulk_note)
        self.bulk=QPlainTextEdit(); self.bulk.setPlaceholderText("ABC1234, Owner, 2026-09-01, 2026-10-01"); self.bulk.setMaximumHeight(90)
        bulk_l.addWidget(self.bulk)
        self.bulk_box.setVisible(False)
        row=QHBoxLayout()
        manage=api.can("subscribers.manage")
        add=QPushButton(action_label("Register plate", "Ctrl+N")); add.clicked.connect(self.add); add.setVisible(manage); add.setToolTip("Register plate (Ctrl+N)")
        bulk=QPushButton("Register these plates"); bulk.clicked.connect(self.add_bulk); bulk.setVisible(manage)
        edit=QPushButton(action_label("Edit", "Ctrl+E")); edit.clicked.connect(self.edit); edit.setVisible(manage); edit.setToolTip("Edit (Ctrl+E)")
        delete=QPushButton(action_label("Delete", "Del")); delete.clicked.connect(self.delete); delete.setVisible(manage); delete.setToolTip("Delete (Del)")
        delete_many=QPushButton(action_label("Delete selected", "Del")); delete_many.clicked.connect(self.delete_selected); delete_many.setVisible(manage); delete_many.setToolTip("Delete selected (Del)")
        refresh=QPushButton(action_label("Refresh", "F5")); refresh.clicked.connect(self.refresh); refresh.setToolTip("Refresh (F5)")
        groups=QPushButton("Linked cars & companies…"); groups.clicked.connect(self.open_groups)
        groups.setToolTip("Group a private owner's cars (one inside at a time) or a company's fleet")
        visitors=QPushButton("Visitor passes…"); visitors.clicked.connect(self.open_visitors)
        visitors.setVisible(api.can("visitors.manage") or manage)
        self.refresh_btn=refresh; self.add_btn=add; self.bulk_btn=bulk; self.edit_btn=edit
        self.status=QLabel(""); self.status.setWordWrap(True)
        self.bulk_toggle=QPushButton("Register many…"); self.bulk_toggle.setObjectName("secondary"); self.bulk_toggle.setCheckable(True)
        self.bulk_toggle.setVisible(manage)
        self.bulk_toggle.toggled.connect(self.bulk_box.setVisible)
        bulk_l.addWidget(bulk, 0, Qt.AlignmentFlag.AlignLeft)
        row.addWidget(add); row.addWidget(self.bulk_toggle); row.addWidget(edit); row.addWidget(delete); row.addWidget(delete_many); row.addWidget(refresh)
        row.addStretch(); row.addWidget(groups); row.addWidget(visitors); l.addLayout(row)
        l.addWidget(self.bulk_box)
        l.addWidget(self.table, 1)
        l.addWidget(self.status)
        self.rows=[]; self._loaded=False
    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded:
            self._loaded=True
            self.refresh()
    def refresh(self):
        self.status.setText("Loading registered vehicles…")
        run_task(self, lambda: api.get("/vehicles"), self._fill, buttons=self.refresh_btn, busy_text="Refreshing…",
                 on_error=lambda message, _e: self.status.setText(message))
    def _fill(self, rows):
        self.rows=rows or []
        self.status.setText(f"{len(self.rows)} registered vehicles." if self.rows else "No registered vehicles yet.")
        self.table.setRowCount(len(self.rows))
        for r,v in enumerate(self.rows):
            vals=[
                v["plate"], v.get("owner_name") or "—", v.get("belongs_to") or "—", v.get("plan_name") or "—",
                "Yes" if v.get("auto_open") else "No", "Yes" if v.get("enabled") else "No",
                (v.get("valid_from") or "—")[:10], (v.get("valid_until") or "—")[:10],
            ]
            for c,val in enumerate(vals): self.table.setItem(r,c,QTableWidgetItem(str(val)))
    def selected(self):
        row=self.table.currentRow()
        if row<0 or row>=len(self.rows): return None
        return self.rows[row]
    def selected_ids(self):
        ids=[]
        for index in self.table.selectionModel().selectedRows():
            row=index.row()
            if 0<=row<len(self.rows):
                ids.append(self.rows[row]["id"])
        return ids
    def _saved(self, text):
        show_status(self, text)
        self.status.setText(text)
        self.refresh()
    def open_groups(self):
        from app.desktop.linked_vehicles import GroupsDialog
        GroupsDialog(self).exec(); self.refresh()
    def open_visitors(self):
        from app.desktop.linked_vehicles import VisitorsDialog
        VisitorsDialog(self).exec()
    @staticmethod
    def _plans_and_groups():
        plans=api.get("/access-plans")
        try:
            groups=api.get("/vehicle-groups")
        except Exception:
            groups=[]   # an older Site Service without linked groups
        return plans, groups
    def add(self):
        def with_plans(loaded):
            plans, groups = loaded
            d=VehicleDialog(plans=plans, groups=groups)
            if d.exec():
                payload=d.payload()
                run_task(self, lambda: api.post("/vehicles", payload), lambda _r: self._saved(f"Registered {payload.get('plate')}."),
                         buttons=self.add_btn, busy_text="Saving…", title="Register plate")
        run_task(self, self._plans_and_groups, with_plans, buttons=self.add_btn, busy_text="Opening…", title="Register plate")
    def add_bulk(self):
        lines=[line.strip() for line in self.bulk.toPlainText().splitlines() if line.strip()]
        if not lines:
            QMessageBox.information(self, "Register plates", "Add one plate per line."); return
        vehicles=[]
        for line in lines:
            parts=[part.strip() for part in line.split(",")]
            plate=parts[0] if parts else ""
            owner=parts[1] if len(parts)>1 else ""
            start=parts[2] if len(parts)>2 else ""
            finish=parts[3] if len(parts)>3 else ""
            vehicles.append({
                "plate": plate,
                "owner_name": owner,
                "valid_from": _iso_date(start) if start else None,
                "valid_until": _iso_date(finish, end=True) if finish else None,
            })
        def done(result):
            result=result or {}
            failed="; ".join(item.get("error") or "" for item in (result.get("errors") or []) if item.get("error"))
            created=len(result.get("created") or [])
            self.bulk.clear()
            self.refresh()
            QMessageBox.information(self, "Register plates", f"Registered {created} plates. {failed}".strip())
        run_task(self, lambda: api.post("/vehicles/bulk", {"vehicles": vehicles}), done,
                 buttons=self.bulk_btn, busy_text="Registering…", title="Register plates")
    def edit(self):
        v=self.selected()
        if not v: QMessageBox.information(self,"Edit","Select a plate first."); return
        def with_plans(loaded):
            plans, groups = loaded
            d=VehicleDialog(v, plans=plans, groups=groups)
            if d.exec():
                payload=d.payload(); vid=v['id']
                run_task(self, lambda: api.patch(f"/vehicles/{vid}", payload), lambda _r: self._saved(f"Saved {payload.get('plate')}."),
                         buttons=self.edit_btn, busy_text="Saving…", title="Edit")
        run_task(self, self._plans_and_groups, with_plans, buttons=self.edit_btn, busy_text="Opening…", title="Edit")
    def delete(self):
        v=self.selected()
        if not v: return
        if QMessageBox.question(self,"Delete",f"Remove {v['plate']}?")!=QMessageBox.Yes: return
        vid=v['id']; plate=v['plate']
        run_task(self, lambda: api.delete(f"/vehicles/{vid}"), lambda _r: self._saved(f"Removed {plate}."), title="Delete")
    def delete_selected(self):
        ids=self.selected_ids()
        if not ids:
            QMessageBox.information(self, "Delete", "Select at least one plate."); return
        if QMessageBox.question(self, "Delete", f"Remove {len(ids)} registered plate(s)?")!=QMessageBox.Yes: return
        run_task(self, lambda: api.post("/vehicles/bulk-delete", {"ids": ids}), lambda _r: self._saved(f"Removed {len(ids)} plate(s)."), title="Delete")

class Fees(QWidget):
    def __init__(self):
        super().__init__(); l=QVBoxLayout(self)
        note=QLabel("Day and night rates for this site. Times and amounts are normal fields — save them here.")
        note.setWordWrap(True); l.addWidget(note)
        form=QFormLayout()
        self.currency=QLineEdit()
        self.day_start=QTimeEdit(); self.day_start.setDisplayFormat("HH:mm")
        self.day_end=QTimeEdit(); self.day_end.setDisplayFormat("HH:mm")
        self.free_day=QSpinBox(); self.free_night=QSpinBox()
        self.day_block=QSpinBox(); self.night_block=QSpinBox()
        self.day_fee=QSpinBox(); self.night_fee=QSpinBox()
        self.day_max=QSpinBox(); self.night_max=QSpinBox(); self.daily=QSpinBox()
        for box in (self.free_day, self.free_night, self.day_fee, self.night_fee, self.day_max, self.night_max, self.daily):
            box.setRange(0, 10000000)
        for box in (self.day_block, self.night_block):
            box.setRange(1, 10080)
        form.addRow("Currency", self.currency)
        form.addRow("Day starts", self.day_start); form.addRow("Day ends", self.day_end)
        form.addRow("Free daytime (minutes)", self.free_day); form.addRow("Free night (minutes)", self.free_night)
        form.addRow("Day block (minutes)", self.day_block); form.addRow("Night block (minutes)", self.night_block)
        form.addRow("Fee per day block", self.day_fee); form.addRow("Fee per night block", self.night_fee)
        form.addRow("Day maximum", self.day_max); form.addRow("Night maximum", self.night_max)
        form.addRow("Fee per full day", self.daily)
        l.addLayout(form)
        actions=QHBoxLayout()
        save=QPushButton("Save tariff"); save.clicked.connect(self.save)
        save.setVisible(api.can("fees.manage") or api.can("settings.manage"))
        reload_btn=QPushButton("Reload"); reload_btn.clicked.connect(self.load_tariff)
        self.save_btn=save; self.reload_btn=reload_btn
        actions.addWidget(save); actions.addWidget(reload_btn); actions.addStretch(); l.addLayout(actions)
        self.out=QLabel(""); self.out.setWordWrap(True); l.addWidget(self.out)
        l.addStretch()
        self._loaded=False
    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded:
            self._loaded=True
            self.load_tariff()
    def _set_time(self, edit, value):
        parsed=QTime.fromString(str(value or "")[:5], "HH:mm")
        if parsed.isValid():
            edit.setTime(parsed)
    def load_tariff(self):
        self.out.setText("Loading tariff…")
        run_task(self, lambda: api.get("/fees/tariff"), self._show_tariff, buttons=self.reload_btn, busy_text="Loading…",
                 on_error=lambda message, _e: self.out.setText(message))
    def _show_tariff(self, data):
        data=data or {}
        editor=(data or {}).get("editor") or {}
        self.currency.setText(editor.get("currency") or data.get("currency") or "")
        self._set_time(self.day_start, editor.get("day_start"))
        self._set_time(self.day_end, editor.get("day_end"))
        self.free_day.setValue(int(float(editor.get("free_day_minutes") or 0)))
        self.free_night.setValue(int(float(editor.get("free_night_minutes") or 0)))
        self.day_block.setValue(max(1, int(float(editor.get("day_block_minutes") or 1))))
        self.night_block.setValue(max(1, int(float(editor.get("night_block_minutes") or 1))))
        self.day_fee.setValue(int(editor.get("day_block_fee") or 0))
        self.night_fee.setValue(int(editor.get("night_block_fee") or 0))
        self.day_max.setValue(int(editor.get("day_max") or 0))
        self.night_max.setValue(int(editor.get("night_max") or 0))
        self.daily.setValue(int(editor.get("daily_wrap_fee") or 0))
        name=data.get("name") or "Tariff"
        self.out.setText(f"{name} · {self.currency.text()}. Day rate {self.day_fee.value()} per {self.day_block.value()} min.")
    def save(self):
        payload={
            "currency": self.currency.text().strip(),
            "day_start": self.day_start.time().toString("HH:mm"),
            "day_end": self.day_end.time().toString("HH:mm"),
            "free_day_minutes": self.free_day.value(),
            "free_night_minutes": self.free_night.value(),
            "day_block_minutes": self.day_block.value(),
            "night_block_minutes": self.night_block.value(),
            "day_block_fee": self.day_fee.value(),
            "night_block_fee": self.night_fee.value(),
            "day_max": self.day_max.value(),
            "night_max": self.night_max.value(),
            "daily_wrap_fee": self.daily.value(),
        }
        def done(_r):
            self.load_tariff()
            show_status(self, "Tariff saved.")
            QMessageBox.information(self, "Tariff", "Tariff saved.")
        run_task(self, lambda: api.patch("/fees/tariff", payload), done, buttons=self.save_btn, busy_text="Saving…", title="Tariff")

class SimPage(QWidget):
    def __init__(self):
        super().__init__(); l=QVBoxLayout(self)
        title=QLabel("Testing & Simulation"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
        note=QLabel("Practice entry and exit without live cameras. Registered vehicles follow the same access rules as the live site.")
        note.setWordWrap(True); l.addWidget(note)
        form=QFormLayout()
        self.gate=QComboBox()
        self.plate=QLineEdit(); self.plate.setPlaceholderText("ABC 1234")
        self.file_label=QLabel("No photo selected")
        pick=QPushButton("Choose car photo…"); pick.clicked.connect(self.pick_file)
        form.addRow("Lane", self.gate); form.addRow("Plate", self.plate); form.addRow("Photo", pick); form.addRow("", self.file_label)
        l.addLayout(form)
        self.preview=QLabel("Car photo"); self.preview.setObjectName("video"); self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter); self.preview.setMinimumHeight(140)
        l.addWidget(self.preview)
        row=QHBoxLayout()
        typed=QPushButton("Enter plate as ENTRY"); typed.clicked.connect(self.do_plate_entry)
        entry=QPushButton("Upload as ENTRY"); entry.clicked.connect(lambda: self.do_upload("ENTRY"))
        taken=QPushButton("Receipt taken (open barrier)"); taken.clicked.connect(self.do_taken)
        pay=QPushButton("Mark paid"); pay.clicked.connect(self.do_pay)
        exitb=QPushButton("Upload as EXIT"); exitb.clicked.connect(lambda: self.do_upload("EXIT"))
        for w in (typed, entry, taken, pay, exitb): row.addWidget(w)
        row.addStretch(); l.addLayout(row)
        self.out=QPlainTextEdit(); self.out.setReadOnly(True); l.addWidget(self.out, 1)
        self._sid=None; self._path=""; self._workers=[]
    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_ready", False):
            self._ready=True
            self.reload()
    def _keep(self, worker):
        self._workers.append(worker)
        worker.finished.connect(lambda w=worker: self._workers.remove(w) if w in self._workers else None)
    def reload(self):
        self.gate.clear()
        self.out.setPlainText("Loading lanes…")
        def fill(lanes):
            self.gate.clear()
            for g in lanes or []:
                self.gate.addItem(g["name"], g["id"])
            self.out.setPlainText("" if lanes else "No lanes yet. Add site cameras so a lane exists.")
        run_task(self, lambda: api.get("/lanes"), fill, on_error=lambda message, _e: self.out.setPlainText(message))
    def pick_file(self):
        path,_=QFileDialog.getOpenFileName(self,"Car photo","","Images (*.jpg *.jpeg *.png)")
        if not path: return
        self._path=path
        self.file_label.setText(path)
        image=QImage(path)
        if not image.isNull():
            self.preview.setPixmap(QPixmap.fromImage(image).scaled(self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
    def do_plate_entry(self):
        plate=self.plate.text().strip()
        if not plate:
            QMessageBox.information(self,"Simulation","Type a number plate first."); return
        if self.gate.currentData() is None:
            QMessageBox.information(self,"Simulation","Add a lane first."); return
        w=Worker(lambda: api.post("/sim/entry", {"plate": plate, "gate_id": self.gate.currentData(), "side": "ENTRY"}, timeout=20))
        w.done.connect(self._show_result); w.failed.connect(lambda e: self.out.setPlainText(str(e))); self._keep(w); w.start()
    def do_upload(self, side):
        if not self._path:
            QMessageBox.information(self,"Simulation","Choose a JPEG photo of the car first."); return
        if self.gate.currentData() is None:
            QMessageBox.information(self,"Simulation","Add site cameras so a lane exists, then try again."); return
        path=self._path; gate_id=self.gate.currentData()
        def send():
            with open(path, "rb") as fh:
                data=fh.read()
            name=path.replace("\\","/").rsplit("/",1)[-1]
            return api.post_file("/sim/capture", {"file": (name, data, "image/jpeg")}, {"gate_id": str(gate_id), "side": side}, timeout=40)
        w=Worker(send)
        w.done.connect(self._show_result); w.failed.connect(lambda e: self.out.setPlainText(str(e))); self._keep(w); w.start()
    def _show_result(self, data):
        data=data or {}
        sess=data.get("session") or {}
        if sess.get("id"): self._sid=sess.get("id")
        parts=[]
        if data.get("receipt"): parts.append(data["receipt"])
        if data.get("say"): parts.append(data["say"])
        if data.get("message"): parts.append(data["message"])
        alpr=data.get("alpr") or {}
        best=(alpr.get("best") or {})
        if best.get("plate"): parts.append(f"Recognition: {best.get('plate')} ({int(round((best.get('confidence') or 0)*100))}%)")
        parts.append(json.dumps({k:v for k,v in data.items() if k not in {"alpr","receipt"}}, indent=2, default=str))
        self.out.setPlainText("\n\n".join(parts))
        crop=(
            best.get("crop_url")
            or sess.get("crop_url")
            or (data.get("capture") or {}).get("crop_url")
            or alpr.get("annotated_url")
            or sess.get("snapshot_url")
        )
        if crop:
            w=Worker(lambda url=crop: api.get_bytes(url, timeout=8))
            w.done.connect(lambda jpeg: self._pix(jpeg)); self._keep(w); w.start()
        if str(data.get("action") or "").upper() == "ENTRY" and (data.get("receipt") or data.get("qr_url") or sess.get("public_token")):
            qr_url=data.get("qr_url") or ""
            token=sess.get("public_token") or data.get("public_token") or ""
            if not qr_url and token:
                qr_url=f"/p/{token}/qr.png"
            show_printable_receipt(
                self,
                data.get("receipt") or "",
                ((data.get("print") or {}).get("path") or ""),
                qr_url=qr_url,
                qr_payload=data.get("qr_payload") or data.get("public_url") or sess.get("qr_payload") or "",
            )
    def _pix(self, jpeg):
        image=QImage.fromData(jpeg)
        if image.isNull(): return
        self.preview.setPixmap(QPixmap.fromImage(image).scaled(self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
    def do_taken(self):
        if not self._sid:
            QMessageBox.information(self,"Simulation","Upload an ENTRY photo first."); return
        w=Worker(lambda: api.post(f"/sim/sessions/{self._sid}/receipt-taken", {}, timeout=20))
        w.done.connect(self._show_result); w.failed.connect(lambda e: self.out.setPlainText(str(e))); self._keep(w); w.start()
    def do_pay(self):
        if not self._sid:
            QMessageBox.information(self,"Simulation","Upload an ENTRY photo first."); return
        w=Worker(lambda: api.post(f"/sim/sessions/{self._sid}/pay", {}, timeout=20))
        w.done.connect(self._show_result); w.failed.connect(lambda e: self.out.setPlainText(str(e))); self._keep(w); w.start()
