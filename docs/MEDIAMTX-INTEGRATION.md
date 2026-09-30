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

## Paths and control API

Generated config writes two paths per camera:

- `cam{id}` — operator live (WebRTC and the desktop MJPEG cache)
- `cam{id}_detect` — software recognition

`detect_endpoint()` returns `rtsp://127.0.0.1:8554/cam{id}_detect`. Path changes are written to `mediamtx.yml` (MediaMTX hot-reloads that file) and pushed with the Control API:

- `POST /v3/config/paths/add/{name}`
- `POST /v3/config/paths/replace/{name}` when the path already exists
- `DELETE /v3/config/paths/delete/{name}`

There is no `/v3/config/paths/reload`. Site Service must not start or stop MediaMTX; `SmartParkMediaService` owns the process.

Metrics listen on `127.0.0.1:9998` (`metrics: yes`). The control API stays on `127.0.0.1:9997`.

Desktop live view reads `/cameras/{id}/live.mjpeg`. When MediaMTX is the live provider, one persistent decoder fills that JPEG cache from `cam{id}`. A failed MJPEG stream retries the same stream. It does not poll `snapshot.jpg`.

The `webrtc_live_enabled` flag controls browser transport, not MediaMTX source
selection. With MediaMTX selected and WebRTC disabled, `/live/endpoint` reports
MediaMTX with MJPEG transport, and desktop/browser MJPEG reads the local proxy
cache. Disabling WebRTC must not reopen a direct camera connection.

## Failure behavior

Binary missing → health `ok=false`, note that the sidecar is optional. HVX JPEG live view continues.

## Security

MediaMTX binds localhost in the generated config. Do not publish 8554/8889 off the parking LAN.
