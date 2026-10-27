# SmartPark Production Video Streaming Stabilization & Multi-Camera Reengineering

You are working directly on the **current SmartPark/ParkSystem repository**.

Your task is to **audit, diagnose, implement, test, and stabilize the complete live-video subsystem** for BOTH:

1. Standard IP cameras such as Hikvision, Dahua, ONVIF/RTSP-compatible cameras, and other generic IP cameras.
2. The existing vendor/HVX/QY ALPR cameras that SmartPark currently connects to through the vendor SDK / SDK host.

This is **NOT a rewrite of SmartPark**.

Do not redesign working parking, gate, receipt, payment, session, or hardware-control logic unless a proven video-related defect requires a narrowly scoped change.

The goal is:

> SmartPark must have low-latency, continuously moving, production-quality live video from every supported camera while FastALPR operates independently on fresh frames without causing the video to freeze, stall, accumulate latency, or jump forward.

---

# 1. SOURCE CODE IS THE AUTHORITY

Before changing anything, inspect the CURRENT repository.

Do not assume old documentation describes the current implementation.

Trace the actual runtime code.

At minimum inspect all current modules related to:

- camera connection
- vendor/HVX SDK host
- vendor SDK wrappers
- RTSP discovery
- RTSP probing
- MediaMTX
- media registry
- media gateway
- live preview
- MJPEG
- WebRTC/WHEP
- browser video
- desktop video
- recognition decoder
- FastALPR
- latest-frame buffers
- FFmpeg
- stream profiles
- camera roles
- camera health
- reconnect logic
- camera lifecycle
- recognition worker
- node/gate camera assignment

Search the repository for at least:

```text
Net_StartVideo
Net_GetImage
Net_GetJpgBuffer
Net_RegImageRecv
live_jpeg
live-jpeg
MediaMTX
WHEP
WebRTC
RTSP
MJPEG
ffmpeg
LatestFrameBuffer
take_latest_jpeg
recognition_decoder
recognition_worker
snapshot
preview
stream
CameraMediaSession
```

Do not begin by inventing a new architecture.

First document internally:

```text
Current physical camera
    ↓
current acquisition mechanism
    ↓
current media owner
    ↓
current decoder
    ↓
current buffer
    ↓
current API
    ↓
current UI
```

for every camera type.

---

# 2. CURRENT OBSERVED FAILURE

The physical cameras connect successfully.

SmartPark can see frames and FastALPR can detect/crop/read plates.

However, live video has production-critical problems:

- video sometimes freezes
- moving vehicles appear stationary temporarily
- video later jumps/skips forward
- frames appear discontinuous
- video may become slower while recognition is running
- vendor-camera live video does not appear as fluid as the vendor/ParkWatch software
- previous versions have suffered several seconds of live-video latency
- recognition has previously operated on frames that were already too old

Treat these as real production failures.

Do not hide the symptoms by increasing buffers.

---

# 3. FUNDAMENTAL REAL-TIME RULE

SmartPark is a parking/access-control system, NOT an NVR.

For live video:

> CURRENT FRAME IS MORE IMPORTANT THAN EVERY FRAME.

If frames arrive:

```text
100
101
102
103
104
105
```

but the consumer cannot keep up, displaying:

```text
100 → 101 → 102 → 103 → 104 → 105
```

several seconds later is WRONG.

Prefer:

```text
100 → 105
```

if necessary.

Never allow live video to accumulate a large historical queue.

Use bounded buffers.

For live/recognition handoff:

```text
capacity ≈ 1 latest frame
```

where appropriate.

But understand this distinction:

**Dropping stale frames is correct. Producer starvation is not.**

If acquisition stops for two seconds and resumes, latest-frame-wins will visibly produce:

```text
moving
freeze
freeze
jump
moving
```

The task is therefore to find and eliminate acquisition stalls while retaining bounded buffers.

---

# 4. SUPPORT TWO FUNDAMENTALLY DIFFERENT CAMERA CLASSES

Do NOT force all cameras through one acquisition implementation.

Create/retain a clean abstraction while allowing different optimized transports.

## Camera class A — Standard RTSP/ONVIF cameras

Examples:

- Hikvision
- Dahua
- generic ONVIF cameras
- generic RTSP cameras

Preferred architecture:

```text
CAMERA
   │
   │ RTSP H.264/H.265
   ▼
MediaMTX
   │
   ├────────────→ WebRTC/WHEP → browser/operator live view
   │
   ├────────────→ local RTSP → recognition decoder
   │
   └────────────→ evidence/snapshot consumer if required
```

MediaMTX should be the primary video transport/router.

SmartPark should NOT independently open multiple upstream RTSP connections for:

- UI
- recognition
- snapshot
- diagnostics

unless there is a proven technical requirement.

Prefer:

```text
ONE upstream camera stream
        ↓
     MediaMTX
        ↓
multiple consumers
```

---

# 5. VENDOR / HVX / QY CAMERA INVESTIGATION

This is a critical part of the task.

The current implementation appears to use something similar to:

```text
Vendor camera
     ↓
Net_StartVideo
     ↓
SDK Host
     ↓
Net_GetJpgBuffer
     ↓
/live-jpeg/{handle}
     ↓
repeated HTTP polling
     ↓
LatestFrameBuffer
     ↓
MJPEG/UI
```

Audit the current implementation and verify whether this remains true.

The code may repeatedly call:

```python
host.live_jpeg(handle)
```

which performs an HTTP request against something like:

```text
/live-jpeg/{handle}
```

The SDK host may return the previous JPEG repeatedly until a new JPEG becomes available.

This can produce:

```text
frame 1
frame 2
frame 2
frame 2
frame 2
frame 7
```

which appears to the operator as:

```text
movement
FREEZE
jump
movement
```

DO NOT simply increase the polling frequency.

Determine the actual cause.

---

# 6. INVESTIGATE THE VENDOR'S REAL VIDEO CAPABILITIES

The vendor ecosystem contains functions previously discovered such as:

```text
Net_StartVideo
Net_GetImage
Net_GetJpgBuffer
Net_RegImageRecv
Net_RegReportMessEx
```

Search the current repository, vendor SDK files, headers, reverse-engineered bindings, existing SDK-host implementation and any available original ParkWatch/OcxConfig code/configuration.

Determine:

1. How does `Net_StartVideo` actually work?
2. Does it establish a continuous compressed video stream?
3. Is `Net_GetJpgBuffer` merely a convenience snapshot API?
4. Is there a video callback?
5. Is there a raw/compressed frame callback?
6. Does `Net_RegImageRecv` receive event photographs only or continuous video?
7. Can the SDK render directly to a window?
8. Can it provide H.264/H.265 packets?
9. Can it expose decoded RGB/YUV frames?
10. Does the camera expose RTSP independently of the SDK?
11. What RTSP paths/ports does the original software use?
12. Does the camera expose ONVIF?
13. Does the camera expose HTTP video endpoints?
14. How does the original ParkWatch/vendor viewer achieve smooth live video?

Do not guess.

Use repository evidence and runtime probes where possible.

---

# 7. FIRST PREFERENCE FOR VENDOR CAMERAS: FIND RTSP

Determine whether the vendor camera exposes a usable RTSP stream.

Probe intelligently.

Do NOT aggressively scan unrelated network devices.

For the configured camera IP, investigate common/configured vendor endpoints and existing configuration.

If reliable RTSP exists, prefer:

```text
HVX/QY CAMERA
       │
       ├──────── RTSP ───────→ MediaMTX
       │                         │
       │                         ├→ WebRTC → UI
       │                         │
       │                         └→ RTSP → recognition
       │
       └──────── Vendor SDK
                    │
                    ├→ native ALPR event
                    ├→ coil/presence
                    ├→ GPIO
                    ├→ gate relay
                    └→ vendor-specific operations
```

This separation is desirable.

The vendor SDK does NOT need to own video merely because it owns gate control.

---

# 8. SECOND PREFERENCE: PROPER SDK CONTINUOUS VIDEO

If the vendor cameras do NOT expose reliable RTSP, determine whether the SDK provides continuous video more efficiently than repeated JPEG HTTP polling.

The desired architecture becomes:

```text
Vendor camera
      ↓
Net_StartVideo
      ↓
continuous SDK video acquisition
      ↓
ONE CameraVideoProducer
      │
      ├────────────→ operator live view
      │
      └────────────→ latest recognition frame
```

If the SDK produces compressed H.264/H.265 packets and it is technically safe to do so, investigate publishing that stream into MediaMTX.

For example conceptually:

```text
Vendor SDK compressed stream
        ↓
small adapter
        ↓
MediaMTX
        ↓
WebRTC + recognition consumers
```

Do NOT implement this blindly.

Only do it if the SDK's actual data format and lifecycle are understood.

---

# 9. JPEG POLLING MUST BECOME FALLBACK, NOT IDEAL VIDEO

If `Net_GetJpgBuffer` polling remains necessary, make it a robust fallback.

Do not pretend that repeated JPEG snapshots are equivalent to a native video stream.

The implementation must distinguish:

```text
NATIVE_RTSP
SDK_CONTINUOUS
SDK_JPEG_FALLBACK
GENERIC_RTSP
```

or equivalent internal transport modes.

Expose the selected transport in diagnostics.

Example:

```text
Camera 1
transport: VENDOR_RTSP
upstream_fps: 25
display_fps: 24.7
fresh_frame_age: 52 ms
```

versus:

```text
Camera 2
transport: SDK_JPEG_FALLBACK
poll_fps: 20
unique_frame_fps: 7
duplicate_ratio: 61%
```

This distinction is important.

---

# 10. DETERMINE WHY THE CURRENT VIDEO FREEZES

Instrument before making speculative fixes.

For every camera collect:

```text
camera_id
transport
source
source_fps
frames_received
frames_changed
duplicate_frames
duplicate_ratio
live_fps
frame_interval_avg_ms
frame_interval_p50_ms
frame_interval_p95_ms
frame_interval_max_ms
live_frame_age_ms
last_received_age_ms
decoder_restarts
reconnects
decode_errors
buffer_depth
CPU load if practical
recognition active/inactive
```

For SDK JPEG cameras distinguish:

```text
HTTP requests completed
JPEG responses
unique JPEGs
duplicate JPEGs
empty JPEG responses
request latency p50
request latency p95
request latency max
SDK acquisition latency
```

This allows distinguishing:

### Failure A — repeated SDK image

```text
requests ↑
frames_received ↑
duplicate_frames ↑↑
frames_changed slowly
```

### Failure B — SDK/HTTP acquisition blocked

```text
requests stall
frames_received stalls
```

### Failure C — consumer/UI problem

```text
frames_changed healthy
live_frame_age healthy
displayed frames stall
```

### Failure D — CPU contention

```text
recognition OFF → video healthy
recognition ON → frame intervals explode
```

### Failure E — decoder/reconnect thrashing

```text
decoder_restarts ↑↑
reconnects ↑↑
```

Make these states visible in diagnostics.

---

# 11. RUN AN A/B RECOGNITION CONTENTION TEST

Implement a diagnostic/test procedure that compares:

## Test A

```text
camera connected
recognition disabled
live video running
```

Measure video metrics.

## Test B

```text
same camera
recognition enabled
live video running
```

Measure the same metrics.

If recognition causes:

```text
live_fps ↓
frame_interval_p95 ↑
fresh frame age ↑
```

then investigate:

- Python event-loop blocking
- ONNX thread oversubscription
- FastALPR CPU saturation
- JPEG encoding
- excessive copies
- excessive HTTP polling
- FFmpeg process count
- recognition concurrency
- synchronous CPU work in async functions

Do not fix CPU starvation by buffering video.

---

# 12. LIVE VIDEO MUST NEVER WAIT FOR FASTALPR

Enforce this invariant:

```text
video acquisition
      │
      ├────────→ UI
      │
      └────────→ latest-frame mailbox
                       ↓
                    FastALPR
```

NOT:

```text
camera
 ↓
frame
 ↓
FastALPR
 ↓
next frame
 ↓
FastALPR
 ↓
UI
```

FastALPR may be slow.

Live video must continue independently.

If OCR takes 800 ms, the UI must still receive current video.

---

# 13. SEPARATE LIVE FPS FROM RECOGNITION FPS

Cars approach slowly and normally stop at the barrier.

Therefore SmartPark does NOT need to run OCR at camera frame rate.

Target concept:

```text
camera/source:       15–25 FPS where available
operator live view:  15–25 FPS where practical
recognition sampling: 3–5 fresh FPS
OCR: only while plate recognition is needed
```

Keep these independently configurable.

Do not reduce live-video FPS merely because recognition only needs 4 FPS.

---

# 14. RECOGNITION MUST USE LATEST-FRAME-WINS

Recognition queue capacity must remain bounded.

Conceptually:

```text
inference running on frame 100

101 arrives
102 arrives
103 arrives
104 arrives

inference finishes

next frame = 104
```

NOT:

```text
101 → 102 → 103 → 104
```

Never allow FastALPR to become seconds behind the physical lane.

Measure:

```text
frame_capture_timestamp
recognition_start_timestamp
recognition_end_timestamp
```

Calculate:

```text
input_frame_age_ms
inference_ms
result_age_ms
```

Reject stale recognition work where appropriate.

---

# 15. DO NOT CONFUSE FRAME SKIPPING WITH VIDEO FAILURE

Some frame skipping is desirable when the system falls behind.

But this:

```text
25 FPS source
→ occasional dropped frame
→ live age 50–150 ms
```

is acceptable.

This:

```text
freeze 2 sec
→ jump
→ freeze 3 sec
→ jump
```

is NOT acceptable.

Optimize for:

```text
freshness
continuity
bounded latency
```

not perfect delivery of every frame.

---

# 16. STANDARD RTSP CAMERA REQUIREMENTS

For Hikvision, Dahua and generic RTSP cameras:

- prefer camera substream for live operator view when appropriate
- use MediaMTX as upstream router
- avoid unnecessary transcoding
- remux whenever possible
- use H.264 when browser compatibility requires it
- handle H.265 capability explicitly
- correctly detect unsupported browser codecs
- prefer WebRTC/WHEP for low-latency browser display
- use local RTSP for recognition
- implement reconnect with bounded exponential backoff
- avoid spawning repeated FFmpeg processes
- ensure dead child processes are reaped
- maintain one logical media session per camera

Test both TCP and UDP where appropriate, but default to the most reliable LAN behavior based on evidence.

Do not blindly switch transport.

---

# 17. WEBRTC/WHEP MUST WORK FROM ANOTHER COMPUTER

Audit browser endpoint construction carefully.

Internal service URLs and browser URLs are NOT necessarily the same.

This is valid for internal recognition:

```text
rtsp://127.0.0.1:8554/camera
```

But sending this to an operator browser on another PC is wrong:

```text
http://127.0.0.1:8889/camera/whep
```

because `127.0.0.1` then refers to the operator PC.

Maintain separate concepts:

```text
INTERNAL_MEDIA_BASE
BROWSER_REACHABLE_MEDIA_BASE
```

or use same-origin/proxy/host rewriting.

Audit:

- WHEP URL
- browser host
- CORS
- HTTP/HTTPS mixed-content restrictions
- ICE candidates
- MediaMTX WebRTC ports
- Windows firewall
- LAN firewall
- codec compatibility
- autoplay behavior
- WHEP lifecycle
- reconnect lifecycle

A failed WebRTC connection must show a meaningful UI diagnostic rather than a permanently black rectangle.

---

# 18. DO NOT TRANSCODE UNLESS NECESSARY

Preferred:

```text
Camera H.264
    ↓
MediaMTX remux
    ↓
WebRTC
```

not:

```text
H.264
 ↓
decode
 ↓
encode H.264
 ↓
WebRTC
```

unless compatibility requires transcoding.

Recognition necessarily needs pixels:

```text
MediaMTX RTSP
      ↓
decoder
      ↓
pixel/JPEG frame
      ↓
FastALPR
```

That decode is legitimate.

Do not perform an additional unnecessary video encode just for FastALPR.

---

# 19. REVIEW CURRENT FFMPEG SETTINGS

Inspect the actual current FFmpeg invocation.

Do not blindly apply generic "low latency" flags.

Measure:

- startup time
- first-frame time
- steady-state latency
- CPU
- reconnect time
- frame freshness

Review current values such as:

```text
probesize
analyzeduration
rtsp_transport
fflags
flags low_delay
threads
fps filter
scale filter
```

If current values such as large probe/analyze windows delay startup, benchmark smaller safe values.

Do not sacrifice stream reliability just to save 100 ms.

---

# 20. KEEP DECODERS WARM

If recognition currently starts an FFmpeg decoder only when a vehicle appears, benchmark the startup penalty.

A car should not wait for:

```text
spawn FFmpeg
→ probe stream
→ wait for keyframe
→ initialize decoder
→ first frame
→ initialize model
→ detection
```

every visit.

For active entry/exit lanes, strongly prefer persistent/warm recognition decoders if resource usage permits.

Model initialization should also occur before the first real vehicle.

---

# 21. KEYFRAME/GOP INVESTIGATION

Measure whether long camera GOP intervals contribute to recovery delays.

Collect where possible:

```text
codec
FPS
GOP/keyframe interval
resolution
bitrate
```

If a stream reconnects and waits several seconds for the next IDR frame, report it clearly.

Do not arbitrarily modify customer camera settings without a deliberate configuration path.

---

# 22. VENDOR SDK HOST MUST NOT BECOME A BOTTLENECK

Audit whether the SDK host serializes camera calls globally.

With four cameras, ensure this does NOT happen:

```text
Camera A GetJpgBuffer
        ↓
Camera B waits
        ↓
Camera C waits
        ↓
Camera D waits
```

unless the SDK itself requires global serialization.

Determine whether:

- locks are global
- locks are per camera
- HTTP handlers block one another
- SDK calls block the host's request thread
- image retrieval blocks event retrieval
- gate/GPIO operations block video
- one broken camera blocks other cameras

Prefer independent per-camera acquisition state.

But respect vendor SDK thread-safety requirements.

Do not remove necessary SDK locks without evidence.

---

# 23. ONE BAD CAMERA MUST NOT DAMAGE ANOTHER

Camera isolation is mandatory.

If ENTRY camera fails:

```text
ENTRY: reconnecting
EXIT: continues normally
```

If Camera A freezes:

```text
Camera A producer restart
Camera B unaffected
Camera C unaffected
Camera D unaffected
```

Never restart the entire media subsystem because one stream freezes.

---

# 24. RECONNECT CORRECTLY

Implement/verify a per-camera state machine similar to:

```text
DISCONNECTED
    ↓
CONNECTING
    ↓
STREAMING
    ↓
DEGRADED
    ↓
RECONNECTING
    ↓
STREAMING
```

Use bounded backoff.

Avoid:

```text
fail
spawn
fail
spawn
fail
spawn
```

hundreds of times.

Track:

```text
reconnect_count
last_reconnect_reason
last_reconnect_at
```

---

# 25. FROZEN-FRAME DETECTION

Receiving bytes is not sufficient to declare video healthy.

Detect the difference between:

```text
new JPEG
```

and:

```text
same JPEG returned again
```

Maintain metrics like:

```text
last_received_at
last_fresh_frame_at
duplicate_frames
frames_changed
```

If:

```text
last_received_at = recent
last_fresh_frame_at = old
```

the camera is effectively frozen.

Mark:

```text
DEGRADED / FROZEN
```

and apply appropriate recovery.

Do not restart too aggressively on a naturally static scene.

Use image identity/change detection carefully.

A parked/stationary scene can legitimately produce visually identical frames.

If byte-level JPEG identity is used, understand whether the camera normally re-encodes identical scenes into different JPEG bytes.

Do not confuse "nothing moved" with "decoder dead."

---

# 26. UI LIVE VIEW

The operator UI should prioritize live operational visibility.

For every pane show diagnostic state when needed:

```text
CONNECTING
LIVE
DEGRADED
RECONNECTING
OFFLINE
UNSUPPORTED CODEC
WEBRTC FAILED
MEDIA ROUTER UNAVAILABLE
```

Do not leave stale video looking live indefinitely.

If the frame is older than the allowed threshold, indicate stale/offline state.

But do not clutter the normal production UI with developer telemetry.

Detailed metrics can live in diagnostics.

---

# 27. MULTI-CAMERA / TWO-LANE OPERATION

SmartPark must reliably handle at least:

```text
Gate A
    ENTRY camera
    EXIT camera

Gate B
    ENTRY camera
    EXIT camera
```

Depending on deployment, a node may own one gate or all cameras.

Each physical camera must have independent:

```text
media session
decoder
latest-frame state
health
reconnect state
recognition mailbox
recognition visit
metrics
```

Never share mutable frame state between cameras.

Test simultaneous:

```text
A ENTRY vehicle
A EXIT vehicle
B ENTRY vehicle
B EXIT vehicle
```

The inference scheduler may share bounded resources, but camera acquisition must remain independent.

---

# 28. CPU RESOURCE BUDGET

Audit actual process/thread use.

Look for:

```text
MediaMTX
FFmpeg processes
FastAPI workers
SDK host
ONNX Runtime threads
FastALPR detector
OCR model
desktop/browser
```

Avoid CPU oversubscription.

For example, four inference workers each internally using all CPU cores can starve media processing.

Measure before tuning.

Recognition concurrency should be bounded.

Video transport should retain enough CPU scheduling headroom to remain responsive.

---

# 29. STRENGTHEN ALPR WITHOUT DAMAGING VIDEO

While auditing the media path, preserve/improve the current recognition pipeline:

```text
fresh frame
   ↓
optional lane ROI
   ↓
plate detector
   ↓
candidate boxes
   ↓
rank candidates
   ↓
crop
   ↓
crop validation
   ↓
OCR
   ↓
Tanzania normalization
   ↓
temporal consensus
   ↓
one accepted visit/event
```

Do not blindly OCR `boxes[0]` if multiple detections exist.

Rank candidates using appropriate signals such as:

- detector confidence
- expected lane region
- bounding-box dimensions
- plate aspect ratio
- pixel quality
- expected position

Strengthen crop handling:

- clamp coordinates
- configurable padding
- minimum pixel dimensions
- optional upscale
- avoid clipping characters
- reject obviously invalid crops

Use staged preprocessing.

Do not run every expensive OCR variant on every frame.

Try:

```text
normal crop
    ↓
strong result?
 YES → accept/consensus
 NO
    ↓
enhanced crop/preprocessing
```

Then move to the next fresh frame rather than endlessly processing an old frame.

---

# 30. FAST CONFIDENCE PATH

Cars stop at the barrier.

A strong recognition should not unnecessarily wait for an entire consensus window.

If a result is sufficiently strong and passes format/quality checks, permit the existing high-confidence fast path.

Otherwise use temporal consensus.

Consensus should publish immediately once its criteria are satisfied.

Do not wait for the full window if the decision is already stable.

---

# 31. EARLY EXIT AFTER PLATE CONFIRMATION

Once a vehicle's plate is confirmed for the current physical visit:

STOP expensive OCR for that visit.

Continue only cheap presence/departure monitoring.

Conceptually:

```text
vehicle arrives
 ↓
recognition active
 ↓
T123ABC confirmed
 ↓
event published
 ↓
OCR OFF
 ↓
presence/departure monitor
 ↓
vehicle leaves
 ↓
visit reset
 ↓
recognition armed
```

This saves CPU for video and the other lane.

---

# 32. DO NOT BREAK EXACTLY-ONCE PARKING BEHAVIOR

Media changes must not reintroduce duplicate business actions.

Invariant:

> One physical vehicle visit must produce at most one accepted recognition event, one authoritative entry/exit action, one session transition, one receipt workflow and one automatic gate-open workflow.

Do not rely solely on a short in-memory time dedupe.

Preserve/verify:

```text
visit identity
recognition event identity
controller idempotency
session constraints
receipt idempotency
gate command idempotency
```

A vehicle remaining in front of the camera for 20 seconds must not create repeated sessions.

But:

```text
same vehicle leaves
then returns later
```

must be treated as a new physical visit.

---

# 33. DO NOT BREAK WORKING HARDWARE

Preserve working vendor functionality including:

- SDK camera connection
- existing SDK host architecture unless modification is specifically required
- gate relay
- GPIO
- coil/presence
- native recognition events
- manual gate open
- receipt flow
- entry controller
- exit controller
- parking sessions
- payment
- monthly/season access
- camera credentials
- existing FastALPR functionality

Do not rewrite these systems merely to make the media architecture aesthetically cleaner.

---

# 34. IMPLEMENT A CAMERA LAB

Create or improve a safe diagnostic mode that does NOT:

- create parking sessions
- print receipts
- charge customers
- open gates automatically

It should allow selecting a camera and testing:

```text
camera connection
transport
RTSP
SDK video
MediaMTX
WebRTC
MJPEG fallback
recognition stream
FastALPR
```

Show metrics including:

```text
source transport
codec
resolution
source FPS
live FPS
unique-frame FPS
duplicate ratio
frame age
p50 frame interval
p95 frame interval
max frame interval
reconnects
decoder restarts
recognition FPS
recognition input age
detector latency
OCR latency
```

This is important for field deployment.

---

# 35. REQUIRED TEST MATRIX

Test at minimum:

### Generic RTSP

```text
Hikvision-like RTSP camera
Dahua-like RTSP camera
generic RTSP camera
```

Where physical hardware is unavailable, use deterministic test streams/mocks but clearly distinguish simulated results from real hardware validation.

### Vendor

```text
HVX/QY SDK camera
```

### Failure tests

1. camera starts normally
2. camera unplugged
3. camera reconnected
4. network temporarily interrupted
5. MediaMTX killed/restarted
6. SDK host killed/restarted
7. one camera freezes
8. one camera returns repeated JPEG
9. recognition intentionally slowed
10. CPU stressed
11. browser opened/closed repeatedly
12. multiple browser viewers
13. four cameras simultaneously
14. entry + exit recognition simultaneously
15. one camera credentials invalid
16. one camera unavailable
17. RTSP stream stops mid-session
18. WebRTC negotiation fails
19. unsupported browser codec
20. long-running soak test

---

# 36. PRODUCTION ACCEPTANCE TARGETS

Do not fake test results.

Where hardware permits, target:

## Live video

```text
normal frame age: < 500 ms
no multi-second accumulated playback backlog
no recurring freeze → multi-second jump cycle
viewer reconnect without restarting SmartPark
one failed camera does not disturb others
```

For LAN WebRTC, aim substantially below 500 ms where practical.

## Recognition

For a vehicle stopped at the gate:

```text
first fresh frame available quickly
strong plate recognition commonly ~1–3 seconds or better
recognition input frame preferably < 1000 ms old
no 10–20 second normal recognition delay
```

`alpr_timeout_seconds` may remain a failure watchdog.

It must NOT represent acceptable normal recognition latency.

## Stability

During soak:

```text
bounded memory
bounded queues
bounded child processes
no FFmpeg process leaks
no HTTP-client leaks
no continuous reconnect storm
no growing latency
no cross-camera starvation
```

---

# 37. IMPLEMENT IN PHASES

Do not perform one enormous uncontrolled refactor.

## Phase 1 — map current implementation

Produce an internal topology of:

```text
generic RTSP path
vendor video path
browser path
desktop path
recognition path
```

## Phase 2 — instrumentation

Add enough metrics to prove where freezes occur.

## Phase 3 — generic RTSP stabilization

Make:

```text
Camera → MediaMTX → WebRTC
```

reliable.

## Phase 4 — vendor video investigation

Determine:

```text
RTSP?
continuous SDK?
JPEG fallback?
```

using evidence.

## Phase 5 — vendor stabilization

Use the best verified transport.

## Phase 6 — recognition isolation

Ensure FastALPR cannot stall live video.

## Phase 7 — resource optimization

Tune decoder/model/process/thread budgets.

## Phase 8 — multi-camera validation

Test ENTRY + EXIT and four-camera behavior.

## Phase 9 — failure/recovery testing

Test all failure scenarios.

## Phase 10 — soak test

Run extended stability testing and inspect memory/process/latency trends.

Commit coherent changes in small, reviewable groups where practical.

---

# 38. DO NOT DO THESE THINGS

Do NOT:

- rewrite SmartPark from scratch
- replace FastALPR unnecessarily
- replace MediaMTX without proving it is the problem
- introduce Frigate
- introduce Agent DVR
- introduce a full NVR
- add large frame queues
- increase buffering to hide freezes
- make recognition consume every camera frame
- create one FFmpeg process per HTTP request
- create one upstream RTSP connection per consumer unnecessarily
- continuously restart healthy streams
- make browser viewing control recognition lifecycle
- make recognition lifecycle depend on whether UI is open
- use stale cached plate as current recognition
- allow one camera failure to restart every camera
- change gate/receipt/payment/session behavior without a demonstrated requirement
- claim hardware tests passed if they were only mocked

---

# 39. IMPORTANT ENGINEERING PRINCIPLE

The final architecture should approach:

```text
                       PHYSICAL CAMERA
                              │
               ┌──────────────┴──────────────┐
               │                             │
         VIDEO TRANSPORT               VENDOR CONTROL
               │                             │
          MediaMTX where                 HVX SDK Host
           possible                          │
               │                        GPIO / coil
       ┌───────┴────────┐                gate / events
       │                │
       ▼                ▼
    WebRTC          local RTSP/
       │             frame source
       │                │
       ▼                ▼
 Operator UI       latest-frame mailbox
                        │
                     3–5 FPS
                        │
                     lane ROI
                        │
                    detector
                        │
                ranked plate box
                        │
                 validated crop
                        │
                       OCR
                        │
                   consensus
                        │
                  vehicle visit
                        │
            ONE accepted recognition
                        │
                  live_parking
                        │
                Entry / Exit logic
                        │
              receipt / payment / gate
```

For vendor cameras without RTSP:

```text
Vendor camera
      ↓
verified continuous SDK video
      ↓
single video producer
      ↓
live + recognition consumers
```

Only fall back to:

```text
Net_GetJpgBuffer
      ↓
JPEG polling
```

when no better verified transport exists.

---

# 40. FINAL REPORT REQUIRED

After implementation, provide a detailed engineering report.

Include:

## A. Root causes found

For each freeze/skip/latency issue explain:

```text
symptom
root cause
exact files/functions
fix
evidence
```

## B. Final transport for each camera type

Example:

```text
Hikvision:
RTSP → MediaMTX → WebRTC

Dahua:
RTSP → MediaMTX → WebRTC

HVX:
RTSP → MediaMTX
or
SDK continuous video
or
SDK JPEG fallback
```

Do not claim RTSP exists for HVX unless verified.

## C. Resource topology

Report:

```text
number of upstream streams
FFmpeg process count
MediaMTX process count
recognition worker count
model concurrency
```

for two-camera and four-camera operation.

## D. Performance

Report measured:

```text
live FPS
source FPS
unique-frame FPS
frame age
p50/p95/max frame interval
recognition FPS
recognition frame age
detector latency
OCR latency
end-to-end plate latency
CPU
memory
```

## E. Recognition contention

Explicitly compare:

```text
recognition OFF
vs
recognition ON
```

and state whether FastALPR affects live video.

## F. Multi-camera results

Report whether:

```text
ENTRY + EXIT
```

can operate simultaneously without starvation.

Also report four-camera results where testable.

## G. Remaining hardware unknowns

Clearly separate:

```text
VERIFIED
INFERRED
NOT YET TESTED ON PHYSICAL HARDWARE
```

## H. Changed files

List every changed file and why.

## I. Rollback

Explain how to revert to the previous working media path if the new transport fails in the field.

---

# FINAL OBJECTIVE

Do not optimize SmartPark to process the largest possible number of frames.

Optimize it to make the **right current frame available at the right time**.

The production priorities are:

1. **Smooth and fresh operator video**
2. **No accumulated video latency**
3. **Fast fresh-frame plate recognition**
4. **Strong crop/OCR accuracy**
5. **No duplicate physical-visit actions**
6. **Independent entry/exit camera operation**
7. **Failure isolation between cameras**
8. **Reliable automatic reconnection**
9. **Low and predictable CPU/memory usage**
10. **Preservation of working gate/receipt/payment/session behavior**

A car stopped at the gate should never have to wait 10–20 seconds because SmartPark is processing historical frames.

The desired behavior is:

```text
CAR ARRIVES
     ↓
current video remains smooth
     ↓
fresh frame sampled immediately
     ↓
plate detected
     ↓
best crop selected
     ↓
OCR
     ↓
strong result / rapid consensus
     ↓
ONE recognition event
     ↓
existing parking workflow
     ↓
receipt/gate action
```

while the live video continues independently throughout the entire process.

Start by inspecting and tracing the CURRENT source code. Then instrument. Then diagnose. Then implement the smallest architecture changes that solve the measured failures. Do not start by rewriting the subsystem.
