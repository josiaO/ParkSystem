# Stream profiles

## Roles

| Role | Typical use |
|---|---|
| MAIN | Highest useful resolution (evidence / fullscreen) |
| SUB | Grid live view (~10–15 FPS H.264) |
| LIVE | What the operator watches (usually SUB) |
| DETECT | FastALPR (~5 FPS to start) |
| EVIDENCE | Highest useful still |

Stored on `cameras.stream_profiles`. Transport is per camera: AUTO / TCP / UDP (`cameras.rtsp_transport`).

FFmpeg profiles: COMPATIBLE, LOW_LATENCY_LAN, LOSSY_NETWORK, VENDOR_SPECIAL.

Do not apply one global stream to every camera. Warnings (no substream, long GOP, decoder overload) appear on the IPs tab and `/health/details`.
