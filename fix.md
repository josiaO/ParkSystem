You are working directly on the SmartPark/ParkSystem repository.

This is a FIELD-FAILURE engineering pass, not a feature-development pass.

Read AGENTS.md first and obey its architectural invariants.

The previous realtime-stability work has already been merged. Do NOT assume those fixes solved the physical installation merely because tests pass.

I tested the current build against the real parking cameras after the previous fixes.

REAL FIELD RESULTS:

1. Live video is STILL slow / delayed.
2. Plate recognition works reasonably well, but sometimes one camera effectively stops detecting.
3. When this happens, recognition can remain stuck on the previous plate and only start recognizing again after approximately 3–4 vehicles have already passed.
4. There appears to be a fixed/default/hardcoded/stale registration number that remains visible when there is actually no plate.
5. A vehicle/session can still be saved multiple times. This must be prevented.
6. There are four physical cameras. Failure or slow processing on one camera must never interfere with another camera.
7. Do not destroy the working HVX/QY SDK integration, native ALPR callbacks, FastALPR support, gate control, MediaMTX support, or the existing parking architecture.

Treat the field observations above as higher-value evidence than passing unit tests.

# PRIMARY OBJECTIVE

Make the realtime camera -> video -> recognition -> vehicle event -> parking session pipeline deterministic, bounded and self-recovering.

The system must satisfy:

Camera
  -> latest video frame
  -> recognition
  -> vehicle/plate event
  -> exactly-once parking decision

without allowing an old frame, old plate, blocked OCR call, slow camera, duplicated callback, repeated OCR result or UI state to become a new parking event.

---

# PART 1 — TRACE THE REAL PIPELINE BEFORE MODIFYING IT

Do not blindly patch symptoms.

Trace the actual production path for each camera from:

HVX/RTSP input
-> MediaMTX/direct provider
-> live UI
-> recognition input
-> FastALPR/native OCR
-> hybrid/fusion/consensus
-> normalized recognition event
-> EntryLaneController / ExitLaneController
-> ParkingSession persistence
-> UI last-car state

Identify every queue, lock, thread, asyncio task, executor, polling loop, cache and persistence boundary involved.

Specifically inspect the current implementations around:

- app/api_main.py
- app/services/preview.py
- recognition worker/runtime
- FastALPR pipeline
- MediaMTX registry/provider
- HVX host event draining
- hybrid/fusion/consensus
- EntryLaneController
- ExitLaneController
- session-from-capture path
- UI live pane / plate refresh
- camera health/watchdog logic
- event deduplication

Search the entire repository rather than assuming these are the only files involved.

Before changing behavior, determine WHY a camera can stop recognizing for multiple vehicles.

---

# PART 2 — ELIMINATE RECOGNITION BACKLOG

This is critical.

Recognition must implement:

LATEST FRAME WINS.

A slow inference must NEVER create:

frame1 -> frame2 -> frame3 -> frame4 -> frame5 -> ...

waiting for OCR.

For each camera there may be at most ONE pending recognition frame.

If inference is currently processing frame N and N+1, N+2 and N+3 arrive, discard obsolete pending frames and retain only the newest frame.

The next inference should process N+3.

Do not use an unbounded asyncio.Queue.

Prefer a per-camera latest-frame mailbox / single-slot buffer with sequence numbers and monotonic timestamps.

Every recognition request/result should carry:

- camera_id
- frame_seq or event_seq
- captured_at monotonic/wall timestamp
- recognition_started_at
- recognition_finished_at
- frame_age_ms
- inference_ms

A recognition result that belongs to an obsolete vehicle/frame must not overwrite a newer result.

Explicitly protect against out-of-order inference completion.

Example:

camera frame 100 starts OCR
camera frame 101 starts/queues
frame 101 completes first
frame 100 completes later

frame 100 MUST NOT replace frame 101 state.

---

# PART 3 — CAMERA ISOLATION

Each camera must be its own failure domain.

Camera 1 slow/stuck:
    Cameras 2/3/4 continue normally.

FastALPR slow on one camera:
    live video remains smooth
    other recognition workers continue.

HVX request timeout:
    other cameras continue.

Check whether shared:

- semaphore
- executor
- lock
- event loop
- FFmpeg process
- recognition worker
- HTTP connection
- circuit breaker

can still cause starvation.

A global recognition concurrency limit is acceptable only if it cannot allow one camera to monopolize all inference capacity.

Implement fairness if required.

---

# PART 4 — RECOGNITION WATCHDOG

The current system apparently can enter a state where a camera does not produce useful recognition for several passing vehicles.

Add a real per-camera recognition watchdog.

Track at least:

last_frame_at
last_frame_seq
last_recognition_started_at
last_recognition_completed_at
last_successful_read_at
recognition_inflight
recognition_frame_seq
recognition_age_ms
dropped_ai_frames
recognition_restart_count

If video frames continue arriving but recognition has been in-flight longer than SMARTPARK_RECOGNITION_WORKER_STALL_SECONDS:

1. mark that recognition worker/camera STALLED;
2. prevent the stuck result from later overwriting current state;
3. recreate/recover the affected recognition worker or inference context safely;
4. continue from the newest available frame;
5. increment watchdog telemetry;
6. do NOT restart unrelated cameras.

Do not create infinite thread/process leaks.

A recovered worker must invalidate results from the previous worker generation.

Use a generation/token mechanism if necessary.

---

# PART 5 — REMOVE THE PHANTOM / HARDCODED PLATE COMPLETELY

I still see what appears to be a fixed plate when there is no real plate.

Do not merely hide it in one UI component.

Search the ENTIRE repository for:

- sample registration numbers
- placeholder plate numbers
- default plate values
- test plate values accidentally reachable by production
- stale `last_car`
- stale FastALPR result
- stale native `last_capture`
- DB fallback to latest historical detection
- JavaScript defaults
- HTML placeholders
- Python defaults
- demo data
- cached fusion result
- consensus published_plate
- native SDK cached callback

There must be a semantic distinction between:

NO CURRENT VEHICLE / NO CURRENT PLATE

and:

LAST HISTORICAL DETECTION.

The live operator screen must NEVER display historical detection as if it were currently under the camera.

When the lane becomes empty, the current recognition state must transition to:

plate = null/empty
vehicle_present = false
recognition_state = IDLE

after a bounded configurable timeout.

Historical detections remain available in history only.

Do not fabricate a registration when OCR returns nothing.

---

# PART 6 — VEHICLE PRESENCE / VISIT LIFECYCLE

Plate strings alone must not define vehicle visits.

Implement/strengthen an explicit per-camera visit lifecycle:

IDLE
-> VEHICLE_PRESENT
-> RECOGNIZING
-> PLATE_CONFIRMED
-> EVENT_PUBLISHED
-> VEHICLE_DEPARTING
-> IDLE

The same continuously visible vehicle must not repeatedly publish entry events.

A new visit begins only after credible separation from the previous vehicle, based on available evidence such as:

- coil/presence sensor where reliable;
- detection absence;
- bounded no-vehicle interval;
- new native capture event;
- significant temporal separation.

Do not require the plate to change, because the same vehicle can legitimately return later.

Do not allow an old published plate to survive indefinitely into another vehicle visit.

---

# PART 7 — EXACTLY-ONCE PARKING SESSION CREATION

This is a RELEASE-BLOCKING requirement.

One physical vehicle entry must produce ONE parking session.

Deduplication must exist at multiple levels, but the database must provide the final guarantee.

Do not rely solely on an in-memory dictionary or a 2-second timer.

Investigate all code paths capable of creating ParkingSession.

There should ideally be ONE authoritative application/domain entry command.

Possible duplicate sources include:

native OCR callback
+
FastALPR verification
+
hybrid fusion
+
polling
+
repeated camera callback
+
retry
+
UI/API request

These may all refer to the SAME physical vehicle.

Create a stable event/visit/idempotency identity.

Examples:

camera visit ID
camera_id + visit_generation
native image/event ID where available
normalized recognition event UUID

EntryLaneController should consume an idempotency key.

Persistence must enforce the invariant transactionally.

If two concurrent requests attempt:

create_session(same physical visit)

both may execute, but only ONE may create the database session.

The other must return the existing session with:

duplicate=true

or equivalent.

Use an appropriate UNIQUE database constraint / idempotency table / transactional conflict handling.

Do not solve this only with:

if existing:
    return existing

because two concurrent transactions can both pass that check.

Also protect against near-identical OCR variants from the SAME visit, e.g.:

T285DQP
T285DOP
T285DQP

These must not become three sessions.

However, do not globally merge unrelated vehicles merely because plates are similar.

Similarity dedupe must be scoped to the same camera visit/presence window.

---

# PART 8 — LIVE VIDEO LATENCY

The live video remains slow after MediaMTX/WebRTC work.

Measure the actual source of latency instead of adding arbitrary FPS changes.

For every camera determine:

camera timestamp/frame arrival
MediaMTX ingest latency
browser WebRTC latency
recognition frame latency

Verify:

- one upstream connection per camera/stream role;
- no accidental double live transport;
- no MJPEG/snapshot polling behind WebRTC;
- no unnecessary transcoding;
- correct substream selection;
- RTSP transport;
- GOP/keyframe behavior where observable;
- MediaMTX path readiness;
- WHEP/WebRTC actually being used by the browser;
- no fallback silently returning to a delayed legacy transport.

Expose the active live provider visibly in diagnostics:

MEDIAMTX_WEBRTC
DIRECT_MJPEG
SNAPSHOT
OFFLINE

Also expose estimated live frame age where technically measurable.

Do not claim WebRTC is active merely because configuration says MEDIAMTX.

Confirm the browser/player actually negotiated it.

If WebRTC fails and fallback is used, diagnostics must say so.

---

# PART 9 — NEVER COUPLE VIDEO DISPLAY TO OCR

Live video must not wait for:

FastALPR
native OCR
database writes
session creation
gate decision
receipt printing

The video path and recognition path consume the camera independently through the proper media fan-out architecture.

A 2-second OCR inference must not create a 2-second video freeze.

---

# PART 10 — OBSERVABILITY

Add a per-camera realtime diagnostic snapshot/API containing at least:

camera_id
camera_name
live_provider
live_connected
last_frame_at
frame_seq
estimated_frame_age_ms
recognition_state
recognition_generation
recognition_inflight
recognition_frame_seq
last_recognition_completed_at
last_plate
last_plate_age_ms
vehicle_present
visit_id
dropped_ai_frames
recognition_stalls
recognition_restarts
native_events_received
software_reads
published_events
duplicate_events_suppressed
sessions_created

This must make it possible to determine why Camera #N stopped without guessing.

Do not expose credentials.

---

# PART 11 — REGRESSION TESTS

Add deterministic tests for at least:

TEST A — latest-frame-wins

Submit frames:
1,2,3,4,5

while inference is slow.

Verify obsolete pending frames are dropped and the worker processes the newest frame rather than building a five-frame backlog.

TEST B — out-of-order results

Older OCR completes after newer OCR.

Verify old result cannot replace current plate.

TEST C — camera isolation

Block Camera 1 recognition.

Verify Cameras 2,3,4 continue processing.

TEST D — worker stall

Simulate an inference call that never completes normally.

Verify watchdog recovery occurs and the next fresh frame can be recognized.

TEST E — stale plate

Recognize T123ABC.

Then simulate an empty lane.

Verify the live API/UI eventually returns no current plate.

TEST F — phantom/default plate

No OCR/native result exists.

Verify no fabricated/sample registration is returned anywhere in the live path.

TEST G — repeated same recognition

Send the same vehicle recognition repeatedly during one continuous visit.

Verify ONE recognition event / ONE ParkingSession.

TEST H — concurrent duplicate creation

Execute two concurrent entry submissions for the same visit/idempotency key.

Verify database contains exactly ONE ParkingSession.

TEST I — OCR variation

Within one physical visit:

T285DQP
T285DOP
T285DQP

Verify exactly ONE session.

TEST J — same vehicle returns later

Vehicle leaves, lane resets, then T285DQP returns.

Verify a NEW legitimate visit/session can be created.

TEST K — four-camera stress

Simulate all four cameras simultaneously with one slow camera.

Verify no starvation and bounded queues.

---

# PART 12 — FIELD DIAGNOSTIC TOOL

Create a Windows-friendly diagnostic command/script for the real installation.

For 5–10 minutes it should sample all four cameras and produce a report containing:

- live provider;
- frame rate;
- frame age;
- recognition throughput;
- inference latency p50/p95/max;
- dropped AI frames;
- worker stalls/restarts;
- native callback count;
- recognized vehicle count;
- duplicate events suppressed;
- sessions created;
- camera disconnect/reconnect count.

This is essential because unit tests cannot reproduce the physical camera/network/SDK behavior.

Do not require cloud services.

---

# PART 13 — PERFORMANCE TARGETS

For healthy LAN cameras:

LIVE VIDEO:
normal frame age < 500 ms where achievable by the camera/codec/network.

RECOGNITION:
AI input should normally be < 1000 ms old.

QUEUES:
recognition pending queue depth <= 1 per camera.

ISOLATION:
one stalled camera causes zero recognition stoppage on other cameras.

STALE STATE:
an absent vehicle must not leave a plate permanently displayed.

SESSION:
one physical entry visit = exactly one ParkingSession.

RECOVERY:
recognition worker failure must self-recover without restarting SmartPark or unrelated cameras.

---

# PART 14 — DO NOT DO THESE

Do NOT:

- rewrite the entire application;
- replace the working HVX SDK integration;
- guess undocumented relay/GPIO mappings;
- add Redis/Celery just to solve local concurrency;
- use an unbounded queue;
- increase buffering to hide stalls;
- make live video dependent on OCR;
- create sessions directly from raw OCR strings in multiple modules;
- use only UI-side deduplication;
- use only an in-memory timer for session uniqueness;
- silently fall back to a sample/default plate;
- mark a field issue fixed merely because a unit test passes.

Preserve rollback paths.

---

# REQUIRED EXECUTION ORDER

1. Inspect current architecture and latest realtime-stability changes.
2. Write a concise root-cause report for EACH field symptom.
3. Add instrumentation necessary to prove/disprove the root causes.
4. Fix recognition scheduling/backpressure.
5. Fix stale/default plate lifecycle.
6. Fix per-camera isolation/watchdog recovery.
7. Implement database-backed exactly-once session creation.
8. Fix/measure live video latency.
9. Add regression tests.
10. Run narrow tests.
11. Run full test suite.
12. Produce the Windows field diagnostic tool.
13. Update engineering documentation.

Do not stop after analysis. IMPLEMENT the changes.

---

# FINAL REPORT REQUIRED

At completion report:

## Root causes
For each of:
- slow live video
- camera recognition stopping
- old plate sticking
- phantom/default plate
- duplicate ParkingSession

## Code changed
List exact files and important functions/classes.

## Architecture after fix
Show the realtime flow.

## Tests
Give exact commands and pass/fail counts.

## Concurrency guarantees
Explain how:
- frame backlog is bounded;
- stale OCR results are rejected;
- cameras are isolated;
- stalled recognition recovers;
- duplicate sessions are transactionally impossible.

## Field verification
Give exact commands I should run on the real four-camera Windows installation.

## Remaining hardware-dependent checks
Clearly state anything that cannot be proven without the real cameras.

Do not claim the four-camera physical problem is solved until the field diagnostic evidence confirms it.