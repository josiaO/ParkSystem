# CODEX ENGINEERING TASK — SMARTPARK STREAMING AND ALPR ENGINE REIMPLEMENTATION

## ROLE

Act as a principal computer-vision engineer, Windows multimedia systems engineer, and production reliability architect.

Repository: https://github.com/josiaO/ParkSystem

Your mission is to audit, repair, and selectively reimplement SmartPark's camera streaming and AI recognition pipeline so that live video is responsive, number-plate recognition is reliable, camera failures recover automatically, and duplicate parking events cannot occur.

**Do not rewrite the entire application. Do not claim production readiness based only on unit tests.**

Preserve working SDK camera connectivity, native ALPR callbacks, boom control, printing, payment, and parking business logic.

## PHASE 1 — INVESTIGATE THE EXISTING SYSTEM

Read the architecture documents and trace all actual runtime entry points.

Prioritize:

- `docs/MEDIA-ARCHITECTURE.md`
- `docs/FASTALPR-PIPELINE.md`
- `ZIRP PLATFORM ARCHITECTURE.md`
- `app/recognition_worker.py`
- `app/services/recognition_runtime.py`
- `app/services/recognition_decoder.py`
- `app/services/media_gateway.py`
- `app/services/latest_frame.py`
- `app/services/alpr.py`
- `app/infrastructure/media/`
- `app/infrastructure/recognition/`
- `app/infrastructure/hardware/cameras/`
- `app/domain/recognition_engine.py`
- `app/core/consensus.py`
- `app/core/hybrid.py`
- `app/desktop/live_cameras.py`
- `app/desktop/live_pane.py`
- `app/services/hvx_client.py`

Find the complete execution chain for every supported camera type.

Determine:

1. Which process opens each camera stream?
2. Whether multiple processes independently open the same source.
3. How frames move between FFmpeg, SDK hosts, buffers, inference, and the GUI.
4. Whether video frames are unnecessarily decoded or JPEG-encoded multiple times.
5. Whether blocking calls can stall asyncio, Qt, or other camera tasks.
6. Whether the recognition worker and Site Service can simultaneously claim inference ownership.
7. Whether stale frames can reach the recognition engine.
8. Whether inference results from previous frames can overwrite newer results.
9. Whether a previous plate remains visible after vehicle departure.
10. Whether multiple event delivery paths can create duplicate parking sessions.

For each confirmed defect, document the file, function, failure mechanism, and supporting evidence.

Do not mistake existing safeguards for proof that a failure is impossible.

## PHASE 2 — MEASURE BEFORE REIMPLEMENTING

Build a diagnostic mode that runs on the actual Windows machine.

Collect per-camera metrics:

- Source FPS and codec
- Decode FPS
- Display FPS
- Inference admission FPS
- Completed inference FPS
- Capture-to-decode latency where source timestamps permit
- Decode-to-display latency
- Decode-to-inference latency
- Detection and OCR duration
- Frame queue depth
- Dropped frames
- Last complete frame timestamp
- Decoder process PID
- Decoder restarts
- Camera reconnect count
- CPU and RAM utilization
- Recognition-worker ownership
- Recognition events accepted, suppressed, or rejected

Use monotonic clocks for durations and wall-clock timestamps for cross-process event correlation.

Do not label local buffer age as true camera-to-screen latency.

Where camera clocks are unavailable or unsynchronized, report end-to-end latency as unverified and provide a practical visual timestamp or LED-based measurement procedure.

Save baseline results to `docs/engineering/streaming-baseline.md`.

## PHASE 3 — IMPLEMENT CAMERA ACQUISITION OWNERSHIP

Create or refactor an explicit camera acquisition manager.

Each camera must have a declared source owner.

Support:

- QY/HVX vendor SDK
- Generic RTSP cameras
- ONVIF-discovered RTSP profiles
- Simulated and recorded test sources

Preserve the working 32-bit vendor SDK host.

Do not assume that every camera supports the same streaming interface.

Do not create speculative RTSP URLs for native SDK cameras.

MediaMTX may remain the stream distributor for generic RTSP cameras. Reuse it where appropriate rather than introducing another media server.

Ensure that each source owner has:

- Explicit lifecycle states
- Connection timeout
- Last-frame watchdog
- Controlled reconnect
- Exponential backoff with jitter
- Bounded retry behavior
- Graceful shutdown
- Process cleanup
- Independent camera failure isolation

No camera failure may freeze the entire application.

## PHASE 4 — REIMPLEMENT FRAME DELIVERY

Establish distinct consumers for:

**LIVE:** operator display, prioritizing the newest decodable frame and low latency.

**DETECT:** computer vision, prioritizing fresh frames containing useful vehicle/plate evidence.

**EVIDENCE:** immutable image references associated with accepted events.

Use bounded latest-frame buffers.

Avoid unlimited frame queues.

Never allow the display queue to grow indefinitely.

Where practical, avoid JPEG encode/decode cycles between local decode and inference. Evaluate PyAV, FFmpeg rawvideo/shared memory, or an existing compatible solution through benchmarks before choosing.

Do not add a new dependency without demonstrating a measurable improvement.

Avoid holding locks during decoding, inference, database operations, or network I/O.

When a camera reconnects, increment its generation ID and invalidate stale frames, in-flight inference results, and old display updates.

Keep native capture callbacks independent of video-preview recovery.

## PHASE 5 — REIMPLEMENT THE AI PROCESSING SCHEDULER

Preserve FastALPR and the existing ONNX models unless benchmarking proves a replacement is necessary.

Load models once per inference worker and warm them before accepting traffic.

Prevent competing model owners.

Use bounded inference concurrency based on actual CPU/GPU capabilities.

Ensure a slow inference call cannot block video acquisition or the GUI.

Implement:

1. Fresh-frame admission.
2. Lane ROI filtering.
3. Plate detection.
4. Plate crop validation.
5. OCR on appropriate plate crops.
6. Temporal recognition consensus.
7. Native/software fusion where configured.
8. Normalized recognition event generation.

A frame must be rejected if its generation, age, or visit identity is invalid.

Use adaptive inference scheduling when supported by measurements. Do not reduce detection sampling so aggressively that a moving vehicle passes unseen.

Do not blindly run OCR on every display frame.

A failed OCR operation must not stop the decoder or prevent the next camera from being processed.

## PHASE 6 — FIX STALE PLATES AND VEHICLE TRACKING

Implement an explicit per-camera vehicle visit lifecycle:

EMPTY → APPROACHING → TRACKING → RECOGNIZED → DEPARTING → EMPTY

Support an UNKNOWN or DEGRADED state when visual evidence is insufficient.

Use reliable departure evidence from presence sensors, detection results, or temporal observations.

Do not interpret decoder failure as vehicle departure.

Clear the active displayed plate when the associated vehicle visit ends.

Preserve historical plate events separately from the current live detection.

Ensure a new vehicle cannot inherit the previous vehicle's plate, bounding box, evidence image, or consensus state.

Do not rely exclusively on a fixed 20-second suppression timer to identify a vehicle visit.

Test adjacent vehicles, slow-moving vehicles, reversing vehicles, temporary occlusions, and vehicles with similar plates.

## PHASE 7 — PREVENT DUPLICATE PARKING SESSIONS

Trace every path from camera recognition to database session creation.

Verify idempotency at both event ingestion and parking transaction boundaries.

Use stable event IDs, source ownership generations, and vehicle visit IDs.

Enforce appropriate database uniqueness and transactional constraints.

Ensure replaying the same recognition event cannot create a second session.

Ensure native ALPR and FastALPR recognition of the same physical visit do not create separate sessions.

Use atomic transactions for session state transitions.

Preserve the existing payment, receipt, and gate authorization policies.

Never open a boom merely because an OCR result exists.

A duplicate or delayed event must never cause a second gate command.

## PHASE 8 — AUTOMATED RECOVERY

Build health checks that distinguish:

- Camera disconnected
- RTSP source unavailable
- Decoder process exited
- Decoder alive but producing no complete frames
- Frames arriving but stale
- Inference worker blocked
- Model initialization failed
- Event publication failed
- Site Server unavailable
- Desktop video consumer disconnected

Each failure must have a bounded, appropriate recovery action.

Restart the smallest failed component possible.

Do not restart all cameras because one camera fails.

Prevent repeated watchdog restarts from creating duplicate workers or SDK handles.

Ensure shutdown waits for child-process cleanup.

## PHASE 9 — VALIDATION AND REGRESSION TESTS

Add automated tests for:

- Stale frame rejection
- Decoder stalls and partial JPEGs
- Camera disconnect/reconnect
- Multiple simultaneous cameras
- Slow inference
- Worker crashes
- Source ownership transitions
- Previous-plate contamination
- Adjacent vehicles
- False OCR on empty lanes
- Duplicate native/software events
- Replayed events
- Database transaction retries
- GUI consumer disconnect/reconnect
- SDK callback continuity
- Clean Windows shutdown

Run existing regression tests before and after the changes.

Add recorded-video replay tests with ground-truth plate annotations.

Measure precision, recall, missed-vehicle rate, duplicate-session rate, and recognition latency.

For hardware acceptance, test all installed cameras simultaneously, including real vehicle passages, in daylight and at night.

Suggested initial performance targets, subject to hardware benchmarking:

- Display pipeline latency: p95 below 500 ms when measured from camera capture.
- No unbounded frame queues.
- Recognition frame age at admission: normally below 500 ms.
- Recovery from an ordinary network interruption: target below 10 seconds after connectivity returns.
- Duplicate sessions for the same idempotency key: zero.
- Missed-vehicle rate: measured against a labeled field dataset, not assumed to be zero.
- Sustained operation: at least 24 hours for initial soak testing, followed by longer deployment validation.

Do not claim these targets were achieved without measurements.

## PHASE 10 — IMPLEMENTATION AND DELIVERY

Work in small, reviewable changes.

First deliver the audit and baseline.

Then implement the minimal safe architectural changes.

Preserve compatibility with the existing Windows installer and offline deployment bundle.

Use feature flags where necessary for staged rollout and rollback.

After each major change, run focused tests and compare performance against the baseline.

Deliver:

1. `docs/engineering/streaming-audit.md`
2. `docs/engineering/streaming-baseline.md`
3. `docs/engineering/streaming-target-architecture.md`
4. Implementation changes
5. Automated regression tests
6. Windows field diagnostic procedure
7. Performance benchmark results
8. Known limitations
9. Rollback instructions
10. Final acceptance checklist

**Final reporting rule:** distinguish VERIFIED, TESTED WITH MOCKS, NOT TESTED ON HARDWARE, and FAILED.

Never describe a system as production-ready while critical camera, recognition, gate, or database behavior remains unverified.

Begin by auditing the repository and collecting the baseline. Do not start with a wholesale rewrite.
