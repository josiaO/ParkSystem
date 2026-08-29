# Camera troubleshooting

Operator Live Gates shows Camera / Live Video / Plate Recognition / Barrier. Raw SDK/RTSP/FFmpeg belongs in **Hardware Lab** and `/health/details`.

| Symptom | Check |
|---|---|
| Camera Offline | TCP 30000 for HVX; HTTP/RTSP for generic; other cameras should stay up |
| Live Video Offline, Camera Online | MediaGateway session, ffmpeg child, stale_stream_seconds; HVX host `/info` |
| Live skips / jumps | Latest-frame depth, GOP, using MAIN for LIVE, decoder warnings |
| No plates on HVX | Native callback, coil GPIO, `native_alpr_enabled`; FastALPR only if native empty |
| No plates on Dahua/Hik | FastALPR models present, DETECT buffer age, credentials |
| One camera failed | Connect-all skips dead TCP; other lanes continue |
| MediaMTX down | Expected if flag off or binary missing; live stays DIRECT_LEGACY |
| FastALPR process down | Live video remains; Site Service loop still does legacy OCR |

Health domains: camera connection, media gateway, recognition, gate, database, payment.
