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
- Pipeline: **lane ROI → detect plate-shaped box → padded crop → OCR on crop only** (`detect_crop_ocr`). Never OCR the full car JPEG. Never OCR sky, signs, or bollards.
- Empty scenes do not run a second CLAHE detect pass. `ZC…` and other FastALPR empty-lane hallucinations are dropped before presence or parking see them.
- Latest-frame queue size 1–3 (`LatestFrameBuffer`).
- If inference is slower than the source, drop stale frames.
- Default authority is the Site Service camera-event loop (`FASTALPR_LEGACY`).
- `fastalpr_new_pipeline_enabled` starts `SmartParkRecognitionWorker` on `rtsp://127.0.0.1:8554/cam{id}_detect`. The worker keeps one persistent decoder per camera, drops stale frames, and publishes `PlateRecognized` on the durable outbox.
- For cameras on that path, Site Service stops in-process FastALPR and applies the worker event. Native HVX callbacks stay in Site Service. The flag defaults to off, so the legacy loop remains authoritative until it is enabled.

## Worker safeguards

The worker selects its endpoint through `app/infrastructure/media/registry.py`.
Enabled `FASTALPR_ONLY` and `HYBRID` cameras in the rollout set run in the
worker; `NATIVE_ONLY` cameras never run software reads there. Module and
VIDEO_ONLY configuration disable worker inference. Persisted site plate policy
and numeric lane ownership accompany every read.

Model work runs off the asyncio event loop. Worker model calls are serialized;
each camera takes its newest frame only when model capacity is available.
Buffers hold one frame, inputs older than 1000 ms are dropped, and the configured
DETECT FPS caps sampling.

The worker archives evidence once per consensus event, then publishes through a
SQLite outbox shared with Site Service. Site Service persists the capture through
its normal review path before any parking action. Missing/stale worker heartbeat
or frame timestamps release software ownership to the legacy Site Service loop.
`/health/details` includes `recognition_worker`; this is a process-safe health
snapshot, not an in-memory reference to another process.

Camera removal, policy changes and shutdown cancel and await decoder tasks.
An individual failed camera task is restarted independently. Hardware soak
remains an acceptance gate, not a completed claim.

## Temporal consensus (`app/core/consensus.py::ConsensusTrack`)

Reads within 2 s of each other form one *visit*. Every read votes for each
candidate text it resembles (`plate_similarity` ≥ 0.7), weighted by OCR
confidence and similarity, so `T285DOP` supports `T285DQP` instead of splitting
the vote. Publication requires ≥ 2 reads, ≥ 2 identical reads for the winner and
≥ 60 % of the weight, or one read ≥ 0.92. The consensus confidence is the mean
of the identical reads. A plate is published once per visit, never while continuously visible,
and not again within the 20 s hold. The published event carries `consensus`
(`reads`, `agreeing`, `share`, `candidates`) plus the raw `frame_plate` /
`frame_confidence`; a failed durable publish releases the hold so the next
agreeing frame retries.

## Hybrid fusion (native + FastALPR)

For `HYBRID` cameras with a live worker (`worker_owns_software_reads`), the
worker publishes FastALPR *candidates* (`fusion_role=candidate`) and the Site
Service fuses them with the native HVX callback in
`app/services/hybrid_fusion.py` (`app/core/hybrid.py::FusionCoordinator`):

- native and software candidates are paired per camera within 3 s
- agreement is accepted immediately (`AGREED`)
- when the counterpart provider is unavailable (no native adapter / stale worker
  heartbeat) the single provider decides at once; otherwise the first candidate
  waits 1.5 s (`_fusion_flush_loop`) and then decides alone
- disagreements are held for operator review by `resolve_readings`
- a second decision for the same or near-identical plate (similarity ≥ 0.85) on
  the same camera within 20 s is suppressed, so one vehicle never yields two
  captures/sessions

The fused capture is persisted once through `_persist_capture_event` with
`source=hybrid` and the fusion audit on the row. `/health/details` →
`domains.recognition.hybrid_fusion` exposes offered/paired/held/suppressed
counters and pending candidates. When the worker is down the camera falls back to
the in-process native/fusion loop unchanged.

## Durable event idempotency

`SQLiteOutbox.ack(item_id, processed_key=event_id)` deletes the row and records
the event as processed in the same transaction; `was_processed(event_id)`
(7-day retention) and a `vehicle_captures.event_id` lookup are both checked
before a redelivered `PlateRecognized` row is processed. A crash between
business processing and ACK therefore replays the row but cannot create a second
capture or session.

## Modes

Default mode is `FASTALPR_ONLY`: every presence JPEG is read by the FastALPR plate engine (ParkWatch software OCR). `NATIVE_ONLY` keeps the camera text. `HYBRID` uses both. Per-camera `recognition_mode` overrides the process default.

The engine is isolated and replaceable. See [PLATE-ENGINE.md](PLATE-ENGINE.md).

## DETECT FPS vs time-in-view

Default `SMARTPARK_DETECT_FPS=5` is 200 ms between frames. A plate that is readable for about 1 s at typical entry speed yields ~5 frames, which is enough for two agreeing FastALPR reads (or one read ≥ 0.92). Do not drop below ~3 FPS if consensus is required. `/alpr/status` reports this coverage math under `detect`.
