import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from app.desktop.setup import SetupWizard
from app.deployment import DeploymentConfig
from app.deployment import EDGE_NODE


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_fresh_site_server_defaults_to_sqlite_without_external_database(qapp):
    wizard = SetupWizard(DeploymentConfig())

    assert wizard.sqlite_radio.isChecked()
    assert not wizard.postgres_radio.isChecked()
    assert wizard._validate_database_page() is False
    assert "sqlite" in wizard.db_status.text().lower()

    wizard.sqlite_warning.setChecked(True)
    # The default is now the self-contained path; actual preflight is covered
    # separately because this test's process may not own the real data folder.
    assert wizard._database_config().is_sqlite


def test_fresh_site_server_requires_administrator_credentials(qapp):
    wizard = SetupWizard(DeploymentConfig())

    assert wizard._validate_admin_page() is False
    assert "password" in wizard.admin_status.text().lower()

    wizard.admin_username.setText("admin")
    wizard.admin_full_name.setText("Site Administrator")
    wizard.admin_password.setText("a-strong-password-123")
    wizard.admin_confirm.setText("a-strong-password-123")
    assert wizard._validate_admin_page() is True


def test_node_installer_locks_role_and_skips_role_selection(qapp):
    wizard = SetupWizard(DeploymentConfig(), role_locked=EDGE_NODE)

    assert wizard.startId() == wizard.requirements_id
    assert wizard.node_radio.isChecked()
    assert not wizard.server_radio.isEnabled()
    assert not wizard.client_radio.isEnabled()
    assert wizard.postgres_radio.isChecked()
    assert not wizard.sqlite_radio.isVisible()
    assert wizard._database_config().engine == "POSTGRESQL"


def test_node_does_not_require_hidden_local_administrator_password(qapp):
    wizard = SetupWizard(DeploymentConfig(), role_locked=EDGE_NODE)

    assert wizard._validate_admin_page() is True
    assert "do not create an administrator" in wizard.admin_status.text().lower()


def test_node_wizard_requires_its_own_account_password(qapp):
    wizard = SetupWizard(DeploymentConfig(), role_locked=EDGE_NODE)

    assert not wizard.node_credentials_box.isHidden()
    wizard.node_password.setText("short")
    wizard.node_password_confirm.setText("short")
    assert wizard._validate_node_credentials() is False
    assert "12 characters" in wizard.node_credentials_status.text()

    wizard.node_password.setText("node-password-123")
    wizard.node_password_confirm.setText("node-password-123")
    assert wizard._validate_node_credentials() is True
