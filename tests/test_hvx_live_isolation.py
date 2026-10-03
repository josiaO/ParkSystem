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
        text = (ROOT / "app" / "services" / "hvx_client.py").read_text(encoding="utf-8")
        self.assertIn("max_keepalive_connections=16", text)
        self.assertIn("max_connections=32", text)


if __name__ == "__main__":
    unittest.main()
