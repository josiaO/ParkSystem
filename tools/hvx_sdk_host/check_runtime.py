"""Check the vendor DLL loader without calling SDK/camera/relay functions."""
from __future__ import annotations
import argparse
import ctypes
import os
from pathlib import Path
import struct

DLLS = ('Log.dll', 'CommModule.dll', 'DecodeSdk.dll', 'RtspRecvSdk.dll', 'PlaySdk.dll', 'NetSDK.dll')
RUNTIME_URL = 'https://www.microsoft.com/en-gb/download/details.aspx?id=26347'


def check(vendor: Path) -> list[str]:
    if os.name != 'nt' or struct.calcsize('P') != 4:
        return ['Run this check with the bundled 32-bit Windows python32/python.exe.']
    if not vendor.is_dir():
        return [f'Vendor directory missing: {vendor}']
    errors = []
    try:
        from PIL import Image
        image = Image.new("RGB", (2, 2), "black")
        image.close()
    except Exception as exc:
        errors.append(f"32-bit host image encoder unavailable (Pillow): {exc}")
    loaded = []
    with os.add_dll_directory(str(vendor.resolve())):
        for name in DLLS:
            path = vendor / name
            if not path.is_file():
                errors.append(f'Missing vendor DLL: {name}')
                continue
            try:
                loaded.append(ctypes.WinDLL(str(path.resolve())))
            except OSError as exc:
                errors.append(f'{name}: Windows loader error {getattr(exc, "winerror", None)}: {exc}')
    if errors:
        errors.append('This vendor SDK imports MSVCR80.dll. Check Microsoft Visual C++ 2005 SP1 x86 runtime and keep the vendor DLL set matched. Official runtime: ' + RUNTIME_URL)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vendor-dir', type=Path, required=True)
    args = parser.parse_args()
    errors = check(args.vendor_dir)
    print('\n'.join(errors) if errors else 'Vendor DLL loader check passed (no camera connection attempted).')
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
