# SmartPark Real Gate Footage — Virtual Camera, Video Pipeline & ALPR Test Lab

You are working on the **current SmartPark/ParkSystem repository**.

I have added a folder:

```text
TestingData/
```

It contains real testing material captured from the actual parking gate environment, including:

- approximately 8 minutes of CCTV/gate-camera video;
- the original video has been edited to remove long sections where no vehicle was present;
- real vehicles pass through the gate;
- number plates are visible;
- still images of vehicles captured from the actual gate camera are also included;
- some images should contain visible number plates.

These files are intended to become a **repeatable SmartPark test dataset**.

Your task is to build a proper testing/diagnostic facility around these files and use it to evaluate:

1. live video performance;
2. MediaMTX;
3. RTSP handling;
4. WebRTC/live-view behavior;
5. FFmpeg decoding;
6. latest-frame handling;
7. FastALPR;
8. plate detection;
9. plate cropping;
10. OCR;
11. recognition latency;
12. temporal consensus;
13. recognition/video resource contention;
14. multiple simultaneous cameras;
15. reconnection/failure behavior.

Do NOT modify the production recognition algorithm aggressively yet.

This task comes **before** the planned capture → crop → perspective correction → OCR enhancement.

The first objective is to establish a trustworthy baseline.

---

# 1. SOURCE CODE FIRST

Before implementing anything, inspect the CURRENT repository.

Do not rely on stale documentation.

Find and understand the actual current implementations of:

```text
MediaMTX
media gateway
media registry
WebRTC/WHEP
RTSP
FFmpeg
recognition decoder
recognition worker
FastALPR
latest-frame buffers
camera configuration
camera models
camera health
recognition runtime
consensus
deduplication
live parking
entry/exit controllers
```

Search for relevant code instead of assuming filenames.

Do not rewrite working production components.

The test system should exercise existing production code wherever practical.

---

# 2. INSPECT TestingData

Recursively inspect:

```text
TestingData/
```

Do not assume filenames.

Automatically identify:

```text
*.mp4
*.avi
*.mkv
*.mov
*.ts
*.jpg
*.jpeg
*.png
*.webp
```

For every video determine with FFprobe or equivalent:

```text
filename
duration
resolution
codec
container
FPS
bitrate
pixel format
GOP/keyframe information where available
```

For every image determine:

```text
filename
resolution
format
```

Produce a concise inventory.

Do NOT rename, modify, recompress or delete the original files.

Treat `TestingData/` originals as read-only.

Generated artifacts must go somewhere like:

```text
TestingData/output/
TestingData/results/
TestingData/generated/
```

or an equivalent clearly separated ignored directory.

Do not pollute the source dataset.

---

# 3. PRIVACY / REPOSITORY SAFETY

These are real CCTV images/videos.

Before proceeding, inspect `.gitignore`.

The raw footage should NOT accidentally be committed to Git unless explicitly intended.

Ensure appropriate ignore rules exist for:

```text
TestingData/
```

or specifically the raw/generated media portions.

Do not delete local files when adding ignore rules.

Do not upload footage anywhere.

All testing must remain local.

Do not use external/cloud ALPR services.

---

# 4. CREATE A REUSABLE SMARTPARK CAMERA LAB

Do not create a disposable one-off script.

Create a reusable developer/test facility, for example conceptually:

```text
tools/camera_lab/
```

or another location consistent with the existing repository.

It should support at least:

```text
inspect
serve
test-video
test-image
benchmark
multi-camera
failure-test
report
```

The exact CLI/API design should follow the existing project conventions.

Example concept only:

```bash
python -m tools.camera_lab inspect TestingData
```

```bash
python -m tools.camera_lab test-video TestingData/<video>
```

```bash
python -m tools.camera_lab test-image TestingData/<image>
```

```bash
python -m tools.camera_lab serve TestingData/<video>
```

```bash
python -m tools.camera_lab multi-camera TestingData/<video> --cameras 4
```

Do not blindly use these exact commands if they conflict with the repository structure.

Design the cleanest integration.

---

# 5. TURN THE RECORDED VIDEO INTO A VIRTUAL IP CAMERA

This is critical.

Do NOT merely run:

```text
MP4 → FastALPR
```

That tests recognition but does NOT sufficiently test SmartPark's camera/media architecture.

Create a virtual-camera mode using the recorded video.

Preferred architecture:

```text
REAL GATE VIDEO FILE
        │
        ▼
      FFmpeg
        │
   realtime playback
        │
        ▼
      RTSP
        │
        ▼
     MediaMTX
        │
        ├──────────────→ WebRTC/WHEP → SmartPark live UI
        │
        └──────────────→ local RTSP → existing recognition decoder
                                      │
                                      ▼
                                   FastALPR
```

The objective is for SmartPark to consume the test stream similarly to a real Hikvision/Dahua/generic RTSP camera.

Do not bypass production components unnecessarily.

---

# 6. PLAY THE VIDEO IN REAL TIME

This requirement is extremely important.

An 8-minute video must normally behave like an 8-minute camera stream.

Do NOT let FFmpeg read the entire file as fast as the CPU permits.

Use real-time pacing.

The virtual camera should produce frames according to the original video's timestamps/FPS.

Support looping for soak testing:

```text
video
 ↓
end
 ↓
restart
 ↓
continue
```

The loop should be clean and observable.

The normal test mode should therefore approximate:

```text
recorded 25 FPS
       ↓
virtual camera 25 FPS
       ↓
SmartPark
```

not:

```text
recorded 25 FPS
       ↓
decode at 300 FPS
```

---

# 7. PRESERVE SOURCE QUALITY WHERE PRACTICAL

Do not unnecessarily degrade the footage.

For baseline testing preserve:

```text
resolution
aspect ratio
frame rate
```

as closely as practical.

If transcoding is required for RTSP/WebRTC compatibility, document:

```text
input codec
output codec
reason transcoding was required
```

Prefer stream copy/remux when technically possible.

If H.264 encoding is required, use an appropriate low-latency configuration.

Do not silently change the test conditions.

---

# 8. CREATE A SINGLE VIRTUAL CAMERA FIRST

Start with one virtual camera.

Example conceptual stream:

```text
rtsp://127.0.0.1:8554/test-gate-entry
```

Integrate it through the same MediaMTX mechanisms used by production.

Then verify:

```text
video file
   ↓
FFmpeg
   ↓
MediaMTX
   ↓
SmartPark live view
```

and separately:

```text
MediaMTX
   ↓
SmartPark recognition decoder
   ↓
FastALPR
```

Do not proceed to four-camera stress testing until one virtual camera works reliably.

---

# 9. TEST LIVE VIDEO WITHOUT RECOGNITION

Establish baseline A.

Run:

```text
Virtual Camera
      ↓
MediaMTX
      ↓
SmartPark live view
```

with recognition disabled.

Measure:

```text
source FPS
received FPS
display/live FPS
frame age
frame intervals
dropped frames
decoder restarts
reconnects
CPU
memory
```

Where possible calculate:

```text
frame_interval_avg_ms
frame_interval_p50_ms
frame_interval_p95_ms
frame_interval_max_ms
```

Observe whether there are:

```text
freezes
stutters
multi-second jumps
growing latency
```

This establishes whether SmartPark's media pipeline itself is healthy.

---

# 10. TEST LIVE VIDEO WITH RECOGNITION

Then establish baseline B.

Run the same virtual camera with FastALPR enabled.

Measure exactly the same video metrics plus:

```text
recognition FPS
recognition input frame age
detector latency
crop latency
OCR latency
consensus latency
total recognition latency
recognition queue/mailbox state
```

Compare:

```text
A = recognition OFF
B = recognition ON
```

Generate an explicit comparison.

We need to answer:

> Does enabling FastALPR cause SmartPark's live video to freeze, stutter or become stale?

If yes, locate the actual bottleneck.

Investigate:

```text
event-loop blocking
CPU saturation
ONNX thread oversubscription
excessive image copying
JPEG encode/decode
FFmpeg processes
recognition concurrency
synchronous CPU work inside async code
```

Do not "solve" it by adding video buffering.

---

# 11. LATEST-FRAME-WINS MUST REMAIN

The test should verify that SmartPark does NOT process a growing queue of old frames.

Suppose:

```text
frame 100 → OCR starts

101 arrives
102 arrives
103 arrives
104 arrives

OCR finishes
```

The next recognition input should preferably be approximately:

```text
104
```

not:

```text
101
```

Measure this.

Record:

```text
frame_timestamp
recognition_started_at
recognition_completed_at
input_frame_age_ms
```

If recognition begins processing frames several seconds old, flag this as a production failure.

Do NOT fix it by increasing queue sizes.

---

# 12. USE THE STILL IMAGES FOR CONTROLLED ALPR TESTING

The still images provide a useful deterministic recognition test.

For each relevant image:

```text
image
 ↓
existing detector
 ↓
plate bounding box
 ↓
crop
 ↓
existing preprocessing
 ↓
OCR
 ↓
normalization
```

Record:

```text
image
detector result
detector confidence
bbox
crop dimensions
OCR raw text
OCR normalized text
OCR confidence
total latency
```

Save generated plate crops into a test-results directory.

Example:

```text
TestingData/results/images/
```

Do NOT overwrite originals.

---

# 13. SAVE VISUAL DEBUG OUTPUTS

For image/video recognition tests, create optional debug evidence.

Examples:

### Detection image

Original frame with:

```text
plate bbox
detector confidence
recognized plate
OCR confidence
```

### Raw plate crop

Exactly what was passed toward OCR before preprocessing.

### Prepared OCR crop

What OCR actually received.

Keep these clearly separated.

Example:

```text
results/
    detections/
    crops/
        raw/
        prepared/
    reports/
```

This will be important for the next capture/crop/OCR improvement task.

---

# 14. DO NOT MODIFY THE RECOGNITION ALGORITHM YET

This phase is primarily:

```text
TEST
MEASURE
OBSERVE
ESTABLISH BASELINE
```

Do not immediately implement:

```text
perspective correction
new contour algorithms
new OCR model
new detector
new consensus algorithm
```

unless a tiny bug prevents the baseline tests from running.

We need to know what the CURRENT system achieves first.

---

# 15. RECORD DETECTOR VS OCR FAILURES SEPARATELY

For every visible plate failure distinguish:

### Detector failure

```text
vehicle visible
plate visible
NO plate bbox
```

### Crop failure

```text
plate detected
bbox exists
crop clips plate / wrong region
```

### OCR failure

```text
plate crop looks correct
OCR returns wrong characters
```

### Normalization failure

```text
raw OCR reasonable
Tanzania normalization produces wrong result
```

### Temporal failure

```text
correct plate appears in individual frames
consensus fails to confirm it
```

### Stale-frame failure

```text
recognition works
but on old frames
```

Do not combine these into one generic "ALPR failed" result.

---

# 16. CREATE FRAME-LEVEL RECOGNITION TIMELINE

For vehicles in the video, generate a useful timeline.

Conceptually:

```text
00:14.200 vehicle entering ROI
00:14.450 plate detected 0.61
00:14.700 plate detected 0.78 OCR=T482DKL 0.66
00:14.950 plate detected 0.91 OCR=T482DKL 0.88
00:15.200 consensus confirmed T482DKL
```

This is far more useful than only reporting:

```text
T482DKL detected
```

We need to understand **how recognition develops as a car approaches/stops**.

---

# 17. IMPORTANT: VIDEO WAS EDITED

The source video has had sections with no vehicles removed.

Therefore discontinuities introduced by editing must NOT automatically be classified as SmartPark freezes.

Inspect timestamps/container behavior.

Distinguish:

```text
intentional edit/cut in source file
```

from:

```text
SmartPark playback freeze
```

If necessary normalize timestamps when creating the virtual RTSP stream.

Do not report an editing cut as a media bug.

---

# 18. GROUND TRUTH SUPPORT

Do not guess the true plate solely from OCR output.

Provide a simple mechanism to create local ground-truth annotations.

For example:

```text
TestingData/ground_truth.json
```

or another suitable format.

Conceptually:

```json
{
  "video": [
    {
      "start": 12.4,
      "end": 17.8,
      "plate": "T482DKL"
    }
  ],
  "images": {
    "car1.jpg": "T482DKL"
  }
}
```

But do not invent plate numbers.

If no ground truth exists, report:

```text
UNLABELED
```

rather than treating the model's prediction as truth.

Make the format easy for a human to edit.

The original media files remain unchanged.

---

# 19. RECOGNITION METRICS WHEN GROUND TRUTH EXISTS

When labels are available calculate:

```text
plate detection rate
exact plate match rate
character accuracy where useful
time to first detection
time to first correct OCR
time to confirmed recognition
false positive count
duplicate publication count
```

Do not claim accuracy percentages when the dataset has not been labeled.

---

# 20. TEST REPEATED RECOGNITION

The same vehicle remains visible across many frames.

Verify that the existing runtime does NOT treat every frame as a new vehicle.

For one physical appearance:

```text
frame 1 T482DKL
frame 2 T482DKL
frame 3 T482DKL
...
frame 40 T482DKL
```

the recognition pipeline should converge on one visit/event rather than repeatedly publishing it.

For this Camera Lab test:

**DO NOT create real parking sessions, print receipts, charge payments or open gates.**

Use a dry-run/event-sink mode.

We need to inspect recognition without producing real-world side effects.

---

# 21. MULTI-CAMERA SIMULATION

After one stream works, allow the recorded footage to emulate multiple cameras.

For example:

```text
test-gate-a-entry
test-gate-a-exit
test-gate-b-entry
test-gate-b-exit
```

It is acceptable initially to use the same video as multiple independent streams for resource testing.

Even better, if multiple suitable videos exist in `TestingData`, assign different ones.

The objective here is NOT recognition accuracy.

The objective is:

```text
concurrency
CPU
memory
decoder isolation
recognition fairness
video continuity
```

Test:

```text
1 camera
2 cameras
4 cameras
```

Measure how resource usage scales.

---

# 22. FAIRNESS TEST

With multiple recognition cameras active, ensure one busy camera does not monopolize inference.

Collect per-camera:

```text
recognition attempts
recognition FPS
average wait
p95 wait
input frame age
inference latency
```

A camera continuously seeing a plate must not prevent another lane from being processed.

---

# 23. SIMULATE FAILURE

Add controlled test scenarios.

Do NOT damage production configuration.

Support tests such as:

### Stream interruption

```text
video running
 ↓
stop producer
 ↓
wait
 ↓
restart
```

Verify:

```text
DEGRADED/OFFLINE
reconnect
LIVE
```

### MediaMTX restart

Verify consumers recover.

### Recognition slowdown

Artificially delay recognition and verify:

```text
live video stays current
latest-frame-wins remains true
```

### Camera producer restart

One virtual camera should recover without restarting all other cameras.

---

# 24. SIMULATE POOR CAMERA CONDITIONS WHERE USEFUL

Do not replace the original baseline.

Optionally generate temporary derived test streams for:

```text
lower bitrate
lower FPS
packet-like interruption
blur
darkness
overexposure
resolution reduction
```

Generated variants must go outside the original dataset.

Clearly label them as synthetic degradation.

This can help establish when recognition begins failing.

Do not confuse synthetic tests with actual gate-camera results.

---

# 25. TEST LONG-RUN STABILITY

The source video is approximately 8 minutes.

Support looping it for an extended soak test.

For example:

```text
8 minute source
× repeated loops
→ 1 hour or longer
```

During soak monitor:

```text
memory
CPU
FFmpeg process count
recognition worker count
MediaMTX
frame age
live FPS
decoder restarts
reconnects
open connections
```

We need to detect:

```text
memory leaks
process leaks
latency growth
decoder accumulation
HTTP-client accumulation
reconnect storms
```

Do not require a long soak every time automated tests run.

Make it an explicit diagnostic command.

---

# 26. CREATE A MACHINE-READABLE REPORT

Generate results in a structured format such as JSON.

Example categories:

```text
environment
source_media
live_video
recognition
per_camera
failures
resource_usage
```

Also generate a concise human-readable report.

The report must clearly distinguish:

```text
PASS
WARNING
FAIL
NOT TESTED
```

Do not turn arbitrary target thresholds into fake scientific guarantees.

---

# 27. COMPARE AGAINST THE REAL CAMERA PROBLEM

One of the most important conclusions is this comparison:

## Virtual RTSP

```text
Recorded gate footage
        ↓
FFmpeg
        ↓
MediaMTX
        ↓
SmartPark
```

versus later:

## Vendor camera

```text
HVX camera
    ↓
Vendor SDK
    ↓
SDK host
    ↓
SmartPark
```

If virtual RTSP remains smooth while vendor live video freezes:

Flag strong evidence that the problem is upstream around:

```text
vendor camera
vendor SDK
Net_GetJpgBuffer
SDK host
JPEG polling
```

If both freeze when recognition runs:

Investigate downstream SmartPark CPU/concurrency/event-loop behavior.

If virtual RTSP freezes even with recognition disabled:

Investigate:

```text
MediaMTX
FFmpeg
WebRTC
browser
media gateway
```

The Camera Lab should make these distinctions possible.

---

# 28. DO NOT USE THE TEST TO FAKE A VENDOR CAMERA

A video-backed RTSP stream is a useful simulation of:

```text
Hikvision
Dahua
generic RTSP
```

but it is NOT a simulation of the proprietary HVX SDK.

Do not report:

```text
"Vendor camera fixed"
```

because the virtual RTSP stream works.

The vendor SDK path must still be tested against the physical vendor camera.

Use accurate terminology:

```text
virtual RTSP test passed
physical HVX SDK test pending
```

---

# 29. MAKE THIS USEFUL FOR THE NEXT ALPR TASK

The next planned engineering task is to improve:

```text
CAPTURE
  ↓
DETECT
  ↓
CROP
  ↓
QUALITY ASSESSMENT
  ↓
OPTIONAL PERSPECTIVE CORRECTION
  ↓
OCR
  ↓
FRESH-FRAME RETRY
  ↓
CONSENSUS
```

Therefore this Camera Lab must provide enough evidence to compare:

```text
BEFORE
vs
AFTER
```

using the exact same real gate footage.

We should later be able to say objectively:

```text
before:
time to correct recognition = X
exact matches = Y
detector misses = Z

after:
time to correct recognition = X2
exact matches = Y2
detector misses = Z2
```

without relying on subjective observation.

---

# 30. DO NOT OVERENGINEER THE LAB

The Camera Lab is developer infrastructure.

Do not build an enormous new application.

Prefer:

```text
small CLI
existing SmartPark services
existing MediaMTX
existing recognition pipeline
simple generated HTML/JSON report if useful
```

over a completely separate frontend/backend product.

Reuse production code.

The closer the test path is to production, the more valuable the results are.

---

# 31. DO NOT BREAK PRODUCTION

Camera Lab must be explicitly isolated from production side effects.

When Camera Lab is active:

```text
NO automatic gate opening
NO receipt printing
NO payment actions
NO real parking session creation
NO tenant/subscriber modifications
```

Recognition events should terminate in a dry-run test sink.

Do not rely solely on "remembering not to call the gate."

Implement an explicit safety boundary.

---

# 32. EXPECTED OUTPUT

At the end of this task provide:

## A. TestingData inventory

List detected media and properties.

## B. Current pipeline trace

Explain exactly how test video reaches:

```text
MediaMTX
live UI
recognition decoder
FastALPR
```

## C. Baseline live-video results

Recognition OFF.

## D. Recognition-enabled results

Recognition ON.

## E. Comparison

Explain whether FastALPR materially affects video performance.

## F. Image ALPR results

For each test image:

```text
detected?
bbox
crop
OCR
confidence
latency
```

## G. Video ALPR observations

Include:

```text
detection behavior
crop behavior
OCR behavior
consensus behavior
time-to-recognition
```

where measurable.

## H. Failure classification

Separate:

```text
detector
crop
OCR
normalization
consensus
stale-frame
media
resource contention
```

## I. Multi-camera results

Report:

```text
1 stream
2 streams
4 streams
```

where the machine can support the tests.

## J. Generated artifacts

List:

```text
reports
JSON metrics
debug detections
plate crops
prepared OCR crops
```

## K. Production code changes

List every production file changed and explain why it was necessary.

Prefer minimal production changes during this baseline phase.

## L. Next recommendations

Based strictly on measured results, identify what should be addressed in the subsequent:

```text
capture → crop → perspective correction → OCR
```

task.

Do NOT implement those larger ALPR changes yet.

---

# 33. SUCCESS CRITERIA

This task is successful when I can place real footage into:

```text
TestingData/
```

and SmartPark can reproducibly use it to answer:

### Video

- Is live playback smooth?
- Is it current?
- Is it accumulating latency?
- Does recognition make it stutter?
- Does MediaMTX recover after failure?
- Does one camera affect another?

### Recognition

- Does the detector find the plate?
- Which bounding box was selected?
- What exactly was cropped?
- What did OCR actually receive?
- What raw text did OCR produce?
- What normalized plate was produced?
- How long did each stage take?
- How many fresh frames were needed?
- Did consensus help?
- Was the recognition result stale?
- Was one physical vehicle published repeatedly?

### Scalability

- Can one camera run?
- Can two cameras run?
- Can four streams run?
- Does CPU saturation damage video?
- Is inference scheduling fair?

### Future comparison

- Can we run exactly the same dataset after modifying crop/OCR and objectively compare before vs after?

That is the purpose of this task.

Start by inspecting the CURRENT repository and `TestingData/`.

Do not start by changing the recognition algorithm.
