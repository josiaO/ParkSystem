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
