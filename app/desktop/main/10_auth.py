from __future__ import annotations

class Login(QDialog):
    def __init__(self):
        super().__init__(); self.setWindowTitle(f"{PRODUCT_NAME} — Sign In")
        self.setMinimumWidth(360); self.setMaximumWidth(460)
        l=QVBoxLayout(self); l.setContentsMargins(28,28,28,28); l.setSpacing(8)
        brand=QLabel(PRODUCT_NAME); brand.setStyleSheet("font-size:18px;font-weight:700;letter-spacing:-0.2px")
        tag=QLabel(PRODUCT_TAGLINE)
        tag.setObjectName("muted")
        title=QLabel("Sign in"); title.setStyleSheet("font-size:22px;font-weight:700;margin-top:10px")
        self.sub=QLabel("Sign in with the first-run admin password shown at setup")
        self.sub.setObjectName("muted"); self.sub.setWordWrap(True)
        self.user=QLineEdit("admin"); self.user.setPlaceholderText("Username")
        self.pwd=QLineEdit(); self.pwd.setPlaceholderText("Password"); self.pwd.setEchoMode(QLineEdit.Password)
        btn=QPushButton("&Sign in"); btn.clicked.connect(self.login); self.sign_btn=btn
        btn.setDefault(True); btn.setProperty("primary", True)
        l.addWidget(brand); l.addWidget(tag); l.addWidget(title); l.addWidget(self.sub)
        l.addSpacing(8)
        l.addWidget(label_for("&Username", self.user)); l.addWidget(self.user)
        l.addWidget(label_for("&Password", self.pwd)); l.addWidget(self.pwd)
        l.addSpacing(6); l.addWidget(btn)
        # Kiosk PCs sign in with a revocable device credential instead of a
        # person's password, so they never log out mid-shift.
        kiosk_btn=QPushButton("Kiosk device…"); kiosk_btn.clicked.connect(self.manage_kiosk_device); self.kiosk_btn=kiosk_btn
        kiosk_btn.setToolTip("Enrol this PC as a kiosk with a device credential from Admin → Kiosk devices.")
        l.addWidget(kiosk_btn)
        self.user.setFocus()
        fit_window_to_screen(self, (420, 420), min_size=(360, 360))
        QTimer.singleShot(0, self._prefill)
        QTimer.singleShot(0, self._kiosk_auto_sign_in)
    def _kiosk_auto_sign_in(self):
        from app.desktop.kiosk_device import enrolled_device_id, load_device
        device = load_device()
        if device is None:
            if enrolled_device_id():
                self.sub.setText("This kiosk's saved credential could not be read. Use Kiosk device… to enrol it again.")
            return
        self.sign_in_kiosk(*device, on_ok=self.accept)
    def sign_in_kiosk(self, device_id: str, credential: str, on_ok=None):
        """Sign in with the kiosk's device credential in the background."""
        self.sub.setText(f"Signing in as kiosk {device_id}…")
        def work():
            from app.desktop.api import configure_desktop_base_url
            configure_desktop_base_url()
            api.login_device(device_id, credential)
        def failed(message, exc):
            text=message
            if getattr(exc, "status_code", None)==401 or "Invalid kiosk" in text:
                text=f"Kiosk device {device_id} was refused (revoked or wrong credential). Ask an administrator, then use Kiosk device… to enrol again."
            self.sub.setText(text)
        run_task(self, work, lambda _r: on_ok() if on_ok else None,
                 buttons=(getattr(self, "sign_btn", None), getattr(self, "kiosk_btn", None)), busy_text=None, on_error=failed)
    def manage_kiosk_device(self):
        from app.desktop.kiosk_device import enrol, enrolled_device_id, forget
        current = enrolled_device_id()
        if current:
            answer = QMessageBox.question(
                self, "Kiosk device",
                f"This PC is enrolled as kiosk {current}.\n\nForget it? Staff will then sign in with their own accounts.",
            )
            if answer == QMessageBox.StandardButton.Yes:
                forget()
                self.sub.setText("Kiosk enrolment removed from this PC.")
            return
        device_id, ok = QInputDialog.getText(self, "Enrol kiosk", "Kiosk device id (from Admin → Kiosk devices):")
        if not ok or not device_id.strip():
            return
        credential, ok = QInputDialog.getText(self, "Enrol kiosk", "Device credential (shown once when it was created):", QLineEdit.Password)
        if not ok or not credential:
            return
        def signed_in():
            try:
                enrol(device_id.strip(), credential)
            except Exception as e:
                QMessageBox.warning(self, "Kiosk enrolment", f"Signed in, but the credential could not be saved on this PC: {e}")
            self.accept()
        self.sign_in_kiosk(device_id.strip(), credential, on_ok=signed_in)
    def _prefill(self):
        def fetch():
            import httpx
            from app.desktop.api import desktop_base_url
            return httpx.get(f"{desktop_base_url()}/auth/setup", timeout=3, trust_env=False).json()
        run_task(self, fetch, self._apply_prefill, on_error=lambda _m, _e: None)
    def _apply_prefill(self, setup):
        try:
            setup=setup or {}
            if self.user.text().strip() not in ("", "admin") or self.pwd.text():
                return  # the operator already started typing
            if setup.get("username"): self.user.setText(setup["username"])
            if setup.get("password"):
                self.pwd.setText(setup["password"])
            else:
                self.pwd.clear()
            if setup.get("hint"): self.sub.setText(setup["hint"])
        except Exception:
            pass
    def login(self):
        def is_connection_failure(exc) -> bool:
            text = str(exc).lower()
            if isinstance(exc, SiteServerUnreachable):
                return not exc.timed_out
            return isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)) or any(
                marker in text for marker in ("winerror 10061", "connection refused", "connecterror")
            )

        username=self.user.text().strip(); password=self.pwd.text()

        def work():
            # Off the UI thread: sign-in can include starting the local Site
            # Service and waiting for it, which takes many seconds.
            from app.desktop.api import configure_desktop_base_url

            try:
                # The wizard may have just replaced deployment.json. Refresh the
                # endpoint immediately before the first authentication request.
                configure_desktop_base_url()
                api.login(username, password)
                return
            except Exception as e:
                if not is_connection_failure(e):
                    raise
            from app.deployment import load_deployment_config
            from app.desktop.launch import ensure_background_services, wait_for_api

            config = load_deployment_config()
            if config.runs_local_gate_runtime:
                # Safe to call again: the launcher verifies the API
                # health endpoint and uses the Site Service lock.
                ensure_background_services(config=config)
            else:
                wait_for_api(timeout=20.0, base_url=api.base_url)
            configure_desktop_base_url()
            api.login(username, password)

        self.sub.setText("Signing in…")
        run_task(self, work, lambda _r: self.accept(), buttons=(self.sign_btn, getattr(self, "kiosk_btn", None)),
                 busy_text="Signing in…", on_error=lambda message, exc: self._login_failed(exc, message))

    def _login_failed(self, e, message=""):
        text=message or str(e)
        if getattr(e, "status_code", None)==401 or "401" in text or "Invalid username" in text:
            try:
                from app.deployment import EDGE_NODE, load_deployment_config
                edge_node_login = load_deployment_config().role == EDGE_NODE
            except Exception:
                edge_node_login = False
            if edge_node_login and len(self.pwd.text()) >= 12:
                text = (
                    "Invalid Processing Node username or password.\n\n"
                    "Use the node username and password entered in this PC's deployment wizard. "
                    "The Site Server administrator password is intentionally not accepted on an Edge Node. "
                    "If the node was reinstalled, run deployment configuration again to set a new node password."
                )
            elif len(self.pwd.text()) < 12:
                text = (
                    "Authentication failed. The Processing Node password must be at least 12 characters.\n\n"
                    "Enter this Processing Node's configured account password. The Site Server administrator "
                    "password cannot be used here."
                )
            else:
                text = (
                    "Invalid username or password.\n\n"
                    "admin / first-run password only works on a fresh database. "
                    "This PC already has an admin account. "
                    "Reset it with: python -m app.cli reset-admin"
                )
        elif isinstance(e, SiteServerUnreachable) or "Connection" in text or "ConnectError" in text or "8760" in text:
            text = (f"Can't reach the {PRODUCT_NAME} Site Server at {api.base_url}. Check this computer's network "
                    "connection and that the Site Server PC is on, or open deployment configuration.")
        self.sub.setText("Sign in")
        QMessageBox.critical(self,"Sign in failed",text)
