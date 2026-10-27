"""Small native first-run deployment wizard.

The wizard owns only local deployment metadata. Cameras, gates, tariffs and
users remain server-side and are not duplicated on operator workstations.
"""

from __future__ import annotations

import socket

import httpx
from PySide6.QtWidgets import (
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QRadioButton, QVBoxLayout, QWizard, QWizardPage,
)

from app.deployment import OPERATOR_CLIENT, SITE_SERVER, DeploymentConfig, save_deployment_config
from app.config import settings


class SetupWizard(QWizard):
    def __init__(self, current: DeploymentConfig | None = None, parent=None):
        super().__init__(parent)
        self.current = current or DeploymentConfig()
        self.server_identity = None
        self.setWindowTitle("SmartPark Setup")
        self.setMinimumSize(680, 460)
        self.role_page = self._role_page()
        self.server_page = self._server_page()
        self.review_page = self._review_page()
        self.addPage(self._welcome_page())
        self.addPage(self.role_page)
        self.addPage(self.server_page)
        self.addPage(self.review_page)

    def _welcome_page(self):
        page = QWizardPage()
        page.setTitle("SmartPark Setup")
        page.setSubTitle("Configure this computer for the parking site.")
        body = QVBoxLayout(page)
        body.addWidget(QLabel(
            f"Version {settings.app_version}\nComputer: {socket.gethostname()}\n\n"
            "This wizard stores deployment identity only. Parking data, cameras, "
            "gates and recognition remain on the Site Server."
        ))
        body.addStretch()
        return page

    def _role_page(self):
        page = QWizardPage()
        page.setTitle("Deployment role")
        page.setSubTitle("Choose how this computer will be used.")
        body = QVBoxLayout(page)
        self.server_radio = QRadioButton("Site Server")
        self.server_radio.setToolTip("Owns the API, database, cameras, recognition and gate services.")
        self.client_radio = QRadioButton("Operator Workstation")
        self.client_radio.setToolTip("Displays and controls the Site Server through authenticated APIs.")
        if self.current.role == OPERATOR_CLIENT:
            self.client_radio.setChecked(True)
        else:
            self.server_radio.setChecked(True)
        for radio, description in (
            (self.server_radio, "Runs the central SmartPark services and manages the site."),
            (self.client_radio, "Connects to an existing Site Server. It does not run cameras, FastALPR or gates."),
        ):
            group = QGroupBox()
            layout = QVBoxLayout(group)
            layout.addWidget(radio)
            note = QLabel(description)
            note.setWordWrap(True)
            note.setStyleSheet("color:#475467")
            layout.addWidget(note)
            body.addWidget(group)
        body.addStretch()
        return page

    def _server_page(self):
        page = QWizardPage()
        page.setTitle("Site Server connection")
        page.setSubTitle("Operator Workstations connect to the existing server; Site Servers use their local API.")
        form = QFormLayout(page)
        self.server_url = QLineEdit(self.current.server_base_url or "http://127.0.0.1:8760")
        self.server_url.setPlaceholderText("http://smartpark-server:8760")
        self.site_name = QLineEdit(self.current.site_name or settings.site_name)
        self.test_status = QLabel("Not tested")
        self.test_status.setWordWrap(True)
        test = QPushButton("Test Connection")
        test.clicked.connect(self._test_connection)
        row = QHBoxLayout()
        row.addWidget(test)
        row.addWidget(self.test_status, 1)
        form.addRow("Server URL", self.server_url)
        form.addRow("Site name", self.site_name)
        form.addRow("Connection", row)
        return page

    def _review_page(self):
        page = QWizardPage()
        page.setTitle("Review configuration")
        page.setSubTitle("Apply this local deployment configuration.")
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout = QVBoxLayout(page)
        layout.addWidget(self.summary)
        layout.addStretch()
        return page

    def _test_connection(self):
        url = self.server_url.text().strip().rstrip("/")
        if url and not url.startswith(("http://", "https://")):
            url = f"http://{url}"
            self.server_url.setText(url)
        try:
            response = httpx.get(f"{url}/health/live", timeout=3.0)
            response.raise_for_status()
            body = response.json()
            identity = httpx.get(f"{url}/deployment/info", timeout=3.0)
            identity.raise_for_status()
            self.server_identity = identity.json()
            if self.server_identity.get("application") != "SmartPark":
                raise RuntimeError("The endpoint is not a SmartPark Site Server")
            # A fresh client has no trusted site identity yet. Its local
            # machine/node id must not be compared with the server's identity
            # during first-run pairing; the server identity is persisted only
            # after the connection has been verified.
            expected = self.current.installation_id if self.current.configured else ""
            actual = str(self.server_identity.get("installation_id") or "")
            if expected and actual and expected != actual:
                raise RuntimeError("Server identity changed. Verify the selected Site Server before pairing.")
            self.test_status.setText(f"Connected · {body.get('state') or body.get('status') or 'ready'} · {self.server_identity.get('site_name') or 'SmartPark'}")
            self.test_status.setStyleSheet("color:#147a4b")
            return True
        except Exception as exc:
            self.test_status.setText(f"Server unavailable: {exc}")
            self.test_status.setStyleSheet("color:#a33a2b")
            return False

    def nextId(self):
        # The connection page is still useful for a Site Server because it
        # records the local API address and site label for later diagnostics.
        return super().nextId()

    def initializePage(self, page_id):
        super().initializePage(page_id)
        if self.page(page_id) is self.review_page:
            role = "Operator Workstation" if self.client_radio.isChecked() else "Site Server"
            endpoint = self.server_url.text().strip().rstrip("/")
            self.summary.setText(
                f"Role: {role}\nSite: {self.site_name.text().strip() or settings.site_name}\n"
                f"Server: {endpoint}\n\n"
                "Operator Workstations will not start local SmartPark services or access the database."
            )

    def accept(self):
        role = OPERATOR_CLIENT if self.client_radio.isChecked() else SITE_SERVER
        try:
            url = self.server_url.text().strip().rstrip("/")
            if role == OPERATOR_CLIENT:
                if not self._test_connection():
                    QMessageBox.warning(self, "Server unavailable", "Connect to a SmartPark Site Server before completing setup.")
                    return
            elif not url:
                url = f"http://127.0.0.1:{int(settings.api_port)}"
            if role == OPERATOR_CLIENT and not url.startswith(("http://", "https://")):
                url = f"http://{url}"
            if role == SITE_SERVER:
                url = f"http://127.0.0.1:{int(settings.api_port)}"
            identity = self.server_identity or {}
            self.saved = save_deployment_config({
                "role": role,
                "server_base_url": url,
                "server_bind_host": "0.0.0.0" if role == SITE_SERVER else "127.0.0.1",
                "server_bind_port": int(settings.api_port),
                "site_name": self.site_name.text().strip() or settings.site_name,
                "installation_id": str(identity.get("installation_id") or self.current.installation_id),
                "server_id": str(identity.get("server_id") or self.current.server_id),
                "client_id": self.current.client_id,
            })
        except Exception as exc:
            QMessageBox.critical(self, "Setup failed", str(exc))
            return
        super().accept()
