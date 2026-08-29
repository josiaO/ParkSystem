from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.domain.devices import DEFAULT_CAMERA_ADAPTER, ConnectionMode
from app.domain.gates import should_pulse_physical
from app.infrastructure.db import is_postgres, is_sqlite
from app.infrastructure.hardware.cameras import camera_adapter_for
from app.infrastructure.hardware.cameras.onvif import ONVIFCameraAdapter
from app.infrastructure.hardware.cameras.rtsp import RTSPCameraAdapter
from app.infrastructure.hardware.edge import edge_agent_status, is_direct
from app.infrastructure.hardware.gates import live_gate_adapter
from app.infrastructure.hardware.registry import camera_adapter_id, camera_device


def _cam(**overrides):
    fields = {
        "id": 1,
        "name": "1# Entry",
        "ip_address": "192.168.1.144",
        "sdk_port": 30000,
        "username": "admin",
        "password_secret": "admin",
        "rtsp_url": "",
        "sdk_handle": None,
        "adapter_id": "hvx",
        "connection_mode": "DIRECT",
        "enabled": True,
        "gate_id": 1,
        "lane_direction": "ENTRY",
        "controller_ip": "192.168.1.61",
        "display_ip": "192.168.1.62",
        "gate": None,
    }
    fields.update(overrides)
    return type("Camera", (), fields)()


class AdapterWrapTests(unittest.TestCase):
    def test_default_camera_adapter_is_hvx(self):
        camera = _cam(adapter_id="")
        adapter = camera_adapter_for(camera)
        self.assertEqual(adapter.id, DEFAULT_CAMERA_ADAPTER)
        caps = asyncio.run(adapter.capabilities(camera))
        self.assertTrue(caps["sdk_login"])
        self.assertTrue(caps["native_plates"])
        sources = asyncio.run(adapter.live_sources(camera))
        self.assertEqual(sources[0]["kind"], "sdk")

    def test_hvx_connect_delegates_to_working_host_client(self):
        camera = _cam()
        adapter = camera_adapter_for(camera)
        with patch("app.infrastructure.hardware.cameras.hvx.HVXHostClient") as host:
            host.return_value.connect = AsyncMock(return_value={"connected": True, "handle": 7})
            result = asyncio.run(adapter.connect(camera))
        self.assertTrue(result["connected"])
        self.assertEqual(result["handle"], 7)
        host.return_value.connect.assert_awaited_once_with(
            ip="192.168.1.144", port=30000, username="admin", password="admin",
        )

    def test_onvif_cannot_replace_sdk_login(self):
        onvif = camera_adapter_for(_cam(adapter_id="onvif"))
        self.assertIsInstance(onvif, ONVIFCameraAdapter)
        onvif_result = asyncio.run(onvif.connect(_cam(adapter_id="onvif")))
        self.assertFalse(onvif_result["connected"])
        self.assertFalse(asyncio.run(onvif.capabilities(_cam()))["sdk_login"])
        self.assertFalse(asyncio.run(onvif.capabilities(_cam()))["native_plates"])

    def test_rtsp_connects_video_not_sdk_login(self):
        rtsp = camera_adapter_for(_cam(adapter_id="rtsp"))
        self.assertIsInstance(rtsp, RTSPCameraAdapter)
        caps = asyncio.run(rtsp.capabilities(_cam(adapter_id="rtsp")))
        self.assertFalse(caps["sdk_login"])
        self.assertFalse(caps["native_plates"])
        self.assertTrue(caps["local_alpr"])
        jpeg = b"\xff\xd8\xff\xd9"
        with patch(
            "app.infrastructure.hardware.cameras.rtsp.grab_http_snapshot",
            new=AsyncMock(return_value={
                "ok": True, "jpeg": jpeg, "url": "http://192.168.1.144/cgi-bin/snapshot.cgi",
                "url_redacted": "http://192.168.1.144/cgi-bin/snapshot.cgi",
            }),
        ):
            result = asyncio.run(rtsp.connect(_cam(adapter_id="rtsp")))
        self.assertTrue(result["connected"])
        self.assertIsNone(result.get("handle"))
        self.assertFalse(result.get("sdk_login"))
        self.assertFalse(result.get("native_plates"))
        self.assertTrue(result.get("local_alpr"))

    def test_unknown_adapter_falls_back_to_hvx(self):
        self.assertEqual(camera_adapter_for(_cam(adapter_id="not-a-vendor")).id, "hvx")

    def test_dahua_and_hikvision_use_generic_ip_adapter(self):
        self.assertEqual(camera_adapter_for(_cam(adapter_id="dahua")).id, "rtsp")
        self.assertEqual(camera_adapter_for(_cam(adapter_id="hikvision")).id, "rtsp")
        self.assertEqual(camera_adapter_for(_cam(adapter_id="ipcam")).id, "rtsp")
        self.assertFalse(asyncio.run(camera_adapter_for(_cam(adapter_id="dahua")).capabilities(_cam()))["sdk_login"])

    def test_registry_projects_existing_camera_row(self):
        row = camera_device(_cam())
        self.assertEqual(row.adapter_id, "hvx")
        self.assertEqual(row.device_type, "CAMERA")
        self.assertEqual(row.connection_mode, ConnectionMode.DIRECT.value)
        self.assertTrue(row.capabilities["sdk_login"])
        self.assertEqual(camera_adapter_id(_cam()), "hvx")

    def test_edge_agent_is_declared_but_not_the_live_path(self):
        self.assertTrue(is_direct(None))
        self.assertTrue(is_direct("DIRECT"))
        self.assertFalse(is_direct("EDGE_AGENT"))
        status = edge_agent_status()
        self.assertFalse(status["available"])
        self.assertEqual(status["default_mode"], "DIRECT")

    def test_hvx_connect_refuses_edge_agent_mode(self):
        result = asyncio.run(camera_adapter_for(_cam()).connect(_cam(connection_mode="EDGE_AGENT")))
        self.assertFalse(result["connected"])
        self.assertIn("DIRECT", result["error"])

    def test_postgres_remains_optional_url_switch(self):
        self.assertTrue(is_sqlite("sqlite:///tmp/smartpark.db"))
        self.assertTrue(is_postgres("postgresql+psycopg://u:p@localhost/smartpark"))

    def test_shadow_blocks_automatic_pulse_not_manual(self):
        shadow = type("Gate", (), {"mode": "SHADOW"})()
        commissioning = type("Gate", (), {"mode": "COMMISSIONING"})()
        production = type("Gate", (), {"mode": "PRODUCTION"})()
        self.assertFalse(should_pulse_physical(gate=shadow, automatic=True))
        self.assertTrue(should_pulse_physical(gate=shadow, automatic=False))
        self.assertTrue(should_pulse_physical(gate=commissioning, automatic=True))
        self.assertTrue(should_pulse_physical(gate=production, automatic=True))

    def test_gate_adapter_wraps_working_controller(self):
        health = asyncio.run(live_gate_adapter().health())
        self.assertEqual(health["adapter_id"], "hvx")
        self.assertEqual(health["wraps"], "app.services.gates.controller")


if __name__ == "__main__":
    unittest.main()
