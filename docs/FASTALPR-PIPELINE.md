# FastALPR pipeline

## Purpose

Vendor-independent OCR on JPEG frames. It is a **consumer** of the DETECT buffer, never the live-view decoder.

## What owns this

- Engine: `app/services/alpr.py`
- Provider wrap: `app/infrastructure/recognition/fastalpr.py`
- Optional process: `app/recognition_worker.py` (`SmartParkRecognitionWorker`)
- Policy: `app/services/ocr_policy.py`

## Rules

- Load the ONNX models once, warm once, reuse.
- Pipeline: **detect plate → padded crop → OCR on crop only** (`detect_crop_ocr`). Never OCR the full car JPEG.
- Latest-frame queue size 1–3 (`LatestFrameBuffer`).
- If inference is slower than the source, drop stale frames.
- Default authority is the Site Service camera-event loop (`FASTALPR_LEGACY`).
- `fastalpr_new_pipeline_enabled` starts `SmartParkRecognitionWorker` on `rtsp://127.0.0.1:8554/cam{id}_detect`. The worker keeps one persistent decoder per camera, drops stale frames, and publishes `PlateRecognized` on the durable outbox.
- For cameras on that path, Site Service stops in-process FastALPR and applies the worker event. Native HVX callbacks stay in Site Service. The flag defaults to off, so the legacy loop remains authoritative until it is enabled.

## Worker safeguards

The worker selects its endpoint through `app/infrastructure/media/registry.py`.
Only enabled software-only cameras in the rollout set run in the worker; native
and hybrid cameras retain the existing Site Service fusion path. Module and
VIDEO_ONLY configuration disable worker inference. Persisted site plate policy
and numeric lane ownership accompany every read.

Model work runs off the asyncio event loop. Worker model calls are serialized;
each camera takes its newest frame only when model capacity is available.
Buffers hold one frame, inputs older than 1000 ms are dropped, and the configured
DETECT FPS caps sampling. Consensus requires nearby agreeing reads; widely
separated visits do not establish agreement. Low-confidence or policy-held
events remain held for operator review.

The worker archives evidence once per consensus event, then publishes through a
SQLite outbox shared with Site Service. Site Service persists the capture through
its normal review path before any parking action. Missing/stale worker heartbeat
or frame timestamps release software ownership to the legacy Site Service loop.
`/health/details` includes `recognition_worker`; this is a process-safe health
snapshot, not an in-memory reference to another process.

Camera removal, policy changes and shutdown cancel and await decoder tasks.
An individual failed camera task is restarted independently. Hybrid worker
fusion and hardware soak remain acceptance gates, not completed claims.

## Modes

Default mode is `FASTALPR_ONLY`: every presence JPEG is read by the FastALPR plate engine (ParkWatch software OCR). `NATIVE_ONLY` keeps the camera text. `HYBRID` uses both. Per-camera `recognition_mode` overrides the process default.

The engine is isolated and replaceable. See [PLATE-ENGINE.md](PLATE-ENGINE.md).

## DETECT FPS vs time-in-view

Default `SMARTPARK_DETECT_FPS=5` is 200 ms between frames. A plate that is readable for about 1 s at typical entry speed yields ~5 frames, which is enough for two agreeing FastALPR reads (or one read ≥ 0.92). Do not drop below ~3 FPS if consensus is required. `/alpr/status` reports this coverage math under `detect`.
