# SmartPark stabilization report — 19 October 2026

Status: source changes implemented and regression tested. **Physical acceptance is outstanding. This is not a production-readiness certificate.** No real camera, printer, payment provider or barrier was operated during this work. The existing USB kit in `dist/` has not been rebuilt.

## A. Root causes and risks found

### Blank live video

- `app/api_main.py:camera_live_endpoint` already rewrote the request host before this work. Therefore the document's suggested unconditional localhost bug is not the complete diagnosis of this checkout. However, it always returned HTTP signaling, including to HTTPS pages. `app/services/whep.py:browser_endpoint` now distinguishes internal RTSP, LAN HTTP WHEP, configured external signaling, and an authenticated same-origin HTTPS signaling proxy.
- `app/web/index.html:whepStart/startLiveSlot` reported LIVE on peer connection rather than on an actual decoded video frame; audio could occupy `srcObject` before a streamless video track arrived; initial signaling failure stayed on fallback indefinitely; prolonged disconnection and connected-but-frozen video lacked recovery. Switching during pending signaling also needed immediate peer cancellation. These paths now have explicit diagnostics, frame-progress monitoring, cleanup, and retry. Retrying the same camera no longer leaks viewer registrations.
- `app/services/mediamtx.py:write_config` exposed UDP ICE only. TCP 8189 is now an optional negotiated fallback alongside UDP, with matching Private/Domain Windows firewall rules. TCP can accumulate delay under congestion; prefer UDP on a healthy LAN. The setting was verified against the [pinned MediaMTX configuration](https://raw.githubusercontent.com/bluenviron/mediamtx/v1.11.3/mediamtx.yml).
- **Important hardware distinction:** `mediamtx_sources.source_config_for_camera` deliberately leaves some HVX cameras on verified SDK JPEG acquisition. Such a camera does not have a usable MediaMTX stream merely because MediaMTX is installed. No unverified RTSP source was forced onto that hardware. A real installation must identify whether each camera is using SDK JPEG or an explicitly configured RTSP path.

### Slow or stale recognition

- `app/api_main.py:_outbox_loop` slept two seconds between business-event polls. This alone added up to roughly two seconds between recognition and parking work. Its configurable default is now 100 ms (`SMARTPARK_PARKING_EVENT_POLL_SECONDS`).
- `CameraRecognitionLane.accept` accepted stale positive results and only counted stale negative results. Both are now rejected. Frame age is rechecked before detector/OCR execution after waiting for the worker limiter, and after detection. Default recognition policy remains a strict 1000 ms frame-age bound.
- `ConsensusTrack.observe` retained votes older than the observation window when reads arrived continuously. It now expires old votes; matching reads still publish immediately when policy is met. Ties are deterministic.
- `ArrivalGate.note_ocr` reset the settling timer after every unsuccessful read even when the box remained stationary. A settled vehicle can now contribute the next fresh agreeing read without another settling wait. Existing bounded failure cooldown remains.
- Models were lazy and Windows startup did not register the recognition worker. Scheduled tasks and optional SCM registration now include it. Worker startup warms detector and OCR without publishing, waits for a migrating/unavailable database, and reports readiness only after warmup. Fresh worker claims prevent Site Service fallback from simultaneously taking software ownership during warmup/recovery.
- Supervisor recovery awaited a slow model's thread inline. Retiring lane tasks now drain independently, and that camera cannot launch a replacement until its previous task finishes. Other lanes and health heartbeats continue. An actually hung native/model thread still requires process recovery; asyncio cannot forcibly stop it.
- The existing FFmpeg decoder was already persistent, local-only, latest-JPEG draining, and configured with `probesize=32` / `analyzeduration=0`. Those options were retained because no physical startup measurements justified changing them.

### Crop/OCR weakness

- `recognize_arrival_bytes` trusted the first externally supplied box even though the normal detector path already ranked its output. Supplied boxes are now validated and ranked before selection.
- `_hits_from_detections` always enhanced crops. It now tries a padded/resized original crop first, and at most one enhanced retry for a plausible, weaker read. Empty or invalid OCR waits for another frame. Unknown detector confidence is zero, rather than fabricated certainty.
- `should_persist_vehicle_capture` treated a software detector rectangle as native vehicle evidence through `native_from_sdk_capture`. This bypassed software confidence, shape and sign-text checks. Software captures now take their intended validation path.
- Worker single-read acceptance now also requires detector confidence >=0.85, a crop at least 80x20 px, and the configured format policy. OCR still must exceed the configured strict threshold (default 0.92). These are conservative starting values, **not site-benchmarked thresholds**.

### Duplicates

- `domain.events.from_recognition_dict` dropped visit/frame identity at the worker → outbox boundary. Hybrid fusion also dropped local visit metadata. Both preserve it now.
- Capture persistence used image ID or a one-second same-plate burst, without durable event/visit constraints. Event/visit identity now takes precedence; replay returns the existing capture, and unique database indexes resolve concurrent insert races.
- Receipt printing only suppressed TAKEN jobs. Repeated PRESENTED/PRINTING requests could print again. A committed conditional database claim now owns the print job before hardware I/O; duplicate requests return the existing job and receipt QR.
- Gate command ownership was checked on ORM objects before hardware awaits. ENTRY and EXIT now claim the command with conditional database updates. EXIT also recognizes a completed event before touching a later active session for the same plate.

### Lane reliability and packaging

- Unassigned recognition scope meant all cameras. Production now fails closed unless a gate is assigned or all-gates mode is explicitly enabled. Browser lane presets can change scope only in DEVELOPMENT. Operator status reports `NODE NOT ASSIGNED TO GATE`.
- The scheduler named FairInferenceScheduler had no waiting order. It now maintains FIFO camera admission, a bounded global cap, and at most one slot per camera. Generation-mismatched results cannot release a replacement generation's slot.
- `.gitignore`'s broad `media/` rule hid required Python media modules. The missing diagnostics module was restored from the existing packaged source; the existing service module is preserved, and the source package is no longer ignored. CameraLab now imports and runs from source.

## B. Before architecture

RTSP-configured camera → MediaMTX shared role paths → browser HTTP WHEP / local JPEG fallback.

MediaMTX local RTSP → persistent per-camera FFmpeg → capacity-one mailbox → detector → repeated settle wait → first supplied box → enhanced crop OCR → consensus → outbox with lost visit identity → up to 2s poll delay → capture heuristics → entry/exit controller → receipt policy → gate.

HVX SDK-only cameras followed the existing host `Net_StartVideo` / `Net_GetJpgBuffer` and native callbacks, with Site Service software fallback. This hardware path was not silently replaced.

## C. After architecture

RTSP camera → MediaMTX (source discovery, reconnect, role sharing and fan-out) → browser WebRTC media directly. HTTP LAN signaling uses the request host; HTTPS can proxy only signaling through Site Service. Local recognition RTSP stays `rtsp://127.0.0.1:8554/<path>`.

Warm per-camera decoder → latest frame only → fair bounded admission → freshness checks → configured ROI → ranked valid detector box → validated padded crop → original OCR / one conditional enhancement → normalization with raw confidence retained → guarded fast read or early temporal consensus → durable visit/event identity → durable outbox → 100ms polling → unique capture → existing unique session/entry claim → claimed receipt job → receipt-taken safety policy → claimed gate command.

## D. Live-video behavior and configuration

- Default LAN: `http://<Site-Service-request-host>:8889/<path>/whep`.
- HTTPS page: `/cameras/<id>/live/whep` by default, with the same API bearer authorization. Site Service forwards OPTIONS/POST/PATCH/DELETE to a fixed local MediaMTX target and rewrites session Location headers. It does not relay RTP/video.
- Optional override: `SMARTPARK_MEDIAMTX_BROWSER_BASE_URL=https://<reachable-signaling-host>`; an HTTP override on an HTTPS page is explicitly degraded instead of silently creating mixed content.
- ICE media must reach the MediaMTX machine on UDP 8189, or TCP 8189 as fallback. Signaling port 8889 must be reachable for direct LAN mode. RTSP/control/metrics remain local.
- The browser uses a non-trickle gathered SDP offer, video-only `srcObject`, autoplay/muted/playsinline, authenticated same-origin requests, and no API token on cross-origin signaling.
- LIVE requires a video frame. Errors identify signaling failure, ICE failure, a missing video track, absent decoded frames/codec issues, or an offline MediaMTX path. No new CCTV server or always-on transcoder was added.

## E. Recognition performance evidence

**Physical decoder startup, source-to-frame delay, detector p50/p95, OCR p50/p95, consensus latency and total plate latency are unmeasured here.** No numbers were inferred from unit-test execution time.

Worker health now reports warmup time, decoder first-frame time/uptime, current input age, sample FPS, mailbox depth/replacements, detector/crop/OCR/recognition and vehicle-to-plate p50/p95/max (rolling 200 samples), PID, reconnects and errors. Process CPU is reported in units of one CPU core; RAM is the worker's resident memory, not whole-machine or decoder memory.

The timestamp called frame received/decoded is the local decoder's receive time. Without a trustworthy camera timestamp, it does **not** establish sensor-to-host or glass-to-glass latency. Measure that separately on site.

`alpr_timeout_seconds=15` remains a failure ceiling in the legacy Site Service inference wrapper and a liveness allowance in `_worker_ready`; it is not a normal sleep or latency target. The dedicated worker's stall watchdog remains separate. ONNX intra-op threads can be configured through `SMARTPARK_RECOGNITION_MODEL_THREADS` (0 retains the library default). Concurrency was not increased without measurements.

## F. Crop/OCR pipeline

Fresh JPEG → lane ROI/zoom → detector → confidence/geometry ranking → clamped configurable padding → nonempty/minimum geometry checks → aspect-preserving resize → original crop OCR → optional single enhancement for a plausible weak read → Tanzania-aware normalization/validation → raw OCR confidence plus separate detector confidence and consensus evidence.

No plate or invalid crop yields no plate. OCR is not used for departure. After confirmation, OCR pauses and detector-only departure checks continue at the configured interval. Physical coil/native presence is preferable only after the site's signal is verified and made available to the worker; this work does not assume that integration exists across processes.

## G. Duplicate guarantees and limits

1. Per-camera visit and consensus suppress repeated publication while occupied.
2. Visit identity survives worker/outbox/hybrid boundaries. The SQLite outbox's published-identity ledger prevents replayed enqueue after acknowledgement or restart.
3. Capture unique indexes protect `(camera_id,event_id)` and `(camera_id,visit_id)` for nonempty IDs; persistence catches constraint races and returns the winner.
4. Existing site/event, site/camera/visit and active-plate session indexes plus ParkingEntryClaim remain authoritative.
5. Receipt jobs commit ownership before printing and suppress PRINTING/PRESENTED/TAKEN repeats.
6. ENTRY and EXIT commit gate command ownership before invoking hardware, retaining UUIDs for audit/recovery.
7. A genuinely departed/new visit receives a different ID. A plate can enter again once its previous session has completed.

Migration `0008_capture_identity` deliberately refuses historical duplicate identities rather than deleting evidence. Back up the site database before upgrade; reconcile any reported historical conflict and retry migration.

These are durable logical idempotency guarantees for stable identities. A printer/gate without an idempotent hardware acknowledgement cannot offer mathematical physical exactly-once effects through power loss. An indeterminate PRINTING or gate-command claim must be investigated before an operator retry. Physical visit continuity across a worker/process outage, false absence, or bumper-to-bumper vehicles still requires field/sensor verification; do not equate a newly generated visit UUID with proof of a new physical vehicle.

## H. ENTRY/EXIT concurrency

Each camera retains independent decoder, mailbox, sequence/generation, arrival gate, consensus, visit, plate state and reconnect lifecycle. Only inference capacity/models are shared. Slow cancellation drains only its retiring camera; it does not synchronously stop supervision of the other lane. Receipt-taken and payment policies remain in the controllers.

## I. Four-camera behavior

Explicit all-gates mode is `SMARTPARK_RECOGNITION_ALL_GATES_ENABLED=true` with no gate pin. Otherwise each PC should set its own gate ID. FIFO admission is covered with four cameras and concurrency two. Production hardware throughput remains unmeasured; compare concurrency 1 and 2 and ONNX thread counts using the same stopped-vehicle sample set. A finite slow call cannot continually jump ahead of waiting cameras; an indefinitely hung underlying model call still consumes real capacity until process recovery.

## J. Receipt/gate timeline

`lane_timing` carries monotonic visit-relative stages through the outbox/capture and logs structured records keyed by visit/camera/direction: vehicle seen, frame selected/decoded, detector start/end, crop/OCR stages, consensus, capture saved, controller entry, session created, receipt requested/printed, gate requested, controller return. Capture JSON retains the business timeline. `/health/realtime` exposes vehicle-origin business-stage p50/p95/max. Native paths lacking a vehicle-origin timestamp do not fabricate those totals.

Physical plate-confirmed → receipt available → receipt taken → gate timings remain unmeasured. Receipt-taken safety was not bypassed. A waiting-receipt controller return is not a completed gate workflow.

## K. Validation

- Focused Python suite: 175 passed at the first integration checkpoint. Final targeted validation is recorded below.
- Broad Python suite: 643 passed, 5 explicitly deselected, 3 subtests passed in 83.90s. Command:

```bash
SMARTPARK_DATA_DIR=/tmp/smartpark-stabilization-final .venv/bin/python -m pytest -q \
  --deselect=tests/test_migration_architecture.py::OperatorStatusTests::test_required_docs_exist \
  --deselect=tests/test_modules.py::DocsExistTests::test_module_docs_tree \
  --deselect=tests/test_ui_productization.py::ProductUiTests::test_ui_docs_exist \
  --deselect=tests/test_windows_packaging.py::WindowsPackagingTests::test_production_tree_is_this_rebuild \
  --deselect=tests/test_windows_packaging.py::WindowsPackagingTests::test_usb_payload_has_runtime_binaries_and_complete_wheels
```

- The five excluded checks concern pre-existing missing `docs/` files and a forbidden `pyside6_addons-6.12.0` wheel in the existing generated USB payload. An unrestricted run exposed these; they were not hidden by changing the tests. The kit remains unverified and must be rebuilt before distributing this change.
- Final targeted run, including the last timestamp/confidence metadata changes: **191 passed in 24.36s**, with one existing Starlette/httpx deprecation warning. Exact command:

```bash
SMARTPARK_DATA_DIR=/tmp/smartpark-stabilization-final .venv/bin/python -m pytest -q \
  tests/test_production_stabilization.py tests/test_recognition_worker_runtime.py \
  tests/test_alpr.py tests/test_recognition_decoder.py tests/test_mediamtx_telemetry.py \
  tests/test_media_acquisition.py tests/test_parking_exit.py tests/test_parking_entry.py \
  tests/test_parking_receipts.py tests/test_platform_migrations_secrets.py \
  tests/test_hybrid_fusion.py tests/test_windows_ready.py
```

- `node tests/whep-player.test.cjs`: 7 passed. Exercises the actual inline browser functions: full-program parsing, frame-based LIVE, audio/video handling, session DELETE, camera switching including pending signaling, signaling retry, viewer-count stability, token origin isolation and frozen-frame detection.
- `git diff --check`: clean. CameraLab `--help` runs from source.
- New Python regressions cover HTTPS/local endpoint separation, proxy methods/error state, stale positives, bounded independent mailboxes, four-camera FIFO, fast-path guards, consensus expiry/early acceptance, supplied-box ranking/invalid crops, warmup without publication, outbox replay after ack, capture identity across DB sessions and production ownership.
- Existing regression suites exercise crop-only OCR, same-plate returns/departure, entry/session/receipt/gate idempotency, hybrid paths, decoder lifecycle and migration upgrades. Assertions affected by intentional changed behavior were updated, not disabled.

## L. Windows field actions

Use a rebuilt source-matching kit, back up the installation database, and preserve the existing `.env` and credentials. From the installed SmartPark directory, set these keys in `.env` for a one-PC-per-gate deployment:

```dotenv
SMARTPARK_DEPLOYMENT_PROFILE=PRODUCTION
SMARTPARK_RECOGNITION_GATE_ID=1
SMARTPARK_RECOGNITION_ALL_GATES_ENABLED=false
SMARTPARK_RECOGNITION_SAMPLE_FPS=3
```

Use gate ID 2 on the other gate PC. Do not copy a gate pin unchanged to both PCs. All service processes must use the same install directory, data directory and configuration. The optional SCM path defaults to PRODUCTION as well, but still needs its account/data-directory configuration verified on Windows.

Register/restart background tasks and LAN firewall rules from PowerShell (run firewall configuration as Administrator):

```powershell
.\Install-SmartParkServices.ps1 -InstallDir (Get-Location).Path
.\Enable-MediaMTX.ps1 -InstallDir (Get-Location).Path -LiveView
Get-ScheduledTask -TaskName 'SmartPark*'
```

Run non-publishing diagnostics:

```powershell
& .\python64\python.exe -m tools.camera_lab --camera 1 --duration 60 --recognition --latency
& .\python64\python.exe -m tools.camera_lab --gate 1 --duration 300 --recognition --latency
& .\python64\python.exe -m tools.camera_lab --all --duration 1800 --latency
```

Or use `Run-CameraLab.ps1 -Gate 1 -Duration 300 -Recognition -Latency`. The command reads health and optionally OCRs a diagnostic frame; it does not publish captures, sessions, receipts, payments or gate requests. The running Site Service continues its separately configured normal business processing.

On another LAN PC, open `http://<server>:8760`, then Live Gates. Check actual video, camera switching, temporary network interruption and recovery. With HTTPS, verify signaling uses `/cameras/<id>/live/whep` or the configured HTTPS override, and media ICE reaches the server. Check that simultaneous browser viewing does not add a physical RTSP ingest (MediaMTX role sharing/readers and source connections).

Record 30 minutes of simultaneous operation, then test stopped vehicles at ENTRY and EXIT, including an empty lane, weak/unreadable crop, same plate returning after completion, long occupancy, camera reconnect, and simultaneous lanes. Count logical captures/sessions/receipt jobs/automatic command UUIDs per visit. Observe physical receipt removal and passage policy separately. Capture structured timelines and compare concurrency 1 versus 2 and configured model thread counts after restarting the worker for each configuration. Measure glass-to-glass delay with an external visible time/LED reference; transport byte counters alone are insufficient.

## M. Outstanding hardware-dependent acceptance

Actual HVX SDK-versus-RTSP source behavior; camera H.264 profile/B-frame/GOP compatibility; Windows firewall/ICE routes and HTTPS proxy deployment; decoder startup/reconnect on the actual streams; ONNX throughput and model assets; day/night crop quality; false departures and verified loop/presence edges; real printer acknowledgement/removal; physical gate acknowledgement/retry behavior; four-camera CPU/RAM stability; 1–3s stopped-vehicle recognition and sub-500ms video where hardware permits; and 30-minute live stability remain field tests.

Do not release this as production-ready until those measurements meet the requested acceptance targets.
