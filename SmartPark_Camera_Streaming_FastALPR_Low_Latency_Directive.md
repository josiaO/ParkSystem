# SmartPark Edge — Camera Streaming & FastALPR Low-Latency Rebuild Directive

**Audience:** Cursor / implementation agent  
**Priority:** CRITICAL  
**Objective:** Eliminate multi-second live-video skips, keep FastALPR independent from viewing, and make the camera layer universal, observable, low-latency, and resilient.

## 1. Diagnose before rewriting

The symptom:

```text
live video
→ freezes/falls behind
→ jumps ahead several seconds
→ repeats
```

Do not assume this is simply camera FPS.

Likely causes include:
- consuming frames slower than they arrive
- unbounded frame queues
- FastALPR in the same loop as capture/display
- UI rendering blocking decode
- multiple consumers connecting directly to one camera
- RTSP jitter/buffering
- high-resolution/high-bitrate decode pressure
- long GOP/keyframe interval
- smart codec modes
- decoder overload
- reconnect/probe buffering

Add metrics first.

## 2. Baseline each camera outside SmartPark

For the exact stream URL:

1. Check vendor/native viewer.
2. Check direct RTSP with FFprobe/FFplay/VLC.
3. Check SmartPark.

Record:
- connect time
- codec
- resolution
- FPS
- bitrate
- keyframe/GOP interval if measurable
- stalls
- transport
- CPU usage

Interpretation:

```text
vendor smooth + direct RTSP smooth + SmartPark skips
→ SmartPark pipeline bug

vendor/direct also skip
→ camera/network/encoder issue

SmartPark smooth with FastALPR disabled
→ AI is coupled incorrectly to stream ingestion/viewing
```

## 3. AI must never be in the live-view path

Wrong:

```text
Camera
→ VideoCapture.read()
→ FastALPR
→ draw
→ Qt UI
```

Correct:

```text
                     CAMERA
                        |
                        v
                Media Ingest/Gateway
                  /                              /                               v                 v
          LIVE VIEW PATH        AI PATH
          no FastALPR           sampled frames
                |                 |
                v                 v
              Player         FastALPR Worker
                                  |
                                  v
                             Detection Event
```

If FastALPR sleeps or crashes, live video must remain smooth.

## 4. Use one upstream connection per camera where practical

```text
Physical Camera
      |
      v
Local Media Gateway
  |      |       |
  v      v       v
 UI   FastALPR  snapshots
```

Use go2rtc or an equivalent gateway behind a SmartPark abstraction.

Do not let dashboard, full-screen view, FastALPR, snapshot and diagnostics each open independent camera connections.

## 5. MediaGateway abstraction

```python
class MediaGateway:
    async def register_stream(self, camera_id, source): ...
    async def unregister_stream(self, camera_id): ...
    async def health(self, camera_id): ...
    async def get_live_endpoint(self, camera_id): ...
    async def get_detect_endpoint(self, camera_id): ...
    async def snapshot(self, camera_id): ...
```

The rest of SmartPark must not depend directly on go2rtc/FFmpeg/GStreamer internals.

## 6. Separate camera from stream

A camera can expose multiple streams.

```text
CameraDevice
- vendor
- model
- IP
- credentials
- capabilities

CameraStream
- MAIN
- SUB
- LIVE
- DETECT
- EVIDENCE
```

Store per stream:
- protocol
- URI
- codec
- resolution
- FPS
- bitrate
- transport
- GOP/keyframe interval
- audio enabled
- health

Do not store only one `camera_url`.

## 7. Discover streams properly

Priority:

```text
ONVIF GetProfiles
→ ONVIF GetStreamUri
→ vendor adapter
→ verified vendor profile
→ manual RTSP/HTTP URL
```

Do not guess dozens of RTSP paths when ONVIF can provide the media URI.

## 8. Universal source types

Support:

```text
RTSP / RTSPS
HTTP MJPEG
HTTP JPEG snapshot
ONVIF-discovered stream
vendor-native stream
USB/UVC webcam
local video device
simulation/file
```

FastALPR and ParkingService must not care which source type is used.

## 9. Codec policy

For operational live viewing, prefer standard H.264 when available.

Support H.265 when the Windows decoder/hardware path is verified.

Avoid automatically enabling vendor smart codecs such as H.264+/H.265+ on live profiles.

Do not transcode if the source codec is already usable.

Preferred:

```text
Camera H264
→ packet copy/restream
→ viewer
```

Avoid:

```text
H264
→ decode
→ Python frame
→ re-encode
→ decode again
→ UI
```

## 10. Keyframes/GOP

For low-latency live/detect profiles, target roughly one keyframe per second when camera capabilities allow.

Example:

```text
20 FPS → keyframe interval around 20
15 FPS → around 15
```

Very long GOPs can delay stream startup/recovery.

Hardware Lab must report current stream FPS/GOP when possible.

Do not silently change camera settings in production.

## 11. Main vs substream roles

Do not use one heavy stream for every job.

### MAIN/EVIDENCE
- higher resolution
- roughly 15–25 FPS where appropriate
- full-screen/evidence

### SUB/LIVE GRID
- lower resolution
- roughly 10–15 FPS
- dashboard cards

### DETECT
- enough plate pixels for FastALPR
- start around 5 FPS
- increase toward 10 FPS only if site testing proves needed

Tune based on actual plate size and vehicle speed.

## 12. Avoid decoding frames just to throw them away

Bad:

```text
camera = 25 FPS
SmartPark decodes 25
AI uses 5
20 decoded frames wasted
```

Better:

```text
camera detect stream = 5–10 FPS
AI decodes only that stream
```

Configure a lower-FPS stream at the camera when possible.

## 13. Latest-frame-wins buffering

Real-time video cares about being current.

Use a bounded latest-frame buffer:

```text
max frames: 1–3
```

If consumer is slow:
- discard old frames
- retain newest frame

Never queue hundreds of video frames.

At 20 FPS, a queue of 100 frames creates ~5 seconds of backlog.

## 14. GStreamer option

If using GStreamer:

```text
rtspsrc
→ depay/decode
→ tee
   ├─ small leaky queue → display
   └─ small leaky queue → appsink(max-buffers=1) → FastALPR
```

Use:
- bounded queue sizes
- downstream/old-frame dropping
- appsink max buffers
- tuned rtspsrc latency
- drop-on-latency where appropriate

Do not use large default queues blindly.

## 15. FFmpeg tuning

FFmpeg exposes:
- `probesize`
- `analyzeduration`
- `fflags=nobuffer`
- `avioflags=direct`
- `max_delay`
- RTSP timeouts
- transport selection

Do not apply random low-latency flags globally.

Create tested profiles:

```text
COMPATIBLE
LOW_LATENCY_LAN
LOSSY_NETWORK
VENDOR_SPECIAL
```

Reduced probe/buffer settings should have a fallback compatible mode.

## 16. RTSP transport

Support:

```text
AUTO
TCP
UDP
```

Policy:
1. test TCP first for stable delivery
2. A/B test UDP on the local LAN if TCP shows repeated stalls
3. store the best transport per camera
4. never assume one is universally best

Expose transport, reconnect count and latency in diagnostics.

## 17. OpenCV is not the universal RTSP engine

`cv2.VideoCapture` may be used behind an adapter, but SmartPark should not depend on it as the only production network-media layer.

Prefer:
- go2rtc
- FFmpeg
- GStreamer

If OpenCV remains:
- choose FFmpeg/GStreamer backend explicitly
- set open/read timeouts
- verify buffer configuration actually works
- bound application queues
- never put FastALPR directly in capture loop

## 18. Do not route every displayed pixel through Python

Avoid continuous:

```text
RTSP
→ numpy
→ resize
→ BGR/RGB conversion
→ QImage
→ QPixmap
```

for all cameras if a native media path is available.

Prefer:
- go2rtc → WebRTC/MSE viewer
- or native FFmpeg/GStreamer/Qt playback

Python should primarily receive detection metadata.

## 19. FastALPR pipeline

Generic camera:

```text
camera
→ Media Gateway
→ detect stream
→ FastALPR worker
→ NormalizedDetectionEvent
```

Native ALPR camera:

```text
native plate event
→ NormalizedDetectionEvent
```

Optional:

```text
native low-confidence crop
→ local FastALPR/OCR verification
```

## 20. FastALPR process isolation

AI workers are separate from:
- desktop
- site service
- hardware SDK host

Model:
- load once
- warm once
- reuse

Monitor:
- inference milliseconds
- AI FPS
- queue wait
- CPU/GPU
- dropped AI samples

## 21. AI overload policy

Example:

```text
source = 10 FPS
FastALPR capacity = 4 FPS
```

Do not queue six extra frames every second.

AI processes newest available frame.

Metrics:

```text
source_fps
ai_processed_fps
ai_samples_dropped
ai_frame_age_ms
```

Dropping redundant samples is acceptable.
Processing 5-second-old frames is not.

## 22. Deduplicate detections

Same vehicle may appear in several sampled frames.

Deduplicate using:
- camera/lane
- normalized plate
- time window
- track ID when available
- event/image fingerprint

Never create multiple parking sessions for repeated frames.

## 23. Hardware acceleration

Detect what the Windows machine actually supports:
- Intel hardware decode
- NVIDIA
- AMD

Do not hard-code a decoder that may not exist.

Hardware Lab should display:
- software/hardware decode
- codec
- resolution
- decode FPS
- decode CPU

Use hardware decoding only when measured stable and beneficial.

## 24. Stream Profile UI

Add:

```text
Hardware Lab → Camera → Stream Profiles
```

Example:

```text
MAIN
H264
1920x1080
20 FPS
GOP 20
TCP

SUB
H264
1280x720
10 FPS
GOP 10

DETECT
Source: SUB
AI sampling: 5 FPS
```

Warnings:

```text
Smart codec enabled
GOP unusually long
No substream
Main stream used for all roles
Multiple upstream consumers
Decoder overloaded
```

## 25. Different vendors

Do not expect identical stream models.

Examples:
- Hikvision: main/sub/third streams
- Dahua: main/sub streams
- Axis: stream profiles
- ONVIF: media profiles
- generic RTSP: one or multiple direct URLs
- MJPEG: HTTP stream
- webcam: local capture

Negotiate capabilities.

## 26. Camera capabilities

Store:

```text
ONVIF
RTSP
RTSPS
HTTP_MJPEG
SNAPSHOT
H264
H265
MAIN_STREAM
SUB_STREAM
THIRD_STREAM
NATIVE_ALPR
ANALYTICS_METADATA
HARDWARE_EVENTS
```

If ONVIF Profile M analytics are available, use native vehicle/license-plate metadata rather than re-running FastALPR unnecessarily.

## 27. Network measurements

Per camera record:
- stream bitrate
- direct connection count
- reconnects
- network interface
- gateway latency
- packet-loss/jitter data where available

Calculate actual bandwidth rather than assuming the network is overloaded.

Prefer wired Ethernet for fixed parking cameras.

## 28. Time synchronization

Synchronize cameras, server and edge machines with NTP/time service where supported.

Store:
- source timestamp
- received timestamp
- decode timestamp
- AI start/end
- UI render time

## 29. Latency telemetry

Expose:

```text
camera/source → gateway
gateway → decoder
decoder time
AI time
UI delivery
estimated frame age
```

A multi-second delay must become a measured metric.

## 30. Frame counters

Track:

```text
frames_received
frames_decoded
frames_displayed
frames_dropped_live
frames_sampled_ai
frames_dropped_ai
decode_errors
reconnects
last_keyframe_age
```

Interpretation:

```text
received continues, displayed gets older
→ consumer backlog

received stalls
→ camera/network/transport

decode CPU saturated
→ codec/resolution/decoder issue
```

## 31. No DB/API calls inside media-read loop

Never:

```text
read frame
→ wait PostgreSQL
→ next frame
```

or:

```text
read frame
→ HTTP request
→ next frame
```

Media ingest drains continuously.
Events are published asynchronously.

## 32. UI FPS is independent

Separate:
- source FPS
- live-grid FPS
- full-screen FPS
- AI FPS
- metadata refresh rate

Example:

```text
source main: 20 FPS
grid: 10 FPS
fullscreen: 20 FPS
FastALPR: 5 FPS
status: event-driven
```

## 33. Visibility lifecycle

When Live Gates is hidden:
- detach unnecessary UI viewers
- keep media source alive only if AI/events need it
- do not leave invisible Qt frame conversion loops running

When shown:
- connect UI to existing local restream
- do not create a new physical camera session

## 34. Reconnect lifecycle

Use:

```text
DISCONNECTED
CONNECTING
STREAMING
DEGRADED
RECONNECTING
```

Before reconnect:
- cancel old reader
- release socket/decoder
- terminate orphan child process within timeout
- then start one replacement

Track child PIDs.

## 35. Stale-stream watchdog

Maintain:

```text
last_frame_received_at
```

If stale:
1. mark DEGRADED
2. determine whether source socket is alive where possible
3. restart only the media producer after threshold
4. backoff
5. never restart whole SmartPark

## 36. Automatic profile selection

During onboarding:

```text
discover profiles
→ probe
→ classify
→ recommend roles
```

Example:

```text
2688x1520 @20 → MAIN
1280x720 @10 → LIVE/DETECT
640x360 @10 → GRID
```

Admin may override.

## 37. Do not use universal bitrate presets

Read current bitrate and test actual quality/load.

Do not reduce bitrate until plate readability is validated.

## 38. Camera onboarding acceptance

Every camera must pass:

```text
network reachable
credentials valid
profile discovered/manual
direct probe works
gateway producer works
live view smooth for 60 sec+
reconnect works
FastALPR test if needed
resource usage acceptable
```

Store last-known working profile.

## 39. Fallback ladder

Per camera:

```text
Primary: RTSP/TCP preferred stream
Fallback: RTSP/UDP
Fallback: alternate stream
Fallback: vendor-native adapter
```

Do not switch repeatedly while healthy.

## 40. Implementation order

1. Instrument current pipeline.
2. Prove exactly where frame age grows.
3. Decouple FastALPR from live view.
4. Add latest-frame bounded buffers.
5. Introduce one media gateway connection per camera.
6. Split MAIN/SUB/DETECT roles.
7. Tune transport/codec/GOP.
8. Add hardware decode only if still needed.
9. Finish universal onboarding.

## 41. Mandatory tests

### Slow AI
Make FastALPR sleep 1 second per frame.

Expected:
- live view remains smooth
- AI queue does not grow

### Backlog
20 FPS producer, 3 FPS consumer.

Expected:
- queue remains bounded
- newest frame processed
- frame age stays bounded

### Camera disconnect
Disconnect 10 seconds.

Expected:
- UI responsive
- one reconnect worker
- no orphan processes

### Multi-camera
Run all configured cameras.

Expected:
- one poor camera does not stall others

### Hidden page
Leave Live Gates.

Expected:
- GUI decoder load falls

### Transport A/B
TCP vs UDP.

Measure:
- frame age
- corruption
- reconnects
- drops

## 42. Definition of done

Streaming is not complete until:

1. multi-second jumps are no longer normal
2. live viewing survives FastALPR slowdown/crash
3. video queues are bounded
4. live frame age is visible
5. AI frame age is visible
6. stale frames are dropped
7. physical cameras normally have one upstream gateway connection
8. substreams are used where appropriate
9. full-screen can use main stream
10. hidden views release UI decoder work
11. reconnect produces no orphan media processes
12. stream timeouts exist
13. codec/FPS/GOP/transport are visible
14. ONVIF profile discovery works where supported
15. manual RTSP works
16. generic cameras work with FastALPR
17. native-ALPR cameras can bypass FastALPR
18. 24-hour multi-camera soak test is stable
19. one camera failure does not affect others

# Final architecture rule

SmartPark is a parking system with a dedicated media subsystem.

The media subsystem owns:
- stream discovery
- connection
- RTSP/HTTP transport
- jitter/buffering
- decode
- restream
- frame sampling
- reconnection
- latency metrics

FastALPR owns recognition.

Desktop owns presentation.

ParkingService owns parking decisions.

Never merge these responsibilities again.
