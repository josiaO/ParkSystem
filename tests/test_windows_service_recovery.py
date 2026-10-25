import asyncio
import io
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app import api_main, media_service
from app.config import Settings
from app.db import Base
from app.models import Camera
from app.services import mediamtx
from tools.hvx_sdk_host.hvx_sdk import HVXSDK


def test_sqlite_and_environment_paths_do_not_depend_on_service_working_directory(tmp_path, monkeypatch):
    install = tmp_path / "SmartPark Edge"
    install.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setenv("SMARTPARK_HOME", str(install))
    monkeypatch.chdir(install)
    first = Settings(_env_file=None, database_url="sqlite:///site.db").resolved_database_url
    monkeypatch.chdir(other)
    second = Settings(_env_file=None, database_url="sqlite:///site.db").resolved_database_url
    assert first == second == f"sqlite:///{install.as_posix()}/site.db"
    assert Path(Settings.model_config["env_file"]).is_absolute()
    assert Settings(_env_file=None, database_url="sqlite:///:memory:").resolved_database_url == "sqlite:///:memory:"


def test_media_service_waits_for_site_schema_without_creating_another_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'site.db'}")
    factory = sessionmaker(bind=engine)
    config = {"media_gateway_enabled": True, "media_gateway_camera_ids": []}
    running = [False]
    def start():
        running[0] = True
    try:
        with patch("app.db.SessionLocal", factory), \
             patch("app.services.flags.flags", return_value=config), \
             patch.object(mediamtx, "available", return_value=True), \
             patch.object(mediamtx, "running", side_effect=lambda: running[0]), \
             patch.object(mediamtx, "health", return_value={"last_error": ""}), \
             patch.object(mediamtx, "start", side_effect=start) as launch, \
             patch("app.services.mediamtx_sources.sync_camera", return_value={"registered": False}) as sync:
            with pytest.raises(OperationalError):
                media_service._service_step()
            launch.assert_not_called()
            Base.metadata.create_all(engine)
            with factory() as database:
                database.add(Camera(name="Configured entry", ip_address="10.3.0.1", sdk_handle=7))
                database.commit()
            assert media_service._service_step()["state"] == "RUNNING"
            assert media_service._service_step()["state"] == "RUNNING"
            launch.assert_called_once()
            assert sync.call_count == 2
    finally:
        engine.dispose()


def test_media_process_retries_schema_startup_race_instead_of_exiting():
    missing = OperationalError("SELECT cameras", {}, Exception("no such table: cameras"))
    with patch("app.services.logging_setup.configure_logging"), \
         patch("app.services.runtime.install_crash_hooks"), \
         patch("app.services.runtime.set_process_name"), \
         patch("app.services.runtime.acquire_instance_lock", return_value=True), \
         patch.object(media_service, "_service_step", side_effect=[missing, {"state": "RUNNING"}]), \
         patch.object(media_service, "_write_status") as status, \
         patch.object(media_service.time, "sleep", side_effect=[None, KeyboardInterrupt]), \
         patch.object(mediamtx, "stop"):
        assert media_service.main() == 0
    assert [call.args[0]["state"] for call in status.call_args_list] == ["WAITING_FOR_DATABASE", "RUNNING"]


def test_repeated_connect_reuses_native_session_instead_of_leaking_stream_slots():
    sdk = HVXSDK.__new__(HVXSDK)
    sdk._lock = threading.Lock()
    sdk._connection_locks = {}
    sdk._connection_results = {}
    sdk.dll = SimpleNamespace(Net_QueryConnState=Mock(return_value=2))
    sdk._add_and_connect = Mock(side_effect=[{"connected": True, "handle": 7}, {"connected": True, "handle": 8}])
    sdk.disconnect = Mock()
    first = sdk.add_and_connect("10.3.0.1", 30000, 3, "operator", "secret")
    second = sdk.add_and_connect("10.3.0.1", 30000, 3, "operator", "secret")
    assert first["handle"] == second["handle"] == 7
    assert second["reused"]
    sdk._add_and_connect.assert_called_once()
    sdk.disconnect.assert_not_called()
    changed = sdk.add_and_connect("10.3.0.1", 30000, 3, "operator", "new-secret")
    assert changed["handle"] == 8
    sdk.disconnect.assert_called_once_with(7, force=True)


@pytest.mark.parametrize("entry_session", [[], [{"handle": 7, "ip": "10.3.0.2", "state": 2}]])
def test_sdk_host_restart_restores_only_previous_connections_and_checks_ip(tmp_path, entry_session):
    engine = create_engine(f"sqlite:///{tmp_path / 'site.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as database:
        database.add_all([
            Camera(id=1, name="Entry", ip_address="10.3.0.1", sdk_handle=7),
            Camera(id=2, name="Exit", ip_address="10.3.0.2", sdk_handle=8),
            Camera(id=3, name="Not connected by admin", ip_address="10.3.0.3"),
            Camera(id=4, name="Disabled", ip_address="10.3.0.4", sdk_handle=10, enabled=False),
        ])
        database.commit()
    async def restore(camera, database, user, **kwargs):
        assert user is None
        camera.sdk_handle = 9
        database.commit()
    try:
        with patch.object(api_main, "short_session", factory), \
             patch.object(api_main, "_hvx_restore_attempts", {}), \
             patch.object(api_main, "apply_sdk_connect", AsyncMock(side_effect=restore)) as connect:
            asyncio.run(api_main._restore_hvx_sessions({"available": True, "connections": entry_session + [{"handle": 8, "ip": "10.3.0.2"}]}))
            assert connect.await_count == 1
            assert connect.call_args.args[0].id == 1
            asyncio.run(api_main._restore_hvx_sessions({"available": True, "connections": [{"handle": 8, "ip": "10.3.0.2"}, {"handle": 9, "ip": "10.3.0.1"}]}))
            assert connect.await_count == 1
            with factory() as database:
                assert list(database.scalars(select(Camera.sdk_handle).order_by(Camera.id))) == [9, 8, None, 10]
    finally:
        engine.dispose()


def test_sdk_host_restart_restores_only_this_nodes_gate(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'site.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as database:
        database.add_all([
            Camera(id=1, name="Lane 1 entry", ip_address="10.3.0.1", gate_id=1, sdk_handle=7),
            Camera(id=2, name="Lane 2 entry", ip_address="10.3.0.2", gate_id=2, sdk_handle=8),
        ])
        database.commit()

    async def restore(camera, database, user, **kwargs):
        camera.sdk_handle = int(camera.id) + 20
        database.commit()

    from app.config import settings
    try:
        with patch.object(api_main, "short_session", factory), \
             patch.object(api_main, "_hvx_restore_attempts", {}), \
             patch.object(api_main, "apply_sdk_connect", AsyncMock(side_effect=restore)) as connect, \
             patch.object(settings, "deployment_profile", "PRODUCTION"), \
             patch.object(settings, "recognition_gate_id", 2):
            asyncio.run(api_main._restore_hvx_sessions({"available": True, "connections": []}))
            connect.assert_awaited_once()
            assert connect.call_args.args[0].id == 2
    finally:
        engine.dispose()


def test_mediamtx_errors_are_logged_with_credentials_redacted(caplog):
    process = SimpleNamespace(stdout=io.StringIO("ERR cannot open rtsp://operator:camera-secret@10.3.0.1/live\n"))
    mediamtx._read_process_output(process)
    assert "ERR cannot open" in caplog.text
    assert "camera-secret" not in caplog.text
    assert process.stdout.closed
