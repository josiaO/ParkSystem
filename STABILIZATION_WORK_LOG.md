# Production stabilization work log

## Source audit before implementation (2026-10-19)

The request authorizes the stabilization work described in SMARTPARK_PRODUCTION_STABILIZATION.md. That document is the task specification, not evidence that its suspected root causes exist. Physical acceptance requires the Windows installation and real cameras; local tests cannot establish production readiness.

### Actual runtime map

- Live: camera profiles/discovery → `mediamtx_sources.source_config_for_camera` → `mediamtx.path_plan` (identical role URLs share an upstream) → Media Service registers paths → registry `get_live_endpoint` → API `camera_live_endpoint` → inline `whepStart` in `app/web/index.html` → peer track → video `srcObject`. There is no `app/web/mediamtx-reader.js` in this checkout. MJPEG fallback uses a persistent local MediaMTX decoder while watched.
- Recognition: camera → MediaMTX detect path → persistent `RecognitionDecoder` local RTSP → per-camera `CameraRecognitionLane.mailbox` (capacity one) → worker detector/ArrivalGate → padded crop OCR provider → Tanzania normalization → per-camera ConsensusTrack → `_publish_frame` → SQLite outbox → Site Service capture persistence → `live_parking` → Entry/ExitLaneController → session/receipt safety policy → gate adapter. Site Service retains a software fallback based on worker heartbeat.
- Ownership: environment gate assignment / persisted node setting / UI selection → `_camera_rows` and Site Service camera loop → independent decoder, mailbox, arrival, track and LaneVisit per camera → runtime slot cap plus worker semaphore → shared detector/OCR engine. Unassigned scope currently includes every camera. Browser lane presets write recognition scope, so view changes can move ownership.

### Verified risks and existing protections

- The dedicated live endpoint API already rewrites localhost to the request host. It always emits HTTP, however, so HTTPS pages hit mixed-content failures. Other endpoint consumers still see internal URLs. WebRTC has UDP only, and browser connection state is reported LIVE before a usable video frame. Signaling failure falls back permanently instead of retrying WHEP. Track handling can lose video when audio arrives first without a stream.
- Decoder drains JPEG bytes and keeps the latest complete image; pending AI capacity is already one. FFmpeg is persistent. Do not claim startup probing is the measured bottleneck: no physical stream measurements exist here.
- `CameraRecognitionLane.accept` counts stale empty results without rejecting them, and accepts stale nonempty results. A frame can age while waiting for the separate semaphore. Consensus can retain observations older than its window when reads arrive continuously. Slow model threads cannot be killed by asyncio cancellation; supervisor currently awaits their drain inline, potentially delaying all lane supervision.
- Candidate boxes are already sorted in `locate_plate_boxes`, but externally supplied boxes in `recognize_arrival_bytes` are trusted by index. Unknown detector score becomes 1.0. Crop OCR always enhances instead of trying the original first. Single-read acceptance checks OCR confidence alone. Models load lazily; no explicit warmup.
- Visit state stops OCR after acceptance and uses detector-only departure checks. No verified physical-presence integration is available in the worker; do not infer a sensor contract from GPIO names.
- Entry sessions already have unique event, active plate and camera/visit indexes plus transactional ParkingEntryClaim. Capture persistence lacks event/visit unique indexes and uses image ID or a one-second plate burst. Receipt printing suppresses TAKEN only, so a repeated request can reprint PRESENTED/PRINTING jobs. Gate controller persists an entry command UUID before the hardware await; physical exactly-once effects across crashes cannot be guaranteed by software alone.
- Windows kit already includes three processes and Private/Domain firewall rules for TCP 8889 / UDP 8189. Hardware SDK login, callbacks, payment and receipt-taken safety must remain compatible.

## Work and validation

Implementation and measured test results are recorded in the final stabilization report. Hardware timing values must be reported as unmeasured until collected by the diagnostic command on site.

- Completed live signaling/track/retry/cleanup changes, model warmup and startup ownership, strict stale-result rejection, FIFO admission, crop confidence/validation fixes, durable outbox/capture identity, atomic receipt/gate claims and timeline instrumentation.
- Found an additional deterministic latency source: the Site Service outbox consumer polled every two seconds. Default polling is now 100 ms.
- Restored the missing CameraLab diagnostics module from the existing packaged source. Corrected the ignore rule that hid Python media source files; preserved the existing media service module.
- Broad executable regression suite: 643 passed, five explicitly deselected existing documentation/USB checks, three subtests passed. Browser program/lifecycle regression suite: seven passed. `git diff --check` is clean.
- Preserved the user's task document, research files, existing generated kit, SDK/GPIO/payment implementation and receipt-taken policy. No real gates, printers or camera endpoints were exercised. No commits or branches were created.
- Delivery report: `SMARTPARK_STABILIZATION_REPORT.md`, including root causes, before/after paths, exact validation commands, Windows field steps, migration conflict handling and unresolved physical acceptance.
