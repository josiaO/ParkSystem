"""The Windows installer (packaging/installer) ships this application and keeps site data safe."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "packaging" / "installer"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class WindowsInstallerTests(unittest.TestCase):
    def test_production_tree_is_this_rebuild(self):
        for rel in ("app/api_main.py", "app/media_service.py", "app/recognition_worker.py",
                    "tools/hvx_sdk_host/hvx_host.py", "app/services/access.py", "app/services/receipts.py",
                    "app/infrastructure/hardware/printers.py", "app/release_tool.py"):
            self.assertTrue((ROOT / rel).is_file(), rel)
        self.assertIn("Vehicles", _read(ROOT / "app" / "desktop" / "main.py"))
        self.assertIn("Capture snapshot", _read(ROOT / "app" / "web" / "index.html"))

    def test_old_usb_kit_is_gone(self):
        self.assertFalse((ROOT / "packaging" / "windows").exists())
        self.assertFalse((ROOT / "packaging" / "make_windows_kit.sh").exists())

    def test_windows_requirements_include_receipt_and_desktop_deps(self):
        req = _read(INSTALLER / "requirements-windows.txt")
        for name in ("qrcode", "PySide6_Essentials", "fast-alpr", "opencv-python-headless",
                     "pillow", "uvicorn", "alembic", "mako", "markupsafe", "python-dotenv", "greenlet"):
            self.assertIn(name, req)
        self.assertIn("onnxruntime==1.29.0", req)
        packages = [l.split("#", 1)[0].strip().lower() for l in req.splitlines() if l.strip() and not l.strip().startswith("#")]
        self.assertTrue(all("watchfiles" not in line for line in packages))

    def test_receipt_qr_is_parking_identity_on_windows_desktop(self):
        routes = _read(ROOT / "app" / "api" / "module_routes.py")
        self.assertIn('leaf in {"qr.png", "snapshot.jpg", "crop.jpg"}', routes)
        desktop = _read(ROOT / "app" / "desktop" / "main.py")
        self.assertIn("def _qr_png_from_sources", desktop)
        self.assertIn("show_printable_receipt", desktop)

    def test_installer_offers_every_role_including_kiosk(self):
        iss = _read(INSTALLER / "Zirp.iss")
        for role in ("COMBINED", "SERVER", "EDGE", "OPERATOR", "KIOSK"):
            self.assertIn(f"'{role}'", iss)
        self.assertIn("Payment Kiosk", iss)
        ctl = _read(INSTALLER / "bin" / "zirpctl.ps1")
        self.assertIn('"KIOSK"    { return @{ Deployment = "OPERATOR_CLIENT"; Station = "KIOSK"; Services = $false', ctl)
        self.assertIn("Register-KioskTask", ctl)

    def test_rerunning_the_installer_offers_update_or_repair(self):
        """Running setup on a PC that has Zirp asks: update/repair (keep role and
        settings) or change the role first; the folder page is skipped."""
        iss = _read(INSTALLER / "Zirp.iss")
        self.assertIn("DisableDirPage=auto", iss)
        self.assertIn("MaintenancePage := CreateInputOptionPage(wpWelcome", iss)
        self.assertIn("Repair Zirp {#AppVersion}", iss)
        self.assertIn("Update to Zirp {#AppVersion}", iss)
        self.assertIn("Change the role or options of this computer", iss)
        # Only the second choice re-opens the role/kiosk/options pages.
        self.assertIn("Reconfigure := MaintenancePage.SelectedValueIndex = 1;", iss)
        self.assertIn("(IsUpgrade and not Reconfigure)", iss)
        # The installed version comes from the installer's own uninstall entry.
        self.assertIn(r"Uninstall\{6F2B8C4E-3D1A-4B7E-9F05-2A8C7D1E4B93}_is1", iss)

    def test_installer_is_per_machine_versioned_and_keeps_data(self):
        iss = _read(INSTALLER / "Zirp.iss")
        self.assertIn(r"DefaultDirName={autopf}\Zirp", iss)
        self.assertIn("PrivilegesRequired=admin", iss)
        self.assertIn(r'DestDir: "{app}\versions\{#AppVersion}"', iss)
        self.assertIn("uninsneveruninstall", iss)                       # ProgramData survives uninstall
        self.assertIn("MB_DEFBUTTON2", iss)                             # "delete data?" defaults to No
        self.assertIn("if UninstallSilent", iss)                        # silent uninstall never deletes data

    def test_upgrade_backs_up_and_switches_back_when_unhealthy(self):
        ctl = _read(INSTALLER / "bin" / "zirpctl.ps1")
        activate = ctl[ctl.index("function Invoke-Activate"):ctl.index("function Invoke-Rollback")]
        self.assertLess(activate.index("Backup-Database"), activate.index("Set-ActiveVersion $Version"))
        self.assertIn("Test-Health", activate)
        self.assertIn("Set-ActiveVersion $previous", activate)          # automatic switch-back
        rollback = ctl[ctl.index("function Invoke-Rollback"):ctl.index("function Show-Status")]
        self.assertIn("RestoreDatabase", rollback)
        self.assertIn('"RESTORE"', rollback)                            # typed confirmation

    def test_build_signs_and_scans_for_secrets(self):
        build = _read(INSTALLER / "build.ps1")
        self.assertIn("Secret scan", build)
        self.assertIn("deployment.json", build)
        self.assertIn("Set-AuthenticodeSignature", build)
        self.assertIn("/tr $TimestampUrl /td sha256", build)
        iss = _read(INSTALLER / "Zirp.iss")
        self.assertIn("SignedUninstaller=yes", iss)

    def test_lan_installer_download_serves_the_setup_file(self):
        api = _read(ROOT / "app" / "api_main.py")
        web = _read(ROOT / "app" / "web" / "index.html")
        self.assertIn("/downloads/zirp-setup.exe", api)
        self.assertIn("/downloads/zirp-setup.exe", web)
        iss = _read(INSTALLER / "Zirp.iss")
        self.assertIn(r'Source: "{srcexe}"; DestDir: "{app}\installers"', iss)


class ZirpctlRobustnessTests(unittest.TestCase):
    def setUp(self):
        self.ctl = _read(INSTALLER / "bin" / "zirpctl.ps1")
        self.activate = self.ctl[self.ctl.index("function Invoke-Activate"):self.ctl.index("function Invoke-Rollback")]

    def test_prechecks_run_before_anything_is_stopped(self):
        self.assertLess(self.activate.index("Invoke-Preflight"), self.activate.index("Stop-ZirpServices"))
        self.assertLess(self.activate.index("Invoke-Preflight"), self.activate.index("Set-ActiveVersion $Version"))
        self.assertIn("Setup stopped before changing anything", self.ctl)

    def test_health_is_decided_by_bundled_python_not_invoke_webrequest(self):
        health = self.ctl[self.ctl.index("function Test-Health"):self.ctl.index("# ------------------------------------------------------------------ database backup")]
        self.assertIn("Invoke-HealthProbe", health)
        self.assertNotIn("Invoke-WebRequest", health)
        self.assertIn("app.release_tool health", self.ctl)

    def test_failed_upgrade_restores_database_before_switching_back(self):
        failure = self.activate[self.activate.index("} catch {"):]
        self.assertLess(failure.index('@("restore", "--in", $backup, "--yes")'), failure.index("Set-ActiveVersion $previous"))

    def test_services_start_without_blocking_and_runtimes_are_not_reinstalled(self):
        start = self.ctl[self.ctl.index("function Start-ZirpServices"):self.ctl.index("function Stop-ZirpServices")]
        self.assertIn("sc.exe start", start)
        self.assertNotIn("Start-Service -Name", start)
        self.assertIn("Test-VcX64Installed", self.ctl)
        self.assertIn("Test-Vc2005X86Installed", self.ctl)

    def test_state_survives_without_registry_rights(self):
        self.assertIn("state.json", self.ctl)
        setstate = self.ctl[self.ctl.index("function Set-State"):self.ctl.index("function Add-History")]
        self.assertLess(setstate.index("Write-TextFile $StateFile"), setstate.index("New-Item -Path $RegKey"))
        iss = _read(INSTALLER / "Zirp.iss")
        self.assertIn('ValueName: "HvxAsService"', iss)
        self.assertIn('ValueName: "Role"', iss)

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell only")
    def test_no_variable_differs_from_a_parameter_only_by_case(self):
        """PowerShell names are case-insensitive: `$r = ...` overwrote a typed `[string]$R` role
        parameter and turned a result into the text "System.Collections.Hashtable"."""
        script = r'''
$errs = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($args[0], [ref]$null, [ref]$errs)
if ($errs.Count) { "PARSE $($errs.Count)"; exit 2 }
foreach ($fn in $ast.FindAll({ param($a) $a -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)) {
    $params = @()
    if ($fn.Parameters) { $params += $fn.Parameters | ForEach-Object { $_.Name.VariablePath.UserPath } }
    if ($fn.Body.ParamBlock) { $params += $fn.Body.ParamBlock.Parameters | ForEach-Object { $_.Name.VariablePath.UserPath } }
    $used = @($fn.Body.FindAll({ param($a) $a -is [System.Management.Automation.Language.AssignmentStatementAst] -and $a.Left -is [System.Management.Automation.Language.VariableExpressionAst] }, $true) | ForEach-Object { $_.Left.VariablePath.UserPath })
    $used += @($fn.Body.FindAll({ param($a) $a -is [System.Management.Automation.Language.ForEachStatementAst] }, $true) | ForEach-Object { $_.Variable.VariablePath.UserPath })
    foreach ($p in $params) { foreach ($v in $used) { if ($v -ieq $p -and $v -cne $p) { "COLLISION $($fn.Name) $p $v" } } }
}
'''
        ps = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
        probe = Path(tempfile.mkdtemp()) / "scan.ps1"
        probe.write_text(script, encoding="utf-8")
        for target in (INSTALLER / "bin" / "zirpctl.ps1", INSTALLER / "bin" / "Zirp-Kiosk.ps1", INSTALLER / "build.ps1"):
            out = subprocess.run([ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(probe), str(target)],
                                 capture_output=True, text=True, timeout=120)
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
            self.assertNotIn("COLLISION", out.stdout, f"{target.name}: {out.stdout}")


@unittest.skipUnless(os.name == "nt", "Windows PowerShell only")
class ZirpctlArgumentTests(unittest.TestCase):
    """The installer starts zirpctl with `powershell -File ... <args>` (Zirp.iss CurStepChanged).

    With -File, PowerShell passes every argument as text, so e.g. `-Switch:$true`
    cannot bind and zirpctl died before logging anything (seen on 1.0.0-rc1).
    Run the exact argument lines the installer builds; binding must succeed and
    zirpctl must reach its own checks (here: the administrator check).
    """

    def _run(self, args: str) -> subprocess.CompletedProcess:
        ps = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
        root = Path(tempfile.mkdtemp())
        (root / "bin").mkdir()
        shutil.copy(INSTALLER / "bin" / "zirpctl.ps1", root / "bin" / "zirpctl.ps1")
        cmd = f'"{ps}" -NoProfile -ExecutionPolicy Bypass -File "{root / "bin" / "zirpctl.ps1"}" {args} -Root "{root}"'
        return subprocess.run(cmd, capture_output=True, text=True, timeout=120, shell=False)

    def test_installer_argument_lines_bind(self):
        iss = _read(INSTALLER / "Zirp.iss")
        self.assertIn("' -HvxHost service'", iss)
        self.assertIn("' -HvxHost task'", iss)
        self.assertNotIn(":$true", iss)
        lines = [
            'activate -Version "1.0.0-rc1" -Role COMBINED -HvxHost service',
            'activate -Version "1.0.0-rc1" -Role EDGE -HvxHost task',
            'activate -Version "1.0.0-rc1" -Role SERVER',
            'activate -Version "1.0.0-rc1" -Role OPERATOR',
            'activate -Version "1.0.0-rc1" -Role KIOSK -KioskUser "KIOSK01\\kiosk"',
            'services stop',
            'uninstall',
        ]
        is_admin = subprocess.run(["net", "session"], capture_output=True).returncode == 0
        for line in lines:
            with self.subTest(line=line):
                out = self._run(line)
                text = out.stdout + out.stderr
                self.assertNotIn("Cannot process argument", text)
                self.assertNotIn("A parameter cannot be found", text)
                if not is_admin:
                    self.assertIn("elevated (Administrator)", text)


if __name__ == "__main__":
    unittest.main()
