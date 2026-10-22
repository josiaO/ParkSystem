# SmartPark Production Stabilization Audit & Reengineering Task

## Context

You are working on the existing **SmartPark / ParkSystem** codebase.

This task is based on the current repository state after commit:

`0e892ff318ae13b9f08f5a0aa62787131bc196ca`
**Merge PR #6 — "Fixed the mediaMTX issue"**

Do **not** assume that the latest implementation is correct merely because tests pass or because plate recognition works.

The system has been tested against real cameras and currently exhibits these production-critical symptoms:

1. SmartPark can see the vehicle internally, locate/crop the number plate, and OCR it.
2. **Live video is not displaying correctly on the operator screen.**
3. Recognition is **too slow**. A vehicle can already have passed the camera before the recognition result arrives.
4. In real production the vehicle stops at a barrier. The current latency could force a driver to wait **more than 20 seconds** before receipt printing and gate opening. This is unacceptable.
5. Plate crop and OCR work, but need to become more robust and deterministic.
6. **A physical vehicle visit must not create duplicate recognition events, VehicleCaptures, parking sessions, receipts, or automatic gate-open workflows.**
7. The installation has multiple cameras and two directions per gate. The current lane/gate concurrency model must be audited for reliability and isolation.

This is a **production stabilization/reengineering task**, not a feature-building task.

---

# 1. SOURCE CODE IS AUTHORITATIVE

Do not rely on old architecture documents or previous prompts.

Before modifying code, inspect and trace the actual runtime implementation.

At minimum inspect:

- `app/api_main.py`
- `app/config.py`
- `app/media_service.py`
- `app/recognition_worker.py`
- `app/infrastructure/media/`
- `app/infrastructure/recognition/`
- `app/services/mediamtx.py`
- `app/services/mediamtx_live.py`
- `app/services/mediamtx_detect.py`
- `app/services/mediamtx_sources.py`
- `app/services/mediamtx_telemetry.py`
- `app/services/media_gateway.py`
- `app/services/recognition_decoder.py`
- `app/services/recognition_runtime.py`
- `app/services/alpr.py`
- `app/services/camera_framing.py`
- `app/services/captures.py`
- `app/services/dedup.py`
- `app/core/consensus.py`
- `app/services/live_pair.py`
- `app/services/lane_status.py`
- `app/services/node_scope.py`
- `app/application/live_parking.py`
- `app/application/entry_lane.py`
- `app/application/exit_lane.py`
- HVX camera adapters/client/host
- the browser Live Gates implementation
- `app/web/mediamtx-reader.js`
- all browser JavaScript that creates/updates/destroys video players
- all tests related to media, recognition, visits, sessions, lanes and gates
- Windows startup/service/packaging scripts for Site Service, Media Service and Recognition Worker.

Use repository search to find all callers and related implementations.

Do not create a replacement subsystem until you understand the existing one.

---

# 2. START BY BUILDING THE REAL RUNTIME MAP

Before editing, write a short audit in your work log showing the actual current path for:

## Live video

Physical camera
→ source discovery/config
→ MediaMTX
→ endpoint API
→ browser
→ video element

## Recognition

Physical camera
→ MediaMTX
→ local RTSP
→ recognition decoder
→ latest-frame mailbox
→ detector
→ plate crop
→ OCR
→ normalization
→ temporal consensus
→ VehicleCapture/event
→ live parking bridge
→ entry/exit controller
→ receipt/gate.

## Lane ownership

PC/node
→ selected gate
→ ENTRY camera
→ EXIT camera
→ per-camera recognition runtime
→ shared inference resources.

Identify every point where:

- a frame can be buffered;
- a stale frame can survive;
- an FFmpeg process can block;
- inference can block another lane;
- the browser can receive an unusable URL;
- a recognition can be published twice;
- a session can be created twice;
- the same physical camera can be opened multiple times unnecessarily.

Then fix the architecture, not only the symptom.

---

# 3. PRIORITY ZERO — FIX LIVE VIDEO

Recognition working while the operator sees no video is not acceptable.

Audit the complete WebRTC/WHEP path.

The current code constructs MediaMTX endpoints similar to:

`http://127.0.0.1:8889/<path>/whep`

This is potentially correct for a browser running on the MediaMTX machine but incorrect for a browser running on another operator PC.

In a remote browser:

`127.0.0.1`

means the **operator PC**, not the SmartPark server.

At the same time, the generated MediaMTX configuration exposes WebRTC signaling on the LAN.

Investigate this carefully.

Do NOT blindly replace `127.0.0.1` everywhere because localhost is desirable for internal recognition RTSP.

There must be a distinction between:

### Internal endpoint

Used by local SmartPark processes:

`rtsp://127.0.0.1:8554/...`

### Browser endpoint

Must be reachable by the browser:

`http://<smartpark-server-host>:8889/.../whep`

or an equivalent correctly proxied same-origin endpoint.

Prefer a robust solution where the API/browser derives the externally reachable MediaMTX host from the request/server configuration rather than embedding localhost.

If practical, proxy only WHEP signaling appropriately while allowing WebRTC media to use MediaMTX directly. Do not turn FastAPI into the video relay.

Audit:

- endpoint generation;
- host rewriting;
- HTTP vs HTTPS/mixed-content behavior;
- CORS;
- WHEP OPTIONS/POST/PATCH/DELETE;
- ICE candidates;
- UDP 8189;
- TCP fallback;
- Windows firewall requirements;
- browser codec compatibility;
- `<video autoplay muted playsinline>`;
- `srcObject`;
- track events;
- player cleanup/recreation;
- switching cameras/gates;
- reconnect behavior.

Add visible diagnostic errors to the UI. A black video rectangle must not hide the reason.

Examples:

- MEDIA PATH OFFLINE
- WHEP SIGNALING FAILED
- ICE FAILED
- CODEC UNSUPPORTED
- MEDIA RECEIVED BUT VIDEO TRACK MISSING.

Do not report LIVE merely because MediaMTX's process exists.

---

# 4. MEDIA ARCHITECTURE

MediaMTX should carry the video burden.

Target:

```
CAMERA
   |
   v
MediaMTX
   |---------------------> WebRTC/WHEP ---> Browser
   |
   +---------------------> local RTSP ---> Recognition Decoder
   |
   +---------------------> Evidence when required
```

Do not implement a CCTV server in Python.

MediaMTX should own:

- RTSP ingest;
- reconnect to network video where appropriate;
- fan-out;
- WebRTC;
- stream transport.

Python owns:

- configuration/orchestration;
- health;
- recognition;
- parking logic.

Do not add Frigate/Agent DVR/Viseron/etc. unless there is a proven requirement MediaMTX cannot meet.

Do not unnecessarily transcode.

Remux where possible.

---

# 5. LATENCY IS NOW A HARD REQUIREMENT

The current physical behavior is unacceptable if recognition can take 10–20+ seconds.

Measure end-to-end latency.

Instrument timestamps for:

1. source frame received/decoded;
2. recognition frame selected;
3. detector started;
4. detector finished;
5. crop prepared;
6. OCR started;
7. OCR finished;
8. consensus accepted;
9. VehicleCapture/event persisted;
10. parking controller entered;
11. receipt print requested;
12. receipt printed/available;
13. gate command issued.

Report:

- p50;
- p95;
- maximum;
- per-stage duration.

Do not optimize blindly.

Find the actual bottleneck.

---

# 6. PRODUCTION LATENCY TARGET

A stopped vehicle should normally receive a useful recognition result in approximately:

**1–3 seconds**

under healthy LAN/camera conditions.

A high-confidence clean read may be accepted faster.

The driver must not routinely wait 10, 15 or 20 seconds for recognition.

A configurable timeout can exist for fault recovery, but a 15-second ALPR timeout must NOT become the normal latency budget.

The current configuration includes an `alpr_timeout_seconds` around 15 seconds.

Audit every place this timeout is used.

Differentiate:

- watchdog timeout;
- maximum failure timeout;
- normal expected inference time.

Do not wait for a 15-second timeout before moving to the next fresh frame during normal recognition.

---

# 7. THE VEHICLE STOPS AT THE GATE

Do not design this as highway ALPR.

Expected physical behavior:

```
approach
   ↓
slow
   ↓
stop at barrier
   ↓
remain visible for several seconds
   ↓
receipt
   ↓
gate opens
```

Exploit this.

Live video can remain 20–25 FPS.

Recognition does NOT need to infer at 20–25 FPS.

Start around 3–5 fresh recognition samples/sec, benchmark it, and tune.

The important rule is:

**recognition must always work on the newest useful frame.**

---

# 8. NO FRAME BACKLOG

Keep pending AI frame capacity at **one latest frame per camera**.

If:

```
101
102
103
104
105
```

arrive while inference is working on 101, do not process 102 → 103 → 104 later.

Replace pending work until 105 remains.

After inference completes:

process 105.

Measure `input_frame_age_ms`.

Normal recognition should not begin on a frame already several seconds old.

Define a strict stale-frame threshold.

Discard stale work.

---

# 9. AUDIT THE RECOGNITION DECODER

Current code uses a local MediaMTX RTSP stream and FFmpeg in `recognition_decoder.py`.

This is conceptually reasonable.

However, audit the FFmpeg command for actual low-latency behavior.

Current options include probing/analyze durations that can potentially introduce startup latency.

Benchmark startup-to-first-frame.

Do not simply remove FFmpeg options without measuring.

Test appropriate low-latency options for the actual camera streams.

Measure:

- decoder startup ms;
- first-frame ms;
- frame age;
- reconnect time;
- CPU;
- memory.

The decoder must connect only to local MediaMTX.

Do not reconnect directly to the physical camera from recognition.

---

# 10. KEEP DECODERS WARM

Do not repeatedly start FFmpeg for every recognition attempt.

One long-running lightweight decoder per active camera/lane is acceptable.

It should continuously replace the latest frame.

Recognition samples from that current frame.

This removes decoder startup latency from vehicle recognition.

Expected:

```
camera
→ MediaMTX
→ persistent local decoder
→ latest frame slot
                     |
vehicle arrives -----+
                     ↓
                  detector
```

not:

```
vehicle arrives
→ start FFmpeg
→ probe RTSP
→ wait
→ decode
→ detect
```

---

# 11. REENGINEER DETECTION → CROP → OCR IF NECESSARY

The current system already detects and crops plates.

Do not throw that away.

Audit it carefully and strengthen it.

Correct pipeline:

```
fresh frame
   ↓
lane ROI
   ↓
plate detector
   ↓
candidate boxes
   ↓
candidate quality/ranking
   ↓
padded crop
   ↓
crop validation
   ↓
OCR preprocessing
   ↓
OCR
   ↓
TZ normalization/validation
   ↓
temporal consensus
```

OCR must operate primarily on the **plate crop**, not the whole vehicle image.

---

# 12. IMPROVE PLATE BOX SELECTION

Do not blindly use `boxes[0]` unless detector output ordering is guaranteed and tested.

Rank candidate boxes.

Consider:

- detector confidence;
- location within configured lane ROI;
- plate aspect ratio;
- minimum pixel dimensions;
- distance from expected gate recognition zone;
- crop sharpness/quality where useful.

Reject impossible/tiny boxes.

If multiple plausible plates exist, maintain candidates carefully rather than randomly selecting the first returned detection.

---

# 13. CROP QUALITY

For a selected box:

1. clamp coordinates;
2. apply configurable padding;
3. preserve aspect ratio;
4. reject empty/invalid crops;
5. ensure adequate plate pixel size;
6. upscale small plates only when useful;
7. avoid destructive preprocessing.

Benchmark preprocessing variants.

Possible variants:

- original crop;
- contrast enhanced;
- grayscale;
- sharpened;
- adaptive/equalized only if measured useful.

Do not run every preprocessing variant for every frame if one clean crop already produces a high-confidence result.

Use a staged strategy:

```
normal crop OCR
   ↓
if weak
enhanced crop OCR
   ↓
if still weak
wait for next fresh frame
```

A stopped vehicle gives us another frame almost immediately.

That is usually cheaper than repeatedly processing one poor frame.

---

# 14. TANZANIAN PLATES

Preserve the Tanzania-aware cleanup already implemented.

But never fabricate confidence.

Keep separately:

- raw OCR text;
- normalized text;
- OCR confidence;
- detector confidence;
- format validity;
- consensus confidence.

A Tanzania plate pattern can help rank/validate candidates.

It must not turn a 30% OCR read into a 90% read.

---

# 15. FAST ACCEPTANCE

Do not force every vehicle to wait for multiple reads if one result is extremely strong.

Use a two-path policy.

## Strong single read

If:

- detector confidence is strong;
- crop quality is good;
- OCR confidence exceeds a strict high threshold;
- normalized plate passes configured format policy;

then permit fast acceptance.

## Normal read

Otherwise require temporal consensus from multiple fresh frames.

This should allow excellent frames to complete quickly while protecting against OCR mistakes.

Benchmark thresholds from actual site data.

---

# 16. CONSENSUS MUST NOT ADD UNNECESSARY DELAY

Audit `ConsensusTrack`.

A consensus window of two seconds should be a maximum observation opportunity, not an unconditional two-second sleep.

If two agreeing reads arrive at:

`t=0.00`

and:

`t=0.25`

the system should be able to confirm at ~0.25s if policy permits.

Do not wait until the entire consensus window expires.

---

# 17. EARLY EXIT AFTER CONFIRMATION

Once the current vehicle has a confirmed plate:

STOP OCR for that visit.

Live video continues.

Only cheap vehicle-presence/departure logic should continue.

Do not repeatedly OCR:

`T123ABC`

for another ten seconds.

This wastes CPU and creates duplicate risk.

---

# 18. AUDIT DEPARTURE DETECTION

The current recognition worker appears to perform detector-only checks after a plate is confirmed.

Verify whether this is efficient and reliable.

A detector inference every second may still consume meaningful CPU across multiple lanes.

If a reliable physical coil/vehicle-presence signal exists for the HVX lane, prefer it for presence/departure.

Possible priority:

1. physical loop/coil/presence sensor when verified;
2. native camera vehicle-presence event;
3. lightweight visual presence;
4. plate detector as fallback.

Do not require expensive OCR to detect departure.

---

# 19. DUPLICATES — DEFINE THE INVARIANT

For one physical vehicle visit to an ENTRY lane:

```
ONE vehicle visit
→ ONE accepted recognition
→ ONE authoritative VehicleCapture/event
→ AT MOST ONE active parking session
→ AT MOST ONE entry receipt print job
→ AT MOST ONE automatic gate-open workflow
```

Retries may occur internally but must remain idempotent.

For EXIT:

```
ONE vehicle visit
→ ONE accepted recognition
→ ONE authoritative exit event
→ ONE transition of the correct active session
→ AT MOST ONE automatic exit gate-open workflow
```

---

# 20. DUPLICATION MUST BE PREVENTED AT MULTIPLE LEVELS

Do not depend only on an in-memory 2-second deduper.

Audit:

- native callback dedup;
- recognition consensus publication;
- `visit_id`;
- event IDs;
- VehicleCapture persistence;
- entry/exit controller idempotency;
- database uniqueness constraints;
- active-session constraints;
- receipt job idempotency;
- gate command UUID/idempotency.

The current `EventDeduper(window_seconds=2.0)` is useful for noisy callbacks but is not enough as the sole business invariant.

A vehicle can remain at the barrier longer than two seconds.

Visit identity must be the primary dedupe boundary.

Where appropriate enforce invariants at the database level as the final protection.

---

# 21. SAME PLATE CAN RETURN LATER

Do not solve duplicates by permanently suppressing a plate.

Correct:

```
Visit A:
T123ABC
→ publish once

vehicle leaves
→ visit closes

later:

Visit B:
T123ABC
→ may publish again
```

Deduplication must be **visit-scoped**, not permanently plate-scoped.

---

# 22. AUDIT TWO-LANE / TWO-DIRECTION ARCHITECTURE

The current code scopes a node to a `gate_id`.

A gate can have:

- ENTRY camera;
- EXIT camera.

This is conceptually a good architecture if each camera has independent runtime state.

Verify that this is actually true.

Each camera must have its own:

- decoder;
- latest-frame mailbox;
- sequence numbers;
- vehicle visit;
- consensus track;
- crop state;
- current plate;
- recognition state;
- reconnect state;
- metrics.

ENTRY must never overwrite EXIT state.

EXIT must never block ENTRY unnecessarily.

---

# 23. GLOBAL INFERENCE RESOURCE SHARING

The current configuration uses bounded recognition concurrency.

Audit whether the current semaphore/scheduler gives fair service to ENTRY and EXIT.

With two cameras:

```
ENTRY
EXIT
```

both must progress.

With four cameras:

```
Gate A ENTRY
Gate A EXIT
Gate B ENTRY
Gate B EXIT
```

a slow inference from one camera must not starve the others.

If one global semaphore with concurrency=2 is adequate on the production hardware, retain it.

If fairness is weak, implement explicit fair scheduling/round-robin latest-frame work.

Never create an unbounded worker per frame.

---

# 24. FIX AMBIGUOUS NODE OWNERSHIP

Audit `node_scope.py`.

Current behavior can choose the first gate automatically when no explicit assignment exists.

That may be convenient in development but is dangerous in production.

Production must not silently choose a gate.

Implement explicit behavior such as:

### Development

Allow deliberate auto/default selection when a development flag/profile explicitly enables it.

### Production

Require an explicit gate assignment.

If missing:

- recognition does not start;
- UI clearly reports `NODE NOT ASSIGNED TO GATE`;
- do not accidentally OCR another gate.

For a CLIENT node, existing explicit gate requirements should remain.

Make ownership deterministic.

---

# 25. CLARIFY THE PHYSICAL DEPLOYMENT

Do not assume every installation has the same process topology.

Support the intended topology explicitly.

For example:

### One PC per gate

PC A:
- Gate A ENTRY
- Gate A EXIT

PC B:
- Gate B ENTRY
- Gate B EXIT.

Each PC should process only its assigned cameras.

If one server intentionally processes all four cameras, that must be an explicit supported mode with measured resource capacity, not an accidental fallback.

---

# 26. ENTRY PRIORITY

At a parking barrier, ENTRY recognition is latency-sensitive because the driver is waiting for:

recognition
→ session
→ receipt
→ gate.

EXIT is also latency-sensitive but must not cause ENTRY starvation.

Consider fair scheduling and, only if justified by measured contention, slight priority for an actively occupied barrier.

Do not permanently starve another lane.

---

# 27. RECEIPT/GATE CRITICAL PATH

Recognition is only part of the delay.

Measure after plate acceptance.

Trace:

```
accepted plate
→ VehicleCapture
→ live_parking
→ EntryLaneController
→ DB
→ receipt generation
→ printer
→ receipt-taken policy
→ gate command
```

Determine whether receipt generation/printing or DB work adds seconds.

Do not optimize OCR and leave a 10-second printer path.

The desired user experience should be approximately:

```
vehicle stops
~1–3s: plate confirmed
immediately: session decision
immediately: receipt print begins
receipt available/taken
gate opens according to configured safety policy
```

Do not bypass the receipt-taken safety policy merely to improve benchmark numbers.

---

# 28. THREAD/ASYNC AUDIT

The current code uses `asyncio.to_thread`, inference helpers, semaphores and model calls.

Audit for:

- event-loop blocking;
- CPU-bound work on event loop;
- thread oversubscription;
- nested thread pools;
- ONNX thread oversubscription;
- semaphore held longer than necessary;
- tasks waiting on obsolete frames;
- cancellation that cannot cancel an underlying model thread.

Do not solve latency by simply increasing concurrency.

More inference threads can make CPU inference slower.

Benchmark:

- concurrency 1;
- concurrency 2;
- model thread count;
- actual production CPU.

Choose based on measurements.

---

# 29. MODEL WARMUP

Ensure detector/OCR models are initialized and warmed before the first real vehicle.

The first customer of the day must not pay model initialization cost.

At recognition-worker startup:

- initialize models;
- run a safe synthetic/warmup inference if supported;
- report READY only after warmup succeeds.

Do not publish fake recognition events during warmup.

Measure:

- cold inference;
- warm inference.

---

# 30. OBSERVABILITY

For each camera expose:

- MediaMTX path state;
- browser endpoint;
- browser transport;
- source codec;
- decoder PID;
- decoder uptime;
- last decoded frame;
- frame age;
- sampled FPS;
- queue depth;
- dropped/replaced frames;
- detector ms;
- OCR ms;
- total recognition ms;
- last plate;
- current visit ID;
- recognition state;
- duplicate events suppressed;
- captures created;
- sessions created;
- receipt jobs created;
- gate commands issued;
- reconnect count;
- last error.

Do not expose credentials.

---

# 31. ADD AN END-TO-END LANE TIMELINE

For field testing, log one structured timeline per vehicle visit.

Example:

```
visit=abc
camera=1
direction=ENTRY

vehicle_seen        +0ms
frame_selected      +42ms
detector_complete   +185ms
crop_ready          +188ms
ocr_complete        +310ms
consensus_confirmed +570ms
capture_saved       +590ms
session_created     +625ms
receipt_requested   +650ms
receipt_printed     +920ms
gate_requested      +...
```

This will make future performance problems obvious.

Use monotonic timing for durations.

---

# 32. TESTS REQUIRED

Add regression tests for at least:

### Streaming

1. browser WHEP endpoint is not unusable localhost when accessed remotely;
2. local recognition RTSP remains localhost;
3. MediaMTX unavailable gives explicit UI/API state;
4. video player reconnects after temporary WHEP failure;
5. switching camera closes the old peer connection;
6. browser viewing does not start another physical camera ingest.

### Recognition

7. latest-frame mailbox remains <=1;
8. stale frame is dropped;
9. strong clean plate can be accepted quickly;
10. weak plate requires consensus;
11. consensus does not wait full window once criteria are met;
12. OCR receives crop;
13. invalid crop falls back safely;
14. candidate boxes are ranked rather than blindly trusting arbitrary ordering;
15. no plate returns no plate;
16. old plate does not leak into next vehicle;
17. model warmup occurs without publishing an event.

### Duplicate protection

18. same visit cannot publish twice;
19. duplicate recognition event cannot create two VehicleCaptures;
20. duplicate capture cannot create two active entry sessions;
21. receipt cannot print twice for the same entry transaction;
22. automatic gate workflow is idempotent;
23. same plate after a completed/departed visit can legitimately enter again.

### Lane isolation

24. ENTRY and EXIT have independent mailboxes;
25. ENTRY and EXIT have independent visit state;
26. slow ENTRY inference does not corrupt EXIT;
27. slow EXIT does not prevent ENTRY indefinitely;
28. failure/reconnect of one camera does not restart the other;
29. gate/node scope never silently processes the wrong production gate;
30. four-camera scheduler remains bounded and fair.

---

# 33. BUILD A REAL FIELD TEST COMMAND

Create or improve a diagnostic command that can run without opening gates or creating parking sessions.

Examples conceptually:

```
python -m tools.camera_lab --camera 1 --duration 60
python -m tools.camera_lab --gate 1 --duration 300
python -m tools.camera_lab --all --duration 900
```

Adapt to actual project conventions.

Add optional:

```
--recognition
--latency
```

Report:

- stream ready;
- source codec/resolution;
- first-frame latency;
- current frame age;
- decoded FPS;
- sample FPS;
- detector p50/p95;
- OCR p50/p95;
- total recognition p50/p95;
- crop size;
- accepted plates;
- duplicate suppressions;
- CPU;
- RAM;
- decoder count;
- reconnects.

The diagnostic MUST NOT:

- create ParkingSession;
- print receipt;
- open gate;
- mark payment.

---

# 34. ACCEPTANCE TARGETS

Do not declare production-ready only because unit tests pass.

Target under healthy LAN/camera conditions:

### Live video

- visible in operator UI;
- no progressive lag;
- ideally <500 ms glass-to-glass where hardware/browser permit;
- no multi-second accumulated backlog;
- stable for at least 30 minutes initial field test.

### Recognition

- fresh input frame;
- normal stopped vehicle recognition ~1–3 seconds;
- strong clean plate potentially faster;
- no routine 10–20 second recognition;
- no stale vehicle recognized after it has left.

### Resources

- stable process count;
- stable decoder count;
- bounded queues;
- bounded RAM;
- reasonable CPU;
- no process storms.

### Duplicates

One visit must produce one business action.

### Isolation

Failure of one camera/lane must not take down another.

---

# 35. PRESERVE WORKING HARDWARE

Do not casually rewrite:

- HVX/QY SDK host;
- verified camera login;
- native callbacks;
- GPIO;
- gate controller;
- receipt printer adapters;
- payment logic.

If a working hardware component must change, explain exactly why and preserve compatibility.

MediaMTX is video transport.

It does not replace gate control.

---

# 36. IMPLEMENTATION STRATEGY

Use this order.

## Phase 1 — Audit

No architecture assumptions.

Map current runtime.

## Phase 2 — Fix live video

Get reliable browser video from MediaMTX.

Verify locally and from another LAN PC.

## Phase 3 — Instrument latency

Know where time is spent.

## Phase 4 — Fix frame freshness/decoder

Persistent decoder, latest-frame-only.

## Phase 5 — Strengthen detector/crop/OCR

Candidate ranking, crop validation, staged OCR, Tanzania policy.

## Phase 6 — Optimize recognition acceptance

Strong-read fast path + normal temporal consensus.

## Phase 7 — Duplicate-proof the visit

Trace event → capture → session → receipt → gate.

## Phase 8 — Audit/reengineer lane isolation

Explicit node/gate ownership, independent camera state, fair bounded inference.

## Phase 9 — End-to-end latency

Measure through receipt/gate.

## Phase 10 — Tests and field diagnostics.

Do not perform a cosmetic refactor while leaving the runtime behavior unchanged.

Reengineer a subsystem if the current design fundamentally prevents the targets above.

---

# 37. FINAL REPORT

When finished, STOP and report:

## A. Root causes found

For each reported symptom:

- blank live video;
- stale/slow recognition;
- crop/OCR weakness;
- duplicates;
- lane reliability;

give exact file/function and cause.

## B. Before architecture

Show actual previous data flow.

## C. After architecture

Show actual new data flow.

## D. Live video fix

Explain WHEP URL/host, WebRTC and browser changes.

## E. Recognition performance

Report:

- decoder startup;
- frame age;
- detector p50/p95;
- OCR p50/p95;
- consensus time;
- total plate time.

## F. Crop/OCR improvements

Show exact pipeline.

## G. Duplicate guarantees

Explain every idempotency layer.

## H. Two-lane behavior

Explain exactly how ENTRY and EXIT run concurrently and how state is isolated.

## I. Four-camera behavior

Explain resource sharing and fairness.

## J. Receipt/gate latency

Report plate-confirmed → receipt → gate timings.

## K. Tests

Exact commands and results.

## L. Physical field test

Give exact commands/actions I should run on the real SmartPark Windows installation.

## M. Remaining hardware-dependent unknowns

Do not claim these are solved until field tested.

---

# Final engineering principle

The production system should behave like this:

```
                 ┌──────────── Browser / Operator
                 │               smooth WebRTC
                 │
Camera ──> MediaMTX
                 │
                 └──> persistent recognition decoder
                               │
                         latest frame only
                               │
                         lane ROI
                               │
                         plate detector
                               │
                       ranked plate box
                               │
                         validated crop
                               │
                              OCR
                               │
                       temporal consensus
                               │
                       one vehicle visit
                               │
                       ONE accepted event
                               │
                    ENTRY / EXIT controller
                               │
                    receipt / payment / gate
```

For every vehicle, optimize for:

**freshness first, fast correct recognition second, exactly-once business behavior third, and graceful failure throughout.**

Do not optimize raw FPS at the expense of frame age.

Do not optimize OCR accuracy by making drivers wait 20 seconds.

Do not solve duplicates with arbitrary long cooldowns.

Do not make the UI responsible for recognition.

Do not let one lane own or corrupt another lane's state.

Do not call the system production-ready until the real four-camera/gate installation validates these properties.
