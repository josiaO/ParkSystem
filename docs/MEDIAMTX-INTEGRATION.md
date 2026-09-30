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

Generated config writes **one path per distinct upstream stream**, tagged with
the roles it serves (`mediamtx.path_plan`):

- `cam{id}` — LIVE (WebRTC and the desktop MJPEG cache); always on
- `cam{id}_detect` — DETECT, only when the detect URI differs from LIVE; always on
  (`sourceOnDemand: no`) so software recognition never stops when nobody views
- `cam{id}_evidence` — EVIDENCE, only when a distinct MAIN URI is known;
  `sourceOnDemand: yes` because it is read only for explicit snapshots

When a camera exposes a single stream, LIVE/DETECT/EVIDENCE all resolve to
`cam{id}` and the camera is pulled once. `detect_endpoint()` and
`evidence_endpoint()` return whichever path carries that role; the response
reports `shared_upstream` and `on_demand`. `sync_paths()` deletes stale split
paths when roles later collapse onto one upstream. Path changes are written to
`mediamtx.yml` (MediaMTX hot-reloads that file) and pushed with the Control API:

- `POST /v3/config/paths/add/{name}`
- `POST /v3/config/paths/replace/{name}` when the path already exists
- `DELETE /v3/config/paths/delete/{name}`

There is no `/v3/config/paths/reload`. Site Service must not start or stop MediaMTX; `SmartParkMediaService` owns the process.

Metrics listen on `127.0.0.1:9998` (`metrics: yes`). The control API stays on `127.0.0.1:9997`.

## Telemetry

`app/services/mediamtx_telemetry.py` polls the Control API (`/v3/paths/list`,
`/v3/rtspsessions/list`, `/v3/webrtcsessions/list`) with a 1 s timeout and a
2 s shared cache. Per path it reports ready state, source type, readers (RTSP vs
WebRTC), bytes in/out, track codecs, summed RTP packets sent/lost/in-error and
max jitter across reader sessions, and a reconnect count derived from
`readyTime` changes. Nothing here infers health from a `_process` handle owned
by another process; an unreachable Control API is reported as
`control_api_ok=false`, never raised.

Exposure:

- `mediamtx.health()["telemetry"]` — site-wide summary (`/health/details`, `/media/gateway`)
- `/media/gateway` → `mediamtx_paths` — raw per-path rows
- `/cameras/{id}/streams` → `media.mediamtx` — per-role rows (`LIVE`, `DETECT`,
  `EVIDENCE`) plus `state` (`LIVE` / `DEGRADED` when RTP loss is seen / `OFFLINE`)
  and `webrtc` codec compatibility. RTP loss and codec problems are appended to
  `warnings`. Hardware Lab renders this under the stream-profile cards.

## Browser live view (WHEP)

With `webrtc_live_enabled=true`, `/cameras/{id}/live/endpoint` returns
`transport=WEBRTC`, a `whep` URL, the observed `codec` and `webrtc_compatible`.
The browser uses a `<video>` element driven by a WHEP `RTCPeerConnection`
(`whepStart`), not a permanent iframe. Switching cameras calls `whepStop`, which
closes the peer connection and `DELETE`s the WHEP session so MediaMTX reader
counts settle. A pane runs exactly one transport: while a WHEP session exists no
MJPEG or `snapshot.jpg` polling starts. Pane status shows `LIVE`, `DEGRADED`
(reconnecting / WHEP unavailable → MediaMTX-fed MJPEG cache) or `OFFLINE`.

Codec handling: H.264/AV1/VP8/VP9 are treated as compatible; H.265 is reported
as "varies"; anything else (MPEG-4, M-JPEG, MPEG-1/2) makes the registry return
`transport=MJPEG`, `state=DEGRADED` with a `reason`. No hidden transcoding is
started; choose an H.264 substream for LIVE instead. H.264 B-frames cannot be
detected from the Control API and must be checked on the camera when WebRTC
fails to render.

Desktop live view reads `/cameras/{id}/live.mjpeg`. When MediaMTX is the live provider, one persistent decoder fills that JPEG cache from `cam{id}`. A failed MJPEG stream retries the same stream. It does not poll `snapshot.jpg`.

The `webrtc_live_enabled` flag controls browser transport, not MediaMTX source
selection. With MediaMTX selected and WebRTC disabled, `/live/endpoint` reports
MediaMTX with MJPEG transport, and desktop/browser MJPEG reads the local proxy
cache. Disabling WebRTC must not reopen a direct camera connection.

## Failure behavior

Binary missing → health `ok=false`, note that the sidecar is optional. HVX JPEG live view continues.

## Security

MediaMTX binds localhost in the generated config. Do not publish 8554/8889 off the parking LAN.
