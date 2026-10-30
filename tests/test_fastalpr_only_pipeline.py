import asyncio
from contextlib import contextmanager
from pathlib import Path
from pathlib import PureWindowsPath
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app import api_main as api
from app.config import settings
from app.core.fusion import resolve_readings
from app.models import Camera
from app.services import alpr


def test_windows_evidence_paths_are_serialized_as_url_paths(tmp_path, monkeypatch):
    from app.models import VehicleCapture
    from app.services import captures
    monkeypatch.setattr("app.config.default_data_dir", lambda: tmp_path)
    monkeypatch.setattr(captures, "Path", PureWindowsPath)
    relative=captures._write_jpeg("snapshots", "car.jpg", b"\xff\xd8snapshot")
    assert relative == "snapshots/car.jpg"
    capture=VehicleCapture(plate="T123ABC", snapshot_path=r"snapshots\car.jpg", crop_path=r"crops\plate.jpg")
    body=captures.capture_dict(capture)
    assert body["snapshot_url"] == "/media/snapshots/car.jpg"
    assert body["crop_url"] == "/media/crops/plate.jpg"
    from app.application.live_parking import event_from_capture
    event=event_from_capture(Camera(id=1, site_id=1), capture)
    assert event.image_ref == "/media/snapshots/car.jpg"
    assert event.plate_crop_ref == "/media/crops/plate.jpg"
    hit=alpr.PlateHit("T123ABC", "T123ABC", .95, plate_crop_path=r"crops\plate.jpg")
    assert hit.as_dict()["crop_url"] == "/media/crops/plate.jpg"


@pytest.mark.parametrize("mode", ["LOCAL", "LOCAL_ONLY", "FASTALPR", "FASTALPR_ONLY"])
def test_software_only_never_uses_camera_text_when_local_read_is_empty(mode):
    decision=resolve_readings(native_plate="T999CAM", native_confidence=.99, mode=mode)
    assert decision.resolved_plate == ""
    assert decision.method == "LOCAL_ONLY"
    assert decision.needs_review


def test_camera_confidence_cannot_promote_a_weak_software_read():
    decision=resolve_readings(native_plate="T123ABC", native_confidence=.99,
                              local_plate="T123ABC", local_confidence=.8, mode="FASTALPR_ONLY")
    assert decision.resolved_confidence == .8
    assert decision.needs_review
    assert decision.native_plate == ""


@pytest.mark.parametrize("cores,configured,expected", [(4, 0, 1), (32, 0, 2), (4, 3, 3)])
def test_model_threads_reserve_cpu_for_video(cores, configured, expected, monkeypatch):
    fast=pytest.importorskip("fast_alpr")
    monkeypatch.setattr(alpr, "_engine", None)
    monkeypatch.setattr(alpr, "ensure_alpr_model_cache", lambda: {"detector": True, "ocr": True})
    monkeypatch.setattr(alpr.os, "cpu_count", lambda: cores)
    monkeypatch.setattr(settings, "recognition_model_threads", configured)
    monkeypatch.setattr(settings, "recognition_max_concurrency", 4)
    options={}
    monkeypatch.setattr(fast, "ALPR", lambda **kwargs: options.update(kwargs) or object())
    alpr._load_engine()
    for name in ("detector_sess_options", "ocr_sess_options"):
        session=options[name]
        assert session.intra_op_num_threads == expected
        assert session.inter_op_num_threads == 1
        assert session.get_session_config_entry("session.intra_op.allow_spinning") == "0"


def test_crop_ocr_failure_is_not_reported_as_a_healthy_empty_read(monkeypatch):
    np=pytest.importorskip("numpy")
    box={"x1": 30, "y1": 30, "x2": 130, "y2": 60, "image_width": 200, "image_height": 100, "confidence": .95}
    def fail(crop):
        raise RuntimeError("OCR runtime unavailable")
    monkeypatch.setattr(alpr, "decode_alpr_image", lambda jpeg: np.zeros((100,200,3), dtype=np.uint8))
    monkeypatch.setattr(alpr, "_load_engine", lambda: SimpleNamespace(ocr=SimpleNamespace(predict=fail)))
    result=alpr.recognize_arrival_bytes(b"jpeg", detected_boxes=[box])
    assert result["ok"] is False
    assert "OCR runtime unavailable" in result["detail"]
    assert result["best"] is None


@pytest.mark.parametrize("same_image", [False, True])
def test_software_only_starts_with_its_own_detector_not_native_box_or_crop(same_image):
    async def run():
        from app.services.recognition_runtime import runtime
        camera=Camera(id=9901, name="Entry", ip_address="10.1.0.2", adapter_id="hvx", recognition_mode="FASTALPR_ONLY")
        jpeg=b"\xff\xd8snapshot\xff\xd9"
        native={"plate": "T999CAM", "confidence": .99, "bbox": {"x1": 1, "y1": 1, "x2": 40, "y2": 20}}
        ticket=SimpleNamespace(jpeg=jpeg)
        with patch("app.services.node_scope.camera_in_recognition_scope", return_value=True), \
             patch.object(runtime, "offer_frame"), \
             patch.object(runtime, "begin_if_idle", return_value=ticket), \
             patch("app.api_main._run_local_alpr_locked", new=AsyncMock(return_value={"ok": True})) as read:
            await api._run_local_alpr(None, camera, jpeg, native=native, force=True,
                                      plate_crop=jpeg if same_image else b"\xff\xd8camera crop")
            assert read.await_args.kwargs["native"] == {}
            assert read.await_args.kwargs["plate_crop"] == b""
        api._local_alpr_at.pop(camera.id, None)
    asyncio.run(run())


def test_bundled_models_crop_and_read_real_vehicle_stills(tmp_path, monkeypatch):
    pytest.importorskip("fast_alpr")
    pytest.importorskip("onnxruntime")
    from open_image_models.detection.core import hub as detector_hub
    from fast_plate_ocr.inference import hub as ocr_hub
    from PIL import Image

    root=Path(__file__).resolve().parents[1]
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(detector_hub, "MODEL_CACHE_DIR", tmp_path / ".cache/open-image-models")
    monkeypatch.setattr(ocr_hub, "MODEL_CACHE_DIR", tmp_path / ".cache/fast-plate-ocr")
    monkeypatch.setattr(alpr, "_engine", None)
    monkeypatch.setattr(settings, "alpr_country", "")
    monkeypatch.setattr(settings, "plate_validation", "NONE")
    photos = sorted((root / "TestingData").glob("*.jpg")) + sorted((root / "TestingData").glob("*.jpeg"))
    if not photos:
        pytest.skip("SmartPark TestingData does not contain a JPEG fixture")
    reader=alpr._load_engine()
    real_predict=reader.ocr.predict
    ocr_shapes=[]
    def predict(crop):
        ocr_shapes.append(crop.shape)
        return real_predict(crop)
    monkeypatch.setattr(reader.ocr, "predict", predict)
    for photo in photos[:3]:
        jpeg=photo.read_bytes()
        with Image.open(photo) as image:
            width, height=image.size
        boxes, located=alpr.locate_plate_boxes(jpeg)
        assert located["available"] and boxes
        count=len(ocr_shapes)
        result=alpr.recognize_arrival_bytes(jpeg, detected_boxes=boxes, save_evidence=False)
        assert result["pipeline"] == "arrival_crop_ocr"
        assert result["best"] is not None
        assert result["best"]["plate"]
        assert len(ocr_shapes) > count
        assert all(shape[0] < height and shape[1] < width for shape in ocr_shapes[count:])
        assert result["best"]["bbox"]["crop"]
    async def route_stopped_vehicle():
        from app.services.camera_framing import gate_for
        from app.services.recognition_runtime import runtime
        camera=Camera(id=9902, name="Entry", ip_address="10.1.0.3", adapter_id="hvx",
                      recognition_mode="FASTALPR_ONLY", sdk_handle=7, stream_profiles={})
        jpeg=photos[0].read_bytes()
        expected = alpr.recognize_arrival_bytes(jpeg, save_evidence=False)["best"]
        assert expected and expected.get("plate")
        @contextmanager
        def session():
            yield SimpleNamespace(get=lambda model, key: camera if model is Camera else None)
        runtime.reset()
        gate_for(camera.id).reset()
        api._detect_at.pop(camera.id, None)
        api._alpr_fp.pop(camera.id, None)
        ocr_shapes.clear()
        try:
            with patch("app.recognition_worker.worker_owns_software_reads", return_value=False), \
                 patch("app.api_main.short_session", session), \
                 patch("app.services.media_gateway.gateway.peek_detect", return_value=SimpleNamespace(jpeg=jpeg, seq=1, received_at=api.time.monotonic())), \
                 patch("app.services.node_scope.camera_in_recognition_scope", return_value=True), \
                 patch("app.api_main.site_policy", return_value={"plate_validation": "NONE"}), \
                 patch("app.api_main._native_capture_for_camera", new=AsyncMock(side_effect=AssertionError("camera OCR must not be queried"))) as native, \
                 patch("app.api_main._persist_capture_event", new=AsyncMock()) as persist:
                await api._maybe_watch_local_alpr(camera.id, 7)
                await api._maybe_watch_local_alpr(camera.id, 7)
                assert not ocr_shapes
                persist.assert_not_awaited()
                await asyncio.sleep(.6)
                await api._maybe_watch_local_alpr(camera.id, 7)
                persist.assert_awaited_once()
                assert persist.await_args.args[2]["plate"] == expected["plate"]
                assert persist.await_args.args[3] == jpeg
                assert persist.await_args.args[4].startswith(b"\xff\xd8")
                native.assert_not_awaited()
        finally:
            runtime.reset()
            gate_for(camera.id).reset()
            for cache in (api._detect_at, api._alpr_fp, api._local_alpr_at):
                cache.pop(camera.id, None)
    asyncio.run(route_stopped_vehicle())
