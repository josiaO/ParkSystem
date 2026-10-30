"""Build the optional LAN installer download from the installed Zirp runtime.

The archive is intentionally assembled from the application installation, not
from the site's data directory.  It therefore contains the approved runtime
and installer scripts but never copies the database, media, logs, credentials,
or deployment identity to another computer.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
import zipfile

from app.config import settings


ARCHIVE_NAME = "Zirp-Installer.zip"
_PACKAGE_DIRS = (
    "app",
    "tools",
    "vendor",
    "python64",
    "python32",
    "wheels",
    "wheels32",
    "models",
    "documentation",
)
_PACKAGE_FILES = (
    "BUILD-INFO.txt",
    "requirements-windows.txt",
    "get-pip.py",
    "Install-SmartPark.ps1",
    "Install-SmartPark.bat",
    "Install-SmartParkServices.ps1",
)
_SKIP_PARTS = {"__pycache__", ".git", ".pytest_cache"}


def installed_root() -> Path:
    """Return the directory containing ``app/`` in both source and Windows builds."""
    return Path(__file__).resolve().parents[2]


def _files_to_package(root: Path) -> list[tuple[Path, str]]:
    files: list[tuple[Path, str]] = []
    for relative in _PACKAGE_FILES:
        path = root / relative
        if path.is_file():
            files.append((path, relative.replace(os.sep, "/")))
    for directory in _PACKAGE_DIRS:
        base = root / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or any(part in _SKIP_PARTS for part in path.parts):
                continue
            if path.suffix.lower() in {".pyc", ".pyo"}:
                continue
            relative = path.relative_to(root).as_posix()
            files.append((path, relative))
    return files


def _build_marker(root: Path) -> str:
    info = root / "BUILD-INFO.txt"
    if info.is_file():
        return hashlib.sha256(info.read_bytes()).hexdigest()
    entries = _files_to_package(root)
    digest = hashlib.sha256()
    for path, relative in entries:
        stat = path.stat()
        digest.update(relative.encode("utf-8"))
        digest.update(str(stat.st_size).encode("ascii"))
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
    return digest.hexdigest()


def build_installer_archive() -> Path:
    """Return a cached installer archive, rebuilding it after a new kit install."""
    root = installed_root()
    required = root / "app"
    if not required.is_dir():
        raise FileNotFoundError("The installed Zirp application directory is missing")
    files = _files_to_package(root)
    if not files:
        raise FileNotFoundError("No installer runtime files are available")

    cache_dir = settings.data_dir / "downloads"
    cache_dir.mkdir(parents=True, exist_ok=True)
    archive = cache_dir / ARCHIVE_NAME
    marker_path = archive.with_suffix(".sha256")
    marker = _build_marker(root)
    if archive.is_file() and marker_path.is_file() and marker_path.read_text(encoding="ascii").strip() == marker:
        return archive

    fd, temporary = tempfile.mkstemp(prefix="zirp-installer-", suffix=".zip", dir=str(cache_dir))
    os.close(fd)
    temporary_path = Path(temporary)
    try:
        with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as bundle:
            for path, relative in files:
                bundle.write(path, relative)
        os.replace(temporary_path, archive)
        marker_path.write_text(marker + "\n", encoding="ascii")
    finally:
        temporary_path.unlink(missing_ok=True)
    return archive
