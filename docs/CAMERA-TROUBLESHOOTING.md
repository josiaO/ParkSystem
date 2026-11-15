# Camera troubleshooting

> Restored from history and checked against the code on 2026-11-15 (Phase 6). Not yet re-verified on site hardware.

Operator Live Gates shows Camera / Live Video / Plate Recognition / Barrier. Raw SDK/RTSP/FFmpeg belongs in **Hardware Lab** and `/health/details`.

| Symptom | Check |
|---|---|
| Camera Offline | TCP 30000 for HVX; HTTP/RTSP for generic; other cameras should stay up |
| Live Video Offline, Camera Online | HVX: host `/info` and the watchdog's SDK video age; generic: Media Service running and the MediaMTX path ready (System Health) |
| Live skips / jumps | Latest-frame depth, GOP, using MAIN for LIVE, decoder warnings |
| No plates on HVX/QY | Default mode is HYBRID: native read verified by FastALPR, native read kept if FastALPR reads nothing. Check the native callback, coil GPIO, `native_alpr_enabled` |
| No plates on Dahua/Hik/RTSP | FastALPR models present, Recognition Worker running, detection zone, plate width (`camera_lab_replay measure`) |
| "Frames wait N ms before recognition" in System Health | p95 frame age over 300 ms: CPU overloaded or detect width too large; see RECOGNITION-MEASUREMENTS.md |
| One camera failed | Connect-all skips dead TCP; other lanes continue; the watchdog resets only that camera |
| MediaMTX / Media Service down | Production live view and recognition for generic cameras stop; HVX/QY SDK cameras are unaffected. Check the `SmartParkMediaService` service and its log |
| Recognition Worker down | Live video remains; generic cameras are not read until the worker restarts (the service restarts it). HVX/QY native reads continue |
| Red "Server link down" banner | The gate PC cannot reach the database; barriers do not open automatically. Use the receipt QR / operator; see OFFLINE-OPTIONS.md |

Health domains: camera connection, media gateway, recognition, gate, database, payment, plus the watchdog (`/health/details` → `watchdog`) and clock skew.
