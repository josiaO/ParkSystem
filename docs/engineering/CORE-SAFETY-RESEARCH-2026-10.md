# SmartPark core engineering research and decisions — 2026-10-01

This document records the external engineering references used for the current
core cleanup and the architectural decisions that follow from them.

## 1. Camera integration and media transport

### Keep MediaMTX as the media gateway

MediaMTX already matches SmartPark's needs better than embedding a full NVR.
Its Control API can manage/query active paths, and its RTSP/WebRTC/HLS support
lets SmartPark separate camera acquisition from UI and recognition consumers.

References:
- https://mediamtx.org/docs/features/control-api
- https://mediamtx.org/docs/read/web-browsers
- https://mediamtx.org/docs/features/authentication

Decision:
- Keep MediaMTX behind SmartParkMediaService.
- Keep Control API and metrics on localhost.
- Prefer one upstream pull per distinct camera stream and fan it out locally.
- UI and FastALPR must not each open their own independent RTSP camera session.

Frigate/go2rtc documents the same operational pattern: restream once and let
live-view/detection consume the restream, avoiding duplicate camera
connections and unnecessary re-encoding:
- https://docs.frigate.video/configuration/restream/

SmartPark should copy the pattern, not embed Frigate as its parking engine.

### ONVIF stays capability-driven

ONVIF Profile M explicitly covers metadata/events for vehicle and license plate
analytics and can carry recognition events through metadata streams, event
services or MQTT. Profile T complements it for modern video streaming.

References:
- https://www.onvif.org/profiles/profile-m/
- https://www.onvif.org/profiles/profile-t/

Decision:
- Native vendor SDK stays for HVX-specific functions proven on site.
- ONVIF Profile M is a normalized analytics/event provider when supported.
- ONVIF/RTSP must remain optional capabilities, not assumptions about every
  camera.

### Latest-frame-wins remains the right recognition policy

GStreamer's appsink documentation warns that queued frames accumulate if the
application cannot consume fast enough, and specifically provides max-buffers
and leaky/drop behavior to bound queues.

References:
- https://gstreamer.freedesktop.org/documentation/app/appsink.html
- https://gstreamer.freedesktop.org/documentation/application-development/advanced/pipeline-manipulation.html

Decision:
- SmartPark's recognition queue must stay bounded to the newest frame.
- Never allow OCR backlog to create multi-second stale recognition.
- Media and recognition remain separate processes/failure domains.
- Do not migrate to GStreamer merely for fashion; use it later only if the
  current FFmpeg decoder cannot meet measured latency/resource targets.

## 2. Gate/barrier authority

A display/LED is not a barrier actuator.

Decision implemented:
- A gate command succeeds only when GPIO/vendor relay or the physical board
  relay succeeds.
- LED/display delivery is telemetry only and can never set GateCommandResult.ok.

The physical passage sensor/loop remains the eventual source for VEHICLE_PASSED.
OPEN_COMMAND_COUNTS_AS_PASSED is a commissioning fallback, not the desired
production truth when passage hardware is available.

## 3. Receipt printer and receipt-taken sensing

Generic ESC/POS printing only proves that bytes were submitted to the printer
transport. It does not prove the driver removed a presented ticket.

Decision implemented:
- Real printer transport errors now fail closed.
- Saving an HTML/PNG slip to disk is not a successful physical print.
- Generic Windows/LAN ESC/POS adapters no longer advertise paper-status or
  taken-sensor capabilities that they cannot query.
- Production receipt-taken state requires a real taken sensor event or an
  explicit sensor-confirmed integration.
- Simulation keeps a simulated taken sensor for development.

Future hardware recommendation:
- Prefer a kiosk/presenter printer or external presenter sensor exposing
  explicit PRESENTED/TAKEN state.
- Implement that hardware behind ReceiptPrinterAdapter or a dedicated
  ReceiptTakenSensorAdapter; do not encode device-specific GPIO in parking
  business logic.

## 4. QR scanner fallback

For USB QR readers configured as keyboard/HID devices, no special camera/vision
library is required; treat the scan as input into the operator/kiosk UI. For a
scanner exposing a COM/serial interface, pySerial is the appropriate narrow
dependency and must use bounded read timeouts.

Reference:
- https://pyserial.readthedocs.io/en/latest/pyserial_api.html
- https://pyserial.readthedocs.io/en/latest/shortintro.html

Decision for Phase 6/7:
- Add QrScannerAdapter with HID-keyboard and serial implementations.
- A QR scan resolves the existing opaque public token and enters the same
  ExitLaneController as plate recognition; it must never create a second
  exit/payment implementation.

## 5. Session and multi-site database constraints

SQLite supports partial indexes, which SmartPark already uses for constraints
such as one open session per site+plate. PostgreSQL also supports the production
equivalent.

Reference:
- https://www.sqlite.org/partialindex.html

Decision implemented:
- Registered-vehicle entitlement lookup is now explicitly site-scoped.
- Camera site identity comes from Camera.site_id, not indirectly through Gate.
- Keep unique/idempotency constraints in the database instead of relying on
  process-memory dedupe for business authority.

## 6. Payments

Flutterwave's webhook guidance treats webhooks as asynchronous notifications;
SmartPark's provider verification/reconciliation design should continue to
verify provider-side transaction state before crediting the parking ledger.

Reference:
- https://developer.flutterwave.com/docs/webhooks

Decision implemented:
- Public request amounts are ignored; the server recomputes the exact
  outstanding parking balance at payment-intent creation.
- Simulated browser payments are disabled by default.
- Only verified provider settlement or authenticated local kiosk cash can mint
  SUCCEEDED ledger entries.
- Barrier code never calls the payment provider directly.

Money cleanup still required:
- move model/service annotations away from float toward Decimal or integer
  minor units end-to-end. SQLAlchemy Numeric is designed for fixed-precision
  numeric values:
  https://docs.sqlalchemy.org/en/20/core/type_basics.html

## 7. Code authority cleanup

Implemented in this branch:
- live ENTRY camera events now go through EntryLaneController;
- simulation.handle_plate_event refuses non-simulated ENTRY events;
- EXIT remains on the legacy path only until ExitLaneController is built;
- production receipt-taken no longer delegates to the simulation bypass.

Next deletion milestone:
1. Build and physically verify ExitLaneController.
2. Route live EXIT + QR fallback into it.
3. Remove legacy handle_exit and the EXIT half of handle_plate_event.
4. Keep only explicit /sim fixtures in simulation.py.
5. Run one-lane hardware validation, then 8h and 24–72h soak tests.
