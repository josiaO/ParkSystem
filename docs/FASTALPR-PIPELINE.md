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
- `fastalpr_new_pipeline_enabled` turns on the worker as a shadow/new path. Parking still uses the legacy loop until `recognition_pipeline=FASTALPR_NEW` after soak tests.

## Modes

Default mode is `FASTALPR_ONLY`: every presence JPEG is read by the FastALPR plate engine (ParkWatch software OCR). `NATIVE_ONLY` keeps the camera text. `HYBRID` uses both. Per-camera `recognition_mode` overrides the process default.

The engine is isolated and replaceable. See [PLATE-ENGINE.md](PLATE-ENGINE.md).

## DETECT FPS vs time-in-view

Default `SMARTPARK_DETECT_FPS=5` is 200 ms between frames. A plate that is readable for about 1 s at typical entry speed yields ~5 frames, which is enough for two agreeing FastALPR reads (or one read ≥ 0.92). Do not drop below ~3 FPS if consensus is required. `/alpr/status` reports this coverage math under `detect`.

