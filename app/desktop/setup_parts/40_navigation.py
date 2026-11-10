from __future__ import annotations

class _SetupNavigationMixin:
    def _node_credentials_visibility(self):
        visible = self.node_radio.isChecked()
        self.node_credentials_box.setVisible(visible)

    def _sync_node_database_host(self):
        """Use the paired Site Server host for PostgreSQL unless overridden."""
        if not self.node_radio.isChecked() or not hasattr(self, "pg_host"):
            return
        try:
            host = urlsplit(self.server_url.text().strip()).hostname or ""
        except ValueError:
            return
        if not host or host.lower() in {"localhost", "127.0.0.1", "::1"}:
            return
        current = self.pg_host.text().strip()
        auto_host = str(getattr(self, "_auto_database_host", "") or "")
        if not current or current.lower() in {"localhost", "127.0.0.1", "::1"} or current == auto_host:
            self.pg_host.setText(host)
            self._auto_database_host = host

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
            self.db_result = preflight(
                db_config,
                initialize=not self.node_radio.isChecked(),
                password=(self.pg_password.text() or None) if not db_config.is_sqlite else None,
                required_tables=NODE_SCHEMA_TABLES if self.node_radio.isChecked() else (),
            )
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

            # The button/page test uses the password currently in the wizard.
            # Windows services do not: they reopen deployment.json and resolve
            # the protected secret from the service data directory. Verify
            # that exact persisted-runtime path before publishing CONFIGURED;
            # otherwise Finish can succeed while the first service start
            # fails with a misleading generic connection error.
            if db_config.engine == POSTGRESQL:
                persisted_result = preflight(
                    db_config,
                    initialize=False,
                    required_tables=NODE_SCHEMA_TABLES if self.node_radio.isChecked() else (),
                )
                if not persisted_result.get("ok"):
                    raise RuntimeError(
                        "PostgreSQL passed the direct test, but the saved service configuration "
                        "could not reopen it. "
                        f"{self._format_preflight(persisted_result)}"
                    )
            candidate["database"] = db_config
            self.saved = save_deployment_config(candidate, state=CONFIGURED)
        except Exception as exc:
            log.exception(
                "Deployment setup failed role=%s database=%s",
                "EDGE_NODE" if self.node_radio.isChecked() else "SITE_SERVER",
                getattr(locals().get("db_config"), "display_name", "unknown"),
            )
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

    @staticmethod
    def _default_node_username() -> str:
        identity = re.sub(r"[^a-z0-9]+", "-", str(settings.node_id or socket.gethostname()).lower()).strip("-")
        return f"node-{identity[:24] or 'local'}"
