"""Release tooling: DB backup/restore helper, kiosk station config, installer role file."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run_tool(db_url: str, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, SMARTPARK_DATABASE_URL=db_url, SMARTPARK_LATENCY_TRACE="0", PYTHONPATH=str(ROOT))
    code = (
        "import sys; sys.path.insert(0, %r); from app.release_tool import main; raise SystemExit(main(%r))"
        % (str(ROOT), list(args))
    )
    return subprocess.run([sys.executable, "-c", code], env=env, cwd=str(ROOT), capture_output=True, text=True, timeout=120)


class ReleaseToolTests(unittest.TestCase):
    def test_sqlite_backup_and_restore_round_trip(self):
        folder = Path(tempfile.mkdtemp())
        db = folder / "site.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE visits (id INTEGER PRIMARY KEY, plate TEXT)")
        conn.execute("INSERT INTO visits (plate) VALUES ('T100AAA')")
        conn.commit(); conn.close()
        url = f"sqlite:///{db.as_posix()}"
        dump = folder / "backups" / "before.sql"
        made = _run_tool(url, "backup", "--out", str(dump))
        self.assertEqual(made.returncode, 0, made.stderr)
        meta = json.loads(Path(str(dump) + ".json").read_text())
        self.assertEqual(meta["dialect"], "sqlite")
        self.assertIn("T100AAA", dump.read_text())

        conn = sqlite3.connect(db)
        conn.execute("INSERT INTO visits (plate) VALUES ('T777XYZ')")
        conn.commit(); conn.close()

        refused = _run_tool(url, "restore", "--in", str(dump))
        self.assertEqual(refused.returncode, 2)          # needs --yes
        done = _run_tool(url, "restore", "--in", str(dump), "--yes")
        self.assertEqual(done.returncode, 0, done.stderr)
        kept = Path(json.loads(done.stdout.strip().splitlines()[-1])["kept_previous"])
        self.assertTrue(kept.is_file())                  # the replaced database is kept
        conn = sqlite3.connect(db)
        plates = [row[0] for row in conn.execute("SELECT plate FROM visits ORDER BY id")]
        conn.close()
        self.assertEqual(plates, ["T100AAA"])


class HealthAndCheckTests(unittest.TestCase):
    def test_health_reports_unreachable_api_without_raising(self):
        out = _run_tool("sqlite://", "health", "--url", "http://127.0.0.1:9/health/live", "--timeout", "1")
        self.assertEqual(out.returncode, 1, out.stderr)
        self.assertTrue(out.stdout.strip())

    def test_check_passes_on_a_pc_that_is_not_set_up_yet(self):
        folder = Path(tempfile.mkdtemp())
        env = dict(os.environ, PROGRAMDATA=str(folder), SMARTPARK_LATENCY_TRACE="0")
        env.pop("SMARTPARK_DATABASE_URL", None)   # a database URL alone counts as an existing site
        code = "import sys; sys.path.insert(0, %r); from app.release_tool import main; raise SystemExit(main(['check']))" % str(ROOT)
        out = subprocess.run([sys.executable, "-c", code], env=env, cwd=str(ROOT), capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr)
        report = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertFalse(report["configured"])
        self.assertEqual(report["problems"], [])


class StationConfigTests(unittest.TestCase):
    def test_kiosk_station_only_for_operator_client(self):
        from app.deployment import _from_mapping

        kiosk = _from_mapping({"role": "OPERATOR_CLIENT", "station": "kiosk", "installation_id": "x"})
        self.assertTrue(kiosk.is_kiosk)
        self.assertFalse(_from_mapping({"role": "OPERATOR_CLIENT", "installation_id": "x"}).is_kiosk)
        with self.assertRaises(ValueError):
            _from_mapping({"role": "SITE_SERVER", "station": "KIOSK", "installation_id": "x"})
        with self.assertRaises(ValueError):
            _from_mapping({"role": "OPERATOR_CLIENT", "station": "ATM", "installation_id": "x"})

    def test_installed_role_file_sets_defaults_without_overriding(self):
        from app.desktop import launch

        folder = Path(tempfile.mkdtemp())
        role = folder / "role.json"
        role.write_text(json.dumps({"deployment_role": "OPERATOR_CLIENT", "station": "KIOSK",
                                    "deployment_profile": "PRODUCTION"}), encoding="utf-8")
        keys = ("SMARTPARK_ROLE_LOCKED", "SMARTPARK_STATION", "SMARTPARK_DEPLOYMENT_PROFILE")
        saved = {k: os.environ.pop(k, None) for k in keys}
        original = launch.installed_role_path
        try:
            launch.installed_role_path = lambda: role
            os.environ["SMARTPARK_DEPLOYMENT_PROFILE"] = "DEVELOPMENT"   # explicit env wins
            launch._apply_installed_role()
            self.assertEqual(os.environ["SMARTPARK_ROLE_LOCKED"], "OPERATOR_CLIENT")
            self.assertEqual(os.environ["SMARTPARK_STATION"], "KIOSK")
            self.assertEqual(os.environ["SMARTPARK_DEPLOYMENT_PROFILE"], "DEVELOPMENT")
        finally:
            launch.installed_role_path = original
            for k, v in saved.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v

    def test_machine_settings_file_is_preferred(self):
        from app import config

        folder = Path(tempfile.mkdtemp())
        machine = folder / "zirp.env"
        machine.write_text("SMARTPARK_SITE_NAME=Test\n", encoding="utf-8")
        old = os.environ.get("SMARTPARK_ENV_FILE")
        try:
            os.environ["SMARTPARK_ENV_FILE"] = str(machine)
            self.assertEqual(config.env_file_location(), machine.resolve())
        finally:
            if old is None:
                os.environ.pop("SMARTPARK_ENV_FILE", None)
            else:
                os.environ["SMARTPARK_ENV_FILE"] = old


if __name__ == "__main__":
    unittest.main()
