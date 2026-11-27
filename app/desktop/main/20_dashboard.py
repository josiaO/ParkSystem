from __future__ import annotations

# Lane states arrive as codes ("states") and are worded here, in the
# desktop's language; the words the server sends follow the site language.
LANE_STATE_WORDS = {
    "online": "Online", "offline": "Offline", "ready": "Ready", "degraded": "Degraded",
    "unknown": "Not set", "unassigned": "Not assigned", "other_gate": "Other gate",
}
LANE_STATE_COLOURS = {"online": "#1a7f37", "ready": "#1a7f37", "degraded": "#b54708", "offline": "#b42318"}


class Dashboard(QWidget):
    def __init__(self):
        super().__init__(); self.layout=QVBoxLayout(self)
        title=QLabel("Overview"); title.setStyleSheet("font-size:24px;font-weight:700")
        self.layout.addWidget(title)
        # The figures in one row, then the lanes as a table: the figures used
        # to be tall cards three to a row with the lanes as text cards below,
        # mostly empty space.
        self.grid=QGridLayout(); self.grid.setSpacing(8); self.layout.addLayout(self.grid)
        self.lanes=QTableWidget(0, 6)
        self.lanes.setHorizontalHeaderLabels(["Lane", "Camera", "Live video", "Plate recognition", "Barrier", "Last plate"])
        configure_table(self.lanes)
        self.lanes.setAccessibleName("Lane status")
        self.layout.addWidget(self.lanes, 1)
        self.alert=QLabel(""); self.alert.setWordWrap(True); self.layout.addWidget(self.alert)
        self.backup=QLabel(""); self.backup.setWordWrap(True); self.layout.addWidget(self.backup)
        backup_row=QHBoxLayout()
        self.open_reports=QPushButton("Open reports"); self.open_reports.clicked.connect(self._open_reports); self.open_reports.setVisible(False)
        self.snooze_backup=QPushButton("Remind me tomorrow"); self.snooze_backup.clicked.connect(self._snooze_backup); self.snooze_backup.setVisible(False)
        backup_row.addWidget(self.open_reports); backup_row.addWidget(self.snooze_backup); backup_row.addStretch()
        self.layout.addLayout(backup_row)
        self._cards=[]
        self._workers=[]
        QTimer.singleShot(0, self.refresh)
    def _keep(self, worker):
        self._workers.append(worker)
        worker.finished.connect(lambda w=worker: self._workers.remove(w) if w in self._workers else None)
    def _card(self, label, value):
        frame=QFrame(); frame.setObjectName("card")
        box=QVBoxLayout(frame); box.setContentsMargins(12, 8, 12, 8); box.setSpacing(0)
        val=QLabel(str(value)); val.setStyleSheet("font-size:22px;font-weight:700")
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
            self.grid.addWidget(frame, 0, i)
        lanes=data.get("lanes") or []
        self.lanes.setRowCount(len(lanes))
        for r,lane in enumerate(lanes):
            states=lane.get("states") or {}
            cells=[lane.get("label") or lane.get("name") or ""]
            for key in ("camera", "live_video", "plate_recognition", "barrier"):
                code=states.get(key)
                cells.append(LANE_STATE_WORDS.get(code, str(code)) if code else str(lane.get(key) or ""))
            cells.append(lane.get("last_plate") or "—")
            for c,value in enumerate(cells):
                item=QTableWidgetItem(str(value))
                code=states.get(("camera", "live_video", "plate_recognition", "barrier")[c-1]) if 1 <= c <= 4 else None
                if code in LANE_STATE_COLOURS:
                    item.setForeground(QColor(LANE_STATE_COLOURS[code]))
                self.lanes.setItem(r,c,item)
        self.lanes.setVisible(bool(lanes))
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
        def failed(_message, _exc):
            self.backup.setText("")
            self.open_reports.setVisible(False)
            self.snooze_backup.setVisible(False)
        run_task(self, lambda: api.get("/backup"), self._show_backup, on_error=failed)
    def _show_backup(self, status):
        status=status or {}
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
        run_task(self, lambda: api.post("/backup/snooze", {}), lambda _r: self._load_backup(),
                 buttons=self.snooze_backup, busy_text="Snoozing…", title="Backup")
