from pathlib import Path
from unittest.mock import patch

from app.database_config import DatabaseConfig, POSTGRESQL, SQLITE, preflight
from app.deployment import (
    CONFIGURED, RECOVERY_REQUIRED, SITE_SERVER, DeploymentConfig,
    load_deployment_config, save_deployment_config,
)


def test_sqlite_preflight_initializes_schema_and_reports_head(tmp_path):
    result = preflight(DatabaseConfig(engine=SQLITE, sqlite_path=str(tmp_path / "smartpark.db")), initialize=True)

    assert result["ok"] is True
    assert result["migration"]["up_to_date"] is True
    assert Path(tmp_path / "smartpark.db").is_file()


def test_deployment_state_is_not_marked_configured_for_recovery(tmp_path):
    path = tmp_path / "deployment.json"
    config = DeploymentConfig(role=SITE_SERVER, state=RECOVERY_REQUIRED, configured=False)

    with patch("app.deployment.config_path", return_value=path):
        saved = save_deployment_config(config, state=RECOVERY_REQUIRED)
        loaded = load_deployment_config()

    assert saved.configured is False
    assert loaded.state == RECOVERY_REQUIRED
    assert loaded.configured is False


def test_postgres_config_contains_no_password():
    config = DatabaseConfig(
        engine=POSTGRESQL,
        postgres_host="127.0.0.1",
        postgres_database="smartpark",
        postgres_username="smartpark",
        postgres_secret_reference="database:abc12345",
    )
    assert "password" not in config.to_mapping()
    assert config.postgres_secret_reference.startswith("database:")


def test_blank_postgres_password_reuses_protected_secret():
    from app.database_config import _postgres_password

    config = DatabaseConfig(
        engine=POSTGRESQL,
        postgres_secret_reference="database:abc12345",
    )
    with patch("app.infrastructure.secrets.resolve_secret", return_value="stored-secret") as resolve:
        assert _postgres_password(config, password="") == "stored-secret"
    resolve.assert_called_once_with("database:abc12345")


def test_server_identity_keeps_site_and_installation_identity_distinct():
    from app.deployment import public_server_identity

    identity = public_server_identity(DeploymentConfig(
        configured=True,
        state=CONFIGURED,
        installation_id="server-installation",
        server_id="server-node",
        site_id="site-1",
    ))

    assert identity["server_installation_id"] == "server-installation"
    assert identity["server_id"] == "server-node"
    assert identity["site_id"] == "site-1"
    assert not any("password" in key.lower() or "secret" in key.lower() for key in identity)
