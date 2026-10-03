# RECOGNITION Module

Plate reading is a separate engine. The camera snaps the JPEG. The engine returns the plate. Parking consumes the normalized event.

The known engine is **FastALPR** (`fastalpr-1`). It replaces ParkWatch SimpleLPR (`LPRHelper.Recognize` on a captured JPEG). QY/HVX cameras supply video and optional native callbacks; they are not the plate engine unless a lane is `NATIVE_ONLY`.

ParkWatch (`CameraType=3` QY, `InALPR=ON` / `OutALPR=ON`): login → live stream for display → capture JPEG (`CaptureWaitTime=200ms`) → SimpleLPR with `Contrast=918`. SmartPark keeps that split: camera JPEG → FastALPR (`alpr_csf=0.918`) → one plate event. Latest-frame mailbox bounds OCR so four cameras cannot stack.

Contract, retrain steps, and how to register another library: [../PLATE-ENGINE.md](../PLATE-ENGINE.md).

Pipeline details: [../FASTALPR-PIPELINE.md](../FASTALPR-PIPELINE.md).

Code:

- `app/infrastructure/recognition/engines/` — engine contract, FastALPR, registry, training packs
- `app/services/alpr.py` — lane ROI, detect plate-shaped boxes, crop, OCR; reject empty-scene `ZC…` ghosts
- `app/services/recognition_runtime.py` — per-camera latest-frame mailbox, fair OCR limiter, visit lifecycle, watchdog
- `app/services/ocr_policy.py` — `FASTALPR_ONLY` by default
- Desktop page **Plate Engine** (Windows and Linux)

Realtime rules: one pending AI frame per camera; a stalled worker is recovered
without restarting other cameras; the live operator plate is never a historical
detection. Field soak: `tools/field_realtime_report.py`.

