# Migration and rollback

Tag/branch: `hardware-working-baseline`.

## Flags

Stored in env (`SMARTPARK_*`) and overrideable at `PATCH /settings/migration`.

| Flag | Default | Meaning |
|---|---|---|
| media_gateway_enabled | false | Start/register MediaMTX in parallel |
| media_gateway_camera_ids | empty | Empty = all cameras if enabled; else allow-list |
| webrtc_live_enabled | false | Live endpoint may return MediaMTX WebRTC |
| live_view_provider | DIRECT_LEGACY | Rollback: DIRECT_LEGACY ← MEDIAMTX |
| fastalpr_new_pipeline_enabled | false | Recognition worker samples DETECT |
| recognition_pipeline | FASTALPR_LEGACY | Rollback: FASTALPR_LEGACY ← FASTALPR_NEW |
| native_alpr_enabled | true | Keep HVX callbacks in fusion |

## Stages

1. Current HVX + LocalMediaGateway authoritative (now).
2. MediaMTX parallel on one camera.
3. One live view through MediaMTX.
4. One generic camera FastALPR via DETECT worker (shadow).
5. Move remaining live views one camera at a time.
6. Remove DIRECT_LEGACY only after long soak.

Never migrate all cameras at once. No emergency code edit: flip the flags.
