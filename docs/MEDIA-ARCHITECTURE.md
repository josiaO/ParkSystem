# Media architecture

## Purpose

Keep **camera connectivity**, **media streaming**, and **recognition** on separate paths. Live video must not wait on FastALPR. FastALPR must not open its own camera session.

## What owns this

- Contract: `app/domain/media.py`
- Production gateway: `app/services/media_gateway.py` (`LocalMediaGateway`)
- Optional MediaMTX sidecar: `app/services/mediamtx.py`, process `app/media_service.py`
- Registry: `app/infrastructure/media/`

## What it must NOT do

- Put FastALPR in the Qt UI, HVX host, or MediaMTX process
- Open a second RTSP/SDK session per viewer
- Make MediaMTX a production dependency
- Expose camera RTSP URLs on a public network

## Path

```text
PHYSICAL CAMERA
  ├─ HVX SDK host (login, native event, GPIO, gate) — not replaced by MediaMTX
  └─ RTSP, when the camera exposes it
        └─ MediaMTX (one upstream per distinct URI, remux)
              ├─ WebRTC/WHEP → browser
              ├─ local RTSP → recognition decoder → FastALPR
              └─ evidence path, on demand
DIRECT_LEGACY (LocalMediaGateway MJPEG) remains the rollback live view.
```

MediaMTX is the preferred video router when `live_view_provider=MEDIAMTX` and `media_gateway_enabled=true` (the current defaults). The registry falls back to `DIRECT_LEGACY` when MediaMTX is not running. HVX/QY pictures stay on the SDK JPEG pump so a second RTSP client is not stacked on those cameras. Generic RTSP cameras are pulled once by MediaMTX; the recognition worker decodes only `rtsp://127.0.0.1:8554/<path>`.

`GET /media/gateway` reports local sessions, FFmpeg profiles, decode path, MediaMTX health, per-path MediaMTX telemetry (`mediamtx_paths`), and rollback names (`DIRECT_LEGACY` / `FASTALPR_LEGACY`).

## Stream roles

`MAIN`, `SUB`, `LIVE`, `DETECT`, `EVIDENCE` are stored per camera in `stream_profiles`. Roles are resolved to upstream URIs by `mediamtx_sources.upstream_role_uris`; `mediamtx.path_plan` then creates one MediaMTX path per *distinct* URI so a single-stream camera is pulled once. LIVE/DETECT paths are never on demand; EVIDENCE is on demand. The registry exposes `get_live_endpoint`, `get_detect_endpoint`, `get_evidence_endpoint` and `media_telemetry`; nothing outside `app/infrastructure/media/registry.py` chooses between MediaMTX and legacy.

## Freshness

`LocalMediaGateway` keeps one `CameraMediaSession` per camera. LIVE and DETECT buffers hold one frame. A repeated JPEG updates `last_received_at` only. `last_fresh_frame_at` and `live_frame_age_ms` move when the picture bytes change, so a stuck image does not look healthy. An HVX host that keeps returning that same cached JPEG stays connected; the pump restarts only when the host stops sending bytes, or when an RTSP decoder repeats one frame. Other cameras are left running. The host drains `Net_GetJpgBuffer` until the queue is empty before it sleeps, so a deep JPEG queue is not left several seconds behind.

Application code asks `app.infrastructure.media.MediaService` for `latest_live_frame`, `latest_detect_frame`, `evidence_frame`, and `health`. The HVX host, FFmpeg, and MediaMTX stay behind that object.

## HVX source

Moving HVX/QY video is `Net_StartVideo` + `Net_GetJpgBuffer` on the 32-bit host. MediaMTX is not registered for those cameras, because a second RTSP client stacks the camera. Generic RTSP cameras can still use MediaMTX. `DIRECT_LEGACY` remains the rollback live view.

Frame age and FPS are separate. On the parking PC, after Install-SmartPark.bat, double-click `Run-CameraLab.bat` in the install folder. That watches every camera for 15 minutes while SmartPark is already open. One camera for 10 minutes:

```text
powershell -ExecutionPolicy Bypass -File .\Run-CameraLab.ps1 -Camera 1 -Duration 600
```

The lab only reads Site Service media health. It does not create a parking session, receipt, gate command, or payment. The log is `%ProgramData%\SmartParkEdge\logs\camera_lab_*.txt`. Component 1 is field-complete only after the physical cameras run that test.

## Failure behavior

MediaMTX missing or crashed → live view stays on LocalMediaGateway; HVX native plates and gates stay up.

## Tests

`tests/test_media_gateway.py`, `tests/test_migration_architecture.py`, `tests/test_media_registry.py`, `tests/test_mediamtx_telemetry.py`.
