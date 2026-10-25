from pathlib import Path
from unittest.mock import patch

from app.desktop import launch
from app.services import mediamtx, mediamtx_telemetry


def test_existing_api_does_not_skip_video_and_recognition_services(tmp_path):
    with patch.object(launch, "start_hvx_host"), patch.object(launch, "_port_open", return_value=True), \
         patch.object(launch, "start_pipeline_services") as pipeline:
        launch.ensure_background_services(tmp_path)
    pipeline.assert_called_once_with(tmp_path)


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
    assert '-Arguments "-m app.recognition_worker"' in services
    assert 'Register-SmartParkTask -Name "SmartPark Recognition Worker"' in services
    assert '& $enableMedia -InstallDir $InstallDir -LiveView' in installer
