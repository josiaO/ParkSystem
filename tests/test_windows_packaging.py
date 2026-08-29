"""The Windows USB kit must ship this rebuild, not smartpark_edge_fastapi."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class WindowsPackagingTests(unittest.TestCase):
    def test_production_tree_is_this_rebuild(self):
        self.assertTrue((ROOT / "app" / "api_main.py").is_file())
        self.assertTrue((ROOT / "app" / "media_service.py").is_file())
        self.assertTrue((ROOT / "app" / "recognition_worker.py").is_file())
        self.assertTrue((ROOT / "docs" / "MEDIA-ARCHITECTURE.md").is_file())
        self.assertTrue((ROOT / "docs" / "MIGRATION-AND-ROLLBACK.md").is_file())
        self.assertTrue((ROOT / "tools" / "hvx_sdk_host" / "hvx_host.py").is_file())
        self.assertTrue((ROOT / "app" / "services" / "access.py").is_file())
        self.assertTrue((ROOT / "app" / "services" / "receipts.py").is_file())
        self.assertTrue((ROOT / "app" / "infrastructure" / "hardware" / "printers.py").is_file())
        self.assertIn("Vehicles", (ROOT / "app" / "desktop" / "main.py").read_text(encoding="utf-8"))
        self.assertIn("Capture snapshot", (ROOT / "app" / "web" / "index.html").read_text(encoding="utf-8"))

    def test_old_fastapi_tree_is_archive_only(self):
        old = ROOT / "smartpark_edge_fastapi"
        if not old.is_dir():
            old = ROOT.parent / "smartpark_edge_fastapi"
        if not old.is_dir():
            self.skipTest("smartpark_edge_fastapi not present in current workspace")
        self.assertNotEqual(old.resolve(), ROOT.resolve())
        kit = (ROOT / "packaging" / "make_windows_kit.sh").read_text(encoding="utf-8")
        self.assertNotIn("smartpark_edge_fastapi", kit)
        self.assertIn('"$ROOT/app/"', kit)
        self.assertIn("hvx_host.py", kit)

    def test_windows_requirements_include_receipt_and_desktop_deps(self):
        req = (ROOT / "packaging" / "windows" / "requirements-windows.txt").read_text(encoding="utf-8")
        for name in ("qrcode", "PySide6_Essentials", "fast-alpr", "opencv-python-headless", "pillow", "uvicorn"):
            self.assertIn(name, req)
        pkgs = [line.split("#", 1)[0].strip().lower() for line in req.splitlines() if line.strip() and not line.strip().startswith("#")]
        self.assertTrue(all("watchfiles" not in line for line in pkgs))

    def test_kit_script_copies_host_and_vendor(self):
        kit = (ROOT / "packaging" / "make_windows_kit.sh").read_text(encoding="utf-8")
        self.assertIn("OcxConfig/", kit)
        self.assertIn("python32", kit)
        self.assertIn("Install-SmartPark.ps1", kit)
        self.assertIn("Install-SmartParkServices.ps1", kit)
        self.assertIn("run_hvx_host.bat", kit)

    def test_installer_runs_background_services_script(self):
        installer = (ROOT / "packaging" / "windows" / "Install-SmartPark.ps1").read_text(encoding="utf-8")
        self.assertIn("Install-SmartParkServices.ps1", installer)
        self.assertIn("& $svcScript -InstallDir $InstallDir", installer)
        self.assertIn("Unregister-ScheduledTask", installer)
        services = (ROOT / "packaging" / "windows" / "Install-SmartParkServices.ps1").read_text(encoding="utf-8")
        self.assertIn("SmartPark Site Service", services)
        self.assertIn("Start-ScheduledTask", services)

    def test_usb_payload_matches_this_rebuild(self):
        payload = ROOT / "dist" / "SmartParkEdge-Install" / "payload"
        self.assertTrue(payload.is_dir(), "Rebuild the USB kit with ./packaging/make_windows_kit.sh")
        self.assertTrue((payload / "app" / "media_service.py").is_file())
        self.assertTrue((payload / "app" / "recognition_worker.py").is_file())
        self.assertTrue((payload / "app" / "services" / "access.py").is_file())
        self.assertTrue((payload / "app" / "services" / "receipts.py").is_file())
        self.assertTrue((payload / "app" / "infrastructure" / "hardware" / "printers.py").is_file())
        self.assertIn("qrcode", (payload / "requirements-windows.txt").read_text(encoding="utf-8"))
        self.assertIn("Vehicles", (payload / "app" / "desktop" / "main.py").read_text(encoding="utf-8"))
        self.assertIn("Capture snapshot", (payload / "app" / "web" / "index.html").read_text(encoding="utf-8"))
        self.assertTrue((payload / "tools" / "hvx_sdk_host" / "hvx_host.py").is_file())
        self.assertTrue((payload / "tools" / "hvx_sdk_host" / "run_hvx_host.bat").is_file())
        wheels = list((payload / "wheels").glob("*qrcode*.whl"))
        self.assertTrue(wheels, "USB wheels must include qrcode for receipt QR codes")
        names = [p.name for p in (payload / "wheels").glob("*.whl")]
        dists = [n.split("-", 1)[0].lower() for n in names]
        dupes = sorted({d for d in dists if dists.count(d) > 1})
        self.assertEqual(dupes, [], f"USB wheels must not ship two versions of the same package: {dupes}")
        self.assertEqual(len([n for n in names if n.lower().startswith("websockets-")]), 1)
