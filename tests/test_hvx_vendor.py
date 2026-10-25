import unittest
from unittest.mock import patch

from app.services.hvx_vendor import pe_image_info, resolve_vendor_dir, vendor_inventory
from app.services.rtsp_probe import vendor_candidates


class VendorPackageTests(unittest.TestCase):
    def test_ocxconfig_package_is_pe32_x86(self):
        vendor = resolve_vendor_dir()
        self.assertTrue((vendor / "NetSDK.dll").exists(), vendor)
        pe = pe_image_info(vendor / "NetSDK.dll")
        self.assertTrue(pe["ok"] and pe["x86"])
        self.assertEqual(pe["machine"], "i386/x86")
        inventory = vendor_inventory()
        self.assertTrue(inventory["present"])
        self.assertEqual(inventory["missing"], [])
        self.assertEqual(inventory["sdk_control_port_default"], 30000)
        self.assertEqual(inventory["sdk_picture_port"], 40000)
        self.assertEqual(inventory["http_ui_port_not_sdk"], 80)
        self.assertIn("OcxConfig.ocx", inventory["official_config_ui"])
        seq = " ".join(inventory["connect_sequence"])
        self.assertIn("Net_RegReportMessEx", seq)
        self.assertIn("Net_ConnCamera(", seq)
        self.assertIn("unsigned short", seq)
        self.assertIn("Net_RegImageRecvEx2", seq)
        site = inventory["site"]
        self.assertEqual(site["sdk_port"], 30000)
        self.assertEqual(site["http_port"], 80)
        self.assertEqual(
            set(site["camera_ips"]),
            {"192.168.1.144", "192.168.1.145", "192.168.1.49", "192.168.1.50"},
        )
        self.assertEqual(
            set(site["controller_ips"]),
            {"192.168.1.61", "192.168.1.69", "192.168.1.65", "192.168.1.67"},
        )
        self.assertEqual(
            set(site["display_ips"]),
            {"192.168.1.62", "192.168.1.70", "192.168.1.66", "192.168.1.68"},
        )
        lane1 = next(row for row in site["lanes"] if row["name"] == "1#")
        self.assertEqual(lane1["entry"]["camera_ip"], "192.168.1.144")
        self.assertEqual(lane1["entry"]["controller_ip"], "192.168.1.61")
        self.assertEqual(lane1["entry"]["display_ip"], "192.168.1.62")
        self.assertEqual(lane1["exit"]["camera_ip"], "192.168.1.145")
        self.assertEqual(lane1["exit"]["controller_ip"], "192.168.1.69")
        self.assertEqual(lane1["exit"]["display_ip"], "192.168.1.70")
        lane2 = next(row for row in site["lanes"] if row["name"] == "2#")
        self.assertEqual(lane2["entry"]["camera_ip"], "192.168.1.49")
        self.assertEqual(lane2["entry"]["controller_ip"], "192.168.1.65")
        self.assertEqual(lane2["entry"]["display_ip"], "192.168.1.66")
        self.assertEqual(lane2["exit"]["camera_ip"], "192.168.1.50")
        self.assertEqual(lane2["exit"]["controller_ip"], "192.168.1.67")
        self.assertEqual(lane2["exit"]["display_ip"], "192.168.1.68")
        self.assertNotEqual(lane2["exit"]["display_ip"], "192.168.1.43")

    def test_site_ini_matches_canonical_lane_ips(self):
        from app.services.site_cameras import load_site_lanes, site_ini_path, flatten_site_cameras

        ini = site_ini_path()
        self.assertTrue(ini.is_file(), ini)
        cameras = flatten_site_cameras(load_site_lanes(ini))
        self.assertEqual({row["name"] for row in cameras}, {"1# Entry", "1# Exit", "2# Entry", "2# Exit"})
        self.assertEqual(
            {row["ip_address"] for row in cameras},
            {"192.168.1.144", "192.168.1.145", "192.168.1.49", "192.168.1.50"},
        )
        self.assertEqual(
            {row["controller_ip"] for row in cameras},
            {"192.168.1.61", "192.168.1.69", "192.168.1.65", "192.168.1.67"},
        )
        self.assertEqual(
            {row["display_ip"] for row in cameras},
            {"192.168.1.62", "192.168.1.70", "192.168.1.66", "192.168.1.68"},
        )

    def test_image_callback_keeps_uslpbox_at_parkwatch_offsets(self):
        import struct
        import sys
        from pathlib import Path
        host = Path(__file__).resolve().parents[1] / "tools" / "hvx_sdk_host"
        sys.path.insert(0, str(host))
        import hvx_sdk

        blob = bytearray(0x44)
        struct.pack_into("<HH", blob, 0, 1920, 1080)
        blob[8:16] = b"T285DQP\x00"
        struct.pack_into("<HHHH", blob, 0x18, 807, 303, 866, 354)
        blob[0x25] = 2
        blob[0x40] = 91
        parsed = hvx_sdk.parse_image_user_info(bytes(blob))
        self.assertEqual(parsed["plate_box"], [807, 303, 866, 354])
        self.assertEqual(parsed["image_width"], 1920)
        self.assertEqual(parsed["image_height"], 1080)
        self.assertEqual(parsed["score"], 91)
        self.assertTrue(parsed["have_vehicle"])
        self.assertTrue(hvx_sdk.plate_box_usable(parsed["plate_box"]))
        empty = {
            "image_id": 9, "plate": "T285DQP", "plate_box": [0, 0, 0, 0],
            "captured_at_epoch": 100.0, "image_width": 0, "image_height": 0,
        }
        kept = hvx_sdk.retain_plate_box(
            {"image_id": 9, "plate": "T285DQP", "plate_box": [807, 303, 866, 354],
             "captured_at_epoch": 99.0, "image_width": 1920, "image_height": 1080},
            empty,
            now=100.0,
        )
        self.assertEqual(kept["plate_box"], [807, 303, 866, 354])
        self.assertEqual(kept["image_width"], 1920)
        other_car = hvx_sdk.retain_plate_box(
            {"image_id": 9, "plate": "T285DQP", "plate_box": [807, 303, 866, 354], "captured_at_epoch": 99.0},
            {"image_id": 10, "plate": "T111AAA", "plate_box": [0, 0, 0, 0], "captured_at_epoch": 100.0},
            now=100.0,
        )
        self.assertEqual(other_car["plate_box"], [0, 0, 0, 0])

    def test_hvx_sdk_protocol_matches_qy_header(self):
        import sys
        from pathlib import Path
        host = Path(__file__).resolve().parents[1] / "tools" / "hvx_sdk_host"
        sys.path.insert(0, str(host))
        import hvx_sdk
        self.assertEqual(hvx_sdk.DC_NO_ERROR, 0)
        self.assertEqual(hvx_sdk.CONN_STATE_SUCC, 2)
        self.assertEqual(hvx_sdk.describe_rc(0), "DC_NO_ERROR")
        self.assertEqual(hvx_sdk.describe_rc(20), "DC_PASSWD_ERROR")
        self.assertTrue(any("Net_RegReportMessEx" in step for step in hvx_sdk.SDK_CONNECT_SEQUENCE))
        self.assertTrue(any("Net_StartVideo" in step for step in hvx_sdk.SDK_CONNECT_SEQUENCE))
        host_src = (Path(__file__).resolve().parents[1] / "tools" / "hvx_sdk_host" / "hvx_sdk.py").read_text(encoding="utf-8")
        self.assertIn("_camera_video_loop", host_src)
        self.assertIn("_ensure_camera_pump", host_src)
        self.assertIn("hvx-live-", host_src)
        self.assertIn("hvx-play-ui", host_src)
        self.assertEqual(hvx_sdk.T_DCImageSnap._fields_[0][0], "uiImageId")
        self.assertEqual(hvx_sdk.T_ControlGate._fields_[0][0], "ucState")
        self.assertEqual(hvx_sdk.GATE_STATE_OPEN, 1)

    def test_ocx_function_list_selects_highest_priority_gate_stream(self):
        import struct
        import sys
        from pathlib import Path
        host = Path(__file__).resolve().parents[1] / "tools" / "hvx_sdk_host"
        sys.path.insert(0, str(host))
        import hvx_sdk

        blob = bytearray(hvx_sdk.FUNCTION_LIST_BYTES)
        blob[0] = 1
        struct.pack_into("<I", blob, hvx_sdk.FUNCTION_LIST_FLAGS_OFFSET, 0x20000 | 0x10000 | 0x200)
        self.assertEqual(hvx_sdk.function_list_flags(blob), 0x30200)
        self.assertEqual(hvx_sdk.stream_type_from_function_list(blob), 4)

        blob[hvx_sdk.FUNCTION_LIST_FLAGS_OFFSET:hvx_sdk.FUNCTION_LIST_FLAGS_OFFSET + 4] = b"\x00" * 4
        self.assertEqual(hvx_sdk.stream_type_from_function_list(blob), 0)

    def test_query_function_list_is_cached_as_video_diagnostics(self):
        import ctypes
        import sys
        import threading
        from pathlib import Path
        from types import SimpleNamespace
        host = Path(__file__).resolve().parents[1] / "tools" / "hvx_sdk_host"
        sys.path.insert(0, str(host))
        import hvx_sdk

        sdk = hvx_sdk.HVXSDK.__new__(hvx_sdk.HVXSDK)
        sdk._lock = threading.Lock()
        sdk._function_lists = {}

        def function_list(handle, pointer):
            ctypes.memset(pointer, 0, hvx_sdk.FUNCTION_LIST_BYTES)
            ctypes.memmove(pointer, b"\x01", 1)
            ctypes.memmove(ctypes.c_void_p(pointer.value + hvx_sdk.FUNCTION_LIST_FLAGS_OFFSET), (0x8000).to_bytes(4, "little"), 4)
            return 0

        sdk.dll = SimpleNamespace(Net_FuntionListRsp=function_list)
        result = sdk.query_function_list(17)
        self.assertTrue(result["ok"])
        self.assertEqual(result["stream_type"], 3)
        self.assertEqual(sdk.selected_stream_type(17), 3)

    def test_jpg_drain_keeps_newest_and_reports_backlog(self):
        import hvx_sdk
        sdk = hvx_sdk.HVXSDK.__new__(hvx_sdk.HVXSDK)
        queued = [b"\xff\xd8" + bytes([i]) for i in range(10)]
        sdk._get_jpg_buffer = lambda handle: queued.pop(0) if queued else b""
        latest, backlog = sdk._latest_jpg_buffer(3)
        self.assertEqual(latest, b"\xff\xd8" + bytes([7]))
        self.assertTrue(backlog)
        self.assertEqual(len(queued), 2)
        latest, backlog = sdk._latest_jpg_buffer(3)
        self.assertEqual(latest, b"\xff\xd8" + bytes([9]))
        self.assertFalse(backlog)
        self.assertEqual(queued, [])

    def test_live_jpeg_poll_is_not_written_to_stdout(self):
        import io
        import sys
        from pathlib import Path
        host = Path(__file__).resolve().parents[1] / "tools" / "hvx_sdk_host"
        sys.path.insert(0, str(host))
        import hvx_host
        handler = hvx_host.Handler.__new__(hvx_host.Handler)
        handler.path = "/live-jpeg/2"
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            handler.log_message("GET %s", "/live-jpeg/2")
        self.assertEqual(buf.getvalue(), "")
        handler.path = "/info"
        with patch("sys.stdout", buf):
            handler.log_message("%s", "host-info")
        self.assertIn("host-info", buf.getvalue())

    def test_host_classifies_normal_windows_peer_reset_as_benign(self):
        import sys
        from pathlib import Path
        host = Path(__file__).resolve().parents[1] / "tools" / "hvx_sdk_host"
        sys.path.insert(0, str(host))
        import hvx_host
        self.assertTrue(hvx_host._is_peer_disconnect(ConnectionResetError(10054, "forcibly closed")))
        self.assertTrue(hvx_host._is_peer_disconnect(OSError("[WinError 10054] An existing connection was forcibly closed by the remote host")))
        self.assertFalse(hvx_host._is_peer_disconnect(OSError("SDK connection failed")))

    def test_vendor_candidates_use_configured_credentials(self):
        xs = vendor_candidates("192.168.1.49", "admin", "secret")
        self.assertTrue(any("/av0_0" in x and "user=admin" in x for x in xs))
        self.assertTrue(any("/av0_1" in x for x in xs))
        self.assertTrue(any(x.endswith(":554/video") for x in xs))
        self.assertTrue(any("/subvideo" in x for x in xs))
        self.assertTrue(any("password=secret" in x for x in xs))
        self.assertFalse(any("password=admin" in x for x in xs))
        self.assertTrue(any("/Streaming/Channels/101" in x for x in xs))
        self.assertTrue(any("cam/realmonitor" in x for x in xs))


if __name__ == "__main__":
    unittest.main()
