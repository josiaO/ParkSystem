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
        self.user.setFocus()
        fit_window_to_screen(self, (420, 420), min_size=(360, 360))
        QTimer.singleShot(0, self._prefill)
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
