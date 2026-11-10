from __future__ import annotations

class _SetupPagesMixin:
    def _review_page(self):
        page = QWizardPage()
        page.setTitle("Review and apply")
        page.setSubTitle("Apply only after the displayed role and server address are correct.")
        self.summary = _label("")
        body = QVBoxLayout(page)
        body.addWidget(self.summary)
        body.addStretch()
        return page

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
        self.server_url.editingFinished.connect(self._sync_node_database_host)
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
