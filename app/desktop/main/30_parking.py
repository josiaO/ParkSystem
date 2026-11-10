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
        note=QLabel("Manual commands apply to one selected camera side, never both barriers. Select a configured gate, press 1 for entry or 2 for exit, then F8 / F9.")
        note.setWordWrap(True); l.addWidget(note)
        self.table=QTableWidget(0,6); self.table.setHorizontalHeaderLabels(["ID","Lane","Mode","Enabled","Sides (camera / controller / display)","Action"])
        configure_table(self.table); l.addWidget(self.table, 1)
        self.shortcut_hint=QLabel("Select a lane, then 1 = entry, 2 = exit. F8 / F9 pulse that side only.")
        self.shortcut_hint.setWordWrap(True); l.addWidget(self.shortcut_hint)
        self._armed_side=None
        row=QHBoxLayout()
        add=QPushButton(action_label("Add Gate", "Ctrl+N")); add.clicked.connect(self.add_gate); add.setVisible(api.can("gates.manage")); add.setToolTip("Add Gate (Ctrl+N)")
        edit=QPushButton(action_label("Edit", "Ctrl+E")); edit.clicked.connect(self.edit_gate); edit.setVisible(api.can("gates.manage")); edit.setToolTip("Edit (Ctrl+E)")
        delete=QPushButton(action_label("Delete", "Del")); delete.clicked.connect(self.delete_gate); delete.setVisible(api.can("gates.manage")); delete.setToolTip("Delete (Del)")
        led=QPushButton("LED text"); led.clicked.connect(self.write_led); led.setVisible(api.can("gates.open"))
        row.addWidget(add); row.addWidget(edit); row.addWidget(delete); row.addWidget(led); row.addStretch(); l.addLayout(row); self.rows=[]; self.refresh()
        sc1=QShortcut(QKeySequence("1"), self); sc1.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut); sc1.activated.connect(lambda: self.arm_side("ENTRY"))
        sc2=QShortcut(QKeySequence("2"), self); sc2.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut); sc2.activated.connect(lambda: self.arm_side("EXIT"))
    def refresh(self):
        try: rows=api.runtime_client().get("/gates")
        except Exception: rows=[]
        self.rows=rows
        self.table.setRowCount(len(rows))
        for r,g in enumerate(rows):
            cams=g.get("cameras") or []
            summary="; ".join(
                f'{row.get("side") or row.get("lane_direction")}: cam {row.get("ip_address")} / ctrl {row.get("controller_ip") or "—"} / disp {row.get("display_ip") or "—"}'
                for row in cams
            ) or "—"
            for c,v in enumerate([g["id"],g["name"],g["mode"],"Yes" if g["enabled"] else "No", summary]): self.table.setItem(r,c,QTableWidgetItem(str(v)))
            cell=QWidget(); hl=QHBoxLayout(cell); hl.setContentsMargins(0,0,0,0)
            seen=set()
            for cam in cams:
                side=(cam.get("lane_direction") or cam.get("side") or "").upper()
                if side not in {"ENTRY","EXIT"} or side in seen:
                    continue
                seen.add(side)
                b=QPushButton("Open entry" if side=="ENTRY" else "Open exit")
                b.clicked.connect(lambda _,gid=g["id"],s=side: self._open_and_arm(gid,s,"open"))
                hl.addWidget(b)
                cbtn=QPushButton("Close entry" if side=="ENTRY" else "Close exit")
                cbtn.clicked.connect(lambda _,gid=g["id"],s=side: self._open_and_arm(gid,s,"close"))
                hl.addWidget(cbtn)
            self.table.setCellWidget(r,5,cell)
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
    def _open_and_arm(self, gid, side, action):
        self._armed_side=side
        self.arm_side(side)
        self.command_gate(gid, side, action)
    def add_gate(self):
        d=GateDialog()
        if d.exec():
            try: api.runtime_client().post("/gates",d.payload()); self.refresh()
            except Exception as e: QMessageBox.critical(self,"Gate",str(e))
    def edit_gate(self):
        gate=self.selected_gate()
        if not gate: QMessageBox.information(self,"Edit gate","Select a gate first."); return
        d=GateDialog(gate)
        if d.exec():
            try: api.runtime_client().patch(f"/gates/{gate['id']}",d.payload()); self.refresh()
            except Exception as e: QMessageBox.critical(self,"Edit gate",str(e))
    def delete_gate(self):
        gate=self.selected_gate()
        if not gate: QMessageBox.information(self,"Delete gate","Select a gate first."); return
        if QMessageBox.question(self,"Delete gate",f"Delete {gate['name']}?")!=QMessageBox.Yes: return
        try: api.runtime_client().delete(f"/gates/{gate['id']}"); self.refresh()
        except Exception as e: QMessageBox.critical(self,"Delete gate",str(e))
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
            try: QMessageBox.information(self,"Barrier",str(api.runtime_client().post(f"/gates/{gid}/open",{"reason":reason,"side":side,"action":verb}, timeout=20)))
            except Exception as e: QMessageBox.critical(self,"Barrier",str(e))
    def write_led(self):
        gate=self.selected_gate()
        if not gate: QMessageBox.information(self,"LED","Select a lane first."); return
        cams=gate.get("cameras") or []
        if not cams: QMessageBox.information(self,"LED","No cameras on this lane."); return
        text,ok=QInputDialog.getText(self,"LED text","Message", text="WELCOME")
        if not ok or not text: return
        try:
            first=cams[0]
            QMessageBox.information(self,"LED",str(api.runtime_client().post(f"/cameras/{first['id']}/led",{"text":text})))
        except Exception as e: QMessageBox.critical(self,"LED",str(e))

class VehicleDialog(QDialog):
    def __init__(self, vehicle=None, plans=None):
        super().__init__(); self.setWindowTitle("Edit vehicle" if vehicle else "Register plate")
        form=QFormLayout(self)
        self.plate=QLineEdit(); self.owner=QLineEdit(); self.plan=QComboBox(); self.enabled=QComboBox(); self.enabled.addItems(["Yes","No"]); self.notes=QLineEdit()
        self.use_from=QCheckBox("Starts on")
        self.valid_from=QDateEdit(QDate.currentDate()); self.valid_from.setCalendarPopup(True); self.valid_from.setDisplayFormat("yyyy-MM-dd")
        self.use_until=QCheckBox("Ends on")
        self.valid_until=QDateEdit(QDate.currentDate()); self.valid_until.setCalendarPopup(True); self.valid_until.setDisplayFormat("yyyy-MM-dd")
        for p in plans or []: self.plan.addItem(p["name"], p["id"])
        if vehicle:
            self.plate.setText(vehicle.get("plate") or ""); self.owner.setText(vehicle.get("owner_name") or "")
            idx=self.plan.findData(vehicle.get("plan_id"));
            if idx>=0: self.plan.setCurrentIndex(idx)
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
            "notes": self.notes.text().strip(),
            "valid_from": _iso_date(self.valid_from.date().toString("yyyy-MM-dd")) if self.use_from.isChecked() else None,
            "valid_until": _iso_date(self.valid_until.date().toString("yyyy-MM-dd"), end=True) if self.use_until.isChecked() else None,
        }

class Sessions(QWidget):
    def __init__(self):
        super().__init__(); l=QVBoxLayout(self)
        title=QLabel("Parking sessions"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
        note=QLabel("Find a visit by scanning the receipt QR or typing the plate. Compare the photo and the time inside before taking money. Payment stays off when nothing is owed.")
        note.setWordWrap(True); l.addWidget(note)
        find=QHBoxLayout()
        self.query=QLineEdit(); self.query.setPlaceholderText("Scan QR, paste the receipt link, or type the plate")
        self.query.returnPressed.connect(self.lookup)
        find_btn=QPushButton("Find visit"); find_btn.clicked.connect(self.lookup)
        find.addWidget(label_for("&Find visit", self.query)); find.addWidget(self.query, 1); find.addWidget(find_btn); l.addLayout(find)
        card=QFrame(); card.setObjectName("card"); card_l=QHBoxLayout(card)
        photos=QVBoxLayout()
        self.photo=QLabel("No entry photo stored."); self.photo.setMinimumSize(200, 140); self.photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.photo.setObjectName("video"); self.photo.setAccessibleName("Selected visit entry photograph")
        self.crop=QLabel(""); self.crop.setMinimumHeight(80); self.crop.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.crop.setObjectName("video"); self.crop.setAccessibleName("Selected visit plate crop")
        photos.addWidget(self.photo); photos.addWidget(self.crop)
        detail=QVBoxLayout()
        self.kiosk_plate=QLabel("—"); self.kiosk_plate.setStyleSheet("font-size:28px;font-weight:700;letter-spacing:2px")
        self.kiosk_stay=QLabel("Scan a receipt or pick a session.")
        self.kiosk_stay.setWordWrap(True)
        self.kiosk_due=QLabel(""); self.kiosk_due.setStyleSheet("font-size:18px;font-weight:700")
        self.kiosk_note=QLabel(""); self.kiosk_note.setWordWrap(True)
        self.correct=QLineEdit(); self.correct.setPlaceholderText("Correct plate")
        actions=QVBoxLayout()
        save_plate=QPushButton("Save corrected plate"); save_plate.clicked.connect(self.correct_plate)
        self.pay_btn=QPushButton("Record payment"); self.pay_btn.clicked.connect(self.pay_visit); self.pay_btn.setEnabled(False)
        self.mobile_btn=QPushButton("Pay with mobile on this computer"); self.mobile_btn.clicked.connect(self.pay_mobile); self.mobile_btn.setEnabled(False)
        can_pay=api.can("payments.create") or api.can("kiosk.use")
        self.pay_btn.setVisible(can_pay)
        self.mobile_btn.setVisible(can_pay)
        actions.addWidget(save_plate); actions.addWidget(self.pay_btn); actions.addWidget(self.mobile_btn)
        detail.addWidget(self.kiosk_plate); detail.addWidget(self.kiosk_stay); detail.addWidget(self.kiosk_due); detail.addWidget(self.kiosk_note)
        detail.addWidget(label_for("&Correct plate", self.correct)); detail.addWidget(self.correct); detail.addLayout(actions)
        card_l.addLayout(photos, 1); card_l.addLayout(detail, 2)
        l.addWidget(card)
        self.table=QTableWidget(0,8); self.table.setHorizontalHeaderLabels(["Plate","Kind","Status","Receipt","Entry","Due","Paid","Gate"])
        configure_table(self.table); l.addWidget(self.table, 1)
        self.table.itemSelectionChanged.connect(self._on_row)
        row=QHBoxLayout()
        pay=QPushButton("Record kiosk payment"); pay.clicked.connect(self.pay); pay.setVisible(can_pay)
        receipt=QPushButton("Show / print receipt"); receipt.clicked.connect(self.print_receipt)
        refresh=QPushButton("Refresh"); refresh.clicked.connect(self.refresh)
        row.addWidget(pay); row.addWidget(receipt); row.addWidget(refresh); row.addStretch(); l.addLayout(row)
        self.rows=[]; self.visit=None; self.refresh()
    def _pixmap(self, label, path, empty):
        if not path:
            label.setPixmap(QPixmap()); label.setText(empty); return
        try:
            data=api.get_bytes(path, timeout=12)
            pix=QPixmap(); pix.loadFromData(data)
            if pix.isNull():
                label.setText(empty); return
            label.setText("")
            label.setPixmap(pix.scaled(320, 180, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        except Exception:
            label.setPixmap(QPixmap()); label.setText(empty)
    def _show_visit(self, data):
        self.visit=data or None
        if not data:
            self.kiosk_plate.setText("—")
            self.kiosk_stay.setText("No visit matches that QR code or plate.")
            self.kiosk_due.setText("")
            self.kiosk_note.setText("")
            self.pay_btn.setEnabled(False)
            self.mobile_btn.setEnabled(False)
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
        self.correct.setText("" if data.get("image_matches_plate") is False else (data.get("plate") or ""))
        payable=bool(data.get("payable"))
        self.pay_btn.setEnabled(payable)
        self.mobile_btn.setEnabled(payable and bool(data.get("token")))
        self._pixmap(self.photo, data.get("snapshot_url"), "No entry photo stored.")
        self._pixmap(self.crop, data.get("crop_url"), "")
    def lookup(self):
        from urllib.parse import quote
        q=self.query.text().strip()
        if not q:
            QMessageBox.information(self, "Find visit", "Scan a QR code or type a plate."); return
        try:
            data=api.get(f"/sessions/lookup?q={quote(q, safe='')}", timeout=15)
        except Exception as exc:
            self._show_visit(None)
            self.kiosk_stay.setText(str(exc))
            return
        self._show_visit(data)
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
        try: self.rows=api.get("/sessions")
        except Exception as e: QMessageBox.warning(self,"Sessions",str(e)); return
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
        self._filling=False
    def selected(self):
        row=self.table.currentRow()
        if row<0 or row>=len(self.rows): return None
        return self.rows[row]
    def print_receipt(self):
        s=self.selected()
        if not s: QMessageBox.information(self,"Receipt","Select a session first."); return
        try:
            issued=api.post(f"/sessions/{s['id']}/receipt", {}, timeout=15)
        except Exception as e:
            QMessageBox.critical(self,"Receipt",str(e)); return
        body=(issued or {}).get("receipt") or ""
        printed=(issued or {}).get("print") or {}
        record=(issued or {}).get("receipt_record") or {}
        path=printed.get("path") or (record.get("payload") or {}).get("path") or ""
        qr_url=(issued or {}).get("qr_url") or ""
        if not qr_url and (issued or {}).get("public_token"):
            qr_url=f"/p/{issued['public_token']}/qr.png"
        qr_payload=(issued or {}).get("qr_payload") or (issued or {}).get("public_url") or ""
        if not body:
            try:
                slip=api.get(f"/sessions/{s['id']}/receipt")
                body=slip.get("body_text") or ""
                path=(slip.get("payload") or {}).get("path") or path
                qr_payload=qr_payload or slip.get("qr_payload") or ""
                if not qr_url and slip.get("qr_url"):
                    qr_url=slip.get("qr_url")
            except Exception:
                pass
        show_printable_receipt(self, body, path, qr_url=qr_url, qr_payload=qr_payload)
        self.refresh()
    def correct_plate(self):
        visit=self.visit or {}
        session_id=visit.get("session_id")
        plate=self.correct.text().strip()
        if not session_id or not plate:
            QMessageBox.information(self, "Correct plate", "Find the visit and type the plate you can see."); return
        try:
            api.post(f"/sessions/{session_id}/correct-plate", {"plate": plate})
        except Exception as exc:
            QMessageBox.critical(self, "Correct plate", str(exc)); return
        self.query.setText(plate)
        self.lookup()
        self.refresh()
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
        try:
            if method == "KIOSK_CASH" and token:
                result=api.post(f"/p/{token}/kiosk-pay", {"method": "KIOSK_CASH"})
            elif method == "KIOSK_CASH" and session_id:
                result=api.post(f"/sessions/{session_id}/pay", {"method": "KIOSK_CASH"})
            elif token:
                result=api.post(f"/p/{token}/pay", {"method": "MOBILE_SIMULATED"})
            else:
                raise RuntimeError("This visit has no receipt code for phone payment.")
        except Exception as exc:
            QMessageBox.critical(self, "Payment", str(exc)); return
        if result.get("already_paid"):
            QMessageBox.information(self, "Payment", "Already settled.")
        else:
            QMessageBox.information(self, "Payment", "Payment recorded.")
        if "payable" in (result or {}):
            self._show_visit(result)
        self.refresh()
    def pay_visit(self):
        self._settle("KIOSK_CASH")
    def pay_mobile(self):
        self._settle("MOBILE_SIMULATED")
    def pay(self):
        s=self.selected()
        if s:
            self.query.setText(s.get("public_token") or s.get("plate") or "")
            self.lookup()
        if not (self.visit or {}).get("session_id") and s:
            self.visit={"session_id": s.get("id"), "plate": s.get("plate"), "token": s.get("public_token"), "payable": float(s.get("amount_due") or 0) > float(s.get("amount_paid") or 0)}
        self.pay_visit()

class Payments(QWidget):
    def __init__(self):
        super().__init__(); l=QVBoxLayout(self)
        title=QLabel("Payments"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
        note=QLabel("Kiosk and mobile payments share one ledger. A phone success screen is not paid until a verified transaction exists.")
        note.setWordWrap(True); l.addWidget(note)
        self.table=QTableWidget(0,6); self.table.setHorizontalHeaderLabels(["When","Session","Method","Amount","Status","Provider"])
        configure_table(self.table); l.addWidget(self.table, 1)
        refresh=QPushButton("Refresh"); refresh.clicked.connect(self.refresh)
        row=QHBoxLayout(); row.addWidget(refresh); row.addStretch(); l.addLayout(row)
        self.refresh()
    def refresh(self):
        try: rows=api.get("/payments")
        except Exception as e: QMessageBox.warning(self,"Payments",str(e)); return
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
        self.table=QTableWidget(0,7); self.table.setHorizontalHeaderLabels(["Plate","Owner","Plan","Auto-open","Enabled","From","Until"])
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        configure_table(self.table); l.addWidget(self.table, 1)
        bulk_note=QLabel("Register many, one plate per line: plate, owner, start date, end date")
        l.addWidget(bulk_note)
        self.bulk=QPlainTextEdit(); self.bulk.setPlaceholderText("ABC1234, Owner, 2026-09-01, 2026-10-01"); self.bulk.setMaximumHeight(90)
        l.addWidget(self.bulk)
        row=QHBoxLayout()
        manage=api.can("subscribers.manage")
        add=QPushButton(action_label("Register plate", "Ctrl+N")); add.clicked.connect(self.add); add.setVisible(manage); add.setToolTip("Register plate (Ctrl+N)")
        bulk=QPushButton("Register these plates"); bulk.clicked.connect(self.add_bulk); bulk.setVisible(manage)
        edit=QPushButton(action_label("Edit", "Ctrl+E")); edit.clicked.connect(self.edit); edit.setVisible(manage); edit.setToolTip("Edit (Ctrl+E)")
        delete=QPushButton(action_label("Delete", "Del")); delete.clicked.connect(self.delete); delete.setVisible(manage); delete.setToolTip("Delete (Del)")
        delete_many=QPushButton(action_label("Delete selected", "Del")); delete_many.clicked.connect(self.delete_selected); delete_many.setVisible(manage); delete_many.setToolTip("Delete selected (Del)")
        refresh=QPushButton(action_label("Refresh", "F5")); refresh.clicked.connect(self.refresh); refresh.setToolTip("Refresh (F5)")
        row.addWidget(add); row.addWidget(bulk); row.addWidget(edit); row.addWidget(delete); row.addWidget(delete_many); row.addWidget(refresh); row.addStretch(); l.addLayout(row)
        self.rows=[]; self.refresh()
    def refresh(self):
        try: self.rows=api.get("/vehicles")
        except Exception as e: QMessageBox.warning(self,"Vehicles",str(e)); return
        self.table.setRowCount(len(self.rows))
        for r,v in enumerate(self.rows):
            vals=[
                v["plate"], v.get("owner_name") or "—", v.get("plan_name") or "—",
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
    def add(self):
        d=VehicleDialog(plans=api.get("/access-plans"))
        if d.exec():
            try: api.post("/vehicles", d.payload()); self.refresh()
            except Exception as e: QMessageBox.critical(self,"Register plate",str(e))
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
        try:
            result=api.post("/vehicles/bulk", {"vehicles": vehicles})
        except Exception as exc:
            QMessageBox.critical(self, "Register plates", str(exc)); return
        failed="; ".join(item.get("error") or "" for item in (result.get("errors") or []) if item.get("error"))
        created=len(result.get("created") or [])
        self.bulk.clear()
        self.refresh()
        QMessageBox.information(self, "Register plates", f"Registered {created} plates. {failed}".strip())
    def edit(self):
        v=self.selected()
        if not v: QMessageBox.information(self,"Edit","Select a plate first."); return
        d=VehicleDialog(v, plans=api.get("/access-plans"))
        if d.exec():
            try: api.patch(f"/vehicles/{v['id']}", d.payload()); self.refresh()
            except Exception as e: QMessageBox.critical(self,"Edit",str(e))
    def delete(self):
        v=self.selected()
        if not v: return
        if QMessageBox.question(self,"Delete",f"Remove {v['plate']}?")!=QMessageBox.Yes: return
        try: api.delete(f"/vehicles/{v['id']}"); self.refresh()
        except Exception as e: QMessageBox.critical(self,"Delete",str(e))
    def delete_selected(self):
        ids=self.selected_ids()
        if not ids:
            QMessageBox.information(self, "Delete", "Select at least one plate."); return
        if QMessageBox.question(self, "Delete", f"Remove {len(ids)} registered plate(s)?")!=QMessageBox.Yes: return
        try: api.post("/vehicles/bulk-delete", {"ids": ids}); self.refresh()
        except Exception as e: QMessageBox.critical(self,"Delete",str(e))

class Fees(QWidget):
    def __init__(self):
        super().__init__(); l=QVBoxLayout(self)
        title=QLabel("Tariffs & Schedules"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
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
        actions.addWidget(save); actions.addWidget(reload_btn); actions.addStretch(); l.addLayout(actions)
        quote_form=QFormLayout()
        self.entry=QLineEdit(); self.exit=QLineEdit()
        from datetime import datetime, timedelta
        now=datetime.now()
        self.entry.setText((now-timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S"))
        self.exit.setText(now.strftime("%Y-%m-%dT%H:%M:%S"))
        quote_form.addRow("Entry (site time)", self.entry); quote_form.addRow("Exit (site time)", self.exit)
        l.addLayout(quote_form)
        quote=QPushButton("Quote Car1 fee"); quote.clicked.connect(self.quote); l.addWidget(quote)
        self.out=QLabel(""); self.out.setWordWrap(True); l.addWidget(self.out)
        l.addStretch()
        self.load_tariff()
    def _set_time(self, edit, value):
        parsed=QTime.fromString(str(value or "")[:5], "HH:mm")
        if parsed.isValid():
            edit.setTime(parsed)
    def load_tariff(self):
        try: data=api.get("/fees/tariff")
        except Exception as e: self.out.setText(str(e)); return
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
        try:
            api.patch("/fees/tariff", payload)
        except Exception as exc:
            QMessageBox.critical(self, "Tariff", str(exc)); return
        self.load_tariff()
        QMessageBox.information(self, "Tariff", "Tariff saved.")
    def quote(self):
        try:
            data=api.post("/fees/quote",{"entry_time":self.entry.text().strip(),"exit_time":self.exit.text().strip(),"car_type":"Car1"})
        except Exception as e:
            QMessageBox.critical(self,"Fee",str(e)); return
        minutes=max(0, int(int(data.get("duration_seconds") or 0) / 60))
        due=int(data.get("due") or 0)
        currency=data.get("currency") or self.currency.text() or "TZS"
        self.out.setText(f"{currency} {due:,} for {minutes} min.")

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
        try:
            for g in api.get("/lanes"):
                self.gate.addItem(g["name"], g["id"])
        except Exception as e:
            self.out.setPlainText(str(e))
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
