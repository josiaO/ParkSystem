from __future__ import annotations

class Dashboard(QWidget):
    def __init__(self):
        super().__init__(); self.layout=QVBoxLayout(self)
        title=QLabel("Overview"); title.setStyleSheet("font-size:24px;font-weight:700")
        self.layout.addWidget(title)
        self.grid=QGridLayout(); self.layout.addLayout(self.grid)
        self.alert=QLabel(""); self.alert.setWordWrap(True); self.layout.addWidget(self.alert)
        self.backup=QLabel(""); self.backup.setWordWrap(True); self.layout.addWidget(self.backup)
        backup_row=QHBoxLayout()
        self.open_reports=QPushButton("Open reports"); self.open_reports.clicked.connect(self._open_reports); self.open_reports.setVisible(False)
        self.snooze_backup=QPushButton("Remind me tomorrow"); self.snooze_backup.clicked.connect(self._snooze_backup); self.snooze_backup.setVisible(False)
        backup_row.addWidget(self.open_reports); backup_row.addWidget(self.snooze_backup); backup_row.addStretch()
        self.layout.addLayout(backup_row)
        self.layout.addStretch()
        self._cards=[]
        self._workers=[]
        QTimer.singleShot(0, self.refresh)
    def _keep(self, worker):
        self._workers.append(worker)
        worker.finished.connect(lambda w=worker: self._workers.remove(w) if w in self._workers else None)
    def _card(self, label, value):
        frame=QFrame(); frame.setObjectName("card")
        box=QVBoxLayout(frame)
        val=QLabel(str(value)); val.setStyleSheet("font-size:28px;font-weight:700")
        cap=QLabel(label); cap.setObjectName("muted")
        box.addWidget(val); box.addWidget(cap)
        prepare_page(frame, label)
        return frame, val
    def refresh(self):
        w=Worker(lambda: api.get("/dashboard"))
        w.done.connect(self._apply)
        w.failed.connect(lambda e: self.alert.setText(f"Unable to load dashboard: {e}"))
        self._keep(w); w.start()
    def _apply(self, data):
        data=data or {}
        stats=self._dashboard_stats(data)
        while self.grid.count():
            item=self.grid.takeAt(0)
            w=item.widget()
            if w is not None:
                w.deleteLater()
        for i,(label,value) in enumerate(stats):
            frame,_=self._card(label, value)
            self.grid.addWidget(frame, i//3, i%3)
        for i,lane in enumerate(data.get("lanes") or []):
            text=(
                f"{lane.get('label') or lane.get('name') or ''}\n"
                f"Camera: {lane.get('camera')}\n"
                f"Live Video: {lane.get('live_video')}\n"
                f"Plate Recognition: {lane.get('plate_recognition')}\n"
                f"Barrier: {lane.get('barrier')}"
            )
            frame=QFrame(); frame.setObjectName("card")
            box=QVBoxLayout(frame)
            cap=QLabel(text); cap.setWordWrap(True)
            box.addWidget(cap)
            self.grid.addWidget(frame, 2 + i//2, i%2)
        alerts=data.get("alerts") or []
        self.alert.setText("  ·  ".join(alerts) if alerts else "No hardware alerts.")
        self._load_backup()
    def _dashboard_stats(self, data):
        kind=deployment_kind()
        online=data.get("sdk_connected", 0)
        cameras=data.get("cameras", 0)
        if kind=="lpr":
            return [
                ("Cameras online", online),
                ("Cameras configured", cameras),
                ("Registered vehicles", data.get("registered_plates", 0)),
            ]
        if kind=="security":
            return [
                ("Cameras online", online),
                ("Cameras configured", cameras),
                ("Active notices", len(data.get("alerts") or [])),
            ]
        if kind=="access":
            return [
                ("Registered vehicles", data.get("registered_plates", 0)),
                ("Cameras online", online),
                ("Devices configured", cameras),
            ]
        return [
            ("Vehicles inside", data.get("vehicles_inside", 0)),
            ("Entries today", data.get("entries_today", 0)),
            ("Exits today", data.get("exits_today", 0)),
            ("Revenue today", data.get("revenue_today_label") or money_label(data.get("revenue_today"), data.get("currency"))),
            ("Unpaid sessions", data.get("unpaid_active", 0)),
            ("Subscribers inside", data.get("subscribers_inside", 0)),
        ]
    def _load_backup(self):
        try:
            status=api.get("/backup")
        except Exception:
            self.backup.setText("")
            self.open_reports.setVisible(False)
            self.snooze_backup.setVisible(False)
            return
        due=bool(status.get("offline_due") or status.get("cloud_due"))
        bits=[]
        if status.get("offline_due"):
            bits.append(status.get("offline_message") or "")
        if status.get("cloud_due"):
            bits.append(status.get("cloud_message") or "Cloud backup is due.")
        self.backup.setText(" ".join(bit for bit in bits if bit))
        self.open_reports.setVisible(due)
        self.snooze_backup.setVisible(due)
    def _open_reports(self):
        window=self.window()
        nav=getattr(window, "nav", None)
        if nav is None:
            return
        for i in range(nav.count()):
            if "report" in nav.item(i).text().lower():
                nav.setCurrentRow(i)
                return
    def _snooze_backup(self):
        try:
            api.post("/backup/snooze", {})
        except Exception as exc:
            QMessageBox.warning(self, "Backup", str(exc))
            return
        self._load_backup()
