from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.config import settings
from app.infrastructure.hardware.cameras import adapter_requires_native_stream
from app.infrastructure.hardware.cameras.rtsp import RTSPCameraAdapter
from app.services.media_gateway import CameraLiveSpec, LocalMediaGateway
from app.services.flags import direct_generic_media_allowed, validate_media_configuration
from app.services.mediamtx_sources import validate_camera_source


JPEG = b"\xff\xd8frame\xff\xd9"


def _camera(**overrides):
    values = {
        "id": 1,
        "ip_address": "192.0.2.10",
        "sdk_port": 30000,
        "username": "admin",
        "password_secret": "secret",
        "adapter_id": "hvx",
        "rtsp_url": "",
        "stream_profiles": {},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_hvx_legacy_alias_is_native_only_even_before_login():
    assert adapter_requires_native_stream("hvx")
    result = validate_camera_source(_camera())
    assert result["valid"]
    assert result["owner"] == "OcxConfig/NetSDK"


def test_generic_connect_does_not_start_a_competing_ffmpeg_reader():
    async def scenario():
        camera = _camera(
            adapter_id="rtsp",
            rtsp_url="rtsp://192.0.2.10/stream",
        )
        adapter = RTSPCameraAdapter()
        with patch(
            "app.infrastructure.hardware.cameras.rtsp.grab_camera_frame",
            new=AsyncMock(side_effect=AssertionError("connect opened a second decoder")),
        ):
            return await adapter.connect(camera)

    result = asyncio.run(scenario())
    assert result["connected"]
    assert result["configured_only"]
    assert result["url"] == "rtsp://192.0.2.10/stream"


def test_invalid_generic_media_configuration_is_explicit():
    result = validate_camera_source(
        _camera(
            adapter_id="rtsp",
            rtsp_url="http://192.0.2.10/not-rtsp",
            stream_profiles={"LIVE": {"protocol": "sdk"}},
        )
    )
    assert not result["valid"]
    assert len(result["errors"]) == 2


def test_health_exposes_startup_and_reconnect_timing():
    gateway = LocalMediaGateway()
    gateway.publish(11, JPEG, source="rtsp", source_seq=1)
    row = gateway.health_sync(11)
    assert row["last_successful_frame_at"]
    assert "stream_startup_ms" in row
    assert "time_since_reconnect_seconds" in row
    assert row["media_generation"] == 1


def test_normalized_contract_preserves_frame_identity_timestamp_and_generation():
    gateway = LocalMediaGateway()
    row = gateway._session_for(CameraLiveSpec(
        id=12, ip="", username="", password="", rtsp_url="", sdk_handle=None,
    ))
    row.generation = 3
    gateway.publish(12, JPEG, source="mediamtx", source_seq=7, generation=3)
    contract = gateway.stream_contract(12).as_dict()
    assert contract["camera_id"] == 12
    assert contract["generation"] == 3
    assert contract["latest_frame"]["sequence"] == 1
    assert contract["latest_frame"]["timestamp"]
    assert contract["frame_timestamp"]


def test_production_rejects_direct_generic_reader_and_invalid_rollout():
    with patch.object(settings, "deployment_profile", "PRODUCTION"):
        assert not direct_generic_media_allowed()
        validation = validate_media_configuration({
            "media_gateway_enabled": False,
            "live_view_provider": "DIRECT_LEGACY",
        })
        assert not validation["valid"]
        assert len(validation["errors"]) == 2


def test_production_generic_connect_is_media_owner_configuration_only():
    async def scenario():
        camera = _camera(adapter_id="rtsp", rtsp_url="rtsp://192.0.2.10/stream")
        adapter = RTSPCameraAdapter()
        with patch.object(settings, "deployment_profile", "PRODUCTION"), patch(
            "app.infrastructure.hardware.cameras.rtsp.grab_camera_frame",
            new=AsyncMock(side_effect=AssertionError("production opened a direct decoder")),
        ), patch(
            "app.infrastructure.hardware.cameras.rtsp.grab_http_snapshot",
            new=AsyncMock(side_effect=AssertionError("production opened a direct HTTP reader")),
        ):
            return await adapter.connect(camera)

    result = asyncio.run(scenario())
    assert result["configured_only"]
    assert result["source"] == "rtsp"
