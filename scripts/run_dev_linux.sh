#!/usr/bin/env bash
# Multiplatform operator path: Site Service + browser UI (Linux/macOS/any OS).
# Desktop (PySide6) also runs on Linux: python -m app.desktop.launch
# The HVX NetSDK host stays Windows-only (NetSDK.dll).
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -d .venv ]]; then
  echo "Create a venv first:"
  echo "  python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "Starting SmartPark Edge (web UI) at http://127.0.0.1:8760"
echo "Sign in as admin with the first-run password from GET /auth/setup (written to bootstrap_password.txt)."
echo "Non-LAPR cameras: set Adapter to rtsp (or dahua/hikvision), then Connect."
echo "HVX LAPR / camera GPIO: needs a Windows PC with the 32-bit SDK host."
exec python -m app.web.launch
