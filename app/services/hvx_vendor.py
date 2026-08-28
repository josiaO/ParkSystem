from __future__ import annotations

from pathlib import Path
import os
import struct

from app.config import settings
from app.services.site_cameras import site_layout

REQUIRED_DLLS = (
    "NetSDK.dll",
    "CommModule.dll",
    "PlaySdk.dll",
    "Log.dll",
    "RtspRecvSdk.dll",
    "DecodeSdk.dll",
)

# Literal templates recovered from OcxConfig/RtspRecvSdk.dll.
RTSP_TEMPLATES = (
    "rtsp://<ip>/av0_0&user=<username>&password=<password>",
    "rtsp://<ip>/av0_1&user=<username>&password=<password>",
    "RTSP://<ip>:<port>/video",
    "RTSP://<ip>:<port>/subvideo",
)

MACHINES = {0x14C: "i386/x86", 0x8664: "x64", 0xAA64: "arm64"}
OPTIONAL_MAGICS = {0x10B: "PE32", 0x20B: "PE32+"}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_vendor_dir() -> Path:
    env = os.environ.get("SMARTPARK_HVX_VENDOR_DIR") or settings.hvx_vendor_dir
    if env:
        return Path(env)
    ocx = repo_root() / "OcxConfig"
    copied = repo_root() / "tools" / "hvx_sdk_host" / "vendor"
    for candidate in (ocx, copied):
        if (candidate / "NetSDK.dll").exists():
            return candidate
    return ocx if ocx.exists() else copied


def pe_image_info(path: Path) -> dict:
    data = path.read_bytes()
    if data[:2] != b"MZ":
        return {"ok": False, "error": "Not a Windows MZ/PE image"}
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if data[e_lfanew:e_lfanew + 4] != b"PE\0\0":
        return {"ok": False, "error": "Not a PE image"}
    machine = struct.unpack_from("<H", data, e_lfanew + 4)[0]
    optional_magic = struct.unpack_from("<H", data, e_lfanew + 24)[0]
    return {
        "ok": True,
        "machine": MACHINES.get(machine, hex(machine)),
        "format": OPTIONAL_MAGICS.get(optional_magic, hex(optional_magic)),
        "x86": machine == 0x14C and optional_magic == 0x10B,
    }


def vendor_inventory() -> dict:
    vendor_dir = resolve_vendor_dir()
    files = {name: (vendor_dir / name).exists() for name in REQUIRED_DLLS}
    missing = [name for name, present in files.items() if not present]
    net_sdk = vendor_dir / "NetSDK.dll"
    pe = pe_image_info(net_sdk) if net_sdk.exists() else {"ok": False, "error": "NetSDK.dll not found"}
    return {
        "path": str(vendor_dir),
        "present": net_sdk.exists(),
        "product": "OcxConfig NetSDK 3.2.3.6",
        "source": "OcxConfig.ocx official camera config + NetSDK.dll",
        "official_config_ui": "OcxConfig/OcxConfig.ocx",
        "official_config_client": "OcxConfig/OcxConfigClient.exe",
        "sdk_control_port_default": 30000,
        "sdk_picture_port": 40000,
        "http_ui_port_not_sdk": 80,
        "pe": pe,
        "files": files,
        "missing": missing,
        "rtsp_templates": list(RTSP_TEMPLATES),
        "connect_sequence": [
            "Net_Init()",
            "Net_AddCamera(ip)",
            "Net_RegReportMessEx(handle) before connect",
            "Net_ConnCameraEx(handle, port=30000, timeout_seconds as unsigned short, username, password)  # OcxConfig.ocx AutoLoginEx uses timeout 3",
            "Net_ConnCamera(handle, port, timeout_seconds) fallback — OcxConfigClient uses (30000, 5)",
            "Net_QueryConnState(handle)  # 2 = CONN_STATE_SUCC",
            "Net_RegOffLineClient(handle)",
            "Net_RegImageRecvEx2(handle)  # OcxConfig.ocx official native plate+JPEG",
            "Net_RegImageRecvEx(handle) fallback — QY IPC native plate+JPEG",
            "Net_StartVideo(handle, stream, HWND) then Net_GetJpgBuffer for live frames",
        ],
        "site": site_layout(),
        "note": "NetSDK.dll is PE32/x86 stdcall. Load it only from a 32-bit Windows HVX host. Presence of this package is not an SDK connection.",
    }
