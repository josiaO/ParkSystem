from __future__ import annotations

class SystemHealth(QWidget):
    def __init__(self):
        super().__init__()
        l=QVBoxLayout(self)
        title=QLabel("System Health"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
        note=QLabel("Parking stays up when one camera or the HVX host is degraded. The summary is in plain language.")
        note.setWordWrap(True); l.addWidget(note)
        self.state=QLabel("…"); self.state.setStyleSheet("font-size:18px;font-weight:700"); l.addWidget(self.state)
        self.summary=QLabel("…"); self.summary.setWordWrap(True); l.addWidget(self.summary)
        self.clock=QLabel(""); self.clock.setWordWrap(True); self.clock.setAccessibleName("Clock synchronisation"); l.addWidget(self.clock)
        self.info=QPlainTextEdit(); self.info.setReadOnly(True); self.info.setVisible(False); l.addWidget(self.info, 1)
        row=QHBoxLayout(); refresh=QPushButton("Refresh"); refresh.clicked.connect(self.refresh); self.refresh_btn=refresh
        self.details_btn=QPushButton("Show technical details"); self.details_btn.clicked.connect(self._toggle_details)
        row.addWidget(refresh); row.addWidget(self.details_btn); row.addStretch(); l.addLayout(row)
        self._timer=QTimer(self); self._timer.setInterval(4000); self._timer.timeout.connect(self.refresh)
    def showEvent(self, event):
        super().showEvent(event)
        if not self._timer.isActive():
            self._timer.start()
        self.refresh()
    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)
    def shutdown(self):
        self._timer.stop()
    def refresh(self):
        if getattr(self, "_busy", False):
            return
        self._busy=True
        def fetch():
            live=api.get("/health/live")
            try:
                data=api.get("/health/details")
            except Exception:
                try:
                    data=api.get("/health/ready")
                except Exception as e:
                    data={"error": friendly_error(e), "live": live}
            return live, data, self._workstation_clock()
        def failed(message, _exc):
            self._busy=False
            self.state.setText("OFFLINE")
            self.summary.setText(message)
            self.info.setPlainText(message)
        def done(result):
            self._busy=False
            self._show(*result)
        run_task(self, fetch, done, on_error=failed)
    def _show(self, live, data, workstation):
        state=(live.get("state") or live.get("process", {}).get("state") or "UNKNOWN")
        data=dict(data or {})
        if workstation is not None:
            data["workstation_clock"]=workstation
        self.state.setText(str(data.get("state") or state))
        self.summary.setText(health_sentences(data, live))
        self.clock.setText(clock_summary(data.get("clock"), workstation))
        self.info.setPlainText(json.dumps(data, indent=2, default=str))
    def _workstation_clock(self):
        """This computer's clock against the Site Server (half round trip removed)."""
        import time as _time
        from app.services.clock_skew import skew_from_server_time
        try:
            started=_time.time()
            clock=api.get("/settings/clock")
            return skew_from_server_time(clock.get("server_time_utc") or "", round_trip_seconds=_time.time()-started)
        except Exception:
            return None
    def _toggle_details(self):
        show=not self.info.isVisible()
        self.info.setVisible(show)
        self.details_btn.setText("Hide technical details" if show else "Show technical details")

class Hardware(QWidget):
    def __init__(self):
        super().__init__(); l=QVBoxLayout(self)
        title=QLabel("Hardware Lab"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
        warn=QLabel("Technician tools: camera connection, media streaming, recognition, gate I/O, and logs."); warn.setWordWrap(True); l.addWidget(warn)
        self.info=QPlainTextEdit(); self.info.setReadOnly(True); self.info.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.info.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        l.addWidget(self.info, 1)
        row=QHBoxLayout()
        b=QPushButton("Check HVX SDK Host"); b.clicked.connect(self.check)
        a=QPushButton("Check recognition"); a.clicked.connect(self.check_alpr)
        m=QPushButton("Check media gateway"); m.clicked.connect(self.check_media)
        d=QPushButton("Check decode path"); d.clicked.connect(self.check_decode)
        self._buttons={"/hardware/hvx/info": b, "/alpr/status": a, "/media/gateway": m, "/hardware/decode": d}
        row.addWidget(b); row.addWidget(a); row.addWidget(m); row.addWidget(d); row.addStretch(); l.addLayout(row)
    def _check(self, path):
        self.info.setPlainText("Checking…")
        run_task(self, lambda: api.get(path, timeout=15),
                 lambda data: self.info.setPlainText(json.dumps(data, indent=2, default=str)),
                 buttons=getattr(self, "_buttons", {}).get(path), busy_text="Checking…",
                 on_error=lambda message, _e: self.info.setPlainText(message))
    def check_alpr(self): self._check("/alpr/status")
    def check_media(self): self._check("/media/gateway")
    def check_decode(self): self._check("/hardware/decode")
    def check(self): self._check("/hardware/hvx/info")
    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_ready", False):
            self._ready=True
            self.check()

class OnboardingWizard(QWidget):
    """Full 8-step deployment setup (prompt §9), driven by /onboarding/*."""
    def __init__(self):
        super().__init__()
        self._status = {}
        self._step = 1
        root = QVBoxLayout(self)
        title = QLabel("Setup Wizard")
        title.setStyleSheet("font-size:24px;font-weight:700")
        root.addWidget(title)
        self.subtitle = QLabel("Configure this deployment in eight steps.")
        self.subtitle.setWordWrap(True)
        self.subtitle.setObjectName("muted")
        root.addWidget(self.subtitle)
        self.step_label = QLabel("Step 1 of 8")
        self.step_label.setStyleSheet("font-weight:700;color:#0E7C72")
        root.addWidget(self.step_label)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        # 1 purpose
        p1 = QWidget(); l1 = QVBoxLayout(p1)
        l1.addWidget(QLabel("What do you want to use this site for?"))
        self.use_case = QComboBox()
        for cid, label in [
            ("LPR", "License Plate Recognition"),
            ("SECURITY", "Security Monitoring"),
            ("ACCESS", "Vehicle Access Control"),
            ("PARKING", "Parking Management"),
            ("CUSTOM", "Custom"),
        ]:
            self.use_case.addItem(label, cid)
        l1.addWidget(self.use_case)
        self.stack.addWidget(p1)

        # 2 topology
        p2 = QWidget(); l2 = QVBoxLayout(p2)
        l2.addWidget(QLabel("How is this site laid out?"))
        self.topo_preset = QComboBox()
        self.topo_preset.addItem("1 entry / 1 exit", "1in1out")
        self.topo_preset.addItem("One bidirectional lane", "bidirectional")
        self.topo_preset.addItem("No gates", "lpr_only")
        self.topo_preset.addItem("Multiple lanes — keep current", "keep")
        l2.addWidget(self.topo_preset)
        form2 = QFormLayout()
        self.site_name = QLineEdit("Default Site")
        self.site_tz = QLineEdit("UTC")
        self.site_cur = QComboBox()
        for code, label in (
            ("USD", "US Dollar (USD)"),
            ("EUR", "Euro (EUR)"),
            ("GBP", "British Pound (GBP)"),
            ("KES", "Kenyan Shilling (KES)"),
            ("TZS", "Tanzanian Shilling (TZS)"),
            ("AED", "UAE Dirham (AED)"),
        ):
            self.site_cur.addItem(label, code)
        self.site_lang = QComboBox()
        for code, label in (("en", "English"), ("sw", "Kiswahili"), ("ar", "Arabic"), ("fr", "French"), ("pt", "Portuguese")):
            self.site_lang.addItem(label, code)
        form2.addRow("Site name", self.site_name)
        form2.addRow("Timezone", self.site_tz)
        form2.addRow("Currency", self.site_cur)
        form2.addRow("Language", self.site_lang)
        l2.addLayout(form2)
        self.stack.addWidget(p2)

        # 3 hardware
        p3 = QWidget(); l3 = QVBoxLayout(p3)
        l3.addWidget(QLabel("Add cameras now, or skip and add them later under Devices."))
        self.hw_info = QPlainTextEdit(); self.hw_info.setReadOnly(True)
        l3.addWidget(self.hw_info)
        disc = QPushButton("Discover cameras on LAN")
        disc.clicked.connect(self._discover); self.disc_btn = disc
        l3.addWidget(disc)
        self.stack.addWidget(p3)

        # 4 recognition
        p4 = QWidget(); l4 = QVBoxLayout(p4)
        l4.addWidget(QLabel("How should plates be read?"))
        self.rec_mode = QComboBox()
        for mid, label in [
            ("NATIVE_ONLY", "Use camera recognition"),
            ("FASTALPR_ONLY", f"Use {PRODUCT_NAME} AI recognition"),
            ("HYBRID", "Use both"),
            ("VIDEO_ONLY", "Video only"),
        ]:
            self.rec_mode.addItem(label, mid)
        self.rec_mode.setCurrentIndex(2)
        l4.addWidget(self.rec_mode)
        self.stack.addWidget(p4)

        # 5 modules
        p5 = QWidget(); l5 = QVBoxLayout(p5)
        l5.addWidget(QLabel("Optional features. Disabled features disappear from navigation."))
        self.mod_list = QListWidget()
        self.mod_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        l5.addWidget(self.mod_list)
        self.stack.addWidget(p5)

        # 6 users
        p6 = QWidget(); l6 = QVBoxLayout(p6)
        l6.addWidget(QLabel("Optional: create an operator account (leave blank to skip)"))
        form6 = QFormLayout()
        self.new_user = QLineEdit(); self.new_full = QLineEdit()
        self.new_pass = QLineEdit(); self.new_pass.setEchoMode(QLineEdit.Password)
        self.new_role = QComboBox(); self.new_role.addItems(["Operator", "Admin", "Cashier", "Technician"])
        form6.addRow("Username", self.new_user)
        form6.addRow("Full name", self.new_full)
        form6.addRow("Password", self.new_pass)
        form6.addRow("Role", self.new_role)
        l6.addLayout(form6)
        self.stack.addWidget(p6)

        # 7 health
        p7 = QWidget(); l7 = QVBoxLayout(p7)
        l7.addWidget(QLabel("Module health — Disabled is neutral, not an error."))
        self.health_view = QPlainTextEdit(); self.health_view.setReadOnly(True)
        l7.addWidget(self.health_view)
        refresh = QPushButton("Refresh health")
        refresh.clicked.connect(self._load)
        l7.addWidget(refresh)
        self.stack.addWidget(p7)

        # 8 activate
        p8 = QWidget(); l8 = QVBoxLayout(p8)
        self.ready = QLabel("Ready to activate this deployment.")
        self.ready.setWordWrap(True)
        self.ready.setStyleSheet("font-size:16px;font-weight:600")
        l8.addWidget(self.ready)
        self.stack.addWidget(p8)

        nav = QHBoxLayout()
        self.back_btn = QPushButton("Back"); self.back_btn.clicked.connect(self._back)
        self.skip_btn = QPushButton("Skip step"); self.skip_btn.setObjectName("secondary"); self.skip_btn.clicked.connect(lambda: self._next(skip=True))
        self.next_btn = QPushButton("Continue"); self.next_btn.clicked.connect(lambda: self._next(skip=False))
        self.act_btn = QPushButton("Activate deployment"); self.act_btn.clicked.connect(self._activate)
        nav.addWidget(self.back_btn); nav.addStretch(); nav.addWidget(self.skip_btn); nav.addWidget(self.next_btn); nav.addWidget(self.act_btn)
        root.addLayout(nav)
        self.err = QLabel(""); self.err.setStyleSheet("color:#C0372E"); self.err.setWordWrap(True)
        root.addWidget(self.err)
        QTimer.singleShot(0, self._load)

    def _discover(self):
        self.hw_info.setPlainText("Searching the LAN for cameras… (up to 45 s)")
        def done(data):
            cams = data.get("cameras") if isinstance(data, dict) else data
            n = len(cams) if isinstance(cams, list) else 0
            self.hw_info.setPlainText(f"{n} camera(s) found.\nOpen Devices to add and connect them.")
        run_task(self, lambda: api.runtime_client().get("/cameras/discover?scan_lan=true", timeout=45), done,
                 buttons=self.disc_btn, busy_text="Searching…", on_error=lambda message, _e: self.hw_info.setPlainText(message))

    def _load(self):
        self.err.setText("")
        run_task(self, lambda: api.get("/onboarding/status"), self._apply_status,
                 on_error=lambda message, _e: self.err.setText(message))

    def _apply_status(self, status):
        try:
            self._status = status or {}
            self._step = max(1, min(int(self._status.get("step") or 1), 8))
            uc = self._status.get("use_case")
            if uc:
                idx = self.use_case.findData(uc)
                if idx >= 0:
                    self.use_case.setCurrentIndex(idx)
            site = ((self._status.get("topology") or {}).get("site") or {})
            if site.get("name"):
                self.site_name.setText(site["name"])
            if site.get("timezone"):
                self.site_tz.setText(site["timezone"])
            if site.get("currency"):
                idx = self.site_cur.findData(site["currency"])
                if idx < 0:
                    self.site_cur.addItem(str(site["currency"]), site["currency"])
                    idx = self.site_cur.findData(site["currency"])
                if idx >= 0:
                    self.site_cur.setCurrentIndex(idx)
            if site.get("language"):
                idx = self.site_lang.findData(site["language"])
                if idx >= 0:
                    self.site_lang.setCurrentIndex(idx)
            self.mod_list.clear()
            for row in self._status.get("optional_module_choices") or []:
                item = QListWidgetItem(f"{row.get('label')} — {row.get('description', '')}")
                item.setData(Qt.ItemDataRole.UserRole, row.get("id"))
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if row.get("enabled") else Qt.CheckState.Unchecked)
                self.mod_list.addItem(item)
            comps = ((self._status.get("health") or {}).get("components") or {})
            lines = [f"{k}: {v.get('state', '—')}" for k, v in comps.items()]
            self.health_view.setPlainText("\n".join(lines) or "No health data.")
            enabled = self._status.get("enabled_modules") or []
            self.ready.setText(
                f"Profile {self._status.get('profile') or '—'} · {len(enabled)} modules enabled.\n"
                + ", ".join(enabled)
            )
            counts = self._status.get("counts") or {}
            self.hw_info.setPlainText(
                f"Cameras: {counts.get('cameras', 0)} · Gates: {counts.get('gates', 0)} · Lanes: {counts.get('lanes', 0)}"
            )
            self._show_step()
        except Exception as e:
            self.err.setText(str(e))

    def _show_step(self):
        self.stack.setCurrentIndex(self._step - 1)
        self.step_label.setText(f"Step {self._step} of 8")
        self.back_btn.setEnabled(self._step > 1)
        self.skip_btn.setVisible(self._step not in (1, 8))
        self.next_btn.setVisible(self._step < 8)
        self.act_btn.setVisible(self._step >= 8)

    def _payload(self, next_step, *, activate=False, skip=False):
        body = {
            "step": next_step,
            "use_case": self.use_case.currentData(),
            "activate": activate,
            "skip": skip,
        }
        if self._step == 2 and not skip:
            body["site"] = {
                "name": self.site_name.text().strip(),
                "timezone": self.site_tz.text().strip() or "UTC",
                "currency": self.site_cur.currentData() or "USD",
                "language": self.site_lang.currentData() or "en",
                "locale": self.site_lang.currentData() or "en",
            }
            preset = self.topo_preset.currentData()
            if preset != "keep":
                body["topology"] = {"preset": preset}
        if self._step == 3 and not skip:
            body["hardware"] = {"reviewed": True}
        if self._step == 4 and not skip:
            body["recognition_mode"] = self.rec_mode.currentData()
        if self._step == 5 and not skip:
            selected = []
            for i in range(self.mod_list.count()):
                item = self.mod_list.item(i)
                if item.checkState() == Qt.CheckState.Checked:
                    selected.append(item.data(Qt.ItemDataRole.UserRole))
            body["optional_modules"] = selected
        if self._step == 6 and not skip:
            u = self.new_user.text().strip()
            p = self.new_pass.text()
            if u and p:
                body["user"] = {
                    "username": u,
                    "password": p,
                    "full_name": self.new_full.text().strip() or u,
                    "role": self.new_role.currentText(),
                }
        if self._step == 7:
            body["health_ok"] = True
        return body

    def _back(self):
        self._step = max(1, self._step - 1)
        self._show_step()

    def _next(self, skip=False):
        self.err.setText("")
        nxt = min(8, self._step + 1)
        payload = self._payload(nxt, skip=skip)
        def done(_r):
            self._step = nxt
            self._load()
        run_task(self, lambda: api.post("/onboarding/step", payload), done,
                 buttons=(self.next_btn, self.skip_btn, self.back_btn), busy_text=None,
                 on_error=lambda message, _e: self.err.setText(message))

    def _activate(self):
        self.err.setText("")
        payload = self._payload(8, activate=True)
        def done(_r):
            QMessageBox.information(self, "Activated", "Deployment activated. Restart navigation by signing out and back in if needed.")
            self._load()
        run_task(self, lambda: api.post("/onboarding/step", payload), done, buttons=self.act_btn, busy_text="Activating…",
                 on_error=lambda message, _e: self.err.setText(message))

class PlateEnginePage(QWidget):
    """Recent plate reads. Engine files stay in the technician view."""

    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        title = QLabel("Detections")
        title.setStyleSheet("font-size:24px;font-weight:700")
        root.addWidget(title)
        intro = QLabel("Recent plate reads from this site. Camera and model details stay in Hardware Lab.")
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        root.addWidget(intro)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Time", "Plate", "Camera", "Lane", "Confidence"])
        configure_table(self.table)
        root.addWidget(self.table, 1)
        self.card = QLabel("")
        self.card.setWordWrap(True)
        self.card.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.card.setVisible(is_technician())
        root.addWidget(self.card)
        row = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.load); self.refresh_btn = refresh
        pack = QPushButton("Apply model pack…"); self.pack_btn = pack
        pack.setObjectName("secondary")
        pack.clicked.connect(self.apply_pack)
        pack.setVisible(is_technician())
        row.addWidget(refresh)
        row.addWidget(pack)
        row.addStretch()
        root.addLayout(row)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

    def showEvent(self, event):
        super().showEvent(event)
        self.load()

    def load(self):
        technician = is_technician()
        def fetch():
            rows = api.get("/captures?limit=50") or []
            engine = None
            if technician:
                try:
                    engine = api.get("/recognition/engine")
                except Exception as exc:
                    engine = {"_error": friendly_error(exc)}
            return rows, engine
        run_task(self, fetch, lambda pair: self._show(*pair), buttons=getattr(self, "refresh_btn", None), busy_text="Loading…",
                 on_error=lambda message, _e: self.status.setText(f"Detections could not be loaded. {message}"))

    def _show(self, rows, data):
        rows = rows or []
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            conf = row.get("confidence")
            pct = ""
            if conf is not None:
                pct = f"{int(round(float(conf) * 100 if float(conf) <= 1 else float(conf)))}%"
            vals = [
                str(row.get("created_at") or "")[:19].replace("T", " "),
                row.get("plate") or "—",
                row.get("camera_id") if row.get("camera_id") is not None else "—",
                row.get("lane_direction") or "—",
                pct or "—",
            ]
            for c, val in enumerate(vals):
                self.table.setItem(r, c, QTableWidgetItem(str(val)))
        if not rows:
            self.status.setText("No detections yet. Detected vehicles will appear here automatically.")
        elif not is_technician():
            self.status.setText("")
        if not is_technician() or data is None:
            return
        if "_error" in data:
            self.card.setText(data["_error"])
            return
        models = data.get("models") or {}
        training = data.get("training") or {}
        engines = ", ".join(row.get("id", "") for row in (data.get("engines") or []))
        lines = [
            f"Engine: {data.get('display_name')} ({data.get('id')}) {data.get('version')}",
            f"Installed: {'yes' if data.get('installed') else 'no'}    Loaded: {'yes' if data.get('loaded') else 'no'}",
            f"Country: {data.get('country')}    Contrast: {data.get('contrast_sensitivity')}",
            f"Detector: {models.get('detector_file')} ({'ready' if models.get('detector_ready') else 'missing'})",
            f"OCR: {models.get('ocr_file')} ({'ready' if models.get('ocr_ready') else 'missing'})",
            f"Model folder: {models.get('bundled_dir') or 'not installed'}",
            f"Registered engines: {engines or data.get('id')}",
            f"Corrections saved for retraining: {training.get('corrections', 0)}",
            str(training.get("retrain") or ""),
        ]
        self.card.setText("\n".join(lines))
        self.status.setText("Technician recognition details are below the detection list.")

    def apply_pack(self):
        folder = QFileDialog.getExistingDirectory(self, "Model pack folder")
        if not folder:
            return
        self.status.setText("Installing model pack…")
        def done(result):
            self.status.setText(f"Installed to {(result or {}).get('installed_to')}. The next car uses the new weights.")
            self.load()
        run_task(self, lambda: api.post("/recognition/model-pack", {"directory": folder}, timeout=60), done,
                 buttons=self.pack_btn, busy_text="Installing…", on_error=lambda message, _e: self.status.setText(message))

class SettingsPage(QWidget):
    """Every site setting in one place, in tabs.

    Each tab loads in the background the first time the page is shown and
    each Save button shows "Saving…" until the Site Server answers, then a
    plain result or a plain error ("Can't reach the Site Server" vs "the
    Site Server refused: …").
    """

    def __init__(self, window):
        super().__init__(); self.window=window; l=QVBoxLayout(self)
        title=QLabel("Settings"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
        self.tabs=QTabWidget(); l.addWidget(self.tabs, 1)
        manage=api.can("settings.manage")
        self._build_general(window, manage)
        if api.can("simulation.run"):
            self._build_parking()
        if api.nav_page("fees") or api.can("fees.view") or api.can("fees.manage"):
            # Tariffs & Schedules moved here from its own page.
            self.tariffs=Fees()
            self.tabs.addTab(self._scroll(self.tariffs), "Tariffs")
        if api.can("cameras.view") or api.can("cameras.manage"):
            self._build_calibration()
        if manage:
            self._build_recognition()
            self._build_payments()
            self._build_alerts()
            self._build_developer()

    # ------------------------------------------------------------ helpers --
    @staticmethod
    def _scroll(widget):
        area=QScrollArea(); area.setWidgetResizable(True); area.setFrameShape(QFrame.Shape.NoFrame); area.setWidget(widget)
        return area

    @staticmethod
    def _note(text):
        label=QLabel(text); label.setWordWrap(True); label.setObjectName("muted"); return label

    @staticmethod
    def _status_label():
        label=QLabel(""); label.setWordWrap(True); label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    @staticmethod
    def _set_combo(combo, value):
        value=str(value if value is not None else "")
        idx=combo.findData(value)
        if idx<0: idx=combo.findText(value)
        if idx<0 and value and combo.isEditable():
            combo.setEditText(value); return
        if idx<0 and value:
            combo.addItem(value, value); idx=combo.findData(value)
        if idx>=0: combo.setCurrentIndex(idx)

    # ------------------------------------------------------------- general --
    def _build_general(self, window, manage):
        page=QWidget(); v=QVBoxLayout(page)
        form=QFormLayout()
        combo=QComboBox(); combo.addItems(APPEARANCES); combo.setCurrentText(window.appearance)
        combo.currentTextChanged.connect(self.change)
        window.appearanceChanged.connect(lambda name: self._sync_appearance(combo, name))
        form.addRow("Appearance (this computer)", combo)
        self.site_name=QLineEdit(); self.site_name.setPlaceholderText("Main car park")
        self.timezone=QLineEdit(); self.timezone.setPlaceholderText("Africa/Dar_es_Salaam")
        self.currency=QLineEdit(); self.currency.setPlaceholderText("TZS"); self.currency.setMaxLength(8)
        self.currency_precision=QSpinBox(); self.currency_precision.setRange(0, 4)
        self.language=QComboBox(); self.language.addItems(["en","sw","ar","fr","pt"])
        self.date_format=QComboBox(); self.date_format.setEditable(True); self.date_format.addItems(["YYYY-MM-DD","DD/MM/YYYY","MM/DD/YYYY"])
        self.time_format=QComboBox(); self.time_format.setEditable(True); self.time_format.addItems(["HH:mm:ss","HH:mm","hh:mm a"])
        self.plate_validation=QComboBox(); self.plate_validation.addItems(["NONE","TZ","KE","ZA","AE"])
        self.public_base_url=QLineEdit(); self.public_base_url.setPlaceholderText("http://smartpark-server:8760")
        self.support_contacts=QLineEdit(); self.support_contacts.setPlaceholderText("Phone or e-mail shown on receipts")
        form.addRow("Site name", self.site_name)
        form.addRow("Timezone (IANA)", self.timezone)
        form.addRow("Currency (ISO 4217)", self.currency)
        form.addRow("Decimal places in money", self.currency_precision)
        form.addRow("Language", self.language)
        form.addRow("Date format", self.date_format)
        form.addRow("Time format", self.time_format)
        form.addRow("Plate validation", self.plate_validation)
        form.addRow("Public receipt URL (QR scans)", self.public_base_url)
        form.addRow("Support contact", self.support_contacts)
        v.addLayout(form)
        self.site_save=QPushButton("Save site settings"); self.site_save.clicked.connect(self.save_site)
        self.site_reload=QPushButton("Reload"); self.site_reload.setObjectName("secondary"); self.site_reload.clicked.connect(self.load_site)
        row=QHBoxLayout(); row.addWidget(self.site_save); row.addWidget(self.site_reload); row.addStretch(); v.addLayout(row)
        if not (manage or api.can("simulation.run")):
            # settings.view users can correct the site clock/display locale,
            # but cannot change fee currency, plate policy, or public QR host.
            for field in (self.site_name, self.currency, self.currency_precision, self.plate_validation,
                          self.public_base_url, self.support_contacts):
                field.setEnabled(False)
            self.timezone.setPlaceholderText("Africa/Dar_es_Salaam or UTC")
        self.site_status=self._status_label(); v.addWidget(self.site_status)
        v.addStretch()
        self.tabs.addTab(self._scroll(page), "Site")

    # ------------------------------------------------------------- parking --
    def _build_parking(self):
        page=QWidget(); v=QVBoxLayout(page)
        v.addWidget(self._note("Parking rules. Live lanes and simulation share these."))
        self.receipt=QCheckBox("Receipt must be taken before the entry barrier opens")
        self.policy=QComboBox()
        for value, label in (("REQUIRE_TAKEN_BEFORE_OPEN", "Print, wait until the driver takes it, then open"),
                             ("PRINT_AND_OPEN", "Print and open at once"),
                             ("PRINT_OPTIONAL", "Print if the printer works; open anyway"),
                             ("OFF", "No entry receipt")):
            self.policy.addItem(label, value)
        self.pay=QCheckBox("Exit stays closed until the visit is paid")
        self.kiosk_cash=QCheckBox("Payment kiosks may take cash")
        self.kiosk_cash.setToolTip("Off: kiosks offer mobile money only and the cash button is hidden.")
        self.grace=QSpinBox(); self.grace.setRange(0, 7200); self.grace.setSuffix(" s"); self.grace.setSingleStep(60)
        self.grace.setToolTip("After paying, the driver has this long to reach the exit before more time is charged.")
        self.passage=QSpinBox(); self.passage.setRange(0, 3600); self.passage.setSuffix(" s")
        self.passage.setToolTip("How long a lane waits for the car to pass the open barrier before it gives up.")
        self.stranded=QSpinBox(); self.stranded.setRange(0, 1440); self.stranded.setSuffix(" min")
        self.stranded.setToolTip("An entry that never completed is cleared after this many minutes (0 = never).")
        self.prompt=QLineEdit()
        self.printer=QComboBox(); self.printer.setEditable(False)
        pf=QFormLayout()
        pf.addRow("Entry receipt", self.policy)
        pf.addRow("", self.receipt)
        pf.addRow("", self.pay)
        pf.addRow("", self.kiosk_cash)
        pf.addRow("Time to leave after paying", self.grace)
        pf.addRow("Wait for car to pass barrier", self.passage)
        pf.addRow("Clear unfinished entries after", self.stranded)
        pf.addRow("Pay prompt on receipt", self.prompt)
        pf.addRow("Thermal receipt printer", self.printer)
        v.addLayout(pf)
        v.addWidget(self._note("Thermal receipt printer (58 mm / 80 mm USB roll): plug it in, pick it here, Save. A detected car prints a ticket, then the gate opens."))
        row=QHBoxLayout()
        self.park_save=QPushButton("Save parking rules"); self.park_save.clicked.connect(self.save_parking)
        self.park_test=QPushButton("Print test ticket"); self.park_test.setObjectName("secondary"); self.park_test.clicked.connect(self.test_printer)
        row.addWidget(self.park_save); row.addWidget(self.park_test); row.addStretch(); v.addLayout(row)
        self.park_status=self._status_label(); v.addWidget(self.park_status)
        v.addStretch()
        self.tabs.addTab(self._scroll(page), "Parking rules")

    # ------------------------------------------------------ calibration --
    def _build_calibration(self):
        """Each camera's capture calibration. The Live Gates view shows it; edits happen here."""
        page=QWidget(); v=QVBoxLayout(page)
        v.addWidget(self._note("Where and how close each camera reads plates. Every camera is calibrated on its own. "
                               "A car is read only when its plate meets that camera's calibration. "
                               "The Live Gates view shows the zone and plate boxes; change them here."))
        self.cal_table=QTableWidget(0, 5)
        self.cal_table.setHorizontalHeaderLabels(["Camera", "Direction", "Gate", "Calibration", "Test mode"])
        configure_table(self.cal_table)
        self.cal_table.itemDoubleClicked.connect(lambda *_: self.open_calibration())
        v.addWidget(self.cal_table, 1)
        row=QHBoxLayout()
        self.cal_open=QPushButton("Calibrate selected camera…"); self.cal_open.clicked.connect(self.open_calibration)
        self.cal_reload=QPushButton("Reload"); self.cal_reload.setObjectName("secondary"); self.cal_reload.clicked.connect(self.load_calibration)
        row.addWidget(self.cal_open); row.addWidget(self.cal_reload); row.addStretch(); v.addLayout(row)
        self.cal_status=self._status_label(); v.addWidget(self.cal_status)
        self._cal_cameras=[]
        self.tabs.addTab(page, "Camera calibration")

    def load_calibration(self):
        self.cal_status.setText("Loading cameras…")
        def fetch():
            runtime=api.runtime_client() if hasattr(api, "runtime_client") else api
            cameras=runtime.get("/cameras") or []
            rows=[]
            for cam in cameras:
                try:
                    data=runtime.get(f"/cameras/{cam['id']}/calibration", timeout=6)
                except Exception:
                    data={}
                rows.append((cam, data or {}))
            return rows
        run_task(self, fetch, self._show_calibration, buttons=self.cal_reload, busy_text="Loading…",
                 on_error=lambda message, _e: self.cal_status.setText(message))

    def _show_calibration(self, rows):
        self._cal_cameras=[cam for cam, _ in rows]
        self.cal_table.setRowCount(len(rows))
        uncalibrated=0
        problems=[]
        for r, (cam, data) in enumerate(rows):
            cfg=data.get("calibration") or {}
            test=data.get("test_mode") or {}
            state=f"Calibrated · version {cfg.get('version')}" if cfg.get("enabled") else "Not calibrated (reads the whole picture)"
            uncalibrated += 0 if cfg.get("enabled") else 1
            name=cam.get("name") or f"Camera {cam.get('id')}"
            notes=list(cfg.get("ignored") or [])
            if data.get("warning"):
                notes.insert(0, str(data["warning"]))
            if notes:
                state += " · CHECK"
                problems.append(f"{name}: " + " ".join(notes))
            values=[cam.get("name") or f"Camera {cam.get('id')}", str(cam.get("lane_direction") or "").title(),
                    cam.get("gate_name") or "—", state,
                    f"On until {str(test.get('until') or '')[11:16]} UTC" if test.get("enabled") else "Off"]
            for c, value in enumerate(values):
                self.cal_table.setItem(r, c, QTableWidgetItem(str(value)))
        summary=f"{uncalibrated} camera(s) not calibrated yet." if uncalibrated else "All cameras calibrated."
        if problems:
            summary += "\n" + "\n".join(problems)
        self.cal_status.setText(summary)

    def open_calibration(self):
        row=self.cal_table.currentRow()
        cams=self._cal_cameras
        if not cams:
            self.cal_status.setText("No cameras yet."); return
        cam=cams[row] if 0 <= row < len(cams) else cams[0]
        from app.desktop.calibration import CalibrationWindow
        window=CalibrationWindow(cam, cameras=cams, parent=self.window)
        window.finished.connect(lambda *_: self.load_calibration())
        window.destroyed.connect(lambda *_: None)
        self._cal_window=window
        window.show()

    # ------------------------------------------------------------ payments --
    def _build_payments(self):
        page=QWidget(); v=QVBoxLayout(page)
        v.addWidget(self._note("Mobile money is collected through ClickPesa. Keys are stored on the Site Server only; "
                               "saved keys are never shown again. Leave a key field empty to keep the stored key."))
        form=QFormLayout()
        self.mm_provider=QComboBox()
        self.mm_provider.addItem("Off — practice payments only (no real money)", "simulated")
        self.mm_provider.addItem("ClickPesa", "clickpesa")
        self.cp_client=QLineEdit(); self.cp_client.setPlaceholderText("ClickPesa client ID")
        self.cp_key=QLineEdit(); self.cp_key.setEchoMode(QLineEdit.EchoMode.Password); self.cp_key.setPlaceholderText("Not set")
        self.cp_checksum=QLineEdit(); self.cp_checksum.setEchoMode(QLineEdit.EchoMode.Password); self.cp_checksum.setPlaceholderText("Not set")
        self.cp_url=QLineEdit(); self.cp_url.setPlaceholderText("https://api.clickpesa.com/third-parties")
        self.cp_live=QCheckBox("Collect real money with ClickPesa")
        self.cp_confirm=QCheckBox("I confirm this site is ready to take real payments")
        self.cp_confirm.setToolTip("ClickPesa has no test mode. Both boxes must be ticked before any real collection.")
        form.addRow("Mobile money", self.mm_provider)
        form.addRow("Client ID", self.cp_client)
        form.addRow("API key", self.cp_key)
        form.addRow("Checksum key (webhooks)", self.cp_checksum)
        form.addRow("ClickPesa address", self.cp_url)
        form.addRow("", self.cp_live)
        form.addRow("", self.cp_confirm)
        v.addLayout(form)
        row=QHBoxLayout()
        self.pay_save=QPushButton("Save mobile money"); self.pay_save.clicked.connect(self.save_payments)
        self.pay_reload=QPushButton("Reload"); self.pay_reload.setObjectName("secondary"); self.pay_reload.clicked.connect(self.load_payments)
        row.addWidget(self.pay_save); row.addWidget(self.pay_reload); row.addStretch(); v.addLayout(row)
        self.pay_status=self._status_label(); v.addWidget(self.pay_status)
        v.addStretch()
        self.tabs.addTab(self._scroll(page), "Mobile money")

    # -------------------------------------------------------------- alerts --
    def _build_alerts(self):
        page=QWidget(); v=QVBoxLayout(page)
        v.addWidget(self._note("Who is told when a barrier is opened by hand, a free exit happens, or a gate command fails."))
        self.al_enabled=QCheckBox("Send alerts")
        self.al_zero=QCheckBox("Also alert on free (zero-fee) exits")
        self.al_failed=QCheckBox("Also alert when a gate command fails")
        v.addWidget(self.al_enabled); v.addWidget(self.al_zero); v.addWidget(self.al_failed)
        v.addWidget(QLabel("Recipients, one per line: channel, address, name   (channel = sms, email or webhook)"))
        self.al_recipients=QPlainTextEdit(); self.al_recipients.setPlaceholderText("sms, +255700000000, Supervisor\nemail, manager@example.com, Manager")
        self.al_recipients.setMaximumHeight(140); v.addWidget(self.al_recipients)
        row=QHBoxLayout()
        self.al_save=QPushButton("Save alerts"); self.al_save.clicked.connect(self.save_alerts)
        self.al_test=QPushButton("Send test to first recipient"); self.al_test.setObjectName("secondary"); self.al_test.clicked.connect(self.test_alert)
        row.addWidget(self.al_save); row.addWidget(self.al_test); row.addStretch(); v.addLayout(row)
        self.al_status=self._status_label(); v.addWidget(self.al_status)
        self._alerts_extra={}
        v.addStretch()
        self.tabs.addTab(self._scroll(page), "Alerts")

    # --------------------------------------------------------- recognition --
    def _build_recognition(self):
        """Settings that used to be lines in zirp.env. Saved in the site database."""
        from PySide6.QtWidgets import QDoubleSpinBox

        page=QWidget(); v=QVBoxLayout(page)
        v.addWidget(self._note("How the lanes take and read plate pictures. Changes apply within a few seconds "
                               "on every Zirp PC; no restart. The site's plate country is under Site → Plate validation."))
        self.rec_trigger=QComboBox()
        for value, label in (("external", "The camera or another parking system triggers the pictures (Zirp only reads)"),
                             ("zirp", "Zirp triggers the camera when its video sees a car"),
                             ("both", "Both: Zirp triggers, and also reads the camera's own pictures")):
            self.rec_trigger.addItem(label, value)
        self.rec_limit=QCheckBox("Read each car at most twice")
        self.rec_limit.setToolTip("Read once; read a second picture only when the first read is unsure. "
                                  "Fewer reads means fewer chances of a misread.")
        self.rec_confident=QDoubleSpinBox(); self.rec_confident.setRange(0.50, 0.99); self.rec_confident.setSingleStep(0.01); self.rec_confident.setDecimals(2)
        self.rec_confident.setToolTip("A read at or above this is final. Below it, Zirp reads one more picture of the car.")
        self.rec_quiet=QDoubleSpinBox(); self.rec_quiet.setRange(1, 30); self.rec_quiet.setSingleStep(0.5); self.rec_quiet.setDecimals(1); self.rec_quiet.setSuffix(" s")
        self.rec_quiet.setToolTip("After this long without a camera trigger the car has gone; the next trigger is a new car.")
        self.rec_max=QDoubleSpinBox(); self.rec_max.setRange(5, 120); self.rec_max.setSingleStep(5); self.rec_max.setDecimals(0); self.rec_max.setSuffix(" s")
        self.rec_max.setToolTip("A car waiting at the barrier longer than this is read again.")
        self.rec_photo=QComboBox()
        for value, label in (("off", "Don't show the entry photo"), ("blurred", "Show it blurred"), ("full", "Show it as taken")):
            self.rec_photo.addItem(label, value)
        form=QFormLayout()
        form.addRow("Who triggers the pictures", self.rec_trigger)
        form.addRow("", self.rec_limit)
        form.addRow("A read is final from", self.rec_confident)
        form.addRow("Car has left after", self.rec_quiet)
        form.addRow("Read a waiting car again after", self.rec_max)
        form.addRow("Photo on the driver's receipt page", self.rec_photo)
        v.addLayout(form)
        self.rec_limit.toggled.connect(lambda on: [w.setEnabled(on) for w in (self.rec_confident, self.rec_quiet, self.rec_max)])
        v.addWidget(self._note("A loop going high, or the camera reporting a different plate, always starts a new car, "
                               "so a queue is never skipped. Operator reads are never limited."))
        row=QHBoxLayout()
        self.rec_save=QPushButton("Save recognition settings"); self.rec_save.clicked.connect(self.save_recognition)
        row.addWidget(self.rec_save); row.addStretch(); v.addLayout(row)
        self.rec_status=self._status_label(); v.addWidget(self.rec_status)
        v.addStretch()
        self.tabs.addTab(self._scroll(page), "Recognition")

    # ----------------------------------------------------------- developer --
    def _build_developer(self):
        page=QWidget(); v=QVBoxLayout(page)
        v.addWidget(self._note("Switch one subsystem at a time while testing a lane. Physical actions stay off when switched off. "
                               "Individual switches only apply while Developer mode is on."))
        labels=(
            ("developer_mode", "Developer mode"),
            ("logging_enabled", "Detailed logging"),
            ("printing_enabled", "Printing"),
            ("gate_opening_enabled", "Gate opening (any)"),
            ("automatic_gate_opening_enabled", "Automatic gate opening"),
            ("recognition_enabled", "Plate recognition"),
            ("capture_enabled", "Saving captures"),
            ("camera_connections_enabled", "Camera connections"),
            ("destructive_tools_enabled", "Allow deleting test data"),
        )
        self.dev_boxes={}
        for key, label in labels:
            box=QCheckBox(label); self.dev_boxes[key]=box; v.addWidget(box)
        row=QHBoxLayout()
        self.dev_save=QPushButton("Save developer controls"); self.dev_save.clicked.connect(self.save_developer)
        row.addWidget(self.dev_save); row.addStretch(); v.addLayout(row)
        self.dev_status=self._status_label(); v.addWidget(self.dev_status)
        v.addStretch()
        self.tabs.addTab(self._scroll(page), "Developer")

    def _sync_appearance(self, combo, name):
        previous = combo.blockSignals(True)
        combo.setCurrentText(name)
        combo.blockSignals(previous)

    def showEvent(self, event):
        super().showEvent(event)
        # Headless presentation fixtures intentionally provide only the
        # navigation surface. The real ApiClient exposes ``base_url``;
        # lightweight UI doubles must not turn a render-only test into a
        # network/settings request.
        if not hasattr(api, "base_url"):
            return
        if api.can("settings.view") and not getattr(self, "_loaded", False):
            self._loaded=True
            self.load_site()
            if hasattr(self, "park_save"):
                self.load_parking()
            if hasattr(self, "pay_save"):
                self.load_payments()
            if hasattr(self, "al_save"):
                self.load_alerts()
            if hasattr(self, "rec_save"):
                self.load_recognition()
            if hasattr(self, "dev_save"):
                self.load_developer()
            if hasattr(self, "cal_table"):
                self.load_calibration()

    # ---------------------------------------------------------------- site --
    def load_site(self):
        self.site_status.setText("Loading site settings…")
        def fetch():
            return api.get("/settings/site"), api.get("/settings/clock")
        run_task(self, fetch, lambda pair: SettingsPage._show_site(self, *pair),
                 buttons=getattr(self, "site_reload", None), busy_text="Loading…",
                 on_error=lambda message, _e: self.site_status.setText(message))
    def _show_site(self, data, clock):
        from app.config import settings as _settings
        data=data or {}; clock=clock or {}
        if getattr(self, "site_name", None) is not None:
            self.site_name.setText(str(data.get("name") or ""))
        self.timezone.setText(str(data.get("timezone") or _settings.site_timezone))
        self.currency.setText(str(data.get("currency") or ""))
        self.public_base_url.setText(str(data.get("public_base_url") or ""))
        idx=self.language.findText(str(data.get("language") or "en"))
        if idx>=0: self.language.setCurrentIndex(idx)
        idx=self.plate_validation.findText(str(data.get("plate_validation") or "NONE"))
        if idx>=0: self.plate_validation.setCurrentIndex(idx)
        if getattr(self, "currency_precision", None) is not None and data.get("currency_precision") is not None:
            try: self.currency_precision.setValue(int(data.get("currency_precision") or 0))
            except (TypeError, ValueError): pass
        if getattr(self, "date_format", None) is not None and data.get("date_format"):
            SettingsPage._set_combo(self.date_format, data.get("date_format"))
        if getattr(self, "time_format", None) is not None and data.get("time_format"):
            SettingsPage._set_combo(self.time_format, data.get("time_format"))
        if getattr(self, "support_contacts", None) is not None:
            contacts=data.get("support_contacts")
            self.support_contacts.setText(contacts if isinstance(contacts, str) else "")
        self.site_status.setText(
            f"Server clock (UTC): {clock.get('server_time_utc', '—')} · "
            f"Site clock ({clock.get('timezone', data.get('timezone') or 'UTC')}): {clock.get('site_time', '—')}"
        )
    def save_site(self):
        from app.config import settings as _settings
        payload={
            "timezone": self.timezone.text().strip() or _settings.site_timezone,
            "language": self.language.currentText(),
        }
        if self.currency.isEnabled():
            payload.update({
                "currency": self.currency.text().strip().upper(),
                "plate_validation": self.plate_validation.currentText(),
                "public_base_url": self.public_base_url.text().strip().rstrip("/"),
            })
            if getattr(self, "site_name", None) is not None and self.site_name.text().strip():
                payload["name"]=self.site_name.text().strip()
            if getattr(self, "currency_precision", None) is not None:
                payload["currency_precision"]=self.currency_precision.value()
            if getattr(self, "support_contacts", None) is not None:
                payload["support_contacts"]=self.support_contacts.text().strip()
        if getattr(self, "date_format", None) is not None:
            payload["date_format"]=self.date_format.currentText().strip()
        if getattr(self, "time_format", None) is not None:
            payload["time_format"]=self.time_format.currentText()
        self.site_status.setText("Saving…")
        def done(saved):
            saved=saved or {}
            self.site_status.setText(f"Saved. Timezone {saved.get('timezone')} · currency {saved.get('currency')}.")
            show_status(self, "Site settings saved.")
        run_task(self, lambda: api.patch("/settings/site", payload), done,
                 buttons=getattr(self, "site_save", None), busy_text="Saving…",
                 on_error=lambda message, _e: self.site_status.setText(message))
    def change(self,text): self.window.apply_theme(text)

    # ------------------------------------------------------------- parking --
    def load_parking(self):
        self.park_status.setText("Loading parking rules…")
        def fetch():
            data=api.get("/settings/parking")
            try:
                status=api.get("/printers/status")
            except Exception:
                status={}
            return data, status
        run_task(self, fetch, lambda pair: self._show_parking(*pair),
                 on_error=lambda message, _e: self.park_status.setText(message))
    def _show_parking(self, data, status):
        data=data or {}; status=status or {}
        self.receipt.setChecked(bool(data.get("receipt_required_before_open")))
        SettingsPage._set_combo(self.policy, data.get("receipt_policy") or "PRINT_AND_OPEN")
        self.pay.setChecked(bool(data.get("exit_requires_payment")))
        self.kiosk_cash.setChecked(bool(data.get("kiosk_cash_enabled", True)))
        self.grace.setValue(int(data.get("payment_exit_grace_seconds") or 0))
        self.passage.setValue(int(data.get("passage_timeout_seconds") or 0))
        self.stranded.setValue(int(data.get("stranded_entry_minutes") or 0))
        self.prompt.setText(str(data.get("pay_prompt") or ""))
        self.printer.clear()
        self.printer.addItem("File only (no paper)", "")
        chosen=str(data.get("printer_name") or status.get("printer_name") or "")
        found=False
        for row in status.get("printers") or []:
            name=str(row.get("name") or "")
            if not name: continue
            label=name
            extras=[]
            if row.get("is_usb"): extras.append("USB")
            if row.get("is_default"): extras.append("default")
            if extras: label=f"{name}  ({', '.join(extras)})"
            self.printer.addItem(label, name)
            if name==chosen: found=True
        if chosen and not found:
            self.printer.addItem(chosen, chosen)
        idx=self.printer.findData(chosen)
        self.printer.setCurrentIndex(idx if idx>=0 else 0)
        self.park_status.setText("")
    def _parking_payload(self):
        name=self.printer.currentData() or ""
        return {
            "receipt_required_before_open": self.receipt.isChecked(),
            "receipt_policy": self.policy.currentData() or self.policy.currentText(),
            "exit_requires_payment": self.pay.isChecked(),
            "kiosk_cash_enabled": self.kiosk_cash.isChecked(),
            "payment_exit_grace_seconds": self.grace.value(),
            "passage_timeout_seconds": self.passage.value(),
            "stranded_entry_minutes": self.stranded.value(),
            "pay_prompt": self.prompt.text().strip(),
            "printer_adapter": "system" if name else "simulated",
            "printer_name": name,
        }
    def save_parking(self):
        payload=self._parking_payload()
        self.park_status.setText("Saving…")
        def done(_saved):
            self.park_status.setText("Saved. Entry prints a thermal ticket on that printer, then the gate opens."
                                     if payload["printer_name"] else "Saved. Receipts are stored as files until you pick a printer.")
            show_status(self, "Parking rules saved.")
        run_task(self, lambda: api.patch("/settings/parking", payload), done, buttons=self.park_save, busy_text="Saving…",
                 on_error=lambda message, _e: self.park_status.setText(message))
    def test_printer(self):
        payload=self._parking_payload()
        self.park_status.setText("Saving and printing a test ticket…")
        def send():
            api.patch("/settings/parking", payload)
            return api.post("/printers/test", {}, timeout=20)
        run_task(self, send, lambda result: self.park_status.setText(str((result or {}).get("message") or "Test ticket sent.")),
                 buttons=self.park_test, busy_text="Printing…", on_error=lambda message, _e: self.park_status.setText(message))

    # ------------------------------------------------------------ payments --
    def load_payments(self):
        self.pay_status.setText("Loading mobile money settings…")
        run_task(self, lambda: api.get("/settings/payments"), self._show_payments, buttons=self.pay_reload, busy_text="Loading…",
                 on_error=lambda message, _e: self.pay_status.setText(message))
    def _show_payments(self, data):
        data=data or {}
        SettingsPage._set_combo(self.mm_provider, data.get("payments_mobile_provider") or "simulated")
        self.cp_client.setText(str(data.get("clickpesa_client_id") or ""))
        self.cp_key.clear(); self.cp_checksum.clear()
        self.cp_key.setPlaceholderText("Saved — leave empty to keep" if data.get("clickpesa_api_key_set") else "Not set")
        self.cp_checksum.setPlaceholderText("Saved — leave empty to keep" if data.get("clickpesa_checksum_key_set") else "Not set")
        self.cp_url.setText(str(data.get("clickpesa_base_url") or ""))
        self.cp_live.setChecked(bool(data.get("clickpesa_live_enabled")))
        self.cp_confirm.setChecked(bool(data.get("payments_live_provider_confirmed")))
        mode={"UNCONFIGURED": "not set up", "MOCK": "test server (no real money)", "LIVE": "LIVE — real money",
              "LIVE_DISABLED": "keys saved, real collection switched off"}.get(str(data.get("mode") or ""), str(data.get("mode") or "—"))
        lines=[f"ClickPesa: {mode}."]
        if data.get("reason"):
            lines.append(str(data.get("reason")))
        overridden=data.get("overridden_by_environment") or []
        if overridden:
            lines.append("Note: these are also set in the Site Server's system environment, which wins after a restart: "
                         + ", ".join(overridden))
        self.pay_status.setText("\n".join(lines))
    def save_payments(self):
        payload={
            "payments_mobile_provider": self.mm_provider.currentData() or "simulated",
            "clickpesa_client_id": self.cp_client.text().strip(),
            "clickpesa_base_url": self.cp_url.text().strip(),
            "clickpesa_live_enabled": self.cp_live.isChecked(),
            "payments_live_provider_confirmed": self.cp_confirm.isChecked(),
        }
        if self.cp_key.text().strip():
            payload["clickpesa_api_key"]=self.cp_key.text().strip()
        if self.cp_checksum.text().strip():
            payload["clickpesa_checksum_key"]=self.cp_checksum.text().strip()
        if payload["clickpesa_live_enabled"] and payload["payments_live_provider_confirmed"]:
            if QMessageBox.question(self, "Real money",
                                    "Drivers will be charged real money through ClickPesa. Continue?") != QMessageBox.StandardButton.Yes:
                return
        self.pay_status.setText("Saving…")
        def done(data):
            self._show_payments(data)
            show_status(self, "Mobile money settings saved.")
        run_task(self, lambda: api.patch("/settings/payments", payload), done, buttons=self.pay_save, busy_text="Saving…",
                 on_error=lambda message, _e: self.pay_status.setText(message))

    # -------------------------------------------------------------- alerts --
    def load_recognition(self):
        self.rec_status.setText("Loading…")
        run_task(self, lambda: api.get("/settings/recognition"), self._show_recognition,
                 on_error=lambda message, _e: self.rec_status.setText(message))
    def _show_recognition(self, data):
        data=data or {}
        self._set_combo(self.rec_trigger, data.get("capture_trigger") or "zirp")
        self.rec_limit.setChecked(bool(data.get("read_budget_enabled", True)))
        self.rec_confident.setValue(float(data.get("read_budget_confident") or 0.90))
        self.rec_quiet.setValue(float(data.get("read_budget_quiet_seconds") or 4.0))
        self.rec_max.setValue(float(data.get("read_budget_max_seconds") or 20.0))
        self._set_combo(self.rec_photo, data.get("public_receipt_photo") or "off")
        for w in (self.rec_confident, self.rec_quiet, self.rec_max):
            w.setEnabled(self.rec_limit.isChecked())
        self.rec_status.setText("")
    def save_recognition(self):
        payload={"capture_trigger": self.rec_trigger.currentData(),
                 "read_budget_enabled": self.rec_limit.isChecked(),
                 "read_budget_confident": round(self.rec_confident.value(), 2),
                 "read_budget_quiet_seconds": self.rec_quiet.value(),
                 "read_budget_max_seconds": self.rec_max.value(),
                 "public_receipt_photo": self.rec_photo.currentData()}
        self.rec_status.setText("Saving…")
        def done(data):
            self._show_recognition(data)
            show_status(self, "Recognition settings saved.")
        run_task(self, lambda: api.patch("/settings/recognition", payload), done, buttons=self.rec_save, busy_text="Saving…",
                 on_error=lambda message, _e: self.rec_status.setText(message))
    def load_alerts(self):
        self.al_status.setText("Loading alerts…")
        run_task(self, lambda: api.get("/settings/alerts"), self._show_alerts,
                 on_error=lambda message, _e: self.al_status.setText(message))
    def _show_alerts(self, data):
        data=data or {}
        self.al_enabled.setChecked(bool(data.get("enabled")))
        self.al_zero.setChecked(bool(data.get("notify_zero_fee")))
        self.al_failed.setChecked(bool(data.get("notify_failed_commands")))
        lines=[", ".join(x for x in (r.get("channel") or "", r.get("to") or "", r.get("name") or "") if x)
               for r in data.get("recipients") or []]
        self.al_recipients.setPlainText("\n".join(lines))
        providers=data.get("providers") or {}
        def _ready(row):
            # The server reports either {"sms": True} or {"sms": {"configured": True}}.
            if isinstance(row, dict):
                return bool(row.get("configured") or row.get("ok"))
            return bool(row)
        ready=[name for name, row in providers.items() if _ready(row)] if isinstance(providers, dict) else []
        self.al_status.setText(f"Channels ready on the Site Server: {', '.join(ready)}." if ready else "")
    def _alert_recipients(self):
        recipients=[]
        for number, line in enumerate(self.al_recipients.toPlainText().splitlines(), 1):
            if not line.strip():
                continue
            parts=[part.strip() for part in line.split(",")]
            if len(parts) < 2:
                raise ValueError(f"Line {number}: write channel, address (for example: sms, +255700000000)")
            recipients.append({"channel": parts[0].lower(), "to": parts[1], "name": ", ".join(parts[2:])})
        return recipients
    def save_alerts(self):
        try:
            recipients=self._alert_recipients()
        except ValueError as exc:
            self.al_status.setText(str(exc)); return
        payload={"enabled": self.al_enabled.isChecked(), "notify_zero_fee": self.al_zero.isChecked(),
                 "notify_failed_commands": self.al_failed.isChecked(), "recipients": recipients}
        self.al_status.setText("Saving…")
        def done(data):
            self._show_alerts(data)
            show_status(self, "Alert settings saved.")
        run_task(self, lambda: api.put("/settings/alerts", payload), done, buttons=self.al_save, busy_text="Saving…",
                 on_error=lambda message, _e: self.al_status.setText(message))
    def test_alert(self):
        try:
            recipients=self._alert_recipients()
        except ValueError as exc:
            self.al_status.setText(str(exc)); return
        if not recipients:
            self.al_status.setText("Add a recipient first."); return
        first=recipients[0]
        self.al_status.setText(f"Sending a test to {first['to']}…")
        run_task(self, lambda: api.post("/settings/alerts/test", {"channel": first["channel"], "to": first["to"]}, timeout=30),
                 lambda result: self.al_status.setText(str((result or {}).get("message") or (result or {}).get("status") or "Test sent.")),
                 buttons=self.al_test, busy_text="Sending…", on_error=lambda message, _e: self.al_status.setText(message))

    # ----------------------------------------------------------- developer --
    def load_developer(self):
        run_task(self, lambda: api.get("/developer/settings"), self._show_developer,
                 on_error=lambda message, _e: self.dev_status.setText(message))
    def _show_developer(self, data):
        data=data or {}
        for key, box in self.dev_boxes.items():
            box.setChecked(bool(data.get(key)))
        self.dev_status.setText("")
    def save_developer(self):
        payload={key: box.isChecked() for key, box in self.dev_boxes.items()}
        self.dev_status.setText("Saving…")
        def done(data):
            self._show_developer(data)
            self.dev_status.setText("Saved.")
            show_status(self, "Developer controls saved.")
        run_task(self, lambda: api.patch("/developer/settings", payload), done, buttons=self.dev_save, busy_text="Saving…",
                 on_error=lambda message, _e: self.dev_status.setText(message))

    def open_web(self):
        import webbrowser
        webbrowser.open(api.base_url + "/")


class CalibrationPage(SettingsPage):
    """Camera calibration on its own page.

    An Edge Node signs in with the Processing Node account: it may manage its
    cameras (cameras.manage) but has no site settings, so the Settings page,
    and with it the calibration tab, never appeared there. The node is also
    the only computer that has the live picture and plate boxes of its
    cameras (the Site Server hands those cameras over to it), so this is where
    they must be calibrated.
    """

    def __init__(self, window):
        QWidget.__init__(self)
        self.window = window
        layout = QVBoxLayout(self)
        title = QLabel("Camera calibration")
        title.setStyleSheet("font-size:24px;font-weight:700")
        layout.addWidget(title)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self._build_calibration()

    def showEvent(self, event):
        QWidget.showEvent(self, event)
        if not hasattr(api, "base_url"):
            return
        if not getattr(self, "_loaded", False):
            self._loaded = True
            self.load_calibration()
