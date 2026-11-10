from __future__ import annotations

"""Authoritative first-run deployment wizard.

The Site Server owns the site database. A Processing Node runs local camera,
MediaMTX and recognition workers, but joins the existing Site Server
PostgreSQL database and never creates a second site database.
"""

import socket

import sys

import re

import logging

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

log = logging.getLogger("smartpark")

NODE_SCHEMA_TABLES = ("nodes", "node_auth_sessions", "node_gate_assignments")

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
