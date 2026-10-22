import asyncio
from contextlib import contextmanager
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx

from app import api_main as api
from app.models import Camera
from app.services import hvx_client
from app.services.camera_framing import ArrivalGate
from app.services.recognition_runtime import runtime


JPEG = b"\xff\xd8frame\xff\xd9"


def test_sdk_publishes_each_frame_before_the_next_native_read():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/hvx_sdk_host"))
    from hvx_sdk import HVXSDK

    sdk = HVXSDK.__new__(HVXSDK)
    published = []
    frames = [JPEG + bytes([number]) for number in range(3)]
    def read(handle):
        if frames:
            assert len(published) == 3 - len(frames)
            return frames.pop(0)
        assert len(published) == 3
        return b""
    sdk._get_jpg_buffer = read
    latest, backlog = sdk._latest_jpg_buffer(7, on_frame=published.append)
    assert published == [JPEG + bytes([number]) for number in range(3)]
    assert latest == published[-1]
    assert not backlog


def test_hot_host_polls_reuse_connections_and_close_at_shutdown():
    async def run():
        real_client = httpx.AsyncClient
        paths = []
        def reply(request):
            paths.append(request.url.path)
            return httpx.Response(200, json={"events": [], "reports": [], "pins": []})
        def factory(**kwargs):
            return real_client(**kwargs, transport=httpx.MockTransport(reply))
        try:
            with patch.object(hvx_client.httpx, "AsyncClient", side_effect=factory) as construct:
                host = hvx_client.HVXHostClient("http://host.test:8010")
                for _ in range(4):
                    await host.state(7)
                    await host.drain_events(7)
                    await host.drain_reports(7)
                    await host.scan_gpio(7)
                assert construct.call_count == 1
                first = hvx_client._shared_poll_client(host.base_url)
                other = hvx_client._shared_poll_client("http://other.test:8010")
                assert first is not other
        finally:
            await hvx_client.close_host_clients()
        assert first.is_closed and other.is_closed
        assert len(paths) == 16
    asyncio.run(run())


def test_one_camera_timeout_does_not_close_its_neighbors_live_client():
    async def run():
        real_client=httpx.AsyncClient
        def reply(request):
            if request.url.path.endswith("/7"):
                raise httpx.ReadTimeout("camera stalled", request=request)
            return httpx.Response(200, content=JPEG)
        def factory(**kwargs):
            return real_client(**kwargs, transport=httpx.MockTransport(reply))
        try:
            with patch.object(hvx_client.httpx, "AsyncClient", side_effect=factory):
                host=hvx_client.HVXHostClient("http://host.test:8010")
                neighbor=hvx_client._shared_live_client(host.base_url, 8)
                assert await host.live_jpeg(7) == b""
                await asyncio.sleep(0)
                assert not neighbor.is_closed
                assert hvx_client._shared_live_client(host.base_url, 8) is neighbor
                assert await host.live_jpeg(8) == JPEG
        finally:
            await hvx_client.close_host_clients()
    asyncio.run(run())


def test_rejected_ocr_does_not_hold_arrival_or_publish_evidence():
    async def run():
        camera = Camera(id=903, name="Entry", ip_address="10.0.0.5", stream_profiles={})
        result = {"ok": True, "best": {"plate": "T123ABC", "confidence": .95}}
        gate = ArrivalGate(stable_seconds=0)
        box = {"x1": 20, "y1": 30, "x2": 100, "y2": 55, "image_width": 200, "image_height": 100}
        gate.observe(box, 1)
        assert gate.observe(box, 2) == "ready"
        with patch("app.services.media_gateway.gateway.peek_detect", return_value=None), \
             patch("app.services.alpr.recognize_arrival_bytes", return_value=result), \
             patch.object(runtime, "finish", return_value=False), \
             patch("app.api_main._persist_capture_event", new=AsyncMock()) as persist, \
             patch("app.services.camera_framing.gate_for", return_value=gate):
            output = await api._run_local_alpr_locked(None, camera, JPEG, ticket=object())
            assert output["persist_skipped"] == "stale recognition result"
            assert not api._note_arrival_result(camera.id, output)
            assert gate.observe(box, 3) == "ready"
            persist.assert_not_awaited()
    asyncio.run(run())


def test_software_hvx_without_sdk_handle_recognizes_existing_video_and_retries_rejected_frame():
    async def run():
        camera = Camera(id=904, name="Exit", ip_address="10.0.0.6", adapter_id="hvx",
                        sdk_handle=None, recognition_mode="FASTALPR_ONLY", stream_profiles={})
        @contextmanager
        def session():
            yield SimpleNamespace(get=lambda *args: camera)
        rejected = {"ok": True, "best": {"plate": "T123ABC"}, "persist_skipped": "stale recognition result"}
        api._alpr_fp.pop(camera.id, None)
        try:
            with patch("app.recognition_worker.worker_owns_software_reads", return_value=False), \
                 patch("app.api_main.short_session", session), \
                 patch("app.services.media_gateway.gateway.peek_detect", return_value=SimpleNamespace(jpeg=JPEG, received_at=api.time.monotonic())), \
                 patch("app.api_main._video_arrival_ready", new=AsyncMock(return_value=True)), \
                 patch("app.api_main._run_local_alpr", new=AsyncMock(return_value=rejected)) as recognize, \
                 patch("app.services.camera_framing.gate_for", return_value=Mock()):
                await api._maybe_local_ipcam_alpr(camera.id)
                await api._maybe_local_ipcam_alpr(camera.id)
                assert recognize.await_count == 2
                assert camera.id not in api._alpr_fp
        finally:
            api._alpr_fp.pop(camera.id, None)
    asyncio.run(run())


def test_recognition_outbox_keeps_the_saved_plate_crop(tmp_path):
    async def run():
        snapshot=tmp_path / "snapshot.jpg"
        crop=tmp_path / "crop.jpg"
        snapshot.write_bytes(JPEG)
        crop.write_bytes(JPEG + b"plate crop")
        processed=asyncio.Event()
        box=SimpleNamespace(pending=lambda **kwargs: [{"id": "item", "payload": {}}],
                            was_processed=lambda key: False,
                            ack=lambda *args, **kwargs: processed.set())
        event={"event_id": "test-event", "camera_id": 905,
               "image_ref": "/media/snapshots/test.jpg", "plate_crop_ref": "/media/crops/test.jpg"}
        camera=Camera(id=905, name="Entry", ip_address="10.0.0.7", enabled=True)
        @contextmanager
        def session():
            yield SimpleNamespace(get=lambda *args: camera, scalar=lambda *args: None)
        with patch("app.services.queues.parking_outbox", return_value=box), \
             patch("app.services.events.recognition_from_outbox", return_value=event), \
             patch("app.api_main.short_session", session), \
             patch("app.services.modules.is_enabled", return_value=True), \
             patch("app.services.hybrid_fusion.routes_camera", return_value=False), \
             patch("app.api_main.adapter_has_native_plates", return_value=False), \
             patch("app.api_main.media_path", side_effect=lambda kind, name: snapshot if kind == "snapshots" else crop), \
             patch("app.api_main._persist_capture_event", new=AsyncMock()) as persist:
            task=asyncio.create_task(api._outbox_loop())
            try:
                await asyncio.wait_for(processed.wait(), 1)
                assert persist.await_args.args[-2:] == (JPEG, JPEG + b"plate crop")
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    asyncio.run(run())


def test_historical_capture_does_not_suppress_the_next_coil_read():
    async def run():
        camera=Camera(id=906, name="Entry", ip_address="10.0.0.8", sdk_handle=7)
        old=SimpleNamespace(id=41, image_id=3, plate="T111OLD")
        fresh=SimpleNamespace(id=42, image_id=4, plate="T222NEW")
        @contextmanager
        def session():
            yield SimpleNamespace(get=lambda *args: camera)
        with patch("app.api_main.short_session", session), \
             patch("app.api_main.latest_for_camera", side_effect=[old, old, old, fresh]), \
             patch("app.api_main.coil_watch.mark_triggered"), \
             patch("app.api_main.HVXHostClient.snapshot_trigger", new=AsyncMock()), \
             patch("app.api_main.HVXHostClient.live_jpeg", new=AsyncMock(return_value=JPEG)), \
             patch("app.api_main._drain_camera_events", new=AsyncMock()), \
             patch("app.api_main._run_local_alpr", new=AsyncMock()) as recognize:
            await api._read_presence_now(camera.id, 7)
            recognize.assert_awaited_once()
            await api._read_presence_now(camera.id, 7)
            recognize.assert_awaited_once()
    asyncio.run(run())
