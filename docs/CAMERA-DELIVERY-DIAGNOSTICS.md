# Camera delivery and recognition investigation

Video login, decoded video, detector progress and OCR are separate checks.
`SDK_CONNECTED` means authentication succeeded; it does not establish live
video. A vehicle callback can supply an image while continuous video is broken.

## Fixes covered by regression tests

- A worker's claimed camera list no longer disables Site Service OCR. The
  worker must report READY with fresh frames and recent inference progress.
- A running MediaMTX process is not sufficient to select it for detection:
  this camera must have a registered DETECT path.
- The Site Service resolves the DETECT path from the media owner's telemetry,
  not another process's empty configuration dictionary. Split detect streams
  therefore do not silently resolve to the live stream.
- SDK JPEG retrieval and decoder start/stop use the same per-camera lock.
  Decoder control has a bounded lock wait rather than waiting indefinitely
  for a native read. Returned native buffers are released on error as well
  as on success.
- Native control holds that lock on the Windows window-owner thread until
  the operation really finishes, even if its HTTP caller times out. Shutdown
  keeps that thread alive until decoder-stop commands have been processed.

These tests reproduce software failures without cameras. They do not establish
which native SDK failure occurs on a particular Windows PC.

## QY/OcxConfig capture and FastALPR contract

The Windows QY path follows the boundary confirmed by the fresh Ghidra and
ParkWatch evidence: `Net_StartVideo`/PlaySdk owns continuous decoded video;
the native image callback owns vehicle-event capture; and FastALPR remains the
application-side plate recognizer. There is one OcxConfig SDK reader per
camera, one latest-frame live buffer, and no browser reader or second QY
decoder.

For a native event, the full panorama is now the primary FastALPR input. The
camera `usLpBox` is scaled from its callback dimensions to the JPEG dimensions
and used only as a fallback when the current detector cannot return a box. The
SDK vehicle-picture buffer is a last-resort OCR source, not the preferred crop.
This prevents an early/partial native rectangle from clipping a plate while
the vehicle panorama is complete. The native OcxConfig four-point plate region
is converted to the FastALPR normalized detection zone only when no explicit
operator zone is configured.

Night/IR crops use one bounded enhanced OCR retry when the first crop is dark
or weak. The raw vehicle panorama remains the evidence image; enhancement is
applied to the OCR crop only. Native camera timestamp, vehicle ID, and snapshot
index are retained with the event so replay and repeated realtime ID `0`
callbacks can be diagnosed.

## Gate-camera evidence on Windows

Use the updated SDK host together with the updated application. In PowerShell,
the default local host exposes cached video diagnostics without triggering a
snapshot, recognition, a relay, or a parking transaction:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8765/info' | ConvertTo-Json -Depth 8
```

Each connection's `video` includes:

- `start_rc`, `start_rc_name`, `requested_stream`, `stream_type`, and `hwnd`.
- `jpeg_rc`, `jpeg_error`, `jpeg_bytes`, `jpeg_attempts`, and `jpeg_read_ms`.
- `jpeg_read_pending` and `pending_read_ms` for a blocked native JPEG read.
- `frames_received`, `frame_age_ms`, `state`, and `control_error`.
- `capture_mode`, `draw_data_primary`, `callback_fps`, `jpeg_production_fps`,
  `jpeg_encode_ms`, `window_capture_ms`, and the source/output JPEG dimensions.

The QY preview profile defaults to a 1280px maximum width, quality 78, and 15
FPS. It is display-only: native recognition callbacks are not downscaled. The
profile can be tuned for a field PC with `SMARTPARK_HVX_JPEG_MAX_WIDTH`,
`SMARTPARK_HVX_JPEG_QUALITY`, and `SMARTPARK_HVX_JPEG_FPS`. A healthy camera
should report `capture_mode=sdk_draw_data` and `draw_data_primary=true`.
`capture_mode=play_sdk_hwnd` identifies the slower PrintWindow/BitBlt
compatibility path.

The running Site Service exposes the same measurements per camera through
`/health/details` and `/health/ready` under the media rows:

- `callback_progress`: native decoded-callback count, rate, and age;
- `jpeg_production`: latest JPEG count/rate, age, and encode time;
- `consumer_demand_age_ms`, `pump_liveness`, `request_duration_ms`, and
  `request_status`;
- `recovery_reason`, `stall_classification`, and `effective_ocr_owner`.

`stall_classification` separates `consumer_inactive`, `pump_dead`,
`native_decoder_stall`, `bridge_or_encode_stall`, and bridge request/error
symptoms. This is diagnostic telemetry only: it does not open a gate, trigger
a capture, or change camera configuration. Core readiness remains separate
from `camera_freshness.operational_ready`; a stale required lane is listed in
`required_stale_camera_ids` even when the database and HTTP service are ready.

For a low-impact Windows host-only snapshot, use:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8765/video-status/0' | ConvertTo-Json -Depth 8
```

Replace `0` with the SDK handle. The endpoint reads cached state and does not
start another decoder or camera reader.

`frames_received` counts valid JPEG samples, not proof that objects are moving.
Compare camera timestamps or visible movement as well. Repeated identical
images alone cannot distinguish an empty scene from a decoder's cached frame.

`START_FAILED` means video initialization returned an error. `NO_FRAMES` with
successful initialization distinguishes SDK errors, empty buffers, invalid
JPEGs, and a still-pending native read. JPEG failures are logged when the reason
changes and at most once every 30 seconds for an unchanged failure reason.
Inspect `%ProgramData%\SmartParkEdge\logs\hvx-host.log`.

During a maintenance window, compare one camera using the matched vendor
viewer and SmartPark, sequentially. Close the other SDK client before each
test. Record the same camera, main/substream, account, Windows user/session,
and loaded DLL set. Do not open gates or disable production gate assignment
to diagnose video. Vendor playback success is not proof that SmartPark's
native JPEG call succeeds; retain both sets of observations.

## Dahua video working but OCR absent

In Hardware Lab, inspect recognition commissioning for the camera:

1. `recognition.in_scope` must be true for automatic processing on this PC.
   A viewable Dahua camera outside the assigned gate intentionally gets no
   automatic OCR. Assign cameras administratively; do not enable every gate.
2. `recognition.module_enabled` must be true and the recognition mode must
   allow software reading.
3. Check DETECT path registration and fresh decoded frames separately from
   browser video. Check worker READY state and detector progress, not just
   process liveness or the claimed camera list.
4. Run the existing one-picture diagnostic read on a clear plate. It does not
   create a parking session or open a barrier. This isolates model/crop/OCR
   from stream delivery and stopped-vehicle gating.
5. Check the configured detection zone and plate size in the actual DETECT
   image. Continuous video is detected for a stopped plate; OCR reads the
   resulting crop, not every moving frame.

The existing Windows logs supplied for the earlier build show successful SDK
logins and empty-decoder restarts. They do not contain native JPEG return
codes or a Dahua commissioning trace, so they cannot establish either remaining
hardware-specific cause. Collect those fields from the Windows test before
claiming the devices are repaired.
