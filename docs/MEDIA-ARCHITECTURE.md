# SmartPark media ownership — 9 November 2026

The desktop is the primary operator interface on the dedicated Windows parking PC. The web interface remains available for administration and remote access. This is a deployment choice, not a measured claim that Qt always outperforms WebRTC.

## Processes and ownership

- **Site Service, 64-bit:** one local instance per lane PC, with API, camera events and parking decisions for that PC's assigned entry/exit pair. Multi-PC deployments share PostgreSQL and evidence storage; see `LANE-DEPLOYMENT.md`.
- **Camera engine boundary:** every camera carries an adapter ID. QY/HVX is one
  vendor adapter backed by the 32-bit Windows OcxConfig/NetSDK host; RTSP and
  ONVIF are separate generic adapters. Adapter identity selects ownership even
  before a native SDK handle exists, so an unconnected QY camera cannot open a
  competing RTSP reader.
- **HVX host, 32-bit Windows:** vendor SDK and callbacks. Video comes from
  Net_StartVideo plus the decoded draw-data/latest JPEG path; capture callbacks
  deliver independent vehicle/plate images. A working plate callback does not
  prove video works. Keep the supplied DLL family together.
- **Recognition worker:** bounded latest-frame sampling, plate detection, crop, OCR and event delivery for generic MediaMTX cameras. SDK cameras stay with the Site Service. OCR waits for a stopped plate and does not run for every displayed frame.
- **MediaMTX:** upstream RTSP connections and distribution for generic cameras;
  QY/HVX adapters do not register guessed RTSP paths. Browser playback uses the
  existing WHEP transport; the server remains pinned to v1.11.3.
- **Desktop:** independent latest-frame MJPEG readers feed the video canvas. Generic MediaMTX streams use one shared local JPEG consumer; SDK streams use the existing JPEG producer. Vehicle snapshots and plate crops have separate panels and bounded image requests.

The camera engine is `app/services/media_gateway/`: it owns per-camera
sessions, one upstream producer, bounded LIVE/DETECT mailboxes, generation
invalidations, and transport telemetry. The display engine is
`app/services/preview.py` plus `app/desktop/streams.py` and
`app/desktop/live_pane.py`: it owns the cache-to-MJPEG boundary, latest-only
desktop delivery, and canvas presentation. The gateway does not import the
display or recognition engines; optional frame/generation observers are
registered by those consumers. This makes a camera/decoder failure visible in
gateway health without requiring the desktop or ALPR worker to be running.

## Video recovery

SDK JPEG retrieval has a finite no-frame interval. The host expires JPEGs when its pump receives no frame for five seconds. Unchanged bytes from a freshly received frame are allowed; historical cache contents are not fresh video. Explicit `adapter_id=qy` never falls back to RTSP; it reports a native-host failure and preserves the camera SDK session for recovery. Legacy `adapter_id=hvx` rows may retain their historical generic fallback behavior until they are migrated to explicit `qy`. Capture callbacks remain active.

In production, MediaMTX owns generic RTSP ingest and distribution; the local
gateway does not start a competing FFmpeg reader. Development and commissioning
may use the bounded direct compatibility lane: it tries the configured URI
before guessed vendor URLs, and JPEG decoding/encoding each use one FFmpeg
thread with one filter thread. A MediaMTX JPEG consumer is stopped before that
compatibility fallback is started; another viewer reuses an active fallback
producer.

MJPEG playback retries on errors, EOF and missing frames. Camera switches cancel the old reader without blocking the GUI and invalidate pending responses. Browser WHEP handles ICE negotiation and reconnection, with MJPEG fallback when necessary.

Repeated JPEG bytes are not treated as a new display frame, so the UI mailbox
stays bounded. They can still represent a healthy static scene when transport
arrivals continue: `/live.mjpeg` emits a one-second heartbeat copy of the
current JPEG without changing the display sequence. If transport arrivals stop,
`last_received_at` expires, the response closes, and only that camera's
decoder is restarted. Pixel freezing remains separately visible through
`frozen`, `duplicate_frames`, `last_received_age_ms`, and
`live_frame_age_ms` diagnostics.

## Resource defaults

Recognition concurrency: 4; ONNX CPU threads use the existing CPU budget or explicit recognition-model thread setting; inter-op threads: 1; spin waiting disabled. Recognition sampling: 4 fps; configured MJPEG output: 10 fps. The recognition worker warms both models before starting lane tasks. Desktop plate updates have one request in flight. Sampling rates are not guarantees of actual recognition latency. Existing environment overrides still apply.

Native event images use per-callback tokens rather than recycled vendor IDs. The event cache has 128 entries and a 64 MiB byte limit. Expired or ambiguous evidence fails empty rather than returning a different car's image. Display snapshots use bounded rolling files and content-versioned URLs.

## Requirements and gaps

The supplied Windows payload contains 32-bit Python, the complete matched QY/OcxConfig DLL family, the OcxConfig OCX/client recovery artifacts, the bundled Microsoft Visual C++ 2005 SP1 x86 runtime, 64-bit Python, Qt Essentials, FFmpeg, MediaMTX and the FastALPR ONNX models. The local Python environment passes `pip check`; the kit verifier passes file/wheel-presence checks. The installer runs `pip check` after installing offline wheels and installs both the QY x86 and application x64 Microsoft runtimes before the loader check. The installer also runs the supplied 32-bit vendor DLL loader check without calling camera APIs. `vendor/QY-SDK-MANIFEST.txt` records the native files and SHA256 hashes, so a field technician can detect a mixed or partially copied SDK. Static file checks on Linux do not prove Windows codec/device compatibility.

The Windows requirements are resolved from an offline wheel bundle and are less strictly pinned than the development requirements. Preserve that tested bundle; do not independently upgrade Qt, ONNX or SDK DLLs on site. Root requirements exclude uvloop on Windows. No evidence currently justifies adding more OCR libraries.

Outstanding field evidence: Windows CPU model, actual source codec/resolution/FPS and configured RTSP URI for each blank camera, per-camera frame age and reconnect counts, and a sustained run with real plates. 16 GB RAM alone does not determine decode capacity. Avoid running both live clients during the initial performance comparison, since both add presentation work.
