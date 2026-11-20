from __future__ import annotations

from unittest.mock import patch

from app.services import installer_download


def test_newest_setup_is_served_and_site_data_is_never_a_candidate(tmp_path):
    root = tmp_path / "Zirp"
    release = root / "versions" / "1.4.0"
    (release / "app").mkdir(parents=True)
    installers = root / "installers"
    installers.mkdir()
    for name in ("Zirp-Setup-1.3.2.exe", "Zirp-Setup-1.4.0-rc1.exe", "Zirp-Setup-1.4.0.exe"):
        (installers / name).write_bytes(b"MZ")
    (installers / "smartpark.db").write_text("must not ship", encoding="utf-8")

    with patch.object(installer_download, "installed_root", return_value=release):
        assert installer_download.latest_installer().name == "Zirp-Setup-1.4.0.exe"


def test_missing_installer_is_reported(tmp_path):
    release = tmp_path / "versions" / "1.0.0"
    release.mkdir(parents=True)
    with patch.object(installer_download, "installed_root", return_value=release):
        try:
            installer_download.latest_installer()
        except FileNotFoundError:
            return
    raise AssertionError("expected FileNotFoundError")
