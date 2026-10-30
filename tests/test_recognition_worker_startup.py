from types import SimpleNamespace

from unittest.mock import patch


def test_worker_applies_selected_deployment_database_before_start(monkeypatch):
    from app import recognition_worker
    from app.config import settings

    database = object()
    deployment = SimpleNamespace(is_server=True, configured=True, database=database)
    monkeypatch.delenv("SMARTPARK_ALPR_CACHE_DIR", raising=False)
    with patch("app.deployment.load_deployment_config", return_value=deployment), \
         patch("app.database_config.apply_runtime_database_config") as apply:
        assert recognition_worker._configure_worker_runtime()

    apply.assert_called_once_with(database)
    assert recognition_worker.os.environ["SMARTPARK_ALPR_CACHE_DIR"] == str(settings.data_dir / "model-cache")


def test_worker_refuses_to_start_unconfigured_installation():
    from app import recognition_worker

    deployment = SimpleNamespace(is_server=True, configured=False, database=object())
    with patch("app.deployment.load_deployment_config", return_value=deployment), \
         patch("app.database_config.apply_runtime_database_config") as apply:
        assert not recognition_worker._configure_worker_runtime()
    apply.assert_not_called()


def test_detector_retry_backoff_is_bounded():
    from app.recognition_worker import _warmup_retry_delay

    assert [_warmup_retry_delay(i) for i in (1, 2, 3)] == [2.0, 4.0, 8.0]
    assert _warmup_retry_delay(100) == 60.0


def test_onnx_dll_failure_is_restart_required_not_a_retry_loop():
    from app.recognition_worker import _fatal_native_load_error

    error = ImportError("DLL load failed while importing onnxruntime_pybind11_state")
    assert _fatal_native_load_error(error)
    assert not _fatal_native_load_error(RuntimeError("temporary model read failure"))


def test_alpr_cache_can_be_shared_by_windows_services(tmp_path, monkeypatch):
    from app.services import alpr

    bundle = tmp_path / "bundle"
    cache = tmp_path / "cache"
    bundle.mkdir()
    (bundle / alpr.DETECTOR_ONNX).write_bytes(b"detector")
    (bundle / alpr.OCR_ONNX).write_bytes(b"ocr")
    (bundle / alpr.OCR_CONFIG).write_text("config", encoding="utf-8")
    monkeypatch.setenv("SMARTPARK_ALPR_CACHE_DIR", str(cache))
    with patch.object(alpr, "bundled_alpr_dir", return_value=bundle):
        result = alpr.ensure_alpr_model_cache()

    assert result["detector_path"] == str(cache / "open-image-models" / alpr.DETECTOR_MODEL / alpr.DETECTOR_ONNX)
    assert (cache / "fast-plate-ocr" / alpr.OCR_MODEL / alpr.OCR_ONNX).is_file()
