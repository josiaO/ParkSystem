# Windows field diagnostic procedure

Run this procedure during a maintenance window. It is media/recognition
diagnostics only: it must not open a boom, print a receipt, create a parking
session, or issue a payment.

## 1. Record the deployment

Record the SmartPark build, Windows version, CPU/RAM, camera model/firmware,
codec, configured resolution/FPS, stream role, adapter ID, node assignment,
and the loaded vendor DLL manifest. Do not upgrade the matched offline QY DLL
family or ONNX/Qt wheels during this test.

## 2. Observe one camera

```powershell
Invoke-RestMethod 'http://127.0.0.1:8765/info' | ConvertTo-Json -Depth 8
Invoke-RestMethod 'http://127.0.0.1:30000/video-status/0' | ConvertTo-Json -Depth 8
python -m tools.camera_lab --camera 1 --duration 300 --recognition --latency
```

Use the actual SDK handle and camera ID. Collect `/health/details` and
`/health/realtime` at the same interval. Save the JSON output with the test
date, but redact credentials and public tokens.

## 3. Collect required fields

For every camera record source FPS/codec, decoded/display/inference FPS, frame
age, queue depth, dropped frames, detector/OCR durations, decoder PID,
reconnects, decoder restarts, media generation, recognition owner, worker
heartbeat, accepted/suppressed/rejected events, and parking sessions created.

For QY/HVX also record callback frames/rate/age, JPEG frames/rate/age, JPEG
read duration/status/error, pending reads, `stall_classification`, and
`recovery_reason`. A connected camera with zero callback frames is not healthy.

## 4. Measure real end-to-end latency

Because camera and PC clocks may be unsynchronized, local frame age is not
camera-to-screen latency. Point the camera at a visible millisecond timestamp
or flash an LED in the scene. Record the camera view and operator display with
one external phone at 60 fps for at least 30 passages. Compute capture-to-screen
p50/p95/max from the same visible event. If this is not done, report the value
as unverified.

## 5. Recovery tests

Test one camera at a time, then all installed cameras together:

- unplug/reconnect the camera network path;
- stop only the relevant MediaMTX/decoder component where applicable;
- introduce a decoder stall or partial JPEG stream in the replay harness;
- disconnect/reconnect the desktop display consumer;
- allow a slow inference call;
- pass adjacent, slow, reversing, occluded, and similar-looking vehicles.

Verify that unaffected cameras continue, old frames do not reappear after the
generation changes, the current plate clears after reliable departure, and a
replayed event creates zero additional captures/sessions/gate commands.

## 6. Acceptance record

Attach the raw diagnostic JSON, labeled vehicle count, accepted/rejected event
counts, duplicate-session count, latency calculation, and operator notes. Do
not mark the target achieved when a value is missing; mark it **unmeasured**.

