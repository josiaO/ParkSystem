# SmartPark media ownership — 15 October 2026

The desktop is the primary operator interface on the dedicated Windows parking PC. The web interface remains available for administration and remote access. This is a deployment choice, not a measured claim that Qt always outperforms WebRTC.

## Processes and ownership

- **Site Service, 64-bit:** one local instance per lane PC, with API, camera events and parking decisions for that PC's assigned entry/exit pair. Multi-PC deployments share PostgreSQL and evidence storage; see `LANE-DEPLOYMENT.md`.
- **HVX host, 32-bit Windows:** vendor SDK and callbacks. Video comes from Net_GetJpgBuffer; capture callbacks deliver independent vehicle/plate images. A working plate callback does not prove video works. Keep the supplied DLL family together.
- **Recognition worker:** bounded latest-frame sampling, plate detection, crop, OCR and event delivery for generic MediaMTX cameras. SDK cameras stay with the Site Service. OCR waits for a stopped plate and does not run for every displayed frame.
- **MediaMTX:** upstream RTSP connections and distribution for generic cameras; SDK cameras do not register guessed RTSP paths. Browser playback uses the existing WHEP transport; the server remains pinned to v1.11.3.
- **Desktop:** independent latest-frame MJPEG readers feed the video canvas. Generic MediaMTX streams use one shared local JPEG consumer; SDK streams use the existing JPEG producer. Vehicle snapshots and plate crops have separate panels and bounded image requests.

## Video recovery

SDK JPEG retrieval has a finite no-frame interval. The host expires JPEGs when its pump receives no frame for five seconds. Unchanged bytes from a freshly received frame are allowed; historical cache contents are not fresh video. If SDK video supplies no JPEG, an explicitly configured RTSP source can be used as fallback. It does not open guessed RTSP streams alongside the SDK. Capture callbacks remain active.

RTSP tries the configured URI before guessed vendor URLs. JPEG decoding and encoding each use one FFmpeg thread, with one filter thread. A MediaMTX JPEG consumer is stopped before the direct fallback is started; another viewer reuses an active fallback producer.

MJPEG playback retries on errors, EOF and missing frames. Camera switches cancel the old reader without blocking the GUI and invalidate pending responses. Browser WHEP handles ICE negotiation and reconnection, with MJPEG fallback when necessary.

## Resource defaults

Recognition concurrency: 4; ONNX CPU threads use the existing CPU budget or explicit recognition-model thread setting; inter-op threads: 1; spin waiting disabled. Recognition sampling: 4 fps; configured MJPEG output: 10 fps. The recognition worker warms both models before starting lane tasks. Desktop plate updates have one request in flight. Sampling rates are not guarantees of actual recognition latency. Existing environment overrides still apply.

Native event images use per-callback tokens rather than recycled vendor IDs. The event cache has 128 entries and a 64 MiB byte limit. Expired or ambiguous evidence fails empty rather than returning a different car's image. Display snapshots use bounded rolling files and content-versioned URLs.

## Requirements and gaps

The supplied Windows payload contains 32-bit Python, the vendor DLL set, 64-bit Python, Qt Essentials, FFmpeg, MediaMTX and both ONNX model files. The local Python environment passes `pip check`; the kit verifier passes file/wheel-presence checks. The installer now runs `pip check` after installing offline wheels. The installer also runs the supplied 32-bit vendor DLL loader check without calling camera APIs. The vendor video and SDK DLLs import MSVCR80.dll: Microsoft Visual C++ 2005 SP1 x86 is a deployment prerequisite. This runtime was not bundled in the existing kit and may already be installed with OcxConfig. Obtain it from [Microsoft](https://www.microsoft.com/en-gb/download/details.aspx?id=26347) if the loader check reports that dependency missing. Static file checks on Linux do not prove Windows codec/device compatibility.

The Windows requirements are resolved from an offline wheel bundle and are less strictly pinned than the development requirements. Preserve that tested bundle; do not independently upgrade Qt, ONNX or SDK DLLs on site. Root requirements exclude uvloop on Windows. No evidence currently justifies adding more OCR libraries.

Outstanding field evidence: Windows CPU model, actual source codec/resolution/FPS and configured RTSP URI for each blank camera, per-camera frame age and reconnect counts, and a sustained run with real plates. 16 GB RAM alone does not determine decode capacity. Avoid running both live clients during the initial performance comparison, since both add presentation work.
