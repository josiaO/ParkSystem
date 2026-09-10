"""OS capabilities: which clients and SDK pieces can run here.

Desktop + HVX NetSDK host stay Windows-only (PE32 DLLs). The Site Service and
browser UI are the multiplatform operator path on Linux/macOS.
"""

from __future__ import annotations

import platform
import struct
import sys


def system_name() -> str:
    return platform.system() or "Unknown"


def is_windows() -> bool:
    return system_name() == "Windows"


def hvx_host_supported() -> bool:
    """NetSDK.dll loads only in a 32-bit Windows process."""
    return is_windows()


def recommended_client() -> str:
    """Primary UI for this OS: desktop on Windows, web everywhere else."""
    return "desktop" if is_windows() else "web"


def recommended_camera_adapter() -> str:
    """Site default remains hvx; non-Windows operators should pick rtsp for IP cams."""
    return "hvx" if is_windows() else "rtsp"


def platform_snapshot() -> dict:
    return {
        "os": system_name(),
        "python": sys.version.split()[0],
        "python_bits": struct.calcsize("P") * 8,
        "hvx_host_supported": hvx_host_supported(),
        "desktop_supported": is_windows(),
        "web_supported": True,
        "recommended_client": recommended_client(),
        "recommended_camera_adapter": recommended_camera_adapter(),
        "note": (
            "HVX NetSDK host and desktop installer are Windows-only. "
            "Use the browser UI at this Site Service for Linux/macOS; "
            "set camera adapter to rtsp/dahua/hikvision for non-LAPR IP cameras."
            if not is_windows()
            else "Windows site PC: desktop or browser. HVX cameras need the 32-bit SDK host."
        ),
    }
