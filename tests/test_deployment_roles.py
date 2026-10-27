from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.deployment import OPERATOR_CLIENT, SITE_SERVER, DeploymentConfig, load_deployment_config, save_deployment_config, server_base_url
from app.desktop import launch


def test_operator_client_config_is_local_metadata_and_round_trips(tmp_path):
    path = tmp_path / "deployment.json"
    config = DeploymentConfig(
        configured=True,
        role=OPERATOR_CLIENT,
        server_base_url="http://smartpark-server:8760/",
        server_bind_port=8760,
        installation_id="site-installation",
        server_id="site-server",
        client_id="operator-1",
        site_name="Rock City",
    )
    with patch("app.deployment.config_path", return_value=path):
        saved = save_deployment_config(config)
        loaded = load_deployment_config()

    assert loaded.role == OPERATOR_CLIENT
    assert loaded.server_base_url == "http://smartpark-server:8760"
    assert server_base_url(loaded) == "http://smartpark-server:8760"
    assert "password" not in path.read_text(encoding="utf-8").lower()
    assert saved.client_id == "operator-1"


def test_operator_client_never_starts_local_pipeline(tmp_path):
    config = DeploymentConfig(
        configured=True,
        role=OPERATOR_CLIENT,
        server_base_url="http://smartpark-server:8760",
        installation_id="site-installation",
        server_id="site-server",
        client_id="operator-1",
    )
    with patch.object(launch, "start_hvx_host") as hvx, \
         patch.object(launch, "start_site_service") as site, \
         patch.object(launch, "start_pipeline_services") as pipeline:
        launch.ensure_background_services(tmp_path, config=config)

    hvx.assert_not_called()
    site.assert_not_called()
    pipeline.assert_not_called()


def test_site_server_role_remains_explicit():
    config = DeploymentConfig(configured=True, role=SITE_SERVER, installation_id="i", server_id="s")
    assert config.is_server
    assert not config.is_operator_client


def test_legacy_site_server_migrates_to_lan_bind(tmp_path):
    legacy_settings = SimpleNamespace(
        data_dir=tmp_path,
        database_url=None,
        api_host="127.0.0.1",
        api_port=8760,
        node_id="legacy-node",
        site_name="Parking Site",
    )
    with patch("app.deployment.settings", legacy_settings), \
         patch.dict("os.environ", {"SMARTPARK_API_HOST": ""}, clear=False):
        (tmp_path / "smartpark.db").touch()
        config = load_deployment_config()

    assert config.is_server
    assert config.server_bind_host == "0.0.0.0"
    assert server_base_url(config) == "http://127.0.0.1:8760"
