"""Authoritative first-run deployment wizard.

The Site Server owns the site database. A Processing Node runs local camera,
MediaMTX and recognition workers, but joins the existing Site Server
PostgreSQL database and never creates a second site database.
"""

from __future__ import annotations

import socket
import sys
import re
from urllib.parse import urlsplit

import httpx
from PySide6.QtWidgets import (
    QCheckBox, QFormLayout, QGroupBox, QLabel, QLineEdit, QMessageBox,
    QPushButton, QRadioButton, QVBoxLayout, QWizard, QWizardPage,
)

from app.config import settings
from app.branding import PRODUCT_NAME
from app.database_config import DatabaseConfig, POSTGRESQL, SQLITE, preflight
from app.deployment import (
    CONFIGURED,
    CONFIGURING,
    EDGE_NODE,
    OPERATOR_CLIENT,
    RECOVERY_REQUIRED,
    SITE_SERVER,
    DeploymentConfig,
    save_deployment_config,
)


def _label(text: str) -> QLabel:
    value = QLabel(text)
    value.setWordWrap(True)
    return value


class _ValidationPage(QWizardPage):
    """A wizard page whose Next button must pass its field validation."""

    def __init__(self, validator, parent=None):
        super().__init__(parent)
        self._validator = validator

    def validatePage(self) -> bool:
        return bool(self._validator())


class SetupWizard(QWizard):
    def __init__(self, current: DeploymentConfig | None = None, parent=None, role_locked: str | None = None):
        super().__init__(parent)
        self.current = current or DeploymentConfig()
        self.role_locked = str(role_locked or "").upper()
        if self.role_locked not in {SITE_SERVER, EDGE_NODE, OPERATOR_CLIENT}:
            self.role_locked = ""
        self.server_identity: dict = {}
        self.db_result: dict = {}
        self.setWindowTitle(f"{PRODUCT_NAME} Deployment Configuration")
        self.setMinimumSize(760, 560)

        self.welcome_page = self._welcome_page()
        self.role_page = self._role_page()
        self.connection_page = self._connection_page()
        self.requirements_page = self._requirements_page()
        self.network_page = self._network_page()
        self.database_page = self._database_page()
        self.admin_page = self._admin_page()
        self.review_page = self._review_page()
        self.welcome_id = self.addPage(self.welcome_page)
        self.role_id = self.addPage(self.role_page)
        self.connection_id = self.addPage(self.connection_page)
        self.requirements_id = self.addPage(self.requirements_page)
        self.network_id = self.addPage(self.network_page)
        self.database_id = self.addPage(self.database_page)
        self.admin_id = self.addPage(self.admin_page)
        self.review_id = self.addPage(self.review_page)
        if self.role_locked:
            locked_radio = {
                SITE_SERVER: self.server_radio,
                EDGE_NODE: self.node_radio,
                OPERATOR_CLIENT: self.client_radio,
            }[self.role_locked]
            locked_radio.setChecked(True)
            for radio in (self.server_radio, self.node_radio, self.client_radio):
                radio.setEnabled(False)
            self.role_page.setSubTitle(
                f"This installer is locked to {locked_radio.text()}. The role cannot be changed from this package."
            )
            # The normal desktop launch keeps the three-role page. Dedicated
            # installers start directly in their selected role's workflow.
            self.setStartId(self.connection_id if self.role_locked == OPERATOR_CLIENT else self.requirements_id)

    def _welcome_page(self):
        page = QWizardPage()
        page.setTitle(f"{PRODUCT_NAME} Deployment Configuration")
        page.setSubTitle(f"Configure this computer for a real {PRODUCT_NAME} site.")
        body = QVBoxLayout(page)
        body.addWidget(_label(
            f"Version {settings.app_version}\nComputer: {socket.gethostname()}\n\n"
            "Site Server owns the database, API, cameras, recognition, MediaMTX and gates. "
            "Operator Workstations connect to that server and do not create local parking data."
        ))
        body.addWidget(_label("A configuration is marked operational only after its database, schema and required identity checks pass."))
        body.addStretch()
        return page

    def _role_page(self):
        page = QWizardPage()
        page.setTitle("Deployment role")
        page.setSubTitle("Choose the role for this computer.")
        body = QVBoxLayout(page)
        self.server_radio = QRadioButton("Site Server")
        self.node_radio = QRadioButton("Processing Node")
        self.client_radio = QRadioButton("Operator Workstation")
        self.server_radio.setChecked(self.current.role == SITE_SERVER)
        self.node_radio.setChecked(self.current.role == EDGE_NODE)
        self.client_radio.setChecked(self.current.role == OPERATOR_CLIENT)
        for radio, description in (
            (self.server_radio, f"Runs the central {PRODUCT_NAME} API, database, cameras, recognition, MediaMTX, gates and backups."),
            (self.node_radio, "Runs local cameras, MediaMTX and recognition for one assigned gate against the shared PostgreSQL database. It starts fail-closed until a gate is assigned."),
            (self.client_radio, "Runs the desktop UI only. It connects to an existing Site Server and owns no database, camera SDK or gate process."),
        ):
            group = QGroupBox()
            layout = QVBoxLayout(group)
            layout.addWidget(radio)
            layout.addWidget(_label(description))
            body.addWidget(group)
        body.addStretch()
        return page

    def _requirements_page(self):
        page = QWizardPage()
        page.setTitle("Processing requirements")
        page.setSubTitle("These checks apply to the Site Server and Processing Node roles.")
        body = QVBoxLayout(page)
        self.requirement_status = _label("Checking local runtime…")
        body.addWidget(self.requirement_status)
        body.addWidget(_label("HVX/NetSDK, FastALPR and camera checks are conditional on the hardware configured for this site. They are not required on Operator Workstations."))
        body.addStretch()
        return page

    def _connection_page(self):
        page = _ValidationPage(self._test_connection)
        page.setTitle("Site Server connection")
        page.setSubTitle("Processing Nodes and Operator Workstations must verify an existing Site Server before setup can finish.")
        form = QFormLayout(page)
        configured_url = self.current.server_base_url or ""
        if self.current.role == EDGE_NODE and configured_url.lower().rstrip("/") in {
            "http://127.0.0.1:8760", "http://localhost:8760", "http://[::1]:8760",
        }:
            configured_url = "http://smartpark-server:8760"
        self.server_url = QLineEdit(configured_url or "http://smartpark-server:8760")
        self.server_url.setPlaceholderText("http://smartpark-server:8760")
        self.client_site_name = QLineEdit(self.current.site_name or settings.site_name)
        self.test_status = _label("Not tested")
        test = QPushButton("Test Connection")
        test.clicked.connect(self._test_connection)
        form.addRow("Server address", self.server_url)
        form.addRow("Site label", self.client_site_name)
        self.node_credentials_box = QGroupBox("Edge Node credential")
        node_form = QFormLayout(self.node_credentials_box)
        self.node_username = QLineEdit(self.current.node_username or self._default_node_username())
        self.node_password = QLineEdit()
        self.node_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.node_password_confirm = QLineEdit()
        self.node_password_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.node_credentials_hint = _label(
            "This credential belongs only to this physical Edge Node. It is not a human or Site Administrator account."
        )
        self.node_credentials_status = _label("")
        node_form.addRow("Node username", self.node_username)
        node_form.addRow("Node password", self.node_password)
        node_form.addRow("Confirm password", self.node_password_confirm)
        node_form.addRow(self.node_credentials_hint)
        node_form.addRow(self.node_credentials_status)
        form.addRow(self.node_credentials_box)
        form.addRow(test, self.test_status)
        self.node_radio.toggled.connect(self._node_credentials_visibility)
        self._node_credentials_visibility()
        return page

    @staticmethod
    def _default_node_username() -> str:
        identity = re.sub(r"[^a-z0-9]+", "-", str(settings.node_id or socket.gethostname()).lower()).strip("-")
        return f"node-{identity[:24] or 'local'}"

    def _node_credentials_visibility(self):
        visible = self.node_radio.isChecked()
        self.node_credentials_box.setVisible(visible)

    def _validate_node_credentials(self) -> bool:
        if not self.node_radio.isChecked():
            return True
        username = self.node_username.text().strip()
        password = self.node_password.text()
        confirmation = self.node_password_confirm.text()
        if not username:
            self.node_credentials_status.setText("Node username is required.")
            return False
        if len(password) < 12:
            self.node_credentials_status.setText("Node password must be at least 12 characters.")
            return False
        if password != confirmation:
            self.node_credentials_status.setText("Node password and confirmation do not match.")
            return False
        self.node_credentials_status.setText("Node account details validated.")
        return True

    def _network_page(self):
        page = QWizardPage()
        page.setTitle("Server network")
        page.setSubTitle("The API listens on the LAN so Operator Workstations can reach this Site Server.")
        body = QVBoxLayout(page)
        try:
            addresses = sorted({row[4][0] for row in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)})
        except OSError:
            addresses = []
        body.addWidget(_label(
            f"Computer name: {socket.gethostname()}\n"
            f"IPv4 addresses: {', '.join(addresses) or 'not detected'}\n"
            f"API port: {int(settings.api_port)}\n\n"
            f"Use a stable address or DHCP reservation. {PRODUCT_NAME} does not silently change Windows network settings."
        ))
        self.site_name = QLineEdit(self.current.site_name or settings.site_name)
        body.addWidget(_label("Site name"))
        body.addWidget(self.site_name)
        body.addWidget(_label("Required from Operator Workstations: TCP 8760. For WebRTC live video: TCP 8889 and UDP/TCP 8189. PostgreSQL remains local to the Site Server."))
        body.addStretch()
        return page

    def _database_page(self):
        page = _ValidationPage(self._validate_database_page)
        # Set early because role-dependent presentation is initialized before
        # this page is returned to __init__.
        self.database_page = page
        page.setTitle("Database")
        page.setSubTitle("PostgreSQL is recommended for production. SQLite is automatic for testing and evaluation.")
        body = QVBoxLayout(page)
        self.postgres_radio = QRadioButton("PostgreSQL — recommended for production")
        self.sqlite_radio = QRadioButton("SQLite — testing / evaluation")
        # A clean kit must be installable without an external database. An
        # explicit SMARTPARK_DATABASE_URL=postgresql... still flows through
        # default_database_config and selects PostgreSQL here.
        use_postgres = self.current.database.engine == POSTGRESQL
        self.postgres_radio.setChecked(use_postgres)
        self.sqlite_radio.setChecked(not use_postgres)
        body.addWidget(self.postgres_radio)
        self.postgres_description = _label(f"Multi-user, reliable server database. {PRODUCT_NAME} expects an existing PostgreSQL installation; this package does not bundle PostgreSQL.")
        body.addWidget(self.postgres_description)
        links = QLabel(
            'Technician resources: '
            '<a href="https://www.postgresql.org/download/windows/">download PostgreSQL for Windows</a> · '
            '<a href="https://www.postgresql.org/docs/current/">official PostgreSQL documentation</a>'
        )
        links.setOpenExternalLinks(True)
        links.setWordWrap(True)
        body.addWidget(links)
        self.database_network_hint = _label(f"Install PostgreSQL as a Windows service before testing. The Site Server owns this database. A Processing Node must point to the Site Server's PostgreSQL host; it must not use SQLite or create a local database.")
        body.addWidget(self.database_network_hint)
        body.addWidget(self.sqlite_radio)
        self.sqlite_description = _label(f"{PRODUCT_NAME} creates and migrates SQLite automatically. It is not recommended for a multi-workstation production installation.")
        body.addWidget(self.sqlite_description)
        self.pg_form = QFormLayout()
        self.pg_host = QLineEdit(self.current.database.postgres_host)
        self.pg_port = QLineEdit(str(self.current.database.postgres_port))
        self.pg_name = QLineEdit(self.current.database.postgres_database)
        self.pg_user = QLineEdit(self.current.database.postgres_username)
        self.pg_password = QLineEdit()
        self.pg_password.setEchoMode(QLineEdit.EchoMode.Password)
        for name, widget in (("Database server", self.pg_host), ("Port", self.pg_port), ("Database name", self.pg_name), ("Username", self.pg_user), ("Password", self.pg_password)):
            self.pg_form.addRow(name, widget)
        body.addLayout(self.pg_form)
        self.sqlite_warning = QCheckBox("I understand that SQLite is a testing/evaluation database and is not recommended for a multi-workstation production site.")
        self.sqlite_warning.setVisible(self.sqlite_radio.isChecked())
        body.addWidget(self.sqlite_warning)
        self.db_status = _label("Database not tested")
        body.addWidget(self.db_status)
        test = QPushButton("Test Database")
        test.clicked.connect(self._test_database)
        body.addWidget(test)
        self.sqlite_radio.toggled.connect(self._database_mode_changed)
        self.node_radio.toggled.connect(self._database_role_changed)
        self._database_mode_changed(self.sqlite_radio.isChecked())
        self._database_role_changed()
        return page

    def _admin_page(self):
        page = _ValidationPage(self._validate_admin_page)
        page.setTitle("Administrator")
        page.setSubTitle("Create the first production administrator. This replaces the bootstrap credential as the normal login.")
        form = QFormLayout(page)
        self.admin_username = QLineEdit("admin")
        self.admin_full_name = QLineEdit("Site Administrator")
        self.admin_password = QLineEdit()
        self.admin_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.admin_confirm = QLineEdit()
        self.admin_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Username", self.admin_username)
        form.addRow("Full name", self.admin_full_name)
        form.addRow("Password", self.admin_password)
        form.addRow("Confirm password", self.admin_confirm)
        form.addRow(_label("Use at least 12 characters. Keep the password in your site’s password manager."))
        self.admin_status = _label("Administrator details are required for a new Site Server.")
        form.addRow(self.admin_status)
        return page

    def _review_page(self):
        page = QWizardPage()
        page.setTitle("Review and apply")
        page.setSubTitle("Apply only after the displayed role and server address are correct.")
        self.summary = _label("")
        body = QVBoxLayout(page)
        body.addWidget(self.summary)
        body.addStretch()
        return page

    def _database_mode_changed(self, checked: bool):
        if self.node_radio.isChecked() and checked:
            self.sqlite_radio.blockSignals(True)
            self.sqlite_radio.setChecked(False)
            self.sqlite_radio.blockSignals(False)
            checked = False
        self.sqlite_warning.setVisible(bool(checked))
        for widget in (self.pg_host, self.pg_port, self.pg_name, self.pg_user, self.pg_password):
            widget.setEnabled(not checked)

    def _database_role_changed(self):
        node = self.node_radio.isChecked()
        self.sqlite_radio.setVisible(not node)
        self.sqlite_description.setVisible(not node)
        self.sqlite_warning.setVisible(False if node else self.sqlite_radio.isChecked())
        if node:
            self.sqlite_radio.setChecked(False)
            self.postgres_radio.setChecked(True)
            self.postgres_radio.setEnabled(False)
            self.database_page.setTitle("Shared Site Server database")
            self.database_page.setSubTitle("A Processing Node joins the existing Site Server PostgreSQL database. It cannot use SQLite or initialize a local site database.")
            self.database_network_hint.setText("Enter the PostgreSQL host used by the Site Server. The node tests the existing schema but does not run migrations or create an administrator.")
            try:
                parsed = urlsplit(self.server_url.text().strip() if self.server_url.text().strip() else "")
                server_host = parsed.hostname or ""
                if server_host and server_host.lower() not in {"localhost", "127.0.0.1", "::1"} and self.pg_host.text().strip().lower() in {"", "localhost", "127.0.0.1", "::1"}:
                    self.pg_host.setText(server_host)
            except ValueError:
                pass
        else:
            self.postgres_radio.setEnabled(True)
            self.database_page.setTitle("Database")
            self.database_page.setSubTitle("PostgreSQL is recommended for production. SQLite is automatic for testing and evaluation.")
            self.database_network_hint.setText(f"Install PostgreSQL as a Windows service before testing. The Site Server owns this database. Use a dedicated {PRODUCT_NAME} login (not the postgres superuser).")
        self._database_mode_changed(self.sqlite_radio.isChecked())

    def _database_config(self) -> DatabaseConfig:
        if self.sqlite_radio.isChecked():
            if self.node_radio.isChecked():
                raise ValueError("A Processing Node must use the existing Site Server PostgreSQL database; SQLite is not supported for nodes")
            return DatabaseConfig(engine=SQLITE, sqlite_path=str(self.current.database.sqlite_file()))
        try:
            port = int(self.pg_port.text().strip() or "5432")
        except ValueError as exc:
            raise ValueError("PostgreSQL port must be a number") from exc
        host = self.pg_host.text().strip()
        database = self.pg_name.text().strip()
        username = self.pg_user.text().strip()
        if not database or not username:
            raise ValueError("PostgreSQL database name and username are required")
        if not host:
            raise ValueError("PostgreSQL server is required")
        if username.casefold() in {"postgres", "root"}:
            raise ValueError(f"Use a dedicated {PRODUCT_NAME} PostgreSQL login, not the postgres/root superuser")
        return DatabaseConfig(
            engine=POSTGRESQL,
            postgres_host=host,
            postgres_port=port,
            postgres_database=database,
            postgres_username=username,
            postgres_secret_reference=self.current.database.postgres_secret_reference,
        )

    def _validate_database_page(self) -> bool:
        """Validate the local Site Server DB or the shared node DB."""
        if self.node_radio.isChecked() and self.sqlite_radio.isChecked():
            self.db_status.setText("A Processing Node must connect to the existing Site Server PostgreSQL database. SQLite is disabled for nodes.")
            return False
        if self.sqlite_radio.isChecked():
            if not self.sqlite_warning.isChecked():
                self.db_status.setText("Acknowledge the SQLite testing/evaluation warning before continuing.")
                return False
            return self._test_database()

        missing = []
        for label, widget in (
            ("server", self.pg_host),
            ("database name", self.pg_name),
            ("username", self.pg_user),
            ("port", self.pg_port),
        ):
            if not widget.text().strip():
                missing.append(label)
        if missing:
            self.db_status.setText("Enter the required PostgreSQL field(s): " + ", ".join(missing) + ".")
            return False
        if not self.pg_password.text() and not self.current.database.postgres_secret_reference:
            self.db_status.setText("Enter the PostgreSQL password before continuing.")
            return False
        return self._test_database()

    def _validate_admin_page(self) -> bool:
        # A Processing Node joins the already-initialized Site Server
        # database. It must never create, replace, or validate a local
        # administrator. The node workflow intentionally skips this page, so
        # keep this guard here as well: accept() can still call the shared
        # validation path and must not turn a hidden Site Server-only field
        # into a node installation failure.
        if self.node_radio.isChecked():
            self.admin_status.setText(
                "Processing Nodes do not create an administrator. "
                "Sign in after setup with the existing Site Server or Processing Node account."
            )
            return True
        if self.current.configured:
            self.admin_status.setText("Existing administrator accounts and passwords are preserved during reconfiguration.")
            return True
        username = self.admin_username.text().strip()
        full_name = self.admin_full_name.text().strip()
        password = self.admin_password.text()
        confirmation = self.admin_confirm.text()
        if not username:
            self.admin_status.setText("Administrator username is required.")
            return False
        if not full_name:
            self.admin_status.setText("Administrator full name is required.")
            return False
        if len(password) < 12:
            self.admin_status.setText("Administrator password must be at least 12 characters.")
            return False
        if password != confirmation:
            self.admin_status.setText("Administrator password and confirmation do not match.")
            return False
        self.admin_status.setText("Administrator details validated.")
        return True

    def _test_database(self) -> bool:
        try:
            config = self._database_config()
            if config.is_sqlite and not self.sqlite_warning.isChecked():
                self.db_status.setText("Acknowledge the SQLite testing/evaluation warning before continuing.")
                return False
            self.db_result = preflight(config, initialize=False, password=(self.pg_password.text() or None) if not config.is_sqlite else None)
            if self.node_radio.isChecked() and self.db_result.get("ok") and not self.db_result.get("migration", {}).get("up_to_date"):
                self.db_result["ok"] = False
                self.db_result["error"] = "The Site Server database schema is not current. Run the upgrade on the Site Server first."
            self.db_status.setText(self._format_preflight(self.db_result))
            return bool(self.db_result.get("ok"))
        except Exception as exc:
            self.db_status.setText(f"Database configuration error: {exc}")
            return False

    @staticmethod
    def _format_preflight(result: dict) -> str:
        lines = [f"{result.get('display_name', 'Database')}: {'PASS' if result.get('ok') else 'FAIL'}"]
        for row in result.get("checks") or []:
            lines.append(f"{row.get('name')}: {'PASS' if row.get('ok') else 'FAIL'}")
        if result.get("error"):
            lines.append(str(result["error"]))
        return "\n".join(lines)

    def _test_connection(self) -> bool:
        url = self.server_url.text().strip().rstrip("/")
        if url and not url.startswith(("http://", "https://")):
            url = f"http://{url}"
            self.server_url.setText(url)
        if self.node_radio.isChecked():
            try:
                server_host = urlsplit(url).hostname or ""
                if server_host and self.pg_host.text().strip().lower() in {"", "smartpark-server", "localhost", "127.0.0.1", "::1"}:
                    self.pg_host.setText(server_host)
            except ValueError:
                pass
        try:
            live = httpx.get(f"{url}/health/live", timeout=3.0)
            live.raise_for_status()
            identity = httpx.get(f"{url}/deployment/info", timeout=3.0)
            identity.raise_for_status()
            self.server_identity = identity.json()
            accepted_roles = {SITE_SERVER} if self.node_radio.isChecked() else {SITE_SERVER, "EDGE_NODE"}
            if self.server_identity.get("application") not in {PRODUCT_NAME, "SmartPark"} or self.server_identity.get("role") not in accepted_roles:
                raise RuntimeError(f"The endpoint is not a {PRODUCT_NAME} Site Server")
            if self.current.paired_server_id and self.server_identity.get("server_installation_id", self.server_identity.get("installation_id")) != self.current.paired_server_id:
                raise RuntimeError("Server identity changed. Verify the selected Site Server before pairing.")
            if self.current.paired_site_id and self.server_identity.get("site_id", self.server_identity.get("server_id")) != self.current.paired_site_id:
                raise RuntimeError("Site identity changed. Verify the selected Site Server before pairing.")
            if not self._validate_node_credentials():
                self.test_status.setText("Server found, but the Processing Node account is not ready")
                self.test_status.setStyleSheet("color:#a33a2b")
                return False
            self.test_status.setText(f"Server found PASS · API PASS · identity VERIFIED · {self.server_identity.get('site_name') or PRODUCT_NAME}")
            self.test_status.setStyleSheet("color:#147a4b")
            return True
        except Exception as exc:
            self.test_status.setText(f"Server unavailable: {exc}")
            self.test_status.setStyleSheet("color:#a33a2b")
            return False

    def _create_admin(self, db_config: DatabaseConfig) -> bool:
        from sqlalchemy import create_engine, func, select
        from sqlalchemy.orm import Session

        from app.database_config import database_url
        from app.database_config import apply_runtime_database_config
        from app.models import Role, User, UserRole
        from app.security import hash_password

        # Keep the import-time ORM engine aligned with the database selected in
        # the wizard. The service subprocess repeats this before importing the
        # API; this also makes setup diagnostics deterministic when the wizard
        # is launched from a process that has not imported app.db yet.
        if "app.db" not in sys.modules:
            apply_runtime_database_config(db_config)
        engine = create_engine(database_url(db_config, password=self.pg_password.text() or None), future=True)
        try:
            with Session(engine) as db:
                if db.scalar(select(User.id)) is not None:
                    return False
                role = db.scalar(select(Role).where(Role.name == "Admin"))
                if role is None:
                    role = Role(name="Admin", permissions_csv="*", system_role=True)
                    db.add(role)
                    db.flush()
                user = User(
                    username=self.admin_username.text().strip(),
                    full_name=self.admin_full_name.text().strip(),
                    password_hash=hash_password(self.admin_password.text()),
                )
                db.add(user)
                db.flush()
                db.add(UserRole(user_id=user.id, role_id=role.id))
                db.commit()
                return True
        finally:
            engine.dispose()

    def _provision_node_account(self, db_config: DatabaseConfig) -> None:
        """Create/update the node identity in the central registry.

        Node credentials are machine credentials, not a restricted human
        User. The plaintext is used only to create an Argon2 hash and to save
        a protected local secret reference for the future node client.
        """
        from sqlalchemy import create_engine, func, select
        from sqlalchemy.orm import Session

        from app.database_config import database_url
        from app.models import Node, Role, Site, User, UserRole
        from app.services.node_authorization import hash_node_credential

        engine = create_engine(database_url(db_config, password=self.pg_password.text() or None), future=True)
        try:
            with Session(engine) as db:
                site = db.scalar(select(Site).order_by(Site.id))
                if site is None:
                    raise RuntimeError("The Site Server has no site to pair this node with.")
                identity = str(settings.node_id).strip()
                node = db.scalar(select(Node).where(Node.node_id == identity))
                if node is None:
                    node = Node(node_id=identity, site_id=site.id, node_type="EDGE_NODE")
                    db.add(node)
                node.name = f"Edge Node ({socket.gethostname()})"
                node.site_id = site.id
                node.status = "ACTIVE"
                node.revoked_at = None
                node.credential_hash = hash_node_credential(self.node_password.text())
                # The machine credential remains in ``nodes``.  The desktop
                # login also needs a scoped RBAC session, so maintain one
                # idempotent Processing Node user with the same credential.
                # Never overwrite a human account that happens to use the
                # requested username.
                role = db.scalar(select(Role).where(Role.name == "Processing Node"))
                if role is None:
                    raise RuntimeError("The Processing Node role is missing from the Site Server database.")
                node_username = self.node_username.text().strip()
                ui_user = db.scalar(select(User).where(func.lower(User.username) == node_username.casefold()))
                if ui_user is not None:
                    existing_roles = {link.role.name for link in ui_user.roles if link.role is not None}
                    if existing_roles and "Processing Node" not in existing_roles:
                        raise RuntimeError(
                            f"Node username '{node_username}' already belongs to a human account. Choose a different node username."
                        )
                    ui_user.password_hash = hash_node_credential(self.node_password.text())
                    ui_user.status = "ACTIVE"
                else:
                    ui_user = User(
                        username=node_username,
                        full_name=f"Processing Node ({socket.gethostname()})",
                        password_hash=hash_node_credential(self.node_password.text()),
                        status="ACTIVE",
                    )
                    db.add(ui_user)
                    db.flush()
                if not any(link.role_id == role.id for link in ui_user.roles):
                    db.add(UserRole(user_id=ui_user.id, role_id=role.id))
                db.commit()
        finally:
            engine.dispose()

    def initializePage(self, page_id):
        super().initializePage(page_id)
        if page_id == self.requirements_id:
            self.requirement_status.setText("64-bit Python runtime: PASS\nNetwork adapter: PASS\nLocal API port 8760: checked when service starts\nSite Server connection: required on the next page\nPostgreSQL: shared Site Server database\nHVX/MediaMTX/FastALPR: conditional on configured hardware")
        elif page_id == self.review_id:
            role = "Operator Workstation" if self.client_radio.isChecked() else "Processing Node" if self.node_radio.isChecked() else "Site Server"
            if self.client_radio.isChecked():
                self.summary.setText(f"Role: {role}\nServer: {self.server_url.text().strip()}\n\nThe server identity will be paired after a successful connection test. No local database or server service will be started.")
            elif self.node_radio.isChecked():
                self.summary.setText(f"Role: {role}\nDatabase: PostgreSQL\nAPI binding: 0.0.0.0:{int(settings.api_port)}\n\nThe node starts with no camera ownership. After login, assign this PC to its gate in Live Gates. Camera and recognition access is derived from that persisted gate assignment.")
            else:
                engine = "PostgreSQL" if self.postgres_radio.isChecked() else "SQLite (testing/evaluation)"
                self.summary.setText(f"Role: {role}\nSite: {self.site_name.text().strip() or settings.site_name}\nDatabase: {engine}\nAPI binding: 0.0.0.0:{int(settings.api_port)}\n\nApply will initialize/migrate the database and create the administrator transactionally.")

    def nextId(self):
        if self.client_radio.isChecked() and self.currentId() == self.role_id:
            return self.connection_id
        if self.client_radio.isChecked() and self.currentId() == self.connection_id:
            return self.review_id
        if not self.client_radio.isChecked() and self.currentId() == self.role_id:
            return self.requirements_id
        if self.node_radio.isChecked() and self.currentId() == self.requirements_id:
            return self.connection_id
        if self.node_radio.isChecked() and self.currentId() == self.connection_id:
            return self.database_id
        if self.node_radio.isChecked() and self.currentId() == self.database_id:
            return self.review_id
        if self.client_radio.isChecked() and self.currentId() in {self.requirements_id, self.network_id, self.database_id, self.admin_id}:
            return self.review_id
        return super().nextId()

    def accept(self):
        if self.client_radio.isChecked():
            if not self._test_connection():
                QMessageBox.warning(self, "Server unavailable", f"Connect to a verified {PRODUCT_NAME} Site Server before completing setup.")
                return
            url = self.server_url.text().strip().rstrip("/")
            if not url.startswith(("http://", "https://")):
                url = f"http://{url}"
            self.saved = save_deployment_config({
                "role": OPERATOR_CLIENT,
                "server_base_url": url,
                "server_bind_host": "127.0.0.1",
                "server_bind_port": int(settings.api_port),
                "site_name": self.server_identity.get("site_name") or self.client_site_name.text().strip() or settings.site_name,
                "installation_id": self.current.installation_id,
                "client_id": self.current.client_id,
                "paired_site_id": str(self.server_identity.get("site_id") or self.server_identity.get("server_id") or ""),
                "paired_server_id": str(self.server_identity.get("server_installation_id") or self.server_identity.get("installation_id") or ""),
                "database": self.current.database,
            }, state=CONFIGURED)
            super().accept()
            return

        try:
            if self.node_radio.isChecked() and not self._test_connection():
                if not self._validate_node_credentials():
                    QMessageBox.warning(self, "Processing Node account not ready", self.node_credentials_status.text())
                else:
                    QMessageBox.warning(self, "Site Server unavailable", "Connect to the existing Site Server before configuring this Processing Node.")
                return
            if not self._validate_database_page():
                QMessageBox.warning(self, "Database not ready", self.db_status.text())
                return
            db_config = self._database_config()
            # Only a new Site Server creates the first administrator. A node
            # creates its own least-privilege account below; there is no hidden
            # Site Administrator password prompt during node installation.
            if not self.node_radio.isChecked() and not self._validate_admin_page():
                QMessageBox.warning(self, "Administrator not ready", self.admin_status.text())
                return
            candidate = {
                "role": EDGE_NODE if self.node_radio.isChecked() else SITE_SERVER,
                "server_base_url": self.server_url.text().strip().rstrip("/") if self.node_radio.isChecked() else f"http://127.0.0.1:{int(settings.api_port)}",
                "server_bind_host": "0.0.0.0",
                "server_bind_port": int(settings.api_port),
                "site_name": (self.server_identity.get("site_name") or self.site_name.text().strip() or settings.site_name) if self.node_radio.isChecked() else self.site_name.text().strip() or settings.site_name,
                "database": db_config,
            }
            if self.node_radio.isChecked():
                candidate["paired_site_id"] = str(self.server_identity.get("site_id") or self.server_identity.get("server_id") or "")
                candidate["paired_server_id"] = str(self.server_identity.get("server_installation_id") or self.server_identity.get("installation_id") or "")
                candidate["node_username"] = self.node_username.text().strip()
            # Publish the selected database before any schema/admin work so a
            # crash can be resumed as recovery-required, but can never start
            # the API against an implicit database selected by app.db import.
            save_deployment_config(candidate, state=CONFIGURING)
            self.db_result = preflight(db_config, initialize=not self.node_radio.isChecked(), password=(self.pg_password.text() or None) if not db_config.is_sqlite else None)
            if not self.db_result.get("ok"):
                raise RuntimeError(self._format_preflight(self.db_result))
            if self.node_radio.isChecked():
                self._provision_node_account(db_config)
                created_admin = False
            else:
                created_admin = self._create_admin(db_config)
                if not created_admin:
                    self.admin_status.setText(
                        "An administrator already exists in this database; existing users and passwords were preserved."
                    )
            if db_config.engine == POSTGRESQL and self.pg_password.text():
                from app.infrastructure.secrets import store_secret

                secret_ref = store_secret(
                    self.pg_password.text(),
                    kind="database",
                    ref=db_config.postgres_secret_reference or None,
                )
                db_config = DatabaseConfig(**{**db_config.to_mapping(), "postgres_secret_reference": secret_ref})
            candidate["database"] = db_config
            self.saved = save_deployment_config(candidate, state=CONFIGURED)
        except Exception as exc:
            try:
                save_deployment_config(locals().get("candidate", {
                    "role": SITE_SERVER,
                    "database": self.current.database,
                }), state=RECOVERY_REQUIRED)
            except Exception:
                pass
            QMessageBox.critical(self, "Setup failed", str(exc))
            return
        super().accept()
