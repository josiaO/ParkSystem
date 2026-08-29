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
- Latest-frame queue size 1–3 (`LatestFrameBuffer`).
- If inference is slower than the source, drop stale frames.
- Default authority is the Site Service camera-event loop (`FASTALPR_LEGACY`).
- `fastalpr_new_pipeline_enabled` turns on the worker as a shadow/new path. Parking still uses the legacy loop until `recognition_pipeline=FASTALPR_NEW` after soak tests.

## Modes

`NATIVE_ONLY`, `FASTALPR_ONLY` / `LOCAL_ONLY`, `HYBRID`. Per-camera `recognition_mode` overrides the process default.
