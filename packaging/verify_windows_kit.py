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
)

REQUIRED_MODELS = (
    "fastalpr/detector/yolo-v9-t-384-license-plates-end2end.onnx",
    "fastalpr/ocr/cct_xs_v2_global.onnx",
    "fastalpr/ocr/cct_xs_v2_global_plate_config.yaml",
)

REQUIRED_HOST = (
    "hvx_host.py",
    "hvx_sdk.py",
    "run_hvx_host.bat",
    "hvx_bindings.json",
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
    if not (vendor / "mediamtx" / "mediamtx.exe").is_file():
        errors.append("MediaMTX missing: vendor/mediamtx/mediamtx.exe")

    models = payload / "models"
    for rel in REQUIRED_MODELS:
        if not (models / rel).is_file():
            errors.append(f"FastALPR model missing: models/{rel}")

    host = payload / "tools" / "hvx_sdk_host"
    for name in REQUIRED_HOST:
        if not (host / name).is_file():
            errors.append(f"HVX host file missing: {name}")

    if not (payload / "python64" / "python.exe").is_file():
        errors.append("64-bit embeddable Python missing: python64/python.exe")
    if not (payload / "python32" / "python.exe").is_file():
        errors.append("32-bit embeddable Python missing: python32/python.exe")
    if not (payload / "get-pip.py").is_file():
        errors.append("get-pip.py missing")
    if not (payload / "app" / "web" / "index.html").is_file():
        errors.append("web UI missing: app/web/index.html")
    if not (payload / "app" / "desktop" / "main.py").is_file():
        errors.append("desktop UI missing: app/desktop/main.py")
    if not (payload / "requirements-windows.txt").is_file():
        errors.append("requirements-windows.txt missing")

    wheels_dir = payload / "wheels"
    wheels = sorted(wheels_dir.glob("*.whl")) if wheels_dir.is_dir() else []
    if not wheels:
        errors.append("no Windows wheels in payload/wheels")
        return errors

    names = [p.name for p in wheels]
    dists = [_wheel_dist(n) for n in names]
    present = set(dists)
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
