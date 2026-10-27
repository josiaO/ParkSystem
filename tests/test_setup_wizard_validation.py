import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from app.desktop.setup import SetupWizard
from app.deployment import DeploymentConfig


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_fresh_site_server_defaults_to_postgres_and_requires_password(qapp):
    wizard = SetupWizard(DeploymentConfig())

    assert wizard.postgres_radio.isChecked()
    assert not wizard.sqlite_radio.isChecked()
    assert wizard._validate_database_page() is False
    assert "password" in wizard.db_status.text().lower()


def test_fresh_site_server_requires_administrator_credentials(qapp):
    wizard = SetupWizard(DeploymentConfig())

    assert wizard._validate_admin_page() is False
    assert "password" in wizard.admin_status.text().lower()

    wizard.admin_username.setText("admin")
    wizard.admin_full_name.setText("Site Administrator")
    wizard.admin_password.setText("a-strong-password-123")
    wizard.admin_confirm.setText("a-strong-password-123")
    assert wizard._validate_admin_page() is True
