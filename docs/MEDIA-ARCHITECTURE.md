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
  ├─ Camera Control Adapter (HVX / RTSP / ONVIF)
  └─ Media Source (SDK JPEG or RTSP)
        └─ LocalMediaGateway (one producer, latest-frame LIVE + DETECT)
              ├─ Live view (MJPEG / optional MediaMTX WebRTC)
              └─ FastALPR (DETECT buffer only)
```

Default live view provider is `DIRECT_LEGACY` (LocalMediaGateway). Set `live_view_provider=MEDIAMTX` and `media_gateway_enabled=true` only after a camera has soaked in parallel.

`GET /media/gateway` reports local sessions, FFmpeg profiles, decode path, MediaMTX health, and rollback names (`DIRECT_LEGACY` / `FASTALPR_LEGACY`).

## Failure behavior

MediaMTX missing or crashed → live view stays on LocalMediaGateway; HVX native plates and gates stay up.

## Tests

`tests/test_media_gateway.py`, `tests/test_migration_architecture.py`.
