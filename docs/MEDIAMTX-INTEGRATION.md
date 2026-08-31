# MediaMTX integration

## Purpose

Optional LAN sidecar that can re-publish camera RTSP as local RTSP/WebRTC. SmartPark must run without it.

## What owns this

`app/services/mediamtx.py`, `app/media_service.py` (`SmartParkMediaService`).

## Enable

1. Install binary: `./scripts/install_mediamtx.sh` or drop `mediamtx` in `vendor/mediamtx/` / `%SMARTPARK_HOME%\vendor\mediamtx\` or set `SMARTPARK_MEDIAMTX_BIN`.
2. Set `SMARTPARK_MEDIA_GATEWAY_ENABLED=true`.
3. Restrict to one camera first: `SMARTPARK_MEDIA_GATEWAY_CAMERA_IDS=3` (2# Entry / `192.168.1.49`).
4. Soak the proxy (10+ minutes, VLC or ffplay on local RTSP only): `./scripts/mediamtx_soak_test.sh 3 10`
5. If the proxy is smooth, switch live view: `SMARTPARK_LIVE_VIEW_PROVIDER=MEDIAMTX` and optional `SMARTPARK_WEBRTC_LIVE_ENABLED=true`.
6. Run `python -m app.media_service` (or Windows scheduled task) so MediaMTX is supervised separately from Site Service.

Rollback: `SMARTPARK_LIVE_VIEW_PROVIDER=DIRECT_LEGACY` (or PATCH `/settings/migration`).

## Failure behavior

Binary missing → health `ok=false`, note that the sidecar is optional. HVX JPEG live view continues.

## Security

MediaMTX binds localhost in the generated config. Do not publish 8554/8889 off the parking LAN.
