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
        for name in (
            "qrcode", "PySide6_Essentials", "fast-alpr", "opencv-python-headless",
            "pillow", "uvicorn", "alembic", "mako", "markupsafe", "python-dotenv", "greenlet",
        ):
            self.assertIn(name, req)
        pkgs = [line.split("#", 1)[0].strip().lower() for line in req.splitlines() if line.strip() and not line.strip().startswith("#")]
        self.assertTrue(all("watchfiles" not in line for line in pkgs))

    def test_receipt_qr_is_parking_identity_on_windows_desktop(self):
        routes = (ROOT / "app" / "api" / "module_routes.py").read_text(encoding="utf-8")
        self.assertIn('leaf in {"qr.png", "snapshot.jpg", "crop.jpg"}', routes)
        self.assertIn('return ("parking.sessions",)', routes)
        desktop = (ROOT / "app" / "desktop" / "main.py").read_text(encoding="utf-8")
        self.assertIn("def _qr_png_from_sources", desktop)
        self.assertIn("os.startfile", desktop)
        self.assertIn("show_printable_receipt", desktop)
        self.assertTrue(
            (ROOT / "app" / "migrations" / "alembic" / "versions" / "0005_receipt_qr_jobs.py").is_file()
        )

    def test_kit_script_copies_host_and_vendor(self):
        kit = (ROOT / "packaging" / "make_windows_kit.sh").read_text(encoding="utf-8")
        self.assertIn("OcxConfig/", kit)
        self.assertIn("python32", kit)
        self.assertIn("Install-SmartPark.ps1", kit)
        self.assertIn("Install-SmartParkServices.ps1", kit)
        self.assertIn("run_hvx_host.bat", kit)
        self.assertIn("hvx_bindings.json", kit)
        self.assertIn("field_acceptance_test.py", kit)
        self.assertIn("camera_lab.py", kit)
        self.assertIn("Run-FieldAcceptanceTest.ps1", kit)
        self.assertIn("Run-CameraLab.bat", kit)
        self.assertIn("Run-CameraLab.ps1", kit)
        self.assertIn("Wipe-SmartPark.ps1", kit)
        self.assertIn("Wipe-SmartPark.bat", kit)
        self.assertIn("verify_windows_kit.py", kit)

    def test_installer_runs_background_services_script(self):
        installer = (ROOT / "packaging" / "windows" / "Install-SmartPark.ps1").read_text(encoding="utf-8")
        self.assertIn("Install-SmartParkServices.ps1", installer)
        self.assertIn("& $svcScript -InstallDir $InstallDir", installer)
        self.assertIn("Unregister-ScheduledTask", installer)
        services = (ROOT / "packaging" / "windows" / "Install-SmartParkServices.ps1").read_text(encoding="utf-8")
        self.assertIn("SmartPark Site Service", services)
        self.assertIn("Start-ScheduledTask", services)
        self.assertTrue((ROOT / "packaging" / "windows" / "Install-SmartParkWinService.ps1").is_file())
        self.assertTrue((ROOT / "packaging" / "windows" / "Run-FieldAcceptanceTest.ps1").is_file())
        self.assertTrue((ROOT / "packaging" / "windows" / "Run-FieldAcceptanceTest.bat").is_file())
        self.assertTrue((ROOT / "packaging" / "windows" / "Run-CameraLab.ps1").is_file())
        self.assertTrue((ROOT / "packaging" / "windows" / "Run-CameraLab.bat").is_file())
        self.assertTrue((ROOT / "packaging" / "windows" / "Wipe-SmartPark.ps1").is_file())
        self.assertTrue((ROOT / "packaging" / "windows" / "Wipe-SmartPark.bat").is_file())
        installer = (ROOT / "packaging" / "windows" / "Install-SmartPark.ps1").read_text(encoding="utf-8")
        self.assertIn("Run-FieldAcceptanceTest.ps1", installer)
        self.assertIn("Run-CameraLab.ps1", installer)
        self.assertIn("Run-CameraLab.bat", installer)
        self.assertIn("Wipe-SmartPark.ps1", installer)
        self.assertIn("Wipe-SmartPark.bat", installer)

    def test_usb_payload_matches_this_rebuild(self):
        payload = ROOT / "dist" / "SmartParkEdge-Install" / "payload"
        self.assertTrue(payload.is_dir(), "Rebuild the USB kit with ./packaging/make_windows_kit.sh")
        self.assertTrue((payload / "app" / "media_service.py").is_file())
        self.assertTrue((payload / "app" / "recognition_worker.py").is_file())
        self.assertIn(
            "recognition_decoder",
            (payload / "app" / "recognition_worker.py").read_text(encoding="utf-8"),
        )
        self.assertTrue((payload / "app" / "services" / "recognition_decoder.py").is_file())
        self.assertIn("--recognition", (payload / "tools" / "camera_lab.py").read_text(encoding="utf-8"))
        lab_script = ROOT / "dist" / "SmartParkEdge-Install" / "Run-CameraLab.ps1"
        self.assertIn("[switch]$Recognition", lab_script.read_text(encoding="utf-8"))
        self.assertTrue((payload / "app" / "services" / "access.py").is_file())
        self.assertTrue((payload / "app" / "services" / "receipts.py").is_file())
        self.assertTrue((payload / "app" / "infrastructure" / "hardware" / "printers.py").is_file())
        req_payload = (payload / "requirements-windows.txt").read_text(encoding="utf-8")
        self.assertIn("qrcode", req_payload)
        self.assertIn("alembic", req_payload)
        self.assertIn("mako", req_payload)
        self.assertIn("python-dotenv", req_payload)
        self.assertIn("Vehicles", (payload / "app" / "desktop" / "main.py").read_text(encoding="utf-8"))
        self.assertIn("_qr_png_from_sources", (payload / "app" / "desktop" / "main.py").read_text(encoding="utf-8"))
        self.assertIn(
            'leaf in {"qr.png", "snapshot.jpg", "crop.jpg"}',
            (payload / "app" / "api" / "module_routes.py").read_text(encoding="utf-8"),
        )
        self.assertTrue(
            (payload / "app" / "migrations" / "alembic" / "versions" / "0005_receipt_qr_jobs.py").is_file()
        )
        self.assertIn("_ini_value", (payload / "app" / "migrations" / "runner.py").read_text(encoding="utf-8"))
        self.assertIn("Capture snapshot", (payload / "app" / "web" / "index.html").read_text(encoding="utf-8"))
        self.assertTrue((payload / "tools" / "hvx_sdk_host" / "hvx_host.py").is_file())
        self.assertTrue((payload / "tools" / "hvx_sdk_host" / "run_hvx_host.bat").is_file())
        self.assertTrue((payload / "tools" / "hvx_sdk_host" / "hvx_bindings.json").is_file())
        wheels = list((payload / "wheels").glob("*qrcode*.whl"))
        self.assertTrue(wheels, "USB wheels must include qrcode for receipt QR codes")
        names = [p.name for p in (payload / "wheels").glob("*.whl")]
        dists = [n.split("-", 1)[0].lower() for n in names]
        dist_keys = {d.replace("_", "-") for d in dists}
        for pkg in (
            "alembic", "mako", "markupsafe", "python-dotenv", "greenlet",
            "fastapi", "uvicorn", "onnxruntime", "fast-alpr", "pyside6-essentials",
            "starlette", "pydantic", "opentelemetry-api", "opencv-python-headless",
        ):
            self.assertIn(pkg, dist_keys, f"USB wheels must include {pkg} for --no-deps install")
        self.assertNotIn("watchfiles", dist_keys)
        self.assertNotIn("pyside6", dist_keys)
        dupes = sorted({d for d in dists if dists.count(d) > 1})
        self.assertEqual(dupes, [], f"USB wheels must not ship two versions of the same package: {dupes}")
        self.assertEqual(len([n for n in names if n.lower().startswith("websockets-")]), 1)

    def test_usb_payload_has_runtime_binaries_and_complete_wheels(self):
        import importlib.util

        verifier = ROOT / "packaging" / "verify_windows_kit.py"
        spec = importlib.util.spec_from_file_location("verify_windows_kit", verifier)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        payload = ROOT / "dist" / "SmartParkEdge-Install" / "payload"
        self.assertTrue(payload.is_dir(), "Rebuild the USB kit with ./packaging/make_windows_kit.sh")
        errors = mod.verify_payload(payload)
        self.assertEqual(errors, [], "\n".join(errors))
