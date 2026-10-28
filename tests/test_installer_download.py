from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
import zipfile

from app.services import installer_download


def test_installer_archive_contains_runtime_but_not_site_data(tmp_path):
    root = tmp_path / "install"
    data = tmp_path / "data"
    (root / "app").mkdir(parents=True)
    (root / "tools").mkdir()
    (root / "app" / "api_main.py").write_text("runtime", encoding="utf-8")
    (root / "tools" / "camera_lab.py").write_text("runtime", encoding="utf-8")
    (root / "BUILD-INFO.txt").write_text("build", encoding="utf-8")
    (root / "Install-SmartPark.bat").write_text("installer", encoding="utf-8")
    (root / "smartpark.db").write_text("must not ship", encoding="utf-8")
    (root / "data").mkdir()
    (root / "data" / "secret.txt").write_text("must not ship", encoding="utf-8")

    with patch.object(installer_download, "installed_root", return_value=root), \
         patch("app.config.default_data_dir", return_value=data):
        archive = installer_download.build_installer_archive()

    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())
    assert "app/api_main.py" in names
    assert "tools/camera_lab.py" in names
    assert "Install-SmartPark.bat" in names
    assert "smartpark.db" not in names
    assert "data/secret.txt" not in names
