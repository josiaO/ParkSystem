"""Phase 3: the desktop launcher works with real Windows services."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.deployment import DeploymentConfig, SITE_SERVER
from app.desktop import launch


def _config():
    return DeploymentConfig(configured=True, role=SITE_SERVER, installation_id="i", server_id="s")


def test_service_state_parses_sc_query():
    running = SimpleNamespace(returncode=0, stdout="SERVICE_NAME: SmartParkSiteService\n        STATE              : 4  RUNNING\n", stderr="")
    missing = SimpleNamespace(returncode=1060, stdout="[SC] OpenService FAILED 1060:", stderr="")
    with patch.object(launch.os, "name", "nt"), patch.object(launch.subprocess, "run", return_value=running):
        assert launch._windows_service_state("SmartParkSiteService") == "RUNNING"
    with patch.object(launch.os, "name", "nt"), patch.object(launch.subprocess, "run", return_value=missing):
        assert launch._windows_service_state("SmartParkSiteService") is None


def test_services_are_started_in_order_and_no_process_is_spawned(tmp_path):
    states = {"SmartParkSiteService": "STOPPED", "SmartParkMediaService": "STOPPED",
              "SmartParkRecognitionWorker": "RUNNING"}
    started = []
    config = _config()  # built before os.name is patched
    with patch.object(launch.os, "name", "nt"), \
         patch.object(launch, "_windows_service_state", side_effect=lambda name: states.get(name)), \
         patch.object(launch, "_start_windows_service", side_effect=lambda name: started.append(name) or True), \
         patch.object(launch, "_scheduled_task_exists", side_effect=lambda name: name == "SmartPark HVX Host"), \
         patch.object(launch, "_start_scheduled_task", return_value=True) as start_task, \
         patch.object(launch, "wait_for_api") as wait, \
         patch.object(launch, "start_site_service") as spawn_api, \
         patch.object(launch, "start_hvx_host") as spawn_hvx, \
         patch.object(launch, "start_pipeline_services") as spawn_pipeline:
        launch.ensure_background_services(tmp_path, config=config)
    # HVX host stays a logon task until proven in Session 0.
    start_task.assert_called_once_with("SmartPark HVX Host")
    # The worker is already running, so it is left alone.
    assert started == ["SmartParkSiteService", "SmartParkMediaService"]
    wait.assert_called_once()
    spawn_api.assert_not_called()
    spawn_hvx.assert_not_called()
    spawn_pipeline.assert_not_called()


def test_hvx_host_service_is_used_when_installed(tmp_path):
    states = {"SmartParkSiteService": "RUNNING", "SmartParkHvxHost": "STOPPED"}
    started = []
    config = _config()
    with patch.object(launch.os, "name", "nt"), \
         patch.object(launch, "_windows_service_state", side_effect=lambda name: states.get(name)), \
         patch.object(launch, "_start_windows_service", side_effect=lambda name: started.append(name) or True), \
         patch.object(launch, "_scheduled_task_exists", return_value=False), \
         patch.object(launch, "wait_for_api"), \
         patch.object(launch, "start_hvx_host") as spawn_hvx, \
         patch.object(launch, "start_pipeline_services") as pipeline:
        launch.ensure_background_services(tmp_path, config=config)
    assert started[0] == "SmartParkHvxHost"
    spawn_hvx.assert_not_called()
    # Media/worker services are not installed: the desktop runs them itself.
    pipeline.assert_called_once()


def test_service_start_failure_is_reported_not_worked_around(tmp_path):
    config = _config()
    with patch.object(launch.os, "name", "nt"), \
         patch.object(launch, "_windows_service_state", side_effect=lambda name: "STOPPED" if name == "SmartParkSiteService" else None), \
         patch.object(launch, "_start_windows_service", return_value=False), \
         patch.object(launch, "_scheduled_task_exists", return_value=False), \
         patch.object(launch, "start_hvx_host"), \
         patch.object(launch, "_log_dir", return_value=tmp_path), \
         patch.object(launch, "start_site_service") as spawn:
        try:
            launch.ensure_background_services(tmp_path, config=config)
        except RuntimeError as exc:
            assert "SmartParkSiteService" in str(exc) and "services.msc" in str(exc)
        else:
            raise AssertionError("a service that will not start must be reported")
    spawn.assert_not_called()


def test_stop_background_services_stops_windows_services_consumers_first(tmp_path):
    stopped = []
    with patch.object(launch.os, "name", "nt"), \
         patch.object(launch, "_windows_service_state", return_value="RUNNING"), \
         patch.object(launch, "_stop_windows_service", side_effect=lambda name: stopped.append(name)), \
         patch.object(launch, "_end_scheduled_task"), \
         patch.object(launch, "_port_open", return_value=False):
        launch.stop_background_services()
    assert stopped == ["SmartParkRecognitionWorker", "SmartParkMediaService", "SmartParkSiteService", "SmartParkHvxHost"]


def test_qy_only_site_does_not_start_media_service_or_recognition_worker(monkeypatch):
    """QY/HVX cameras are read by the SDK host; MediaMTX and the worker only cost CPU there."""
    from app.desktop import launch

    started = []
    monkeypatch.setattr(launch, "_windows_service_state", lambda name: "RUNNING" if name in (launch._SERVICE_SITE, launch._SERVICE_HVX) else ("STOPPED" if name == "SmartParkMediaService" else None))
    monkeypatch.setattr(launch, "_start_windows_service", lambda name: started.append(name) or True)
    monkeypatch.setattr(launch, "wait_for_api", lambda **kw: None)
    monkeypatch.setattr(launch, "start_pipeline_services", lambda root, modules=None: started.append(tuple(modules or ())))
    monkeypatch.setattr(launch, "pipeline_needs", lambda url: {"known": True, "media_service_needed": False, "recognition_worker_needed": False})
    launch._ensure_windows_services(launch.Path("."), "http://127.0.0.1:8760")
    assert "SmartParkMediaService" not in started and not any(isinstance(item, tuple) for item in started)

    started.clear()
    monkeypatch.setattr(launch, "pipeline_needs", lambda url: {"known": True, "media_service_needed": True, "recognition_worker_needed": True})
    launch._ensure_windows_services(launch.Path("."), "http://127.0.0.1:8760")
    assert "SmartParkMediaService" in started and ("app.recognition_worker",) in started


def test_pipeline_needs_falls_back_to_everything_when_the_server_cannot_say(monkeypatch):
    from app.desktop import launch

    assert launch.pipeline_needs("http://127.0.0.1:9") == {"media_service_needed": True, "recognition_worker_needed": True}
