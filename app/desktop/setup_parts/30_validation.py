from __future__ import annotations

class _SetupValidationMixin:
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
            parsed = urlsplit(url)
            server_host = parsed.hostname or ""
            server_port = int(parsed.port or (443 if parsed.scheme == "https" else 80))
            if not server_host:
                raise RuntimeError("Enter a valid Site Server host.")
            with socket.create_connection((server_host, server_port), timeout=3.0):
                pass
            live = httpx.get(f"{url}/health/live", timeout=3.0, trust_env=False)
            live.raise_for_status()
            identity = httpx.get(f"{url}/deployment/info", timeout=3.0, trust_env=False)
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

    def _test_database(self) -> bool:
        try:
            config = self._database_config()
            if config.is_sqlite and not self.sqlite_warning.isChecked():
                self.db_status.setText("Acknowledge the SQLite testing/evaluation warning before continuing.")
                return False
            self.db_result = preflight(
                config,
                initialize=False,
                password=(self.pg_password.text() or None) if not config.is_sqlite else None,
                required_tables=NODE_SCHEMA_TABLES if self.node_radio.isChecked() else (),
            )
            if self.node_radio.isChecked() and self.db_result.get("ok") and not self.db_result.get("migration", {}).get("up_to_date"):
                self.db_result["ok"] = False
                self.db_result["error"] = "The Site Server database schema is not current. Run the upgrade on the Site Server first."
            if not self.db_result.get("ok"):
                log.warning(
                    "Deployment database preflight failed role=%s engine=%s error=%s technical=%s checks=%s",
                    "EDGE_NODE" if self.node_radio.isChecked() else "SITE_SERVER",
                    config.engine,
                    self.db_result.get("error", "unknown database preflight failure"),
                    self.db_result.get("technical", ""),
                    self.db_result.get("checks", []),
                )
            self.db_status.setText(self._format_preflight(self.db_result))
            return bool(self.db_result.get("ok"))
        except Exception as exc:
            log.exception("Deployment database test failed role=%s engine=%s", "EDGE_NODE" if self.node_radio.isChecked() else "SITE_SERVER", getattr(locals().get("config"), "engine", "unknown"))
            self.db_status.setText(f"Database configuration error: {exc}")
            return False

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
            self.database_network_hint.setText(
                "Enter the PostgreSQL host used by the Site Server, usually the same LAN address as the Site Server connection. "
                "The Site Server HTTP port and PostgreSQL port are separate: PostgreSQL must listen on the LAN address, allow this node in pg_hba.conf, and allow TCP 5432 through Windows Firewall."
            )
            try:
                parsed = urlsplit(self.server_url.text().strip() if self.server_url.text().strip() else "")
                server_host = parsed.hostname or ""
                if server_host and server_host.lower() not in {"localhost", "127.0.0.1", "::1"} and self.pg_host.text().strip().lower() in {"", "localhost", "127.0.0.1", "::1"}:
                    self.pg_host.setText(server_host)
                    self._auto_database_host = server_host
            except ValueError:
                pass
        else:
            self.postgres_radio.setEnabled(True)
            self.database_page.setTitle("Database")
            self.database_page.setSubTitle("PostgreSQL is recommended for production. SQLite is automatic for testing and evaluation.")
            self.database_network_hint.setText("PostgreSQL is local to the Site Server. Processing Nodes require PostgreSQL LAN listening and Windows Firewall access on TCP 5432; 127.0.0.1 only works on this computer.")
        self._database_mode_changed(self.sqlite_radio.isChecked())

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

    def _database_mode_changed(self, checked: bool):
        if self.node_radio.isChecked() and checked:
            self.sqlite_radio.blockSignals(True)
            self.sqlite_radio.setChecked(False)
            self.sqlite_radio.blockSignals(False)
            checked = False
        self.sqlite_warning.setVisible(bool(checked))
        for widget in (self.pg_host, self.pg_port, self.pg_name, self.pg_user, self.pg_password):
            widget.setEnabled(not checked)

    @staticmethod
    def _format_preflight(result: dict) -> str:
        lines = [f"{result.get('display_name', 'Database')}: {'PASS' if result.get('ok') else 'FAIL'}"]
        for row in result.get("checks") or []:
            lines.append(f"{row.get('name')}: {'PASS' if row.get('ok') else 'FAIL'}")
        if result.get("error"):
            lines.append(str(result["error"]))
        if result.get("technical"):
            lines.append(f"Technical: {result['technical']}")
        return "\n".join(lines)

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
