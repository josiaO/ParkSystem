from pathlib import Path
from unittest.mock import patch

from app.desktop import launch
from app.deployment import DeploymentConfig, SITE_SERVER
from app.services import mediamtx, mediamtx_telemetry


def test_existing_api_does_not_skip_video_and_recognition_services(tmp_path):
    with patch.object(launch, "start_hvx_host"), patch.object(launch, "_port_open", return_value=True), \
         patch.object(launch, "wait_for_api"), \
         patch.object(launch, "start_pipeline_services") as pipeline:
        launch.ensure_background_services(tmp_path)
    pipeline.assert_called_once_with(tmp_path)


def test_existing_listener_is_health_checked_before_pipeline_start(tmp_path):
    with patch.object(launch, "start_hvx_host"), patch.object(launch, "_port_open", return_value=True), \
         patch.object(launch, "wait_for_api") as wait, patch.object(launch, "start_pipeline_services"):
        launch.ensure_background_services(tmp_path)
    wait.assert_called_once()
    assert wait.call_args.kwargs["base_url"] == "http://127.0.0.1:8760"


def test_site_service_start_waits_for_slow_first_boot(tmp_path):
    with patch.object(launch, "start_site_service", return_value=True), \
         patch.object(launch, "_port_open", return_value=False), \
         patch.object(launch, "start_hvx_host"), \
         patch.object(launch, "wait_for_api") as wait, \
         patch.object(launch, "start_pipeline_services"):
        launch.ensure_background_services(tmp_path)
    assert wait.call_args.kwargs["timeout"] == launch.SITE_SERVICE_START_TIMEOUT_SECONDS


def test_api_timeout_includes_site_service_launch_tail():
    with patch.object(launch, "_site_service_launch_tail", return_value=" Last output: DATABASE STARTUP FAILED"):
        try:
            launch.wait_for_api(timeout=0)
        except RuntimeError as exc:
            assert "DATABASE STARTUP FAILED" in str(exc)
        else:
            raise AssertionError("an API timeout must include the launch log tail")


def test_windows_registered_task_is_started_without_spawning_duplicate_api(tmp_path):
    config = DeploymentConfig(configured=True, role=SITE_SERVER, installation_id="i", server_id="s")
    with patch.object(launch.os, "name", "nt"), \
         patch.object(launch, "_scheduled_site_service_exists", return_value=True) as exists, \
         patch.object(launch, "_start_scheduled_site_service", return_value=True) as start_task, \
         patch.object(launch, "_scheduled_task_exists", return_value=True) as dependent_exists, \
         patch.object(launch, "_start_scheduled_task", return_value=True) as start_dependent, \
         patch.object(launch, "start_hvx_host"), \
         patch.object(launch, "wait_for_api") as wait, \
         patch.object(launch, "start_pipeline_services") as pipeline, \
         patch.object(launch, "start_site_service") as spawn:
        launch.ensure_background_services(tmp_path, config=config)
    exists.assert_called_once_with()
    start_task.assert_called_once_with()
    spawn.assert_not_called()
    wait.assert_called_once_with(
        timeout=launch.SITE_SERVICE_START_TIMEOUT_SECONDS,
        base_url="http://127.0.0.1:8760",
    )
    pipeline.assert_not_called()
    assert dependent_exists.call_count == 3
    assert start_dependent.call_count == 3


def test_windows_task_start_failure_is_reported_without_fallback_process(tmp_path):
    config = DeploymentConfig(configured=True, role=SITE_SERVER, installation_id="i", server_id="s")
    with patch.object(launch.os, "name", "nt"), \
         patch.object(launch, "_scheduled_site_service_exists", return_value=True), \
         patch.object(launch, "_start_scheduled_site_service", return_value=False), \
         patch.object(launch, "_scheduled_task_query", return_value=None), \
         patch.object(launch, "start_hvx_host"), \
         patch.object(launch, "start_site_service") as spawn, \
         patch.object(launch, "start_pipeline_services") as pipeline:
        try:
            launch.ensure_background_services(tmp_path, config=config)
        except RuntimeError as exc:
            assert "SmartPark Site Service" in str(exc)
            assert "Run As User" in str(exc)
        else:
            raise AssertionError("scheduled task failure must be surfaced")
    spawn.assert_not_called()
    pipeline.assert_not_called()


def test_site_service_start_keeps_child_diagnostics(tmp_path):
    with patch.object(launch, "_log_dir", return_value=tmp_path), \
         patch.object(launch, "_port_open", return_value=False), \
         patch.object(launch.subprocess, "Popen") as spawn:
        assert launch.start_site_service(tmp_path)
    assert spawn.call_args.kwargs["stdout"].name.endswith("site-service-launch.log")
    assert spawn.call_args.kwargs["stderr"].name.endswith("site-service-launch.log")


def test_site_service_spawn_failure_does_not_start_an_in_process_api(tmp_path):
    config = DeploymentConfig(configured=True, role=SITE_SERVER, installation_id="i", server_id="s")
    with patch.object(launch, "_port_open", return_value=False), \
         patch.object(launch, "start_site_service", return_value=False), \
         patch.object(launch, "start_pipeline_services") as pipeline:
        try:
            launch.ensure_background_services(tmp_path, config=config)
        except RuntimeError as exc:
            assert "could not be started" in str(exc)
            assert "site-service-launch.log" in str(exc)
        else:
            raise AssertionError("a failed Site Service spawn must stop startup")
    pipeline.assert_not_called()


def test_pipeline_launches_separate_owners_with_logs(tmp_path):
    with patch.object(launch, "_log_dir", return_value=tmp_path), \
         patch.object(launch.subprocess, "Popen") as spawn:
        launch.start_pipeline_services(tmp_path)
    assert [call.args[0][-1] for call in spawn.call_args_list] == ["app.media_service", "app.recognition_worker"]
    assert all(call.kwargs["cwd"] == str(tmp_path) for call in spawn.call_args_list)


def test_api_registration_does_not_overwrite_media_owner_config():
    with patch.object(mediamtx, "_sources", {}), patch.object(mediamtx, "_process", None), \
         patch.object(mediamtx, "running", return_value=True), \
         patch.object(mediamtx, "sync_paths") as sync, \
         patch.object(mediamtx, "write_config") as write:
        mediamtx.register_source(1, {"uri": "rtsp://camera/video"})
    write.assert_not_called()
    # The Site Service may observe an externally owned MediaMTX process, but
    # the Media Service is the only process allowed to push paths.
    sync.assert_not_called()


def test_separate_worker_discovers_detect_path_from_control_api():
    snapshot = {"ok": True, "paths": {
        "cam7": {"ready": True, "codec": "H264"},
        "cam7_detect": {"ready": True, "codec": "H264"},
    }}
    with patch.object(mediamtx, "_sources", {}), patch.object(mediamtx_telemetry, "refresh", return_value=snapshot):
        telemetry = mediamtx_telemetry.camera_telemetry(7)
    assert telemetry["roles"]["DETECT"]["mediamtx_path"] == "cam7_detect"


def test_worker_reads_the_actual_detect_path_not_the_live_fallback():
    import asyncio
    from app.infrastructure.media import registry

    with patch.object(registry, "mediamtx_detect_active", return_value=True), \
         patch.object(mediamtx, "detect_endpoint", return_value={"rtsp": "rtsp://127.0.0.1:8554/cam7"}), \
         patch.object(registry, "media_telemetry", return_value={"roles": {"DETECT": {"mediamtx_path": "cam7_detect"}}}):
        endpoint = asyncio.run(registry.get_detect_endpoint(7))
    assert endpoint["rtsp"] == "rtsp://127.0.0.1:8554/cam7_detect"


def test_windows_registers_and_activates_recognition():
    services = Path("packaging/windows/Install-SmartParkServices.ps1").read_text()
    installer = Path("packaging/windows/Install-SmartPark.ps1").read_text()
    win_service = Path("packaging/windows/Install-SmartParkWinService.ps1").read_text()
    assert '-Arguments "-m app.recognition_worker"' in services
    assert 'Register-SmartParkTask -Name "SmartPark Recognition Worker"' in services
    # The installer owns deployment roles and task startup; pipeline behavior
    # remains the stable main-branch runtime implementation.
    assert 'ValidateSet("SITE_SERVER", "EDGE_NODE", "OPERATOR_CLIENT")' in installer
    assert "PreserveMediaRollout" not in installer
    assert '& $enableMedia -InstallDir $InstallDir -LiveView' not in installer
    assert 'SMARTPARK_NODE_ROLE=SERVER' in services
    assert 'SMARTPARK_NODE_ROLE            = "SERVER"' in installer
    assert 'SMARTPARK_NODE_ROLE=$nodeRole' in win_service


def test_recognition_worker_uses_main_runtime_without_installer_preflight():
    source = Path("app/recognition_worker.py").read_text()
    assert "SMARTPARK_ALPR_PREFLIGHT" not in source
