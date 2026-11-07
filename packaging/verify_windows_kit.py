"""Fail the USB kit if offline payload files or --no-deps wheels are missing."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from zipfile import ZipFile

REQUIRED_DLLS = (
    "NetSDK.dll",
    "CommModule.dll",
    "PlaySdk.dll",
    "Log.dll",
    "RtspRecvSdk.dll",
    "DecodeSdk.dll",
    "ZlibHelper.dll",
)

# These are the QY/OcxConfig native runtime files used by the 32-bit host.
# Discovery helpers are shipped too, but are not required to start a stream.
QY_RUNTIME_DLLS = (
    "NetSDK.dll",
    "CommModule.dll",
    "PlaySdk.dll",
    "RtspRecvSdk.dll",
    "DecodeSdk.dll",
    "Log.dll",
    "ZlibHelper.dll",
)

REQUIRED_PYTHON64_RUNTIME = (
    "msvcp140.dll",
    "msvcp140_1.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
)

REQUIRED_MODELS = (
    "fastalpr/detector/yolo-v9-t-384-license-plates-end2end.onnx",
    "fastalpr/ocr/cct_xs_v2_global.onnx",
    "fastalpr/ocr/cct_xs_v2_global_plate_config.yaml",
)

REQUIRED_HOST = (
    "hvx_host.py",
    "hvx_sdk.py",
    "check_runtime.py",
    "run_hvx_host.bat",
    "hvx_bindings.json",
)

REQUIRED_NATIVE_STREAM_MARKERS = (
    '\"stream_backend\": \"ocxconfig_netsdk\"',
    "Net_StartVideo -> Net_AddPlayWindow -> Net_SetDrawDataOut",
    "_get_native_jpg_buffer",
    "_native_jpeg_disabled_until",
    "draw_data_primary=draw_data_rc",
)
REQUIRED_NATIVE_HOST_MARKERS = (
    REQUIRED_NATIVE_STREAM_MARKERS[0],
    REQUIRED_NATIVE_STREAM_MARKERS[1],
    "Net_SetDrawDataOut (primary decoded-frame callback)",
    "Net_GetJpgBuffer (compatibility fallback)",
    "/video-status/",
)
REQUIRED_NATIVE_SDK_MARKERS = REQUIRED_NATIVE_STREAM_MARKERS[2:] + (
    "consumer_demand_age_ms",
    "pump_last_iteration_age_ms",
    "callback_fps",
)

FORBIDDEN_WHEEL_PREFIXES = ("pyside6-", "pyside6_addons-", "watchfiles-")

# Direct names from packaging/windows/requirements-windows.txt plus pip/setuptools/wheel.
REQUIRED_DISTS = {
    "fastapi",
    "python-multipart",
    "uvicorn",
    "httptools",
    "websockets",
    "sqlalchemy",
    "pydantic",
    "pydantic-settings",
    "httpx",
    "argon2-cffi",
    "shiboken6",
    "pyside6-essentials",
    "psycopg",
    "psycopg-binary",
    "tzdata",
    "pillow",
    "numpy",
    "opencv-python-headless",
    "onnxruntime",
    "protobuf",
    "fast-alpr",
    "colorama",
    "qrcode",
    "alembic",
    "mako",
    "markupsafe",
    "typing-extensions",
    "python-dotenv",
    "greenlet",
    "pip",
    "setuptools",
    "wheel",
}


def _norm(name: str) -> str:
    return name.lower().replace("_", "-")


def _wheel_dist(filename: str) -> str:
    return _norm(filename.split("-", 1)[0])


def _wheel_version(filename: str) -> str:
    return filename.split("-", 2)[1]


def _pinned_requirements(requirements: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    if not requirements.is_file():
        return pins
    for raw in requirements.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-") or "==" not in line:
            continue
        package, version = re.split(r"\s*==\s*", line, maxsplit=1)
        package = re.sub(r"\[.*\]$", "", package).strip()
        pins[_norm(package)] = version.strip()
    return pins


def _requires_dist(wheel: Path) -> list[str]:
    with ZipFile(wheel) as zf:
        metas = [n for n in zf.namelist() if n.endswith(".dist-info/METADATA")]
        if not metas:
            return []
        text = zf.read(metas[0]).decode("utf-8", errors="replace")
    names: list[str] = []
    for line in text.splitlines():
        if not line.startswith("Requires-Dist:"):
            continue
        spec = line[len("Requires-Dist:") :].strip()
        if "extra ==" in spec or 'extra ==' in spec:
            continue
        if "python_version < '3.11'" in spec or 'python_version < "3.11"' in spec:
            continue
        if "sys_platform != 'win32'" in spec:
            continue
        name = re.split(r"[ ;<>=!~(\[]", spec, 1)[0].strip()
        if name:
            names.append(name)
    return names


def verify_payload(payload: Path) -> list[str]:
    errors: list[str] = []
    if not payload.is_dir():
        return [f"payload missing: {payload}"]

    vendor = payload / "vendor"
    for name in REQUIRED_DLLS:
        if not (vendor / name).is_file():
            errors.append(f"vendor DLL missing: {name}")
    manifest = vendor / "QY-SDK-MANIFEST.txt"
    if not manifest.is_file():
        errors.append("QY SDK manifest missing: vendor/QY-SDK-MANIFEST.txt")
    else:
        manifest_text = manifest.read_text(encoding="utf-8", errors="replace")
        for name in QY_RUNTIME_DLLS:
            if f"REQUIRED {name}" not in manifest_text:
                errors.append(f"QY SDK manifest does not mark {name} as required")
        for name in ("OcxConfig.ocx", "OcxConfigClient.exe"):
            if f"OPTIONAL {name}" not in manifest_text:
                errors.append(f"QY SDK field artifact missing from manifest: {name}")
    if not (vendor / "qy-sdk" / "OcxConfig.ocx").is_file():
        errors.append("QY SDK OCX missing: vendor/qy-sdk/OcxConfig.ocx")
    if not (vendor / "qy-sdk" / "OcxConfigClient.exe").is_file():
        errors.append("QY SDK client missing: vendor/qy-sdk/OcxConfigClient.exe")
    if not (vendor / "vc_redist.x86.exe").is_file():
        errors.append("QY 32-bit MSVC runtime missing: vendor/vc_redist.x86.exe")
    if not (vendor / "mediamtx" / "mediamtx.exe").is_file():
        errors.append("MediaMTX missing: vendor/mediamtx/mediamtx.exe")

    if not (vendor / "ffmpeg" / "bin" / "ffmpeg.exe").is_file():
        errors.append("FFmpeg missing: vendor/ffmpeg/bin/ffmpeg.exe")

    models = payload / "models"
    for rel in REQUIRED_MODELS:
        if not (models / rel).is_file():
            errors.append(f"FastALPR model missing: models/{rel}")

    host = payload / "tools" / "hvx_sdk_host"
    for name in REQUIRED_HOST:
        if not (host / name).is_file():
            errors.append(f"HVX host file missing: {name}")
    host_source = host / "hvx_host.py"
    sdk_source = host / "hvx_sdk.py"
    if host_source.is_file():
        text = host_source.read_text(encoding="utf-8")
        for marker in REQUIRED_NATIVE_HOST_MARKERS:
            if marker not in text:
                errors.append(f"HVX host does not advertise OcxConfig latest-frame delivery: {marker}")
    if sdk_source.is_file():
        text = sdk_source.read_text(encoding="utf-8")
        for marker in REQUIRED_NATIVE_SDK_MARKERS:
            if marker not in text:
                errors.append(f"HVX SDK host missing native streaming guard: {marker}")

    if not (payload / "python64" / "python.exe").is_file():
        errors.append("64-bit embeddable Python missing: python64/python.exe")
    local_runtime_complete = all((payload / "python64" / name).is_file() for name in REQUIRED_PYTHON64_RUNTIME)
    bundled_redist = payload / "vendor" / "vc_redist.x64.exe"
    if not local_runtime_complete and not bundled_redist.is_file():
        errors.append(
            "64-bit Windows runtime missing: provide python64 MSVC DLLs or vendor/vc_redist.x64.exe"
        )
    if not (payload / "python32" / "python.exe").is_file():
        errors.append("32-bit embeddable Python missing: python32/python.exe")
    if not (payload / "get-pip.py").is_file():
        errors.append("get-pip.py missing")
    if not (payload / "app" / "web" / "index.html").is_file():
        errors.append("web UI missing: app/web/index.html")
    if not any((payload / "app" / "assets").glob("*.ico")):
        errors.append("desktop application icon missing: app/assets/*.ico")
    if not any((payload / "app" / "web" / "assets").glob("*.ico")):
        errors.append("browser favicon missing: app/web/assets/*.ico")
    if not (payload / "app" / "desktop" / "main.py").is_file():
        errors.append("desktop UI missing: app/desktop/main.py")
    if not (payload / "tools" / "field_acceptance_test.py").is_file():
        errors.append("field acceptance test missing: tools/field_acceptance_test.py")
    startup = payload / "tools" / "startup_check.py"
    if not startup.is_file():
        errors.append("startup check missing: tools/startup_check.py")
    elif '"dry_run": True' not in startup.read_text(encoding="utf-8"):
        errors.append("startup check must dry-run the gate and must not pulse the barrier")
    decoder = payload / "app" / "services" / "recognition_decoder.py"
    if not decoder.is_file():
        errors.append("recognition decoder missing: app/services/recognition_decoder.py")
    worker = payload / "app" / "recognition_worker.py"
    if worker.is_file() and "recognition_decoder" not in worker.read_text(encoding="utf-8"):
        errors.append("recognition worker in the kit does not use the local MediaMTX decoder")
    lab = payload / "tools" / "camera_lab.py"
    if not lab.is_file():
        errors.append("camera lab missing: tools/camera_lab.py")
    elif "--recognition" not in lab.read_text(encoding="utf-8"):
        errors.append("camera lab in the kit has no --recognition benchmark")
    replay_lab = payload / "tools" / "camera_lab_replay.py"
    if not replay_lab.is_file():
        errors.append("camera lab replay module missing: tools/camera_lab_replay.py")
    if not (payload / "requirements-windows.txt").is_file():
        errors.append("requirements-windows.txt missing")

    wheels32_dir = payload / "wheels32"
    pillow32 = sorted(wheels32_dir.glob("pillow-*-win32.whl")) if wheels32_dir.is_dir() else []
    if len(pillow32) != 1:
        errors.append(f"expected exactly one 32-bit Pillow wheel, found {[p.name for p in pillow32]}")
    pth32 = sorted((payload / "python32").glob("python*._pth"))
    if not pth32:
        errors.append("32-bit Python path file missing: python32/python*._pth")
    elif "..\\tools\\hvx_sdk_host" not in pth32[0].read_text(encoding="utf-8", errors="replace"):
        errors.append("32-bit Python path file does not expose tools/hvx_sdk_host")

    wheels_dir = payload / "wheels"
    wheels = sorted(wheels_dir.glob("*.whl")) if wheels_dir.is_dir() else []
    if not wheels:
        errors.append("no Windows wheels in payload/wheels")
        return errors

    names = [p.name for p in wheels]
    dists = [_wheel_dist(n) for n in names]
    present = set(dists)
    pins = _pinned_requirements(payload / "requirements-windows.txt")
    for name in names:
        dist = _wheel_dist(name)
        required = pins.get(dist)
        if required is not None and _wheel_version(name) != required:
            errors.append(f"wheel {name} violates exact requirement {dist}=={required}")
    dupes = sorted({d for d in dists if dists.count(d) > 1})
    if dupes:
        errors.append(f"duplicate wheel packages: {dupes}")
    for name in names:
        lower = name.lower()
        if lower.startswith(FORBIDDEN_WHEEL_PREFIXES):
            errors.append(f"forbidden wheel in kit: {name}")

    for dist in sorted(REQUIRED_DISTS):
        if dist not in present:
            errors.append(f"required wheel missing: {dist}")

    ws = [n for n in names if n.lower().startswith("websockets-")]
    if len(ws) != 1:
        errors.append(f"expected exactly one websockets wheel, found {ws}")
    else:
        ver = ws[0].split("-")[1]
        parts = []
        for token in ver.split("."):
            try:
                parts.append(int(token))
            except ValueError:
                break
        if parts[:2] >= [17, 1]:
            errors.append(f"websockets must stay <17.1, found {ws[0]}")

    for wheel in wheels:
        for dep in _requires_dist(wheel):
            if _norm(dep) not in present:
                errors.append(f"{wheel.name} requires missing wheel {dep}")

    return errors


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: verify_windows_kit.py <payload-dir>", file=sys.stderr)
        return 2
    payload = Path(args[0])
    errors = verify_payload(payload)
    if errors:
        print("USB kit payload is incomplete:")
        for item in errors:
            print(f"  - {item}")
        return 1
    print(f"USB kit payload OK: {payload}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
