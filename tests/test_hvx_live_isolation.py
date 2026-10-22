"""HVX live video must stay OcxConfig-shaped: one stream per camera, isolated pumps."""

from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.mediamtx_sources import source_config_for_camera, sync_camera
from app.services.stream_roles import hvx_profiles


class HvxLiveIsolationTests(unittest.TestCase):
    def test_hvx_camera_does_not_register_mediamtx_rtsp(self):
        camera = SimpleNamespace(
            id=3,
            ip_address="192.168.1.49",
            username="admin",
            password_secret="admin",
            rtsp_url="",
            rtsp_transport="TCP",
            sdk_handle=7,
            stream_profiles=hvx_profiles(7),
        )
        cfg = source_config_for_camera(camera)
        self.assertFalse(str(cfg.get("uri") or "").startswith("rtsp://"))
        with patch("app.infrastructure.media.registry.register_camera_source") as register, \
             patch("app.infrastructure.media.registry.unregister_camera_source") as unregister:
            out = sync_camera(camera)
        self.assertFalse(out.get("registered"))
        register.assert_not_called()
        unregister.assert_called_once_with(3)

    def test_generic_rtsp_camera_still_registers(self):
        camera = SimpleNamespace(
            id=8,
            ip_address="192.168.1.80",
            username="admin",
            password_secret="admin",
            rtsp_url="rtsp://192.168.1.80/av0_1",
            rtsp_transport="TCP",
            sdk_handle=None,
            stream_profiles={},
        )
        cfg = source_config_for_camera(camera)
        self.assertTrue(cfg["uri"].startswith("rtsp://"))
        with patch("app.infrastructure.media.registry.register_camera_source", return_value={"registered": True}) as register, \
             patch("app.infrastructure.media.registry.unregister_camera_source") as unregister:
            out = sync_camera(camera)
        self.assertTrue(out.get("registered"))
        register.assert_called_once()
        unregister.assert_not_called()

    def test_live_http_pool_can_serve_four_cameras(self):
        import asyncio
        import httpx
        from app.services import hvx_client

        async def run():
            real_client=httpx.AsyncClient
            active=set()
            ready=asyncio.Event()
            async def reply(request):
                active.add(request.url.path)
                if len(active) == 4:
                    ready.set()
                await asyncio.wait_for(ready.wait(), 1)
                return httpx.Response(200, content=b"\xff\xd8" + request.url.path.encode())
            def factory(**kwargs):
                return real_client(**kwargs, transport=httpx.MockTransport(reply))
            try:
                with patch.object(hvx_client.httpx, "AsyncClient", side_effect=factory) as construct:
                    host=hvx_client.HVXHostClient("http://host.test:8765")
                    frames=await asyncio.gather(*(host.live_jpeg(handle) for handle in range(1,5)))
                    self.assertEqual(len(active), 4)
                    self.assertEqual(len(set(frames)), 4)
                    self.assertTrue(all(frame.startswith(b"\xff\xd8") for frame in frames))
                    self.assertEqual(construct.call_count, 4)
            finally:
                await hvx_client.close_host_clients()
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
