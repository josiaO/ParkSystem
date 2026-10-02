# NEXT REALTIME STABILITY ENGINEERING — Codex execution plan

You are the senior engineer responsible for making SmartPark Edge reliable on real
Rock City Mall hardware. Work on branch:

    chatgpt/core-real-path-cleanup

Do not rewrite the working HVX/QY hardware integration. Do not change the current
SmartPark visual identity/colors. Do not add unrelated features. The current job is
realtime video, recognition continuity, stale-state removal, and exactly-once parking
session creation.

## Current field failures that motivated this build

The operator has already tested the system and reported:

- live video remains slow;
- one camera can stop detecting while the others continue;
- recognition can remain stuck on one plate and then resume only after 3–4 cars;
- an old/fixed-looking plate remains visible when there is no current plate;
- the same physical entry can create more than one parking session.

Treat these as production bugs, not cosmetic issues.

## Architecture that must remain

Native ALPR camera:

    HVX/QY callback
        -> event JPEG / native crop
        -> native OCR candidate
        -> FastPlateOCR verification of event crop/JPEG in HYBRID
        -> fusion
        -> normalized recognition event
        -> EntryLaneController / ExitLaneController

Generic non-LPR camera:

    camera RTSP
        -> MediaMTX
        -> DETECT RTSP
        -> RecognitionWorker
        -> latest-frame-only FastALPR
        -> temporal consensus
        -> normalized recognition event
        -> same parking controllers

Operator video:

    camera RTSP
        -> MediaMTX
        -> WHEP/WebRTC
        -> browser

Recognition must never be in the browser/live rendering path.

## Important fixes already implemented on this branch

Do not accidentally revert these.

1. MediaMTX + WebRTC are the preferred defaults on fresh installs, with legacy
   fallback when MediaMTX is unavailable.
2. MediaMTX RTSP stays local; WebRTC signaling listens on TCP 8889 and ICE media
   on UDP 8189.
3. Browser WHEP endpoint uses the SmartPark server's LAN hostname/IP instead of
   127.0.0.1.
4. Browser WebRTC viewers no longer start a hidden server-side FFmpeg->MJPEG
   decoder.
5. Rapid 120ms /snapshot.jpg polling fallback was removed.
6. FFmpeg MJPEG output is FPS-bounded before frames reach Python.
7. RecognitionWorker uses bounded inference concurrency instead of one global
   camera lock.
8. Camera event polling runs cameras concurrently, not serially.
9. HVX circuit breakers are per-camera.
10. Recognition worker restarts a camera task when fresh frames continue but
    inference stops advancing.
11. Native HVX last_capture is timestamped; stale native plate state is rejected.
12. PreviewState expires stale last_car and FastALPR state.
13. Browser and desktop clear the held plate/overlay when live plate state expires.
14. image_id=0 cannot reuse an old capture forever.
15. Permanent _last_image_id suppression was removed so vendor image IDs may
    restart after reconnect.
16. Consensus releases a published plate after a clear-lane/no-plate gap.
17. Exact DB idempotency already protects entry_event and an open site+plate.
18. A short same-lane/camera similar-plate guard collapses OCR variants from the
    same approach.
19. The pinned MediaMTX version is currently v1.11.3. Its WebRTC CORS key is
    webrtcAllowOrigin (singular), not the newer webrtcAllowOrigins.
20. Enable-MediaMTX.ps1 now persists rollout flags into SiteSetting, because DB
    flags override environment defaults.

## Phase A — prove the branch compiles before changing anything else

Run using the project's Python environment:

    python -m compileall -q app tools
    python -m pytest -q -p no:cacheprovider       tests/test_live_plate_freshness.py       tests/test_recognition_worker_runtime.py       tests/test_mediamtx_telemetry.py       tests/test_parking_entry.py       tests/test_recognition_commissioning.py       tests/test_parking_exit.py       tests/test_safety_regressions.py
    python -m pytest -q -p no:cacheprovider
    git diff --check

Fix every regression caused by this branch. Do not weaken assertions merely to make
tests green. Record the exact commands and final counts in
docs/engineering/CORE-PARKING-BUILD-STATUS.md.

If GitHub Actions still has no runner/steps, document it as infrastructure failure;
do not treat that as a product test failure or a passing product test.

## Phase B — validate MediaMTX version/config before runtime testing

The repo's install script currently pins MediaMTX v1.11.3.

Generate the SmartPark MediaMTX config, then start that exact version against the
generated file. It must parse successfully.

Verify:

    webrtcAddress: :8889
    webrtcLocalUDPAddress: :8189
    webrtcIPsFromInterfaces: yes
    webrtcAllowOrigin: '*'

Do not replace the singular v1.11.3 key with the v1.20 syntax unless the bundled
binary is upgraded in the same tested change.

MediaMTX must be the sole RTSP proxy owner. SiteService must not start another
MediaMTX process.

## Phase C — make the live path measurably realtime

On the actual site LAN, use one camera first.

Confirm the browser endpoint says:

    provider = MEDIAMTX
    transport = WEBRTC

If it says MJPEG or DIRECT_LEGACY, stop and fix the rollout/network path rather than
tuning OCR.

Verify from the operator PC:

    TCP server:8889 reachable
    UDP server:8189 allowed on the Private LAN firewall

Do not expose these ports on Public network profiles.

Measure glass-to-glass latency with a moving object or clock. Target:

    WebRTC preferred: normally < 500 ms on the site LAN
    temporary MJPEG fallback: < 1 s and no progressive growth

The critical requirement is bounded latency: after 30 minutes the stream must not be
4 seconds farther behind than it was at minute 1.

Check MediaMTX telemetry for:

    path readiness
    reconnect count
    readers
    RTP loss/errors
    codec
    WebRTC compatibility

Use H.264 for commissioning unless a tested reason requires another codec.

For live view, prefer SUB stream. Do not force MAIN merely for operator video.

## Phase D — prove one camera cannot starve another

Run all four cameras.

Instrument per camera:

    last_frame_at
    last_inference_at
    frame age
    inference latency p50/p95
    frames decoded
    frames dropped by latest-frame buffer
    recognition publications
    task restart count

Acceptance:

- a slow/offline camera must not stop recognition on another camera;
- no global breaker may disable healthy cameras because one HVX camera fails;
- no single inference lock may serialize all cameras;
- a stalled recognition task must self-recover within roughly 5–8 seconds;
- queues remain bounded; there must be no historical-frame backlog.

Do not increase queues to hide the fault.

## Phase E — eliminate stale/stuck plate state

Test this sequence repeatedly:

    car A arrives -> plate A shown
    car A leaves -> no current plate shown after freshness timeout
    empty lane
    car B arrives -> plate B shown immediately

Also test:

    same registration returns later
    camera disconnect/reconnect
    HVX image_id restarts/repeats
    no plate / unreadable vehicle

The live UI may show "No current plate" or equivalent. It must never substitute a
sample/default number.

Historical detections remain in Detections; they must not be presented as the current
vehicle.

Never use ParkWatch's or simulation sample plates as recognition fallback values.

## Phase F — exactly one parking session per physical entry

Use database authority, not UI state.

The following must all reuse one session:

    same event_id repeated
    same exact plate repeated while session is open
    duplicate camera callback
    outbox redelivery
    repeated OCR frames
    near-identical OCR variant from the same lane/approach

The following must create separate sessions:

    two different vehicles on different lanes
    same vehicle after its earlier visit is CLOSED and it returns
    two genuinely different plates that only look superficially similar

Inspect the database after each field pass. For one physical entry there must be:

    one ParkingSession
    one public receipt token
    at most one physical receipt print job for that entry event
    at most one automatic entry gate command

Do not solve duplicate sessions by globally merging fuzzy plates. Similarity dedupe must
remain short-lived and tied to the same camera/lane/physical approach.

If the site has a reliable loop/beam, prefer the physical presence cycle as the visit
boundary:

    clear -> occupied -> one vehicle event -> passed -> clear

and use temporal dedupe only as fallback.

## Phase G — field soak

Do not call the work complete after unit tests.

Run:

1 hour:
    one entry + one exit

8 hours:
    all four cameras, live operator UI open

24 hours:
    all cameras + recognition + parking sessions

then 72 hours before removing rollback code.

During soak, capture:

    CPU/RAM
    child FFmpeg process count
    MediaMTX readers/path count
    per-camera frame age
    p95 inference latency
    camera reconnects
    recognition worker restarts
    DB session duplicates
    stale current-plate incidents

There must be no monotonic growth in:

    frame age
    FFmpeg process count
    queue depth
    RAM caused by video buffers

## Phase H — delete obsolete code only after replacement is proven

After the live ENTRY/EXIT, MediaMTX, RecognitionWorker, and QR fallback have passed
field validation:

- remove live-only legacy media paths that can no longer be selected;
- keep explicit simulation fixtures under /sim;
- delete dead snapshot-polling helpers;
- delete duplicate old recognition orchestration;
- do not delete HVX SDK/gate control code;
- retain one documented rollback provider until the 72-hour soak passes.

## Final report

Update docs/engineering/CORE-PARKING-BUILD-STATUS.md with:

- root cause for each of the five reported field bugs;
- files changed;
- tests and exact result counts;
- actual measured live latency;
- per-camera recognition continuity results;
- duplicate-session test results;
- remaining physical limitations;
- rollback command.

Do not start mobile-payment UI, cloud AI, new design work, or unrelated modules during
this engineering pass. Realtime video + reliable recognition + exactly-once parking
sessions are the release gate.
