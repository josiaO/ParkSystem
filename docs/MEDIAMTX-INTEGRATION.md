# MediaMTX integration

## Purpose

Optional LAN sidecar that can re-publish camera RTSP as local RTSP/WebRTC. SmartPark must run without it.

## What owns this

`app/services/mediamtx.py`, `app/media_service.py` (`SmartParkMediaService`).

## Enable

1. Drop `mediamtx.exe` in `%SMARTPARK_HOME%\vendor\mediamtx\` or set `SMARTPARK_MEDIAMTX_BIN`.
2. Set `SMARTPARK_MEDIA_GATEWAY_ENABLED=true`.
3. Optionally restrict cameras: `SMARTPARK_MEDIA_GATEWAY_CAMERA_IDS=3`.
4. WebRTC live: `SMARTPARK_WEBRTC_LIVE_ENABLED=true` and `SMARTPARK_LIVE_VIEW_PROVIDER=MEDIAMTX`.

Rollback: `SMARTPARK_LIVE_VIEW_PROVIDER=DIRECT_LEGACY` (or PATCH `/settings/migration`).

## Failure behavior

Binary missing → health `ok=false`, note that the sidecar is optional. HVX JPEG live view continues.

## Security

MediaMTX binds localhost in the generated config. Do not publish 8554/8889 off the parking LAN.
