from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.domain.flags import LIVE_VIEW_DIRECT_LEGACY, LIVE_VIEW_MEDIAMTX
from app.infrastructure.media import registry


class MediaRegistryTests(unittest.TestCase):
    def test_direct_legacy_is_default(self):
        with (
            patch.object(registry, "_migration_flags", return_value={
                "media_gateway_enabled": False,
                "live_view_provider": LIVE_VIEW_DIRECT_LEGACY,
                "webrtc_live_enabled": False,
            }),
            patch.object(registry, "media_mtx_for_camera", return_value=False),
            patch.object(registry.gateway, "get_live_endpoint", new=AsyncMock(return_value={
                "kind": "mjpeg",
                "path": "/cameras/3/live.mjpeg",
            })),
        ):
            body = asyncio.run(registry.get_live_endpoint(3))
        self.assertEqual(body["provider"], LIVE_VIEW_DIRECT_LEGACY)
        self.assertIn("live.mjpeg", body["path"])

    def test_mediamtx_live_requires_running_sidecar(self):
        flags = {
            "media_gateway_enabled": True,
            "live_view_provider": LIVE_VIEW_MEDIAMTX,
            "webrtc_live_enabled": True,
        }
        with (
            patch.object(registry, "_migration_flags", return_value=flags),
            patch.object(registry, "media_mtx_for_camera", return_value=True),
            patch.object(registry.mediamtx, "running", return_value=False),
        ):
            self.assertFalse(registry.mediamtx_live_active(3))

    def test_mediamtx_endpoint_is_single_live_transport(self):
        flags = {
            "media_gateway_enabled": True,
            "live_view_provider": LIVE_VIEW_MEDIAMTX,
            "webrtc_live_enabled": True,
        }
        endpoint = {
            "kind": "mediamtx",
            "rtsp": "rtsp://127.0.0.1:8554/cam3",
            "webrtc": "http://127.0.0.1:8889/cam3",
            "hls": "http://127.0.0.1:8888/cam3",
            "running": True,
        }
        with (
            patch.object(registry, "_migration_flags", return_value=flags),
            patch.object(registry, "media_mtx_for_camera", return_value=True),
            patch.object(registry.mediamtx, "running", return_value=True),
            patch.object(registry.mediamtx, "live_endpoint", return_value=endpoint),
        ):
            body = asyncio.run(registry.get_live_endpoint(3))
        self.assertEqual(body["provider"], LIVE_VIEW_MEDIAMTX)
        self.assertEqual(body["webrtc"], endpoint["webrtc"])
        self.assertNotIn("path", body)


if __name__ == "__main__":
    unittest.main()
