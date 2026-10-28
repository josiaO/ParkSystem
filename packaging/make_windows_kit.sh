#!/usr/bin/env bash
# Build the maintainer Windows test/distribution package on Linux. The portable
# folder may be copied to removable media for field testing; it is not the
# production installation workflow described by the installed documentation.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CACHE="$ROOT/packaging/cache"
OUT="${1:-$ROOT/dist/SmartParkEdge-Install}"
PY_VER="3.11.9"
PY64_URL="https://www.python.org/ftp/python/${PY_VER}/python-${PY_VER}-embed-amd64.zip"
PY32_URL="https://www.python.org/ftp/python/${PY_VER}/python-${PY_VER}-embed-win32.zip"
GETPIP_URL="https://bootstrap.pypa.io/get-pip.py"

if [[ -z "$OUT" || "$OUT" == "/" || "$OUT" == "$ROOT" || "$OUT" == "$ROOT/" ]]; then
  echo "Refusing to delete unsafe output path: '$OUT'" >&2
  exit 2
fi
rm -rf -- "$OUT"
mkdir -p "$CACHE" "$OUT/payload"

echo "Preparing existing Zirp icon artwork..."
python3 "$ROOT/packaging/resize_zirp_icon.py" \
  --source "$ROOT/app/assets/zirp-logo.png" \
  --output "$ROOT/app/assets/zirp.ico" \
  --output "$ROOT/app/web/assets/zirp.ico" \
  --output "$ROOT/docs-site/zirp.ico"

echo "Assembling application payload..."
rm -rf "$OUT/payload/app" "$OUT/payload/tools" "$OUT/payload/vendor"
mkdir -p "$OUT/payload/app" "$OUT/payload/tools/hvx_sdk_host" "$OUT/payload/vendor"

rsync -a --delete \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  "$ROOT/app/" "$OUT/payload/app/"

cp "$ROOT/tools/hvx_sdk_host/hvx_host.py" "$OUT/payload/tools/hvx_sdk_host/"
cp "$ROOT/tools/hvx_sdk_host/hvx_sdk.py" "$OUT/payload/tools/hvx_sdk_host/"
cp "$ROOT/tools/hvx_sdk_host/check_runtime.py" "$OUT/payload/tools/hvx_sdk_host/"
cp "$ROOT/tools/hvx_sdk_host/run_hvx_host.bat" "$OUT/payload/tools/hvx_sdk_host/"
cp "$ROOT/tools/field_acceptance_test.py" "$OUT/payload/tools/"
cp "$ROOT/tools/startup_check.py" "$OUT/payload/tools/"
cp "$ROOT/tools/field_realtime_report.py" "$OUT/payload/tools/"
cp "$ROOT/tools/camera_lab.py" "$OUT/payload/tools/"
cp "$ROOT/tools/camera_lab_replay.py" "$OUT/payload/tools/"
cp "$ROOT/tools/__init__.py" "$OUT/payload/tools/"
if [[ -f "$ROOT/tools/hvx_sdk_host/hvx_bindings.json" ]]; then
  cp "$ROOT/tools/hvx_sdk_host/hvx_bindings.json" "$OUT/payload/tools/hvx_sdk_host/"
elif [[ -f "$ROOT/Current_ParkSystem_configs/Camera_config/OcxConfig/hvx_bindings.json" ]]; then
  cp "$ROOT/Current_ParkSystem_configs/Camera_config/OcxConfig/hvx_bindings.json" "$OUT/payload/tools/hvx_sdk_host/"
fi
cp "$ROOT/packaging/windows/requirements-windows.txt" "$OUT/payload/"

HVX_VENDOR_SOURCE="${SMARTPARK_HVX_VENDOR_DIR:-}"
if [[ -z "$HVX_VENDOR_SOURCE" ]]; then
  for candidate in "$ROOT/OcxConfig" "$ROOT/vendor" "$ROOT/tools/hvx_sdk_host/vendor" \
                  "$ROOT/Current_ParkSystem_configs/Camera_config/OcxConfig"; do
    if [[ -f "$candidate/NetSDK.dll" ]]; then
      HVX_VENDOR_SOURCE="$candidate"
      break
    fi
  done
fi
if [[ -z "$HVX_VENDOR_SOURCE" || ! -f "$HVX_VENDOR_SOURCE/NetSDK.dll" ]]; then
  echo "ERROR: SmartPark HVX vendor DLLs are not bundled in this checkout." >&2
  echo "Provide SMARTPARK_HVX_VENDOR_DIR containing NetSDK.dll and its companion DLLs." >&2
  echo "The deleted ParkWatch reference is not a supported vendor source." >&2
  exit 1
fi
shopt -s nullglob
vendor_dlls=("$HVX_VENDOR_SOURCE/"*.dll)
shopt -u nullglob
if [[ ${#vendor_dlls[@]} -eq 0 ]]; then
  echo "ERROR: no DLLs found in SmartPark HVX vendor directory: $HVX_VENDOR_SOURCE" >&2
  exit 1
fi
cp "${vendor_dlls[@]}" "$OUT/payload/vendor/"

download() {
  local url="$1" dest="$2"
  if [[ -f "$dest" ]]; then
    echo "Cached $(basename "$dest")"
    return
  fi
  echo "Downloading $(basename "$dest")..."
  rm -f "$dest.partial"
  curl --http1.1 -L --fail --retry 5 --retry-delay 2 -o "$dest.partial" "$url"
  mv "$dest.partial" "$dest"
}

echo "Bundling FFmpeg (Windows amd64)..."
FFMPEG_ARCHIVE="imageio_ffmpeg-0.6.0-py3-none-win_amd64.whl"
FFMPEG_SHA256="02fa47c83703c37df6bfe4896aab339013f62bf02c5ebf2dce6da56af04ffc0a"
download "https://files.pythonhosted.org/packages/2c/c6/fa760e12a2483469e2bf5058c5faff664acf66cadb4df2ad6205b016a73d/imageio_ffmpeg-0.6.0-py3-none-win_amd64.whl" "$CACHE/$FFMPEG_ARCHIVE"
echo "$FFMPEG_SHA256  $CACHE/$FFMPEG_ARCHIVE" | sha256sum --check --status
python3 - "$CACHE/$FFMPEG_ARCHIVE" "$OUT/payload/vendor/ffmpeg" <<'PYFFMPEG'
import sys
import zipfile
from pathlib import Path
archive, output = sys.argv[1], Path(sys.argv[2])
(output / "bin").mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(archive) as z:
    binary = z.read("imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe")
    if not binary.startswith(b"MZ"):
        raise SystemExit("FFmpeg is not a Windows executable")
    (output / "bin" / "ffmpeg.exe").write_bytes(binary)
    (output / "IMAGEIO-LICENSE.txt").write_bytes(z.read("imageio_ffmpeg-0.6.0.dist-info/LICENSE"))
PYFFMPEG
cp "$ROOT/packaging/licenses/FFmpeg-GPL-3.txt" "$OUT/payload/vendor/ffmpeg/LICENSE.txt"
cat > "$OUT/payload/vendor/ffmpeg/PROVENANCE.txt" <<'FFMPEGINFO'
FFmpeg 7.1 Windows x64, distributed by imageio-ffmpeg 0.6.0.
Archive SHA256: 02fa47c83703c37df6bfe4896aab339013f62bf02c5ebf2dce6da56af04ffc0a
Distribution: https://pypi.org/project/imageio-ffmpeg/0.6.0/
Build scripts: https://github.com/imageio/imageio-ffmpeg/tree/v0.6.0/binaries
FFmpeg source: https://github.com/FFmpeg/FFmpeg/tree/n7.1
FFmpeg is a separate executable, licensed under GPL version 3.
The imageio packaging license is included separately.
FFMPEGINFO

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
  echo "ERROR: mediamtx.exe missing from Windows kit."
  exit 1
fi
if [[ ! -f "$OUT/payload/vendor/NetSDK.dll" ]]; then
  echo "ERROR: OcxConfig/NetSDK.dll was not copied. SDK login will fail."
  exit 1
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
# ONNX Runtime's Windows wheel depends on the MSVC C++ runtime. The
# embeddable Python archive carries vcruntime140*.dll but not MSVCP140*.dll,
# so a fresh Windows PC otherwise fails with:
# "DLL load failed while importing onnxruntime_pybind11_state".
VC_RUNTIME_SOURCE="${SMARTPARK_MSVC_RUNTIME_DIR:-}"
MSVC_REDIST_SOURCE="${SMARTPARK_MSVC_REDIST_EXE:-$CACHE/msvc/vc_redist.x64.exe}"
if [[ -z "$VC_RUNTIME_SOURCE" ]]; then
  for candidate in \
    "$ROOT/packaging/windows/runtime"; do
    if [[ -f "$candidate/msvcp140.dll" && -f "$candidate/msvcp140_1.dll" ]]; then
      VC_RUNTIME_SOURCE="$candidate"
      break
    fi
  done
fi
if [[ -n "$VC_RUNTIME_SOURCE" ]]; then
  for dll in msvcp140.dll msvcp140_1.dll; do
    if [[ ! -f "$VC_RUNTIME_SOURCE/$dll" ]]; then
      echo "ERROR: required Windows runtime DLL is missing: $VC_RUNTIME_SOURCE/$dll" >&2
      exit 1
    fi
    cp "$VC_RUNTIME_SOURCE/$dll" "$OUT/payload/python64/$dll"
  done
  # Prefer the complete, matching MSVC runtime set when the source includes it.
  # Mixing an older MSVCP pair with a newer VCRUNTIME can make ORT fail inside
  # DLL initialization even though every required filename is present.
  for dll in vcruntime140.dll vcruntime140_1.dll msvcp140_2.dll msvcp140_atomic_wait.dll msvcp140_codecvt_ids.dll; do
    if [[ -f "$VC_RUNTIME_SOURCE/$dll" ]]; then
      cp "$VC_RUNTIME_SOURCE/$dll" "$OUT/payload/python64/$dll"
    fi
  done
elif [[ -f "$MSVC_REDIST_SOURCE" ]]; then
  # The official Microsoft bootstrapper is intentionally used when the host
  # cannot extract its embedded CAB. It is run elevated by the Windows
  # installer before the ONNX import self-test, and avoids shipping a mixed
  # or stale local MSVCP/VCRUNTIME pair beside embedded Python.
  MSVC_REDIST_SHA256="843068991daaa1f73ad9f6239bce4d0f6a07a51f18c37ea2a867e9beca71295c"
  actual_redist_sha256="$(sha256sum "$MSVC_REDIST_SOURCE" | awk '{print $1}')"
  if [[ "$actual_redist_sha256" != "$MSVC_REDIST_SHA256" ]]; then
    echo "ERROR: Microsoft VC++ redistributable hash mismatch: $MSVC_REDIST_SOURCE" >&2
    echo "Expected $MSVC_REDIST_SHA256, got $actual_redist_sha256" >&2
    exit 1
  fi
  cp "$MSVC_REDIST_SOURCE" "$OUT/payload/vendor/vc_redist.x64.exe"
  echo "Bundled verified Microsoft VC++ x64 redistributable installer."
else
  echo "ERROR: MSVC runtime DLLs are not bundled in this checkout." >&2
  echo "Provide SMARTPARK_MSVC_RUNTIME_DIR containing msvcp140.dll and msvcp140_1.dll," >&2
  echo "or SMARTPARK_MSVC_REDIST_EXE pointing to the official vc_redist.x64.exe." >&2
  exit 1
fi
printf 'python311.zip\r\n.\r\n..\r\nLib\\site-packages\r\nimport site\r\n' > "$OUT/payload/python64/python311._pth"
printf 'python311.zip\r\n.\r\n..\\tools\\hvx_sdk_host\r\nLib\\site-packages\r\nimport site\r\n' > "$OUT/payload/python32/python311._pth"

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
PIP_DOWNLOAD_FLAGS=(
  --dest "$WHEELS"
  --find-links "$WHEELS"
  --platform win_amd64
  --python-version 311
  --only-binary=:all:
  --retries 10
  --timeout 180
)
if [[ "${SMARTPARK_BUILD_OFFLINE:-0}" == "1" ]]; then
  PIP_DOWNLOAD_FLAGS+=(--no-index)
fi
set +e
$PIP download \
  -r "$ROOT/packaging/windows/requirements-windows.txt" \
  pip setuptools wheel \
  "${PIP_DOWNLOAD_FLAGS[@]}"
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
# One wheel per package (newest unless requirements pin an exact version).
# Cached downloads can accumulate multiple versions of the same dist; selecting
# newest blindly would silently violate an exact safety pin such as the Windows
# ONNX Runtime version below.
python3 - "$WHEELS" "$OUT/payload/wheels" "$ROOT/packaging/windows/requirements-windows.txt" <<'PY'
from pathlib import Path
import shutil
import sys
import re
from packaging.version import InvalidVersion, Version

src, dst, requirements = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
skip = ("pyside6-", "pyside6_addons-", "watchfiles-")
pinned: dict[str, Version] = {}
for raw in requirements.read_text(encoding="utf-8").splitlines():
    line = raw.split("#", 1)[0].strip()
    if not line or line.startswith("-") or "==" not in line:
        continue
    package, version = re.split(r"\s*==\s*", line, maxsplit=1)
    package = re.sub(r"\[.*\]$", "", package).strip().lower().replace("_", "-")
    try:
        pinned[package] = Version(version.strip())
    except InvalidVersion:
        continue
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
    required = pinned.get(key)
    if required is not None and parsed != required:
        continue
    if key == "websockets" and parsed >= Version("17.1"):
        continue
    prev = best.get(key)
    if prev is None or parsed > prev[0]:
        best[key] = (parsed, path)
for _, path in best.values():
    shutil.copy2(path, dst / path.name)
print(f"Copied {len(best)} unique wheels (newest of each package)")
PY
cp "$ROOT/packaging/windows/requirements-windows.txt" "$OUT/payload/"

echo "Downloading 32-bit Windows Pillow for the QY SDK host..."
WHEELS32="$CACHE/wheels-win32"
mkdir -p "$WHEELS32"
if ! compgen -G "$WHEELS32/pillow-*.whl" > /dev/null; then
  set +e
  $PIP download pillow \
    --dest "$WHEELS32" \
    --platform win32 \
    --python-version 311 \
    --implementation cp \
    --only-binary=:all: \
    --no-deps \
    --retries 10 \
    --timeout 180
  PILLOW32_RC=$?
  set -e
  if [[ $PILLOW32_RC -ne 0 ]]; then
    echo "ERROR: A CPython 3.11 win32 Pillow wheel is required for the 32-bit QY host."
    exit "$PILLOW32_RC"
  fi
fi
rm -rf "$OUT/payload/wheels32"
mkdir -p "$OUT/payload/wheels32"
cp "$WHEELS32"/pillow-*.whl "$OUT/payload/wheels32/"

cp "$ROOT/packaging/windows/Install-SmartPark.ps1" "$OUT/"
cp "$ROOT/packaging/windows/Install-SmartPark.bat" "$OUT/"
cp "$ROOT/packaging/windows/Install-SmartPark-Server.bat" "$OUT/"
cp "$ROOT/packaging/windows/Install-SmartPark-Node.bat" "$OUT/"
cp "$ROOT/packaging/windows/Install-SmartPark-Client.bat" "$OUT/"
cp "$ROOT/packaging/windows/Install-SmartParkServices.ps1" "$OUT/"
cp "$ROOT/packaging/windows/Install-SmartParkWinService.ps1" "$OUT/"
cp "$ROOT/packaging/windows/Enable-MediaMTX.ps1" "$OUT/"
cp "$ROOT/packaging/windows/MediaMTX-SoakTest.ps1" "$OUT/"
cp "$ROOT/packaging/windows/Run-FieldAcceptanceTest.ps1" "$OUT/"
cp "$ROOT/packaging/windows/Run-FieldAcceptanceTest.bat" "$OUT/"
cp "$ROOT/packaging/windows/Run-StartupCheck.ps1" "$OUT/"
cp "$ROOT/packaging/windows/Run-StartupCheck.bat" "$OUT/"
cp "$ROOT/packaging/windows/Run-ServerDiagnostics.ps1" "$OUT/"
cp "$ROOT/packaging/windows/Run-ServerDiagnostics.bat" "$OUT/"
cp "$ROOT/packaging/windows/Run-RecordedMediaTests.ps1" "$OUT/"
cp "$ROOT/packaging/windows/Run-RecordedMediaTests.bat" "$OUT/"
cp "$ROOT/packaging/windows/Open-SmartParkLogs.bat" "$OUT/"
cp "$ROOT/packaging/windows/Run-CameraLab.ps1" "$OUT/"
cp "$ROOT/packaging/windows/Run-CameraLab.bat" "$OUT/"
cp "$ROOT/packaging/windows/Wipe-SmartPark.ps1" "$OUT/"
cp "$ROOT/packaging/windows/Wipe-SmartPark.bat" "$OUT/"
cp "$ROOT/packaging/windows/README-USB.txt" "$OUT/README.txt"
cp "$ROOT/FIRST_TEST_WINDOWS.md" "$OUT/FIRST_TEST_WINDOWS.md"
if [[ -f "$ROOT/WINDOWS_CAMERA_UI_FIXES.md" ]]; then
  cp "$ROOT/WINDOWS_CAMERA_UI_FIXES.md" "$OUT/WINDOWS_CAMERA_UI_FIXES.md"
fi
# Make it impossible to confuse a stale USB copy with the package that was
# actually assembled.  The source tree may contain uncommitted fixes, so the
# marker includes hashes of the two startup scripts as well as the Git state.
BUILD_COMMIT="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
BUILD_DIRTY="$(git -C "$ROOT" status --short 2>/dev/null | tr '\n' ' ' || true)"
BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
INSTALLER_SHA="$(sha256sum "$ROOT/packaging/windows/Install-SmartPark.ps1" | awk '{print $1}')"
SERVICES_SHA="$(sha256sum "$ROOT/packaging/windows/Install-SmartParkServices.ps1" | awk '{print $1}')"
cat > "$OUT/BUILD-INFO.txt" <<EOF
Zirp Windows kit
Build UTC: $BUILD_TIME
Git base: $BUILD_COMMIT
Git working tree: ${BUILD_DIRTY:-clean}
Install-SmartPark.ps1 SHA256: $INSTALLER_SHA
Install-SmartParkServices.ps1 SHA256: $SERVICES_SHA
EOF
rm -rf "$OUT/documentation"
mkdir -p "$OUT/documentation"
cp "$ROOT/docs-site/index.html" "$OUT/documentation/"
cp "$ROOT/docs-site/styles.css" "$OUT/documentation/"
cp "$ROOT/docs-site/app.js" "$OUT/documentation/"
cp "$ROOT/docs-site/"*.ico "$OUT/documentation/"
cp "$ROOT/docs-site/README.md" "$OUT/documentation/"
cp "$ROOT/docs/DEPLOYMENT.md" "$OUT/documentation/"
cp "$ROOT/docs/DATABASE_CONFIGURATION.md" "$OUT/documentation/"
cp "$ROOT/docs/POSTGRESQL-PREREQUISITE.md" "$OUT/documentation/"
cp "$ROOT/docs/LANE-DEPLOYMENT.md" "$OUT/documentation/"
cp "$ROOT/docs/MEDIA-ARCHITECTURE.md" "$OUT/documentation/"
cp "$ROOT/docs/CAMERA-DELIVERY-DIAGNOSTICS.md" "$OUT/documentation/"
cp "$ROOT/docs/MIGRATION-AND-ROLLBACK.md" "$OUT/documentation/"
if [[ -f "$ROOT/docs/CAMERA-LAB.md" ]]; then
  cp "$ROOT/docs/CAMERA-LAB.md" "$OUT/documentation/"
fi
echo "Verifying offline payload (wheels, NetSDK, models, Python)..."
python3 "$ROOT/packaging/verify_windows_kit.py" "$OUT/payload"

ZIP="$ROOT/dist/SmartParkEdge-USB.zip"
mkdir -p "$ROOT/dist"
rm -f "$ZIP"
( cd "$ROOT/dist" && python3 -m zipfile -c "$(basename "$ZIP")" "SmartParkEdge-Install" )
sha256sum "$ZIP" > "$ZIP.sha256"

echo
echo "Maintainer Windows test package ready:"
echo "  Folder: $OUT"
echo "  Zip:    $ZIP"
echo "For field testing, copy the folder (or the zip) to the target Windows PC."
echo "On Windows, double-click Install-SmartPark.bat"
echo "Documentation site: $OUT/documentation/index.html"
