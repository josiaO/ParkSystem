from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from app.services.ipcam_discover import adapter_for, fingerprint_http, generic_discovery_row
from app.services.site_cameras import camera_spec_for_ip, discovery_row, scan_prefix


class IpcamDiscoverTests(unittest.TestCase):
    def test_sdk_port_keeps_hvx_engine(self):
        self.assertEqual(adapter_for(sdk_open=True, vendor="hikvision", http_open=True, rtsp_open=True), "hvx")
        self.assertEqual(adapter_for(sdk_open=False, vendor="dahua", http_open=True, rtsp_open=False), "dahua")
        self.assertEqual(adapter_for(sdk_open=False, vendor="hikvision", http_open=True, rtsp_open=True), "hikvision")
        self.assertEqual(adapter_for(sdk_open=False, vendor=None, http_open=False, rtsp_open=True), "rtsp")
        self.assertIsNone(adapter_for(sdk_open=False, vendor=None, http_open=False, rtsp_open=False))

    def test_generic_row_is_not_sdk_connected(self):
        row = generic_discovery_row({
            "ip": "10.0.0.80",
            "adapter_id": "dahua",
            "http_open": True,
            "rtsp_open": True,
            "sdk_open": False,
            "vendor": "dahua",
        })
        self.assertEqual(row["adapter_id"], "dahua")
        self.assertEqual(row["plate_engine"], "fastalpr")
        self.assertTrue(row["reachable"])
        self.assertIn("Not SDK_CONNECTED", row["note"])
        self.assertIn("FastALPR", row["note"])

    def test_scan_prefix_includes_linux_private_lans(self):
        self.assertEqual(scan_prefix("192.168.1.10"), "192.168.1")
        self.assertEqual(scan_prefix("10.8.0.12"), "10.8.0")
        self.assertEqual(scan_prefix("172.16.4.2"), "172.16.4")
        self.assertIsNone(scan_prefix("127.0.0.1"))
        self.assertIsNone(scan_prefix("8.8.8.8"))

    def test_hvx_discovery_row_unchanged(self):
        row = discovery_row("192.168.1.144", tcp_open=True, hvx_found=False)
        self.assertEqual(row["adapter_id"], "hvx")
        self.assertEqual(row["plate_engine"], "native")
        self.assertIn("not an SDK login", row["note"])

    def test_camera_spec_can_set_generic_adapter(self):
        spec = camera_spec_for_ip("10.0.0.81", adapter_id="hikvision")
        self.assertEqual(spec["adapter_id"], "hikvision")

    def test_fingerprint_hikvision_www_authenticate(self):
        class _Resp:
            status_code = 401
            headers = {"WWW-Authenticate": 'Digest realm="IP Camera"', "Server": "App-webs"}
            text = ""

        class _Client:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return False
            async def get(self, url):
                return _Resp()

        with patch("app.services.ipcam_discover.httpx.AsyncClient", return_value=_Client()):
            self.assertEqual(asyncio.run(fingerprint_http("10.0.0.9")), "hikvision")


if __name__ == "__main__":
    unittest.main()
