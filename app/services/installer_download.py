"""Offer this site's Zirp installer to other computers on the LAN.

The Windows installer keeps a copy of itself on a Site Server
(``C:\\Program Files\\Zirp\\installers\\Zirp-Setup-<version>.exe``). The Site
Server serves that exact signed file, so an Edge Node, Operator Workstation or
Kiosk installs the same release without internet or a USB drive. The file is
the installer only: it never contains this site's database, media, logs,
credentials or deployment identity.
"""

from __future__ import annotations

import os
from pathlib import Path


def installed_root() -> Path:
    """The release folder that contains ``app/`` (``...\\Zirp\\versions\\<version>``)."""
    return Path(__file__).resolve().parents[2]


def installer_folders() -> list[Path]:
    root = installed_root()
    folders = []
    explicit = os.environ.get("SMARTPARK_INSTALLER_DIR")
    if explicit:
        folders.append(Path(explicit))
    # versions\<version>\app\services -> versions\<version> -> versions -> <install root>
    folders.append(root.parent.parent / "installers")
    folders.append(root / "installers")
    return folders


def _version_key(path: Path) -> tuple:
    version = path.stem[len("Zirp-Setup-"):]
    core = version.split("-", 1)[0].split("+", 1)[0]
    parts = tuple(int(p) if p.isdigit() else 0 for p in core.split("."))
    final = 1 if version == core else 0          # 1.4.0 sorts after 1.4.0-rc1
    return parts + (final, version)


def latest_installer() -> Path:
    """Newest ``Zirp-Setup-*.exe`` available on this computer."""
    found: list[Path] = []
    for folder in installer_folders():
        if folder.is_dir():
            found += [p for p in folder.glob("Zirp-Setup-*.exe") if p.is_file()]
    if not found:
        raise FileNotFoundError("No Zirp installer is stored on this computer")
    return max(found, key=_version_key)
