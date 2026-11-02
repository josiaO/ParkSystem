# SmartPark Edge system guide

This is the map of the system for operators, developers, and technicians. It
describes the production paths in this repository and points to the deeper
component documents where appropriate.

## 1. System shape

SmartPark is split into a Site Service, an optional Edge/Processing Node, a
browser or desktop operator client, camera/media adapters, recognition, and
parking/payment services.

```text
QY/HVX camera ──OcxConfig/NetSDK host──> bounded JPEG mailbox ─> desktop
                                      └─> FastALPR / native events
Generic IP camera ──RTSP─────────────> Media/preview ─> desktop/browser config
                                                          │
                 printer <─ receipt/payment <─ Site Service ─> gate controller
```

The Site Service is the authority for configuration, sessions, payments,
receipts, recognition events, and gate decisions. A Processing Node owns only
the assigned physical lane/camera scope while using the Site Server database.
It must not create a second local parking database.

Main entry points:

| Part | Responsibility | Main code or document |
|---|---|---|
| Site Service | HTTP API, database, sessions, payment, policy, audit | `app/api_main.py` |
| Web app | Configuration, settings, payment/admin surfaces, developer playground | `app/web/index.html` |
| Desktop app | Technician/operator Qt client and setup wizard | `app/desktop/main.py`, `app/desktop/setup.py` |
| HVX host | 32-bit Windows bridge for vendor DLLs and callbacks | `tools/hvx_sdk_host/` |
| Camera adapters | HVX/QY SDK, RTSP, Dahua, Hikvision and generic IP | `app/infrastructure/hardware/cameras/` |
| Media gateway | One bounded producer; OcxConfig JPEG for QY/HVX, MediaMTX/RTSP for generic cameras | `app/services/media_gateway.py`, `app/services/mediamtx.py` |
| Recognition | Native camera plates, FastALPR, fusion, persistence | `app/services/camera_lpr.py`, `app/recognition_worker.py` |
| Parking | Entry/exit claims, receipt policy, fees, gate decision | `app/services/simulation.py`, `app/services/parking_sessions.py` |
| Payment | Cash/kiosk and public mobile-payment boundary | `app/services/public_pay.py`, `app/infrastructure/payments/` |
| Hardware | Gate pulse, LED, coil/presence, thermal printer | `app/services/gates.py`, `app/services/presence.py` |

## 2. Camera connection and OcxConfig/QY findings

The supplied OcxConfig material was freshly examined with Ghidra and static
binary evidence. The Windows host now follows that stream lifecycle directly;
it is not a browser/WebRTC library and it is not loaded into the Linux/API
process.

The confirmed shape is:

1. The QY adapter loads its matched `NetSDK.dll` family and connects to the
   camera control service, normally TCP port `30000`.
2. The adapter registers report/image/control callbacks.
3. The video path is separate from plate-result callbacks. The QY video code
   uses `PlaySdk.dll`, `RtspRecvSdk.dll`, and `DecodeSdk.dll` to receive/decode
   frames. The OCX path also exposes a JPEG/decode buffer path.
4. The supplied OcxConfig DLL family is kept together; do not replace only one
   vendor DLL.
5. `Net_StartVideo` starts PlaySdk/RTSP/DecodeSdk workers. The host reads the
   decoded callback/current JPEG and keeps only the newest frame. It does not
   create a second RTSP reader for a QY/HVX camera.
6. `Net_ShowPlateRegion`/the PlaySdk overlay path carries the camera's plate
   region, stop line, and prefix line. Native callbacks remain separate from
   application FastALPR.

The important engineering conclusion is that OcxConfig/NetSDK is the
authoritative Windows streaming backend for QY/HVX cameras. SmartPark's media
gateway is only the bounded application mailbox and desktop delivery layer.
The browser is not part of this camera ownership path; operators should use
the Windows desktop for production live video and use the web app for
configuration and administration.

Evidence and reproduction notes are in:

- [Camera protocol research](../research/parkwatch/PARKWATCH_CAMERA_PROTOCOL.md)
- [Video pipeline research](../research/parkwatch/PARKWATCH_VIDEO_PIPELINE.md)
- [Native ALPR](NATIVE-ALPR.md)
- [Media architecture](MEDIA-ARCHITECTURE.md)

## 3. Streaming path

### 3.1 Acquisition

- HVX/QY cameras are connected and streamed by the Windows 32-bit OcxConfig /
  NetSDK host. The host owns the vendor callbacks, native decoder, detection
  overlay, and bounded latest-frame buffer, then exposes status/JPEG data to
  the 64-bit application.
- Generic IP, Dahua, and Hikvision cameras use RTSP/ONVIF/HTTP discovery and
  the configured stream URI.
- A camera connection, a live video frame, and a plate callback are separate
  health signals. One must not be inferred from another.

### 3.2 Distribution

MediaMTX is used for generic RTSP cameras. For QY/HVX cameras, MediaMTX and
guessed RTSP URLs are deliberately not opened: the OcxConfig host is the sole
physical-camera reader. SmartPark keeps one application producer and one-frame
mailboxes for desktop display and FastALPR. Old frames are dropped rather than
stacked.

The desktop diagnostics show stream backend, frame age, source sequence,
decoder state, reconnects, and dropped-frame counters. The `MAIN`, `SUB`,
`DETECT`, `LIVE`, and `EVIDENCE` labels are roles,
not five independent viewers:

- `LIVE`/`SUB`: low-latency operator display.
- `DETECT`: sampled frames for software recognition.
- `MAIN`/`EVIDENCE`: higher-quality source or still evidence.

The design prevents “stacking”: opening another browser pane or requesting a
snapshot does not create another uncontrolled RTSP/FFmpeg reader when the
shared producer is active.

See [MediaMTX integration](MEDIAMTX-INTEGRATION.md), [stream profiles](STREAM-PROFILES.md),
and [camera delivery diagnostics](CAMERA-DELIVERY-DIAGNOSTICS.md).

## 4. Recognition, capture, crop, and detection zone

Recognition has three selectable modes per camera:

- `NATIVE_ONLY`: trust the camera’s authenticated/native plate event.
- `FASTALPR_ONLY`: detect and OCR the plate from sampled video/JPEG frames.
- `HYBRID`: fuse native text and local OCR when both are available.

For QY/HVX on Windows, the source JPEG comes from the OcxConfig host and is
sampled by the application-side FastALPR path. The host's native vehicle/image
callbacks are not FastALPR and an empty native plate is a valid reason for
FastALPR to read the fresh application frame. FastALPR is never run on every
display repaint and never reads the browser.
- `VIDEO_ONLY`: live video and evidence only; no plate-driven parking action.

The normal software path is bounded and staged:

1. Acquire a frame from the shared camera/media path.
2. Detect a vehicle/plate region.
3. Crop the plate using the detected bounding box and configured framing/zone.
4. Run OCR on the crop, with the configured normalization and confidence
   policy.
5. Apply consensus/de-duplication and persistence rules.
6. Store immutable-ish capture evidence (snapshot, crop, plate, confidence,
   source, and timestamps) and publish the vehicle event.
7. The parking/session layer decides whether the event is an entry or exit.

The detection zone is a processing hint and overlay. It restricts where a
plate is accepted and helps prevent background reads; it is not a gate command
by itself. A crop or OCR result is not accepted merely because a JPEG exists.
Evidence should include the full vehicle snapshot and the actual plate crop
used for recognition. The live UI shows both and exposes a “correct plate”
workflow for technician review/training.

For no-crop/no-plate problems, check in order: live frame freshness, camera
recognition scope, detection zone/framing, model readiness, crop dimensions,
OCR confidence/consensus, then event persistence. A live image alone proves
only the acquisition path.

See [FastALPR pipeline](FASTALPR-PIPELINE.md), [native ALPR](NATIVE-ALPR.md),
[camera lab](CAMERA-LAB.md), and [camera troubleshooting](CAMERA-TROUBLESHOOTING.md).

## 5. Presence, sessions, receipts, and gates

Presence/coil state is used to distinguish a vehicle in the lane from an old
or background recognition. Parking sessions use idempotent entry/exit claims
so duplicate native and software events do not create duplicate visits.

Entry normally follows this shape:

```text
vehicle present -> recognized plate -> capture persisted -> session claimed
-> receipt rendered/stored -> receipt policy -> gate decision
```

Exit calculates the fee from the session’s tariff snapshot, applies payment
and entitlement rules, and then asks the gate adapter to pulse the barrier.
The receipt policy can be `OFF`, `PRINT_OPTIONAL`, `PRINT_AND_OPEN`, or
`REQUIRE_TAKEN_BEFORE_OPEN`. Printer storage and the physical printer are
separate; a missing paper device must not erase the stored receipt.

Gate safety is deliberately downstream of recognition: a camera frame or
manual “open” request is not enough if the relevant policy, payment, receipt,
presence, or developer safety flag blocks the action.

## 6. Payment page and public receipts

Each session may receive an opaque public token. `/p/{token}` shows only the
driver-safe projection: plate, vehicle photo, plate crop, entry time, stay,
amount due/paid, payment status, and available payment action. It does not
expose internal camera, node, database, or access-plan identifiers.

The page is intentionally mobile-first: one-column evidence, large touch
targets, stacked payment choices, and the site logo. Public payment ingress
is rate-limited and privacy headers are applied. Configure the public base URL
before printing QR codes so phones resolve the correct host.

## 7. Developer mode / playground

Developer settings are site-scoped and permission-protected. The web Settings
page exposes the playground to authorized developers/technicians; the API is
the enforcement point, so changing browser controls alone cannot bypass it.

Controls are independent where possible, including:

- verbose/debug printing and diagnostic traces;
- simulation and replay actions;
- camera/media/recognition providers;
- public payment availability;
- printer behavior;
- automatic gate opening and physical actuator calls;
- deletion tools, with one-by-one and bulk operations where the user has the
  corresponding management permission.

When gate opening is disabled, manual and automatic gate endpoints reject the
actuator call before hardware access. This is the required test mode for
checking recognition, capture, crop, fee, receipt, and payment behavior without
opening a real barrier. Use simulated gates and dry-run commands for hardware
commissioning.

## 8. Time policy

The system uses one authoritative rule:

- Persisted timestamps, device events, audit records, leases, and comparisons
  are UTC-aware.
- The site’s IANA timezone (for example `Africa/Dar_es_Salaam`) is the
  display and user-input timezone.
- A datetime without an offset from a browser/desktop form is interpreted as
  site-local, then converted to UTC before fee/session calculations.
- Day/night tariff boundaries are evaluated in the site timezone.

Change it in Settings or Setup using an IANA name. After saving, verify the
Settings card’s “Site clock”, then reload Sessions, Payments, Fees, Reports,
and the public receipt. The operating system may remain on UTC; that is not a
reason for the site display to remain UTC.

If a legacy install still reports UTC after saving, check that the user has
`settings.view`, that `/settings/site` returns the new value, and that the
database migration completed. The saved `site_settings` row is durable; a
restart should not reset it.

## 9. Configuration and recovery

Configuration is layered:

1. packaged/default settings provide safe startup values;
2. database site settings provide durable site policy;
3. camera/gate/module settings provide per-device behavior;
4. developer flags provide safe test overrides.

Use the Settings/Hardware pages and the API rather than editing installed
files. Before large changes, download an offline backup. After upgrades run
startup checks, then field acceptance with gate output disabled or simulated.

Important Windows logs are under the installed SmartPark data directory,
including Site Service, recognition worker, media, and HVX host logs. The
default installer also includes the offline repair and startup scripts.

## 10. Verification checklist

For a new or upgraded site:

1. Confirm `/health/details` and the Settings site clock.
2. Confirm camera adapter, TCP/RTSP reachability, and stream freshness.
3. Open one live pane and verify there is no increasing frame age.
4. Run a supervised vehicle sequence with gate opening disabled.
5. Check snapshot, plate crop, zone overlay, source, confidence, and stored
   capture.
6. Check one entry session, receipt, public mobile page, fee quote, payment,
   exit session, and report date.
7. Re-enable only the hardware actions approved for the test site.
8. For Windows packaging, rebuild with `packaging/make_windows_kit.sh` and
   verify `dist/SmartParkEdge-Installer.zip` and its `.sha256` file.

Useful focused tests include:

```text
.venv/bin/pytest -q tests/test_site_time_settings.py
.venv/bin/pytest -q tests/test_camera_load_regressions.py
.venv/bin/pytest -q tests/test_public_ingress.py tests/test_public_receipt_page.py
```

The repository’s existing component documents remain the detailed reference;
this guide is the navigation layer for understanding how they fit together.
