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
        btn=QPushButton("&Sign in"); btn.clicked.connect(self.login)
        btn.setDefault(True); btn.setProperty("primary", True)
        l.addWidget(brand); l.addWidget(tag); l.addWidget(title); l.addWidget(self.sub)
        l.addSpacing(8)
        l.addWidget(label_for("&Username", self.user)); l.addWidget(self.user)
        l.addWidget(label_for("&Password", self.pwd)); l.addWidget(self.pwd)
        l.addSpacing(6); l.addWidget(btn)
        # Kiosk PCs sign in with a revocable device credential instead of a
        # person's password, so they never log out mid-shift.
        kiosk_btn=QPushButton("Kiosk device…"); kiosk_btn.clicked.connect(self.manage_kiosk_device)
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
        if self.sign_in_kiosk(*device):
            self.accept()
    def sign_in_kiosk(self, device_id: str, credential: str) -> bool:
        try:
            from app.desktop.api import configure_desktop_base_url
            configure_desktop_base_url()
            api.login_device(device_id, credential)
            return True
        except Exception as e:
            text=str(e)
            if "401" in text or "Invalid kiosk" in text:
                text=f"Kiosk device {device_id} was refused (revoked or wrong credential). Ask an administrator, then use Kiosk device… to enrol again."
            self.sub.setText(text)
            return False
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
        if not self.sign_in_kiosk(device_id.strip(), credential):
            return
        try:
            enrol(device_id.strip(), credential)
        except Exception as e:
            QMessageBox.warning(self, "Kiosk enrolment", f"Signed in, but the credential could not be saved on this PC: {e}")
        self.accept()
    def _prefill(self):
        try:
            import httpx
            from app.desktop.api import desktop_base_url
            setup=httpx.get(f"{desktop_base_url()}/auth/setup", timeout=3, trust_env=False).json()
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
            return isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)) or any(
                marker in text for marker in ("winerror 10061", "connection refused", "connecterror")
            )

        try:
            # The wizard may have just replaced deployment.json. Refresh the
            # endpoint immediately before the first authentication request.
            from app.desktop.api import configure_desktop_base_url

            configure_desktop_base_url()
            api.login(self.user.text().strip(), self.pwd.text())
            self.accept()
            return
        except Exception as e:
            if is_connection_failure(e):
                try:
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
                    api.login(self.user.text().strip(), self.pwd.text())
                    self.accept()
                    return
                except Exception as retry_error:
                    e = retry_error
            text=str(e)
            if "401" in text or "Invalid username" in text:
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
            elif "Connection" in text or "ConnectError" in text or "8760" in text:
                text = f"Cannot reach the {PRODUCT_NAME} Site Server at {api.base_url}. Check the connection or open deployment configuration."
            QMessageBox.critical(self,"Sign in failed",text)
