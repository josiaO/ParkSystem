import unittest

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
        self.assertEqual(hvx_sdk.T_DCImageSnap._fields_[0][0], "uiImageId")
        self.assertEqual(hvx_sdk.T_ControlGate._fields_[0][0], "ucState")
        self.assertEqual(hvx_sdk.GATE_STATE_OPEN, 1)

    def test_vendor_candidates_use_configured_credentials(self):
        xs = vendor_candidates("192.168.1.49", "admin", "secret")
        self.assertTrue(any("/av0_0" in x and "user=admin" in x for x in xs))
        self.assertTrue(any("/av0_1" in x for x in xs))
        self.assertTrue(any(x.endswith(":554/video") for x in xs))
        self.assertTrue(any("/subvideo" in x for x in xs))
        self.assertTrue(any("password=secret" in x for x in xs))
        self.assertFalse(any("password=admin" in x for x in xs))


if __name__ == "__main__":
    unittest.main()
