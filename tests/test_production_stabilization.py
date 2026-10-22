from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
import numpy as np
import pytest
from fastapi import Request
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.core.consensus import ConsensusTrack
from app.db import Base
from app.domain.events import from_recognition_dict
from app.models import Camera, VehicleCapture
from app.services.alpr import recognize_arrival_bytes, warmup
from app.services.captures import persist_event
from app.services.node_scope import camera_in_recognition_scope, describe_recognition_scope, reset_recognition_scope
from app.services.queues import SQLiteOutbox
from app.services.recognition_runtime import FairInferenceScheduler, RecognitionRuntime
from app.services.whep import browser_endpoint, proxy_signaling


def request(url: str, *, method="POST", body=b"offer") -> Request:
    parsed = httpx.URL(url)
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}
    return Request({"type": "http", "method": method, "scheme": parsed.scheme,
                    "server": (parsed.host, parsed.port or 80), "path": parsed.path,
                    "query_string": b"", "headers": [(b"host", parsed.netloc)]}, receive)


def test_browser_host_and_https_signaling_keep_rtsp_local():
    endpoint = {"provider": "MEDIAMTX", "transport": "WEBRTC", "camera_id": 1,
                "mediamtx_path": "cam1", "rtsp": "rtsp://127.0.0.1:8554/cam1"}
    with patch.object(settings, "mediamtx_browser_base_url", ""):
        remote = browser_endpoint(endpoint, request("http://192.168.1.4:8760"))
        secure = browser_endpoint(endpoint, request("https://parking.example"))
    assert remote["whep"] == "http://192.168.1.4:8889/cam1/whep"
    assert secure["whep"] == "/cameras/1/live/whep"
    assert secure["rtsp"] == endpoint["rtsp"]


@pytest.mark.asyncio
async def test_proxy_rewrites_location_and_forwards_patch_delete():
    client = AsyncMock()
    client.request.return_value = httpx.Response(201, content="answer", headers={"Location": "/cam1/whep/abc-123", "ETag": "v1"})
    context = AsyncMock()
    context.__aenter__.return_value = client
    with patch("app.services.whep.httpx.AsyncClient", return_value=context):
        response = await proxy_signaling(request("https://parking.example/cameras/1/live/whep"), 1, "cam1")
        assert response.headers["location"] == "/cameras/1/live/whep/abc-123"
        assert response.headers["etag"] == "v1"
        for method in ("OPTIONS", "PATCH", "DELETE"):
            await proxy_signaling(request("https://parking.example", method=method), 1, "cam1", "abc-123")
            assert client.request.call_args.args == (method, "http://127.0.0.1:8889/cam1/whep/abc-123")


@pytest.mark.asyncio
async def test_proxy_reports_mediamtx_unavailable():
    from fastapi import HTTPException
    context = AsyncMock()
    context.__aenter__.return_value.request.side_effect = httpx.ConnectError("offline")
    with patch("app.services.whep.httpx.AsyncClient", return_value=context), pytest.raises(HTTPException) as error:
        await proxy_signaling(request("https://parking.example"), 1, "cam1")
    assert error.value.status_code == 503
    assert "WHEP SIGNALING FAILED" in error.value.detail


def test_stale_nonempty_result_is_rejected_and_next_lane_progresses():
    runtime = RecognitionRuntime(max_concurrency=1)
    lane = runtime.lane(1)
    runtime.offer_frame(1, b"frame")
    ticket = runtime.begin_if_idle(1)
    assert not lane.accept(ticket, plate="T123ABC", now=ticket.captured_at + 2, stale_frame_ms=1000)
    runtime.finish(ticket)
    assert lane.last_plate == ""
    runtime.offer_frame(2, b"other")
    assert runtime.begin_if_idle(2) is not None


def test_four_camera_scheduler_fifo_is_bounded():
    scheduler = FairInferenceScheduler(2)
    assert scheduler.try_acquire(1)
    assert scheduler.try_acquire(2)
    assert not scheduler.try_acquire(3)
    assert not scheduler.try_acquire(4)
    scheduler.release(1)
    assert not scheduler.try_acquire(1)
    assert not scheduler.try_acquire(4)
    assert scheduler.try_acquire(3)
    scheduler.release(2)
    assert scheduler.try_acquire(4)
    assert scheduler.snapshot()["inflight"] == 2


def test_lanes_have_independent_visits_and_single_frame_mailboxes():
    runtime = RecognitionRuntime(2)
    for camera_id in (1, 2):
        runtime.lane(camera_id).visit.observe(presence=True)
        for number in range(10):
            runtime.offer_frame(camera_id, bytes([number]))
    assert runtime.lane(1).visit.visit_id != runtime.lane(2).visit.visit_id
    assert runtime.lane(1).mailbox.depth() == runtime.lane(2).mailbox.depth() == 1
    ticket = runtime.begin_if_idle(1)
    runtime.recover(1)
    assert runtime.lane(2).generation == 1
    assert not runtime.finish(ticket, plate="T123ABC")


def test_consensus_expires_old_votes_and_accepts_without_sleeping():
    track = ConsensusTrack(window_seconds=0.5, min_agreeing=3, min_reads=3)
    for stamp in (0.0, 0.3, 0.6):
        assert not track.observe("T123ABC", stamp, confidence=0.8).publish
    clean = ConsensusTrack()
    assert not clean.observe("T123ABC", 0, confidence=0.99, allow_single=False).publish
    assert clean.observe("T123ABC", 0.25, confidence=0.8).publish
    assert ConsensusTrack().observe("T123ABC", 0, confidence=0.99, allow_single=True).publish


def test_high_ocr_confidence_alone_cannot_enable_the_worker_fast_path():
    from app.recognition_worker import strong_read

    event = {"normalized_plate": "T123ABC", "confidence": .99}
    assert not strong_read(event, {"plate_validation": "TZ"})
    event.update(detector_confidence=.95, bbox={"crop": {"x1": 0, "y1": 0, "x2": 160, "y2": 40}})
    assert strong_read(event, {"plate_validation": "TZ"})
    event["normalized_plate"] = "STATION"
    assert not strong_read(event, {"plate_validation": "TZ"})


def test_unknown_detector_confidence_is_not_fabricated():
    from app.services.alpr import _detection_score

    assert _detection_score(SimpleNamespace()) == 0.0


def test_crop_selection_ranks_supplied_candidates_and_skips_invalid():
    small = {"x1": 10, "y1": 10, "x2": 70, "y2": 30, "confidence": 0.5}
    best = {"x1": 90, "y1": 30, "x2": 220, "y2": 70, "confidence": 0.95}
    invalid = {"x1": 1, "y1": 1, "x2": 2, "y2": 2, "confidence": 1}
    with patch("app.services.alpr.decode_alpr_image", return_value=np.zeros((180, 320, 3), dtype=np.uint8)), \
         patch("app.services.alpr._load_engine", return_value=object()), \
         patch("app.services.alpr._hits_from_detections", return_value=[]) as read:
        recognize_arrival_bytes(b"frame", detected_boxes=[invalid, small, best])
        assert read.call_args.args[2][0].bounding_box.x1 == best["x1"]
        read.reset_mock()
        recognize_arrival_bytes(b"frame", detected_boxes=[invalid])
        read.assert_not_called()


def test_warmup_exercises_models_without_publishing():
    engine = SimpleNamespace(detector=Mock(), ocr=Mock())
    with patch("app.services.alpr._load_engine", return_value=engine), \
         patch("app.services.events.publish", side_effect=AssertionError("warmup published")):
        assert warmup()["ready"]
        assert warmup()["cached"]
    engine.detector.predict.assert_called_once()
    engine.ocr.predict.assert_called_once()


def test_visit_identity_survives_contract_and_outbox_ack():
    event = from_recognition_dict({"event_id": "one", "camera_id": 1, "visit_id": "visit-a", "normalized_plate": "T123ABC"})
    assert event["payload"]["visit_id"] == "visit-a"
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "outbox.sqlite3"
        outbox = SQLiteOutbox(path)
        first = outbox.enqueue("PlateRecognized", {"dedupe_key": "camera1:visit-a"})
        outbox.ack(first)
        reopened = SQLiteOutbox(path)
        assert reopened.enqueue("PlateRecognized", {"dedupe_key": "camera1:visit-a"}) == first
        assert reopened.depth() == 0
        reopened.enqueue("PlateRecognized", {"dedupe_key": "camera1:visit-b"})
        assert reopened.depth() == 1


def test_capture_idempotency_survives_new_event_ids_and_session_restart():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    with factory() as db:
        camera = Camera(name="entry", ip_address="127.0.0.1")
        db.add(camera)
        db.commit()
        first = persist_event(db, camera, jpeg=b"", crop=b"", force=True,
                              capture={"plate": "T123ABC", "confidence": .95, "visit_id": "visit-a", "event_id": "one"})
        first_id = first.id
        camera_id = camera.id
    with factory() as db:
        camera = db.get(Camera, camera_id)
        retry = persist_event(db, camera, jpeg=b"", crop=b"", force=True,
                              capture={"plate": "T123ABC", "confidence": .95, "visit_id": "visit-a", "event_id": "two"})
        assert retry.id == first_id
        returned = persist_event(db, camera, jpeg=b"", crop=b"", force=True,
                                 capture={"plate": "T123ABC", "confidence": .95, "visit_id": "visit-b", "event_id": "three"})
        assert returned.id != first_id
        db.add(VehicleCapture(camera_id=camera_id, visit_id="visit-a", event_id="four"))
        with pytest.raises(IntegrityError):
            db.commit()
    engine.dispose()


def test_unassigned_production_is_closed_and_all_gates_is_explicit():
    reset_recognition_scope()
    with patch.object(settings, "deployment_profile", "PRODUCTION"), \
         patch.object(settings, "recognition_gate_id", None), \
         patch.object(settings, "recognition_all_gates_enabled", False):
        assert not camera_in_recognition_scope({"gate_id": 1})
        assert describe_recognition_scope()["detail"] == "NODE NOT ASSIGNED TO GATE"
        with patch.object(settings, "recognition_gate_id", 2):
            assert not camera_in_recognition_scope({"gate_id": 1})
            assert camera_in_recognition_scope({"gate_id": 2})
        with patch.object(settings, "recognition_all_gates_enabled", True):
            assert camera_in_recognition_scope({"gate_id": 1})
