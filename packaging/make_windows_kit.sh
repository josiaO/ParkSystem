#!/usr/bin/env bash
# Build a USB install folder on Linux. Copy dist/SmartParkEdge-Install to a flash drive.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CACHE="$ROOT/packaging/cache"
OUT="${1:-$ROOT/dist/SmartParkEdge-Install}"
PY_VER="3.11.9"
PY64_URL="https://www.python.org/ftp/python/${PY_VER}/python-${PY_VER}-embed-amd64.zip"
PY32_URL="https://www.python.org/ftp/python/${PY_VER}/python-${PY_VER}-embed-win32.zip"
GETPIP_URL="https://bootstrap.pypa.io/get-pip.py"

mkdir -p "$CACHE" "$OUT/payload"

echo "Assembling application payload..."
rm -rf "$OUT/payload/app" "$OUT/payload/tools" "$OUT/payload/vendor"
mkdir -p "$OUT/payload/app" "$OUT/payload/tools/hvx_sdk_host" "$OUT/payload/vendor"

rsync -a --delete \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  "$ROOT/app/" "$OUT/payload/app/"

cp "$ROOT/tools/hvx_sdk_host/hvx_host.py" "$OUT/payload/tools/hvx_sdk_host/"
cp "$ROOT/tools/hvx_sdk_host/hvx_sdk.py" "$OUT/payload/tools/hvx_sdk_host/"
cp "$ROOT/tools/hvx_sdk_host/run_hvx_host.bat" "$OUT/payload/tools/hvx_sdk_host/"
cp "$ROOT/packaging/windows/requirements-windows.txt" "$OUT/payload/"

shopt -s nullglob
cp "$ROOT/OcxConfig/"*.dll "$OUT/payload/vendor/" 2>/dev/null || true
cp "$ROOT/Current_ParkSystem_configs/Camera_config/OcxConfig/"*.dll "$OUT/payload/vendor/" 2>/dev/null || true
shopt -u nullglob

download() {
  local url="$1" dest="$2"
  if [[ -f "$dest" ]]; then
    echo "Cached $(basename "$dest")"
    return
  fi
  echo "Downloading $(basename "$dest")..."
  curl -L --fail --retry 5 --retry-delay 2 -o "$dest.partial" "$url"
  mv "$dest.partial" "$dest"
}

echo "Bundling MediaMTX (Windows amd64, optional sidecar)..."
MEDIAMTX_VER="${MEDIAMTX_VERSION:-v1.11.3}"
MEDIAMTX_ZIP="$CACHE/mediamtx_${MEDIAMTX_VER}_windows_amd64.zip"
download "https://github.com/bluenviron/mediamtx/releases/download/${MEDIAMTX_VER}/mediamtx_${MEDIAMTX_VER}_windows_amd64.zip" \
  "$MEDIAMTX_ZIP"
rm -rf "$OUT/payload/vendor/mediamtx"
mkdir -p "$OUT/payload/vendor/mediamtx"
python3 -m zipfile -e "$MEDIAMTX_ZIP" "$OUT/payload/vendor/mediamtx"
if [[ -f "$ROOT/vendor/mediamtx/LICENSE" ]]; then
  cp "$ROOT/vendor/mediamtx/LICENSE" "$OUT/payload/vendor/mediamtx/LICENSE"
fi
if [[ ! -f "$OUT/payload/vendor/mediamtx/mediamtx.exe" ]]; then
  echo "WARNING: mediamtx.exe missing from Windows kit. Media sidecar will not start."
fi
if [[ ! -f "$OUT/payload/vendor/NetSDK.dll" ]]; then
  echo "WARNING: OcxConfig/NetSDK.dll was not copied. SDK login will fail until it is in payload/vendor."
fi

download "$PY64_URL" "$CACHE/python-${PY_VER}-embed-amd64.zip"
download "$PY32_URL" "$CACHE/python-${PY_VER}-embed-win32.zip"
download "$GETPIP_URL" "$CACHE/get-pip.py"
cp "$CACHE/get-pip.py" "$OUT/payload/get-pip.py"

echo "Extracting Windows Python..."
rm -rf "$OUT/payload/python64" "$OUT/payload/python32"
mkdir -p "$OUT/payload/python64" "$OUT/payload/python32"
python3 -m zipfile -e "$CACHE/python-${PY_VER}-embed-amd64.zip" "$OUT/payload/python64"
python3 -m zipfile -e "$CACHE/python-${PY_VER}-embed-win32.zip" "$OUT/payload/python32"
printf 'python311.zip\r\n.\r\n..\r\nLib\\site-packages\r\nimport site\r\n' > "$OUT/payload/python64/python311._pth"
printf 'python311.zip\r\n.\r\n..\\tools\\hvx_sdk_host\r\nimport site\r\n' > "$OUT/payload/python32/python311._pth"

echo "Downloading FastALPR ONNX models (offline, no HuggingFace on site)..."
MODELS_CACHE="$CACHE/models/fastalpr"
mkdir -p "$MODELS_CACHE/detector" "$MODELS_CACHE/ocr"
download "https://github.com/ankandrew/open-image-models/releases/download/assets/yolo-v9-t-384-license-plates-end2end.onnx" \
  "$MODELS_CACHE/detector/yolo-v9-t-384-license-plates-end2end.onnx"
download "https://github.com/ankandrew/cnn-ocr-lp/releases/download/arg-plates/cct_xs_v2_global.onnx" \
  "$MODELS_CACHE/ocr/cct_xs_v2_global.onnx"
download "https://github.com/ankandrew/cnn-ocr-lp/releases/download/arg-plates/cct_xs_v2_global_plate_config.yaml" \
  "$MODELS_CACHE/ocr/cct_xs_v2_global_plate_config.yaml"
rm -rf "$OUT/payload/models"
mkdir -p "$OUT/payload/models/fastalpr/detector" "$OUT/payload/models/fastalpr/ocr"
cp "$MODELS_CACHE/detector/"* "$OUT/payload/models/fastalpr/detector/"
cp "$MODELS_CACHE/ocr/"* "$OUT/payload/models/fastalpr/ocr/"

echo "Downloading Windows wheels (offline install)..."
WHEELS="$CACHE/wheels-win64"
mkdir -p "$WHEELS"
PIP="$ROOT/.venv/bin/pip"
if [[ ! -x "$PIP" ]]; then PIP="python3 -m pip"; fi
# Prefer wheels already in cache. A slow PyPI read must not abort the kit if
# a previous build already downloaded the Windows packages.
export PIP_DEFAULT_TIMEOUT="${PIP_DEFAULT_TIMEOUT:-180}"
set +e
$PIP download \
  -r "$ROOT/packaging/windows/requirements-windows.txt" \
  pip setuptools wheel \
  --dest "$WHEELS" \
  --find-links "$WHEELS" \
  --platform win_amd64 \
  --python-version 311 \
  --only-binary=:all: \
  --retries 10 \
  --timeout 180
PIP_RC=$?
set -e
if [[ $PIP_RC -ne 0 ]]; then
  echo "PyPI download failed (rc=$PIP_RC). Trying cache-only..."
  set +e
  $PIP download \
    -r "$ROOT/packaging/windows/requirements-windows.txt" \
    pip setuptools wheel \
    --dest "$WHEELS" \
    --find-links "$WHEELS" \
    --no-index \
    --platform win_amd64 \
    --python-version 311 \
    --only-binary=:all:
  PIP_RC=$?
  set -e
  if [[ $PIP_RC -ne 0 ]]; then
    if compgen -G "$WHEELS/*.whl" > /dev/null; then
      echo "WARNING: Using existing cached wheels in $WHEELS"
    else
      echo "ERROR: pip download failed and no cached Windows wheels exist."
      exit "$PIP_RC"
    fi
  fi
fi

rm -rf "$OUT/payload/wheels"
mkdir -p "$OUT/payload/wheels"
# One wheel per package (newest). Cached downloads can accumulate two versions of
# the same dist (e.g. websockets 15 and 17); pip then fails on Windows with
# ResolutionImpossible even with --no-deps.
python3 - "$WHEELS" "$OUT/payload/wheels" <<'PY'
from pathlib import Path
import shutil
import sys
from packaging.version import InvalidVersion, Version

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
skip = ("pyside6-", "pyside6_addons-")
best: dict[str, tuple[Version, Path]] = {}
for path in src.glob("*.whl"):
    name = path.name
    if name.lower().startswith(skip):
        continue
    dist, ver, *_ = name.split("-", 2)
    key = dist.lower().replace("_", "-")
    try:
        parsed = Version(ver)
    except InvalidVersion:
        parsed = Version("0")
    prev = best.get(key)
    if prev is None or parsed > prev[0]:
        best[key] = (parsed, path)
for _, path in best.values():
    shutil.copy2(path, dst / path.name)
print(f"Copied {len(best)} unique wheels (newest of each package)")
PY
cp "$ROOT/packaging/windows/requirements-windows.txt" "$OUT/payload/"

cp "$ROOT/packaging/windows/Install-SmartPark.ps1" "$OUT/"
cp "$ROOT/packaging/windows/Install-SmartPark.bat" "$OUT/"
cp "$ROOT/packaging/windows/Install-SmartParkServices.ps1" "$OUT/"
cp "$ROOT/packaging/windows/Enable-MediaMTX.ps1" "$OUT/"
cp "$ROOT/packaging/windows/MediaMTX-SoakTest.ps1" "$OUT/"
cp "$ROOT/packaging/windows/README-USB.txt" "$OUT/README.txt"
cp "$ROOT/FIRST_TEST_WINDOWS.md" "$OUT/FIRST_TEST_WINDOWS.md"

ZIP="$ROOT/dist/SmartParkEdge-USB.zip"
mkdir -p "$ROOT/dist"
rm -f "$ZIP"
( cd "$ROOT/dist" && python3 -m zipfile -c "$(basename "$ZIP")" "SmartParkEdge-Install" )

echo
echo "USB kit ready:"
echo "  Folder: $OUT"
echo "  Zip:    $ZIP"
echo "Copy the folder (or the zip) onto a flash drive."
echo "On Windows, double-click Install-SmartPark.bat"
