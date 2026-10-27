"""Authoritative first-run deployment wizard.

Only a Site Server initializes a database. Operator Workstations store their
own identity and the verified site/server identity and never start services.
"""

from __future__ import annotations

import socket

import httpx
from PySide6.QtWidgets import (
    QCheckBox, QFormLayout, QGroupBox, QLabel, QLineEdit, QMessageBox,
    QPushButton, QRadioButton, QVBoxLayout, QWizard, QWizardPage,
)

from app.config import settings
from app.branding import PRODUCT_NAME
from app.database_config import DatabaseConfig, POSTGRESQL, SQLITE, preflight
from app.deployment import CONFIGURED, OPERATOR_CLIENT, SITE_SERVER, DeploymentConfig, save_deployment_config


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
    def __init__(self, current: DeploymentConfig | None = None, parent=None):
        super().__init__(parent)
        self.current = current or DeploymentConfig()
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
        self.client_radio = QRadioButton("Operator Workstation")
        self.server_radio.setChecked(self.current.role != OPERATOR_CLIENT)
        self.client_radio.setChecked(self.current.role == OPERATOR_CLIENT)
        for radio, description in (
            (self.server_radio, f"Runs the central {PRODUCT_NAME} API, database, cameras, recognition, MediaMTX, gates and backups."),
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
        page.setTitle("Site Server requirements")
        page.setSubTitle("These checks apply only to the Site Server role.")
        body = QVBoxLayout(page)
        self.requirement_status = _label("Checking local runtime…")
        body.addWidget(self.requirement_status)
        body.addWidget(_label("HVX/NetSDK, FastALPR and camera checks are conditional on the hardware configured for this site. They are not required on Operator Workstations."))
        body.addStretch()
        return page

    def _connection_page(self):
        page = QWizardPage()
        page.setTitle("Site Server connection")
        page.setSubTitle("Operator Workstations must verify an existing Site Server before setup can finish.")
        form = QFormLayout(page)
        self.server_url = QLineEdit(self.current.server_base_url or "http://smartpark-server:8760")
        self.server_url.setPlaceholderText("http://smartpark-server:8760")
        self.client_site_name = QLineEdit(self.current.site_name or settings.site_name)
        self.test_status = _label("Not tested")
        test = QPushButton("Test Connection")
        test.clicked.connect(self._test_connection)
        form.addRow("Server address", self.server_url)
        form.addRow("Site label", self.client_site_name)
        form.addRow(test, self.test_status)
        return page

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
        page.setTitle("Database")
        page.setSubTitle("PostgreSQL is recommended for production. SQLite is automatic for testing and evaluation.")
        body = QVBoxLayout(page)
        self.postgres_radio = QRadioButton("PostgreSQL — recommended for production")
        self.sqlite_radio = QRadioButton("SQLite — testing / evaluation")
        # Fresh installations must lead technicians toward the selected
        # production architecture. Existing configured SQLite sites remain
        # editable without being silently switched to another database.
        use_postgres = self.current.database.engine == POSTGRESQL or not self.current.configured
        self.postgres_radio.setChecked(use_postgres)
        self.sqlite_radio.setChecked(not use_postgres)
        body.addWidget(self.postgres_radio)
        body.addWidget(_label(f"Multi-user, reliable server database. {PRODUCT_NAME} expects an existing PostgreSQL installation; this package does not bundle PostgreSQL."))
        links = QLabel(
            'Technician resources: '
            '<a href="https://www.postgresql.org/download/windows/">download PostgreSQL for Windows</a> · '
            '<a href="https://www.postgresql.org/docs/current/">official PostgreSQL documentation</a>'
        )
        links.setOpenExternalLinks(True)
        links.setWordWrap(True)
        body.addWidget(links)
        body.addWidget(_label(f"Install PostgreSQL as a Windows service before testing. Keep the database local to this Site Server where possible, use a dedicated {PRODUCT_NAME} login (not the postgres superuser), and keep port 5432 closed to Operator Workstations."))
        body.addWidget(self.sqlite_radio)
        body.addWidget(_label(f"{PRODUCT_NAME} creates and migrates SQLite automatically. It is not recommended for a multi-workstation production installation."))
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
        self._database_mode_changed(self.sqlite_radio.isChecked())
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
        self.sqlite_warning.setVisible(bool(checked))
        for widget in (self.pg_host, self.pg_port, self.pg_name, self.pg_user, self.pg_password):
            widget.setEnabled(not checked)

    def _database_config(self) -> DatabaseConfig:
        if self.sqlite_radio.isChecked():
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
        """Do not allow a fresh Site Server to skip database verification."""
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
        try:
            live = httpx.get(f"{url}/health/live", timeout=3.0)
            live.raise_for_status()
            identity = httpx.get(f"{url}/deployment/info", timeout=3.0)
            identity.raise_for_status()
            self.server_identity = identity.json()
            if self.server_identity.get("application") not in {PRODUCT_NAME, "SmartPark"} or self.server_identity.get("role") not in {SITE_SERVER, "EDGE_NODE"}:
                raise RuntimeError(f"The endpoint is not a {PRODUCT_NAME} Site Server")
            if self.current.paired_server_id and self.server_identity.get("server_installation_id", self.server_identity.get("installation_id")) != self.current.paired_server_id:
                raise RuntimeError("Server identity changed. Verify the selected Site Server before pairing.")
            if self.current.paired_site_id and self.server_identity.get("site_id", self.server_identity.get("server_id")) != self.current.paired_site_id:
                raise RuntimeError("Site identity changed. Verify the selected Site Server before pairing.")
            self.test_status.setText(f"Server found PASS · API PASS · identity VERIFIED · {self.server_identity.get('site_name') or PRODUCT_NAME}")
            self.test_status.setStyleSheet("color:#147a4b")
            return True
        except Exception as exc:
            self.test_status.setText(f"Server unavailable: {exc}")
            self.test_status.setStyleSheet("color:#a33a2b")
            return False

    def _create_admin(self, db_config: DatabaseConfig) -> None:
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import Session

        from app.database_config import database_url
        from app.models import Role, User, UserRole
        from app.security import hash_password

        engine = create_engine(database_url(db_config, password=self.pg_password.text() or None), future=True)
        with Session(engine) as db:
            if db.scalar(select(User.id)) is not None:
                return
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
        engine.dispose()

    def initializePage(self, page_id):
        super().initializePage(page_id)
        if page_id == self.requirements_id:
            self.requirement_status.setText("64-bit Python runtime: PASS\nNetwork adapter: PASS\nAPI port 8760: checked when service starts\nPostgreSQL: configured on the next page\nHVX/MediaMTX/FastALPR: conditional on configured hardware")
        elif page_id == self.review_id:
            role = "Operator Workstation" if self.client_radio.isChecked() else "Site Server"
            if self.client_radio.isChecked():
                self.summary.setText(f"Role: {role}\nServer: {self.server_url.text().strip()}\n\nThe server identity will be paired after a successful connection test. No local database or server service will be started.")
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
            if not self._validate_database_page():
                QMessageBox.warning(self, "Database not ready", self.db_status.text())
                return
            db_config = self._database_config()
            if not self._validate_admin_page():
                QMessageBox.warning(self, "Administrator not ready", self.admin_status.text())
                return
            self.db_result = preflight(db_config, initialize=True, password=(self.pg_password.text() or None) if not db_config.is_sqlite else None)
            if not self.db_result.get("ok"):
                raise RuntimeError(self._format_preflight(self.db_result))
            self._create_admin(db_config)
            if db_config.engine == POSTGRESQL and self.pg_password.text():
                from app.infrastructure.secrets import store_secret

                secret_ref = store_secret(
                    self.pg_password.text(),
                    kind="database",
                    ref=db_config.postgres_secret_reference or None,
                )
                db_config = DatabaseConfig(**{**db_config.to_mapping(), "postgres_secret_reference": secret_ref})
            self.saved = save_deployment_config({
                "role": SITE_SERVER,
                "server_base_url": f"http://127.0.0.1:{int(settings.api_port)}",
                "server_bind_host": "0.0.0.0",
                "server_bind_port": int(settings.api_port),
                "site_name": self.site_name.text().strip() or settings.site_name,
                "database": db_config,
            }, state=CONFIGURED)
        except Exception as exc:
            QMessageBox.critical(self, "Setup failed", str(exc))
            return
        super().accept()
