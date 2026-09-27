"""OS capabilities: which clients and SDK pieces can run here.

The PySide desktop and the Site Service run on Windows and Linux. The HVX
NetSDK host stays Windows-only because NetSDK.dll is a 32-bit Windows library.
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
    """PySide desktop is the operator UI on Windows and Linux."""
    return "desktop"


def recommended_camera_adapter() -> str:
    """Site default remains hvx; non-Windows operators should pick rtsp for IP cams."""
    return "hvx" if is_windows() else "rtsp"


def platform_snapshot() -> dict:
    return {
        "os": system_name(),
        "python": sys.version.split()[0],
        "python_bits": struct.calcsize("P") * 8,
        "hvx_host_supported": hvx_host_supported(),
        "desktop_supported": True,
        "web_supported": True,
        "recommended_client": recommended_client(),
        "recommended_camera_adapter": recommended_camera_adapter(),
        "note": (
            "Desktop runs on this OS. The HVX NetSDK host is Windows-only; "
            "use rtsp/dahua/hikvision adapters for IP cameras here."
            if not is_windows()
            else "Windows site PC: desktop or browser. HVX cameras need the 32-bit SDK host."
        ),
    }
