#!/usr/bin/env bash
# Prove MediaMTX local RTSP proxy stays smooth for at least N minutes.
# Usage:
#   ./scripts/mediamtx_soak_test.sh <camera_id> [minutes]
# Env:
#   SMARTPARK_MEDIAMTX_BIN — optional path to mediamtx binary
#   SOAK_UPSTREAM_RTSP — override upstream (else resolved from SmartPark DB)
#
# If the proxy stutters, diagnose camera/network — do not patch SmartPark decode.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
CAMERA_ID="${1:?camera_id required (e.g. 3 for 2# Entry)}"
MINUTES="${2:-10}"
DURATION=$((MINUTES * 60))
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

if [[ -x "$ROOT/vendor/mediamtx/mediamtx" ]]; then
  export SMARTPARK_MEDIAMTX_BIN="$ROOT/vendor/mediamtx/mediamtx"
fi

python3 - <<PY
import os, sys
sys.path.insert(0, "$ROOT")
from app.db import SessionLocal
from app.models import Camera
from app.services import mediamtx
from app.services.mediamtx_sources import source_config_for_camera, sync_camera

cid = int("$CAMERA_ID")
with SessionLocal() as db:
    cam = db.get(Camera, cid)
    if cam is None:
        raise SystemExit(f"Camera {cid} not in database")
    override = os.environ.get("SOAK_UPSTREAM_RTSP", "").strip()
    if override:
        cfg = {"uri": override, "detect_uri": override, "ip": cam.ip_address, "rtsp_url": override}
        mediamtx.register_source(cid, cfg)
    else:
        out = sync_camera(cam, db=db)
        if not out.get("registered"):
            raise SystemExit(f"Could not register MediaMTX source: {out}")
        cfg = source_config_for_camera(cam)
    print("Upstream (redacted):", mediamtx.live_endpoint(cid).get("upstream_redacted"))
    print("Local RTSP:", mediamtx.live_endpoint(cid).get("rtsp"))
    if not str(cfg.get("uri") or "").startswith("rtsp://"):
        raise SystemExit("No RTSP upstream URI — probe camera first: POST /cameras/{id}/rtsp/probe")
if not mediamtx.running():
    print(mediamtx.start())
PY

LOCAL_RTSP="rtsp://127.0.0.1:8554/cam${CAMERA_ID}"
LOG="$ROOT/logs/mediamtx_soak_cam${CAMERA_ID}_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$ROOT/logs"
echo "Soak test: ffplay $LOCAL_RTSP for ${MINUTES} minutes"
echo "Log: $LOG"
if ! command -v ffplay >/dev/null; then
  echo "ffplay not found; falling back to ffmpeg read probe"
  ffmpeg -hide_banner -loglevel warning -rtsp_transport tcp -i "$LOCAL_RTSP" -t "$DURATION" -f null - 2>&1 | tee "$LOG"
else
  timeout "$DURATION" ffplay -rtsp_transport tcp -loglevel warning -autoexit -nodisp "$LOCAL_RTSP" 2>&1 | tee "$LOG" || true
fi
echo "Soak finished. Review $LOG for stalls/errors."
echo "If smooth, enable live view: SMARTPARK_LIVE_VIEW_PROVIDER=MEDIAMTX SMARTPARK_MEDIA_GATEWAY_CAMERA_IDS=$CAMERA_ID"
