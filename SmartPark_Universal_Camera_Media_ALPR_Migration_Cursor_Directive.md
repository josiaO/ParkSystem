# Cursor Directive — SmartPark Universal Media, Camera & ALPR Architecture

## Purpose

Refactor SmartPark into a scalable, vendor-neutral parking product without breaking the currently working camera connectivity, native ALPR, FastALPR processing, or boom-gate control.

This is a controlled migration, not a rewrite of the working hardware layer.

The current working HVX/QY integration is valuable and must remain operational throughout this work.

The target product must be deployable globally and must not assume one country, plate format, currency, language, camera brand, gate topology, or payment provider.

---

## 1. Non-Negotiable Migration Rule

Do not break the current camera and ALPR engine.

Before changing anything:

1. Create a git tag/branch such as `hardware-working-baseline`.
2. Document the current HVX SDK connection flow, working camera configuration, native ALPR callback path, boom-control path, RTSP profiles and FastALPR invocation path.
3. Add regression tests around current working behavior.
4. Preserve the legacy adapter until the replacement path passes shadow, soak and production tests.
5. Never migrate all cameras at once.

---

## 2. Product Architecture Principle

Separate these concerns:

```text
CAMERA CONNECTIVITY
       ↓
MEDIA STREAMING
       ↓
RECOGNITION
       ↓
PARKING BUSINESS LOGIC
```

Gate control is a separate boundary.

A camera vendor must never define parking behavior.
FastALPR must never define camera connection logic.
Video playback must never block recognition.
Gate control must never depend on the video renderer.

---

## 3. Final High-Level Architecture

```text
                         PHYSICAL CAMERA
                               |
                +--------------+--------------+
                |                             |
                v                             v
        Camera Control Adapter          Media Source
        (vendor/ONVIF/etc.)             RTSP/HTTP/etc.
                |                             |
                |                             v
                |                    Media Gateway Layer
                |                     (MediaMTX initially)
                |                        /          \
                |                       /            \
                |                      v              v
                |               Live View         AI Stream
                |                   |                |
                |                   v                v
                |               Desktop          FastALPR
                |                                    |
                |                                    v
                +--------------------------> Recognition Fusion
                                                 |
                                                 v
                                      Normalized Vehicle Event
                                                 |
                                                 v
                                          Parking Engine
                                                 |
                                                 v
                                         Gate Authorization
                                                 |
                                                 v
                                        Gate Controller Adapter
```

---

## 4. Preserve Existing Camera Adapter

The current working HVX integration becomes `HVXCameraAdapter`.

Responsibilities:
- discovery
- authenticated SDK connection
- native ALPR callbacks
- snapshots
- vendor-specific health/events
- proven vendor configuration

It must not:
- render video
- calculate fees
- create sessions
- open gates directly from camera callbacks
- run FastALPR
- contain UI logic

---

## 5. Preserve Existing Gate Adapter

The working boom implementation becomes `HVXGateAdapter`.

```python
class GateControllerAdapter:
    async def open(self, gate_id, command_id, reason): ...
    async def close(self, gate_id, command_id, reason): ...
    async def get_state(self, gate_id): ...
    async def health(self, gate_id): ...
```

Future adapters may support Modbus, PLC, ONVIF relay, HTTP relay, Axis IO, Dahua IO, Hikvision IO and other controllers.

Parking logic must not know which adapter is used.

---

## 6. Introduce a Media Gateway Layer

Add a dedicated media subsystem. Initial implementation: MediaMTX.

Create a SmartPark abstraction:

```python
class MediaGateway:
    async def register_source(self, camera_id, source_config): ...
    async def unregister_source(self, camera_id): ...
    async def get_live_endpoint(self, camera_id): ...
    async def get_detect_endpoint(self, camera_id): ...
    async def get_snapshot(self, camera_id): ...
    async def health(self, camera_id): ...
    async def metrics(self, camera_id): ...
```

Do not spread MediaMTX-specific code across SmartPark.

---

## 7. MediaMTX Must Be an Optional Sidecar

Deploy a `SmartParkMediaService` that owns MediaMTX lifecycle/configuration.

Responsibilities:
- start/monitor MediaMTX
- register camera sources
- generate runtime config
- expose local RTSP/WebRTC endpoints
- gather stream health/metrics
- restart failed paths
- keep upstream camera connections controlled

Failure behavior:

```text
MediaMTX unavailable
→ live viewing degraded
→ FastALPR for generic cameras may degrade
→ native ALPR cameras continue using native events
→ parking engine stays alive
→ gate control stays alive
```

---

## 8. Camera Types and Capabilities

Model by capability, not brand.

Types may include:
- GENERIC_RTSP
- GENERIC_ONVIF
- NATIVE_ALPR
- USB_CAMERA
- HTTP_MJPEG
- VENDOR_SDK_CAMERA

Capabilities may include:
- RTSP / RTSPS
- ONVIF
- HTTP_STREAM
- SNAPSHOT
- NATIVE_ALPR
- NATIVE_VEHICLE_DETECTION
- MAIN_STREAM / SUB_STREAM / THIRD_STREAM
- IO_OUTPUT
- PTZ
- AUDIO
- H264 / H265 / JPEG

Do not infer capability solely from vendor name.

---

## 9. Camera Device vs Camera Stream

Separate `CameraDevice` from `CameraStreamProfile`.

CameraDevice fields:
- id
- site_id
- name
- vendor
- model
- serial
- mac
- ip
- hostname
- adapter_type
- credentials_ref
- capabilities
- timezone
- enabled

CameraStreamProfile fields:
- id
- camera_id
- role
- protocol
- uri/reference
- codec
- width/height
- fps
- bitrate
- GOP
- transport
- audio
- enabled
- health

Roles:
- MAIN
- SUB
- LIVE
- DETECT
- EVIDENCE

---

## 10. Universal Camera Onboarding Wizard

Flow:

### Step 1 — Connection
- IP/hostname
- credentials
- optional port

### Step 2 — Discover
Attempt:
1. existing vendor adapter
2. ONVIF
3. RTSP probe
4. HTTP/MJPEG probe
5. manual stream entry

### Step 3 — Identify profiles
Display codec, resolution, FPS, bitrate, transport and keyframe interval when known.

### Step 4 — Assign roles
Example:
- Main: 1920x1080 @ 20 FPS
- Live: 1280x720 @ 10 FPS
- Detect: 1280x720 @ 5 FPS

### Step 5 — Recognition mode
- NATIVE_ONLY
- FASTALPR_ONLY
- HYBRID

### Step 6 — Test
- 60-second stream stability
- reconnect
- snapshot
- recognition
- latency
- CPU/RAM

### Step 7 — Save
Store last-known-working configuration.

---

## 11. Recognition Architecture

```python
class RecognitionProvider:
    async def process(self, event_or_frame): ...
```

Providers:
- HVXNativeALPRProvider
- FastALPRProvider
- ONVIFAnalyticsProvider
- future vendor providers

Normalized output:

```json
{
  "event_id": "uuid",
  "camera_id": "uuid",
  "site_id": "uuid",
  "lane_id": "uuid",
  "occurred_at": "timestamp",
  "vehicle_detected": true,
  "plate_text": "ABC1234",
  "plate_country": null,
  "plate_region": null,
  "confidence": 0.94,
  "vehicle_type": null,
  "vehicle_color": null,
  "image_ref": "...",
  "plate_crop_ref": "...",
  "source": "FASTALPR"
}
```

Parking logic consumes only normalized events.

---

## 12. Country-Neutral Plate Model

Do not assume Tanzanian plate structure.

Store:
- raw_plate
- normalized_plate
- country_code
- region_code
- plate_type
- recognition_confidence
- validation_result

Use configurable:
- PlateNormalizationPolicy
- PlateValidationPolicy

A site may use no format validation, one-country validation, or multi-country validation.

---

## 13. FastALPR Must Be a Separate Worker

Use `SmartParkRecognitionWorker`.

Do not run FastALPR inside:
- Qt UI
- camera callback
- MediaMTX
- parking engine
- vendor SDK host

Worker rules:
- load model once
- warm once
- reuse
- consume DETECT stream
- latest-frame semantics
- publish normalized events

If overloaded, drop stale frames instead of building backlog.

---

## 14. Latest-Frame Semantics

For FastALPR and any Python-side live sampling:

```text
max queued frames = 1–3
```

If inference is slower than source:
- discard old frames
- keep newest frame

Track:
- frame_age_ms
- frames_received
- frames_processed
- frames_dropped
- inference_ms

Never process a five-second-old vehicle frame.

---

## 15. Live View Path

Live video must not pass through FastALPR.

Preferred:

```text
Camera
→ MediaMTX
→ WebRTC
→ Desktop viewer
```

Fallback:
- local RTSP
- other low-latency local playback

Do not make HLS the primary gate-control-room feed unless necessary.

---

## 16. Independent Failure Domains

Processes:

```text
SmartParkSiteService
SmartParkDesktop
SmartParkHVXHost32
SmartParkMediaService
MediaMTX
SmartParkRecognitionWorker
SmartParkWorker
```

Failure rules:

```text
Recognition worker crashes → live video remains
MediaMTX crashes → native ALPR remains
HVX SDK host crashes → generic RTSP cameras remain
Desktop crashes → parking engine remains
One camera fails → other cameras remain
```

---

## 17. Feature Flags for Safe Migration

Add:
- media_gateway_enabled
- media_gateway_camera_ids
- fastalpr_new_pipeline_enabled
- webrtc_live_enabled
- native_alpr_enabled

Migration stages:
1. current working system remains authoritative
2. MediaMTX runs in parallel
3. one camera live view uses MediaMTX
4. one generic camera FastALPR uses MediaMTX DETECT
5. all live video moves through media gateway
6. old direct live-view path is removed only after long soak tests

---

## 18. Shadow Mode

Support `SHADOW` mode.

Example:
- legacy FastALPR path authoritative
- new MediaMTX/FastALPR path shadow

Compare:
- detections
- frame age
- latency
- CPU/RAM
- dropped frames
- reconnects

Switch authority only after measurable improvement.

---

## 19. Stream Health

Per camera expose:
- network_state
- media_state
- native_alpr_state
- fastalpr_state
- last_frame_at
- last_detection_at
- source_fps
- decode_fps
- display_fps
- ai_fps
- frame_age_ms
- jitter
- packet_loss
- reconnect_count

Do not use one generic ONLINE status.

---

## 20. Stream Optimization Policy

Default guidance:

### Live grid
- substream
- H.264 preferred
- approximately 10–15 FPS

### Fullscreen
- main stream
- native FPS where hardware permits

### FastALPR
- lowest stream that preserves enough plate pixels
- start around 5 FPS
- increase only after real site testing

### Evidence
- highest useful resolution

Do not apply one global stream profile.

---

## 21. RTSP Transport

Per camera:
- AUTO
- TCP
- UDP

A/B test and store best result per camera.

Do not assume one transport is globally superior.

---

## 22. Adapter Registries

Create:
- CameraAdapterRegistry
- GateAdapterRegistry
- RecognitionProviderRegistry
- MediaGatewayRegistry

New vendor flow:

```text
implement adapter
→ declare capabilities
→ register
→ run contract tests
→ expose onboarding config
→ shadow test
→ production
```

Do not edit parking core.

---

## 23. Global Product Configuration

Make configurable:
- timezone
- locale
- language
- currency
- currency precision
- date/time format
- distance units
- plate normalization/validation
- tax behavior
- tariff policy
- receipt templates
- payment methods
- branding
- support contacts

Do not hard-code TZS, Swahili, 45 minutes, 1000, or Tanzania plate formats.

---

## 24. Localization

Use translation keys instead of literal UI text.

Prepare for:
- English
- Swahili
- Arabic
- French
- Portuguese
- other languages

Avoid layout assumptions that make RTL impossible later.

---

## 25. Time Zones

Store timestamps in UTC.

Each site has an IANA timezone such as:
`Africa/Dar_es_Salaam`.

Tariffs use the site's configured timezone, never the Windows server's implicit local timezone.

---

## 26. Currency

Use ISO 4217 currency codes and exact Decimal/integer minor-unit handling.

Never use float for financial amounts.

Examples:
- TZS
- USD
- EUR
- KES
- ZAR
- AED

---

## 27. Multi-Site Readiness

Every operational entity has `site_id`.

Do not necessarily build full cloud multi-site administration now, but avoid making a future multi-site migration painful.

---

## 28. Multi-Vendor Test Matrix

Maintain a test matrix:

```text
Vendor/model
Connection type
ONVIF
RTSP
Native ALPR
FastALPR
Main/substream
Reconnect test
24h soak
Known limitations
```

Do not claim universal camera support without evidence.

---

## 29. Contract Tests

CameraAdapter:
- connect
- health
- capabilities
- streams
- snapshot
- disconnect
- reconnect

RecognitionProvider:
- input
- normalized output
- confidence
- timestamp
- failure behavior

GateControllerAdapter:
- open
- state
- idempotency
- timeout
- health

Every new implementation must pass the same contracts.

---

## 30. Soak Tests

One camera:
- 1 hour
- 8 hours

All cameras:
- 24 hours
- ideally 72 hours

Measure:
- memory
- CPU
- frame age
- reconnects
- orphan processes
- dropped frames
- AI latency

No continuous memory/thread/process growth.

---

## 31. Rollback

Every migration step must have a configuration rollback.

Examples:

```text
Live View Provider:
MEDIAMTX → DIRECT_LEGACY
```

```text
Recognition:
FASTALPR_NEW → FASTALPR_LEGACY
```

Do not require emergency code edits at the parking site.

---

## 32. Security

Media services are LAN/private by default.

Never publicly expose camera RTSP URLs.

Credentials:
- encrypted/reference-based
- hidden from normal UI/logs

Public customer/payment services must have no direct access to media or gate-control APIs.

---

## 33. Observability

Admin/Technician diagnostics must clearly separate:
- camera connection
- media gateway
- recognition
- gate
- database
- payment

Media diagnostics should include:
- upstream connected
- codec
- resolution
- FPS
- transport
- frame age
- jitter
- packet loss
- readers
- reconnects

---

## 34. Normal Operator UI

Operator sees:

```text
Gate A Entry
Camera: Online
Live Video: Online
Plate Recognition: Ready
Barrier: Ready
```

Not raw SDK/RTSP/FFmpeg details.

Technical details belong in Hardware Lab.

---

## 35. Documentation

Create/update:

```text
docs/
  MEDIA-ARCHITECTURE.md
  CAMERA-ADAPTERS.md
  MEDIAMTX-INTEGRATION.md
  FASTALPR-PIPELINE.md
  NATIVE-ALPR.md
  CAMERA-ONBOARDING.md
  STREAM-PROFILES.md
  CAMERA-CAPABILITY-MATRIX.md
  ADDING-A-CAMERA-VENDOR.md
  ADDING-A-RECOGNITION-PROVIDER.md
  GATE-ADAPTERS.md
  MIGRATION-AND-ROLLBACK.md
  CAMERA-TROUBLESHOOTING.md
```

Document the existing HVX integration exceptionally well so it never has to be reverse engineered again.

---

## 36. Implementation Sequence

### Phase 0
Freeze/document current working baseline.

### Phase 1
Introduce interfaces around existing code without changing behavior.

### Phase 2
Add MediaMTX sidecar with no production dependency.

### Phase 3
Route one test camera's live view through MediaMTX.

### Phase 4
Create new FastALPR worker consuming MediaMTX DETECT stream in shadow mode.

### Phase 5
Build universal ONVIF/RTSP/manual onboarding.

### Phase 6
Migrate live views one camera at a time.

### Phase 7
Migrate generic FastALPR cameras one camera at a time.

### Phase 8
Add global locale/timezone/currency/plate policies.

### Phase 9
Run long soak tests and stabilize.

Never migrate all cameras simultaneously.

---

## 37. Definition of Success

The migration is successful when:

1. Existing HVX native ALPR still works.
2. Existing boom control still works.
3. Live streaming is independent from FastALPR.
4. Generic cameras can use FastALPR.
5. Native ALPR cameras can bypass FastALPR.
6. One camera failure does not affect others.
7. MediaMTX can restart without killing SmartPark.
8. FastALPR can restart without killing live video.
9. Mixed camera vendors are supported through adapters.
10. Stream profiles are discoverable/configurable.
11. Locale/currency/timezone are site configuration.
12. Plate normalization is country-neutral.
13. New camera vendors do not require ParkingService changes.
14. New recognition providers do not require UI/gate changes.
15. Rollback to known-working hardware paths remains possible.
16. 24–72 hour soak testing passes.

---

# Final Instruction

Do not rewrite a working hardware stack just to obtain cleaner architecture.

Wrap first.
Observe.
Shadow-test.
Migrate one camera at a time.
Keep rollback paths.
Remove legacy integrations only after replacements prove themselves.

SmartPark must become a global parking platform whose core business logic is independent from camera vendor, country, currency, recognition engine, media server, and gate controller.
