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


def test_node_server_address_syncs_postgres_host(qapp):
    wizard = SetupWizard(DeploymentConfig(), role_locked=EDGE_NODE)

    wizard.server_url.setText("http://192.168.1.240:8760")
    wizard.server_url.editingFinished.emit()

    assert wizard.pg_host.text() == "192.168.1.240"


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


def test_site_server_wizard_asks_for_the_site_timezone(qapp):
    """Phase 2.2: tariff day/night boundaries depend on the site timezone."""
    wizard = SetupWizard(DeploymentConfig())

    assert wizard.site_timezone.currentText() == "Africa/Dar_es_Salaam"
    assert wizard._validate_timezone() is True
    wizard.site_timezone.setEditText("Mars/Olympus_Mons")
    assert wizard._validate_timezone() is False
    assert "timezone" in wizard.timezone_status.text().lower()
    wizard.site_timezone.setEditText("Africa/Nairobi")
    assert wizard._validate_timezone() is True


def test_wizard_saves_timezone_without_overwriting_a_stored_choice(qapp, tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.database_config import DatabaseConfig
    from app.db import Base
    from app.services.site_policy import save_site_policy, site_policy

    path = tmp_path / "site.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    config = DatabaseConfig(engine="SQLITE", sqlite_path=str(path))

    wizard = SetupWizard(DeploymentConfig())
    wizard._save_site_timezone(config)  # fresh database: the default is stored
    with Session(engine) as db:
        assert site_policy(db)["timezone"] == "Africa/Dar_es_Salaam"
        save_site_policy(db, {"timezone": "Africa/Kampala"})

    wizard = SetupWizard(DeploymentConfig())
    wizard._save_site_timezone(config)  # re-run, picker untouched: keep Kampala
    with Session(engine) as db:
        assert site_policy(db)["timezone"] == "Africa/Kampala"

    wizard.site_timezone.setEditText("Africa/Nairobi")
    wizard._save_site_timezone(config)  # technician chose explicitly
    with Session(engine) as db:
        assert site_policy(db)["timezone"] == "Africa/Nairobi"
    engine.dispose()


def test_desktop_settings_page_round_trips_the_site_timezone(qapp):
    from types import SimpleNamespace
    from unittest.mock import patch

    from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit

    import app.desktop.main as desktop

    sent = {}

    class FakeApi:
        def get(self, path):
            if path == "/settings/clock":
                return {"server_time_utc": "t", "timezone": "Africa/Dar_es_Salaam", "site_time": "t"}
            return {"timezone": "", "currency": "TZS", "language": "en", "plate_validation": "TZ"}

        def patch(self, path, body):
            sent.update(body)
            return body

    language, plates = QComboBox(), QComboBox()
    language.addItems(["en", "sw"])
    plates.addItems(["NONE", "TZ"])
    page = SimpleNamespace(timezone=QLineEdit(), currency=QLineEdit(), public_base_url=QLineEdit(),
                           language=language, plate_validation=plates, site_status=QLabel())
    with patch.object(desktop, "api", FakeApi()):
        desktop.SettingsPage.load_site(page)
        assert page.timezone.text() == "Africa/Dar_es_Salaam"  # server sent none: site default
        page.timezone.setText("")
        desktop.SettingsPage.save_site(page)
    assert sent["timezone"] == "Africa/Dar_es_Salaam"
