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
        self.info=QPlainTextEdit(); self.info.setReadOnly(True); self.info.setVisible(False); l.addWidget(self.info, 1)
        row=QHBoxLayout(); refresh=QPushButton("Refresh"); refresh.clicked.connect(self.refresh)
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
        try:
            live=api.get("/health/live")
        except Exception as e:
            self.state.setText("OFFLINE")
            self.info.setPlainText(str(e))
            return
        state=(live.get("state") or live.get("process", {}).get("state") or "UNKNOWN")
        try:
            data=api.get("/health/details")
        except Exception:
            try:
                data=api.get("/health/ready")
            except Exception as e:
                data={"error": str(e), "live": live}
        self.state.setText(str(data.get("state") or state))
        self.summary.setText(health_sentences(data, live))
        self.info.setPlainText(json.dumps(data, indent=2, default=str))
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
        row.addWidget(b); row.addWidget(a); row.addWidget(m); row.addWidget(d); row.addStretch(); l.addLayout(row)
    def check_alpr(self):
        try:
            data=api.get("/alpr/status")
            self.info.setPlainText(json.dumps(data, indent=2, default=str))
        except Exception as e:
            self.info.setPlainText(str(e))
    def check_media(self):
        try:
            data=api.get("/media/gateway")
            self.info.setPlainText(json.dumps(data, indent=2, default=str))
        except Exception as e:
            self.info.setPlainText(str(e))
    def check_decode(self):
        try:
            data=api.get("/hardware/decode")
            self.info.setPlainText(json.dumps(data, indent=2, default=str))
        except Exception as e:
            self.info.setPlainText(str(e))
    def check(self):
        try:
            data=api.get("/hardware/hvx/info")
            self.info.setPlainText(json.dumps(data, indent=2, default=str))
        except Exception as e:
            self.info.setPlainText(str(e))
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
        disc.clicked.connect(self._discover)
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
        try:
            data = api.runtime_client().get("/cameras/discover?scan_lan=true")
            cams = data.get("cameras") if isinstance(data, dict) else data
            n = len(cams) if isinstance(cams, list) else 0
            self.hw_info.setPlainText(f"{n} camera(s) found.\nOpen Devices to add and connect them.")
        except Exception as e:
            self.hw_info.setPlainText(str(e))

    def _load(self):
        self.err.setText("")
        try:
            self._status = api.get("/onboarding/status")
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
        try:
            api.post("/onboarding/step", self._payload(nxt, skip=skip))
            self._step = nxt
            self._load()
        except Exception as e:
            self.err.setText(str(e))

    def _activate(self):
        self.err.setText("")
        try:
            api.post("/onboarding/step", self._payload(8, activate=True))
            QMessageBox.information(self, "Activated", "Deployment activated. Restart navigation by signing out and back in if needed.")
            self._load()
        except Exception as e:
            self.err.setText(str(e))

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
        refresh.clicked.connect(self.load)
        pack = QPushButton("Apply model pack…")
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
        try:
            rows = api.get("/captures?limit=50") or []
        except Exception as exc:
            self.status.setText(f"Detections could not be loaded. {exc}")
            rows = []
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
        if not is_technician():
            return
        try:
            data = api.get("/recognition/engine")
        except Exception as exc:
            self.card.setText(str(exc))
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
        try:
            result = api.post("/recognition/model-pack", {"directory": folder}, timeout=60)
        except Exception as exc:
            self.status.setText(str(exc))
            return
        self.status.setText(f"Installed to {result.get('installed_to')}. The next car uses the new weights.")
        self.load()

class SettingsPage(QWidget):
    def __init__(self, window):
        super().__init__(); self.window=window; l=QVBoxLayout(self)
        title=QLabel("Settings"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
        form=QFormLayout()
        combo=QComboBox(); combo.addItems(APPEARANCES); combo.setCurrentText(window.appearance)
        combo.currentTextChanged.connect(self.change)
        window.appearanceChanged.connect(lambda name: self._sync_appearance(combo, name))
        form.addRow("Appearance", combo)
        self.timezone=QLineEdit("UTC")
        self.currency=QLineEdit()
        self.language=QComboBox(); self.language.addItems(["en","sw","ar","fr","pt"])
        self.plate_validation=QComboBox(); self.plate_validation.addItems(["NONE","TZ","KE","ZA","AE"])
        self.public_base_url=QLineEdit()
        self.public_base_url.setPlaceholderText("http://smartpark-server:8760")
        form.addRow("Timezone (IANA)", self.timezone)
        form.addRow("Currency (ISO 4217)", self.currency)
        form.addRow("Language", self.language)
        form.addRow("Plate validation", self.plate_validation)
        form.addRow("Public receipt URL (QR scans)", self.public_base_url)
        site_save=QPushButton("Save site locale")
        site_save.clicked.connect(self.save_site)
        form.addRow("", site_save)
        if not (api.can("settings.manage") or api.can("simulation.run")):
            # settings.view users can correct the site clock/display locale,
            # but cannot change fee currency, plate policy, or public QR host.
            for field in (self.currency, self.plate_validation, self.public_base_url):
                field.setEnabled(False)
            self.timezone.setPlaceholderText("Africa/Dar_es_Salaam or UTC")
        self.site_status=QLabel("")
        form.addRow("", self.site_status)
        l.addLayout(form)
        if api.can("simulation.run"):
            park=QLabel("Parking rules (simulation and live plates share this)."); park.setWordWrap(True); l.addWidget(park)
            self.receipt=QCheckBox("Receipt must be taken before the entry barrier opens")
            self.policy=QComboBox(); self.policy.addItems(["REQUIRE_TAKEN_BEFORE_OPEN","PRINT_AND_OPEN","PRINT_OPTIONAL","OFF"])
            self.pay=QCheckBox("Exit stays closed until the session is paid")
            self.prompt=QLineEdit()
            self.printer=QComboBox(); self.printer.setEditable(False)
            printer_note=QLabel("Thermal receipt printer (58 mm / 80 mm USB roll): plug it in, pick it here, Save. A detected car prints a ticket, then the gate opens.")
            printer_note.setWordWrap(True)
            l.addWidget(self.receipt); pf=QFormLayout(); pf.addRow("Receipt policy", self.policy); pf.addRow("Pay prompt", self.prompt); pf.addRow("Thermal receipt printer", self.printer); l.addLayout(pf)
            l.addWidget(self.pay); l.addWidget(printer_note)
            row=QHBoxLayout()
            save=QPushButton("Save parking rules"); save.clicked.connect(self.save_parking)
            test=QPushButton("Print test ticket"); test.clicked.connect(self.test_printer)
            row.addWidget(save); row.addWidget(test); row.addStretch(); l.addLayout(row)
            self.park_status=QLabel(""); self.park_status.setWordWrap(True); l.addWidget(self.park_status)
        web=QPushButton("Open web UI"); web.clicked.connect(self.open_web); l.addWidget(web)
        l.addStretch()
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
            if api.can("simulation.run"):
                self.load_parking()
    def load_site(self):
        try:
            data=api.get("/settings/site")
            clock=api.get("/settings/clock")
        except Exception as e:
            self.site_status.setText(str(e)); return
        self.timezone.setText(str(data.get("timezone") or "UTC"))
        self.currency.setText(str(data.get("currency") or ""))
        self.public_base_url.setText(str(data.get("public_base_url") or ""))
        idx=self.language.findText(str(data.get("language") or "en"))
        if idx>=0: self.language.setCurrentIndex(idx)
        idx=self.plate_validation.findText(str(data.get("plate_validation") or "NONE"))
        if idx>=0: self.plate_validation.setCurrentIndex(idx)
        self.site_status.setText(
            f"Server clock (UTC): {clock.get('server_time_utc', '—')} · "
            f"Site clock ({clock.get('timezone', data.get('timezone') or 'UTC')}): {clock.get('site_time', '—')}"
        )
    def save_site(self):
        try:
            saved=api.patch("/settings/site",{
                "timezone": self.timezone.text().strip() or "UTC",
                "currency": self.currency.text().strip().upper(),
                "language": self.language.currentText(),
                "plate_validation": self.plate_validation.currentText(),
                "public_base_url": self.public_base_url.text().strip().rstrip("/"),
            })
            self.site_status.setText(f"Saved {saved.get('timezone')} / {saved.get('currency')}")
        except Exception as e:
            self.site_status.setText(str(e))
    def change(self,text): self.window.apply_theme(text)
    def load_parking(self):
        try:
            data=api.get("/settings/parking")
            status=api.get("/printers/status")
        except Exception as e:
            self.park_status.setText(str(e)); return
        self.receipt.setChecked(bool(data.get("receipt_required_before_open")))
        if hasattr(self, "policy"):
            self.policy.setCurrentText(str(data.get("receipt_policy") or "PRINT_AND_OPEN"))
        self.pay.setChecked(bool(data.get("exit_requires_payment")))
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
    def save_parking(self):
        try:
            name=self.printer.currentData() if hasattr(self, "printer") else ""
            saved=api.patch("/settings/parking",{
                "receipt_required_before_open": self.receipt.isChecked(),
                "receipt_policy": self.policy.currentText() if hasattr(self, "policy") else None,
                "exit_requires_payment": self.pay.isChecked(),
                "pay_prompt": self.prompt.text().strip(),
                "printer_adapter": "system" if name else "simulated",
                "printer_name": name or "",
            })
            self.park_status.setText("Saved. Entry prints a thermal ticket on that printer, then the gate opens." if name else "Saved. Receipts are stored as files until you pick a printer.")
            _ = saved
        except Exception as e:
            self.park_status.setText(str(e))
    def test_printer(self):
        try:
            self.save_parking()
            result=api.post("/printers/test", {}, timeout=20)
            self.park_status.setText(str((result or {}).get("message") or result))
        except Exception as e:
            self.park_status.setText(str(e))
    def open_web(self):
        import webbrowser
        webbrowser.open(api.base_url + "/")
