# Windows camera display and recognition follow-up — 2026-10-22

## Supplied Windows logs: camera-host load and recovery churn

The uploaded Media Service status says RUNNING; this test is not a missing
MediaMTX executable. Its log repeatedly deletes nonexistent camera paths.
The SDK host initially logs four successful logins, then decoder restarts;
its log stops while field acceptance reports the host no longer answers.
Camera Lab records zero new frames during the run and stale images hundreds
of seconds old. The worker heartbeat incorrectly claims cameras 3/4 while its
active camera list is empty. The older database crash file predates this run.

Changes grounded in those logs and the existing vendor header:

- `Net_GetJpgBuffer` is documented as the **current frame**, not a queued
  stream. The host no longer invokes it in repeated eight-read drain batches
  or spins immediately when every JPEG differs. It samples once per tick,
  defaults to 10 JPEGs/second per requested camera, and pauses JPEG encoding
  for cameras with no active live/detection reader. No frame queue is added.
- Start/stop/recovery video operations now run on the existing HWND-owning UI
  thread, not an HTTP or JPEG-reading thread. The control queue and caller wait
  are bounded. Main stream 0 is tried first, matching the locally inspected
  legacy QY adapter; substream 1 remains the fallback. Empty-decoder retries
  are separated by 30 seconds rather than continually reopening video.
- A known handle temporarily reporting native disconnected state is not
  torn down and re-added by the Site Service watchdog. Native reconnect stays
  responsible for that connection. Restoration still repairs missing handles
  and handle/address mismatches after a host restart.
- The MediaMTX-only worker excludes SDK sources. Their existing Site Service
  FastALPR path stays authoritative, avoiding redundant model warmup and
  impossible worker tasks for nonexistent MediaMTX paths. An empty worker no
  longer reports READY just because its models warmed successfully.
- Removing SDK cameras from MediaMTX is idempotent, rather than repeatedly
  sending twelve missing-path DELETE requests every five seconds. SDK display
  endpoints and telemetry also bypass MediaMTX probes completely.
- Browser plate/status polling allows one in-flight request per pane, uses
  bounded request timeouts and ignores late responses after camera changes.
  Failed MJPEG retries back off rather than restarting every second forever.
  Realtime diagnostics now label cached-but-stale pictures disconnected.
- Automatic recognition rejects expired detection/live frames instead of
  treating minutes-old cached evidence as a newly stopped vehicle. Historical
  snapshots/crops remain available as evidence; they do not trigger new OCR.

Regression checks exercise bounded sampling, idle cameras, HWND thread
ownership, responsiveness of the metadata lock during slow native controls,
no reconnect on transient state, no SDK claims in the RTSP worker, idempotent
MediaMTX cleanup and browser request coalescing/backoff. They do not establish
physical Windows frame rate or decode compatibility: repeat the Camera Lab and
field acceptance run on the gate PC before treating the installation as ready.

## October 22 Windows retest: startup and device sessions

The new terminal screenshot shows `sqlite3.OperationalError: no such table:
cameras` while querying enabled cameras. This confirms a database/startup
failure, not a failed plate detector. The second screenshot's “View only”
message is a separate gate-ownership setting: changing the displayed gate does
not transfer this PC's recognition assignment.

Source-confirmed fixes in this kit:

- Media Service queried cameras outside its retry loop. If it started before
  Site Service created/migrated the database, it exited. It now checks the
  required schema read-only, waits/retries through database startup failures,
  and writes `media-service.json` with its state and database identity. Site
  Service remains the only schema migration owner; worker startup never seeds
  or creates a second replacement camera database.
- `.env` loading and relative SQLite URLs are anchored to the installation,
  not whichever working directory Windows used to launch a process. Task
  launchers also explicitly enter the install directory, and Site Service is
  registered/started before its consumers. Site and Media logs report their
  database identity so divergent configuration is visible.
- Persisted SDK handles were treated as valid after the native host restarted.
  The host now reports its live handle-to-camera-address mapping. Site Service
  restores previously connected, enabled cameras when their saved handles
  disappear or belong to a different device. Disabled and never-connected
  cameras are not automatically enrolled. Repeated connection requests reuse
  the same native session instead of leaking another stream slot. Ownership
  and parking workflow settings are not changed by session restoration.
- MediaMTX stderr was discarded. Its output now reaches redacted, rotating
  `media-service.log`; nonzero exits are reported by health. The host writes
  `hvx-host.log` with SDK availability, camera login and decoder retry status.
  The installed `vendor` directory is also found without inherited user
  environment variables, including the optional Windows service launch path.
- “SmartPark logs” is now a Desktop shortcut; `Open-SmartParkLogs.bat` is also
  provided in the USB kit. Logs are under `%ProgramData%\SmartParkEdge\logs`.
  Upgrade instructions no longer advise wiping the site database and losing
  cameras, ownership settings and logs on every test.

Install this update without wiping the existing data. Check Devices reports
the cameras connected, and assign this PC to the intended gate once if the
earlier wipe removed that setting. If video is still missing, provide
`site-service.log`, `media-service.log`, `hvx-host.log` and
`crash-SmartParkMediaService.log` if present. Logs can contain operational site
details; review them before sharing. Do not send the database or `.env` file.

The bundled Linux MediaMTX v1.11.3 was launched on temporary local ports with
the generated configuration and successfully served its Control API. Physical
Windows camera/network access and Windows Task Scheduler still need on-site
verification; a live SDK camera does not require MediaMTX to carry its video.

## October 22: multi-camera display and top navigation

The supplied Windows screenshots show successful plate crops, snapshots and a
97% recognition result while some live panes remain blank. The browser console
shows WHEP 404 responses and MJPEG 409 responses. These are separate failure
paths; a saved recognition snapshot is not proof that live video is healthy.

Changes to the existing implementation:

- Provider selection now excludes SDK cameras from MediaMTX live, detection and
  evidence routing, matching their existing source-registration policy. Running
  the MediaMTX process no longer advertises nonexistent SDK camera WHEP paths.
- The gateway retains the source specification actually used by its running
  producer. Previously `_session_for` replaced that specification before the
  comparison, so changing a camera's SDK handle did not restart its old reader.
  Only the affected producer is replaced; changing recognition consumer demand
  alone does not restart video.
- SDK video start failures previously left no JPEG pump to recover, and an
  empty decoder was never restarted after SDK reconnects. The existing
  per-camera pump now retries its own decoder after five seconds without JPEGs,
  with eight-second retry spacing and alternate sub/main selection. Recovery
  neither logs out cameras nor triggers snapshots, recognition or barrier commands.
- UI-message thread and per-camera pump creation are synchronized. Decoder
  stop/retry operations are serialized per handle, preventing a disconnected
  camera from being restarted by a concurrent recovery attempt.
- Host live JPEGs expire after five seconds without a native JPEG arrival.
  Live status and new MJPEG connections also require recent arrivals; a cached
  picture from many minutes ago is no longer sufficient to report “Live”.
- Page navigation is a horizontal, scrollable row above the workspace, not a
  left sidebar. One persistent “Hide navigation” / “Show navigation” button
  remains reachable even in F11 focus mode. Ctrl+K restores the row and search.
  Existing manual controls, plate crops and snapshot placement are retained.

Recognition algorithms, confidence thresholds, parking workflows, gate ownership
and camera seed data are unchanged in this follow-up. Production cameras still
come from administrator configuration/discovery, not hardcoded addresses.

New regressions cover SDK transport selection, replacement handles while the
neighbor keeps streaming, failed-start recovery, expired JPEGs, thread creation,
top-navigation overflow and hide/show behavior. Physical Windows decoder and
camera behavior still require an ENTRY + EXIT test on the connected Windows PC.

## Earlier October 21 changes

## Scope and limits

One production PC owns one gate's ENTRY and EXIT cameras. The supplied HTML is
visual guidance only: its billing, tariff, animation, and emergency-stop examples
are not implemented as new product features. Existing receipt, payment, gate
authorization, confirmation, and recognition deduplication rules are preserved.

No Windows logs or physical cameras were available for this investigation.
The failure paths below are confirmed in source and regression tests, not a claim
that every possible camera, firmware, driver, or Windows installation fault has
been reproduced or eliminated.

## Confirmed failure paths addressed

### Strict FastALPR crop-first follow-up

After another Windows retest, empty evidence and a “No plate” result were still
reported. The following changes remain inside the existing recognition and
display code; the UI layout and camera connection protocol are unchanged:

- `LOCAL_ONLY`/`FASTALPR_ONLY` fusion previously fell back to camera text when
  software had no result. It no longer does. Camera confidence cannot promote
  a weak local read, either. Native-only and hybrid modes remain explicit choices.
- Windows snapshot/crop writers returned native backslash paths, which were
  inserted directly into `/media/...` URLs. The routes require forward slashes.
  Writers now use POSIX-style relative paths and serializers also normalize
  older saved Windows paths, without moving or deleting files. Regression tests
  simulate Windows paths and fetch both images through the actual API routes.
- Software-only plates polling no longer queries the camera's native result.
  Software-only capture processing ignores native text/boxes and uses FastALPR's
  detector on the frozen snapshot. Its padded crop alone is passed to OCR, even
  if a camera incorrectly labels a full image as a native plate crop. If the
  camera supplies only a crop, that image still goes through the local detector.
- Plate-crop OCR runtime failures were swallowed as empty detections. They now
  return an explicit redacted error to the existing service/worker status path.
- The desktop stream reader had a second time throttle on top of its bounded
  latest-frame mailbox. A JPEG received inside that throttle window could stay
  pending until another network chunk arrived. Complete frames are now offered
  immediately; the existing mailbox still drops obsolete GUI work.
- Live SDK HTTP clients were shared across both cameras. A timeout/reset on one
  camera closed that client, interrupting the other camera's active requests.
  Live clients are now isolated by host, SDK handle, and event loop, cleaned up
  on disconnect/shutdown. A regression verifies that one lane timing out leaves
  its neighbor's connection open and delivering JPEGs.
- Default ONNX thread pools could compete with SDK decoding and rendering on
  smaller Windows PCs. Automatic model threads are now CPU-budgeted (one or two
  per model), with busy-spinning disabled. Explicit thread settings still work.
- SDK-native plate-region drawing is disabled; SmartPark's existing overlay
  rendering owns the display instead.
- The existing detail label identifies software waiting versus camera-only
  configuration. Previously saved native-only settings are not silently rewritten:
  for this deployment choose **FastALPR** for both cameras in Devices → Edit Camera.
  The dropdown now explicitly says **Use FastALPR (read a plate crop)** rather
  than the ambiguous older “SmartPark AI recognition” label.

Actual bundled models were tested against the existing `cars/car1.jpg`,
`cars/car2.jpg`, and `cars/car3-Malaysia.JPG` sample photographs, producing
`TBG4902`, `TBE9321`, and `VD9167`, respectively. The test spies on real OCR inputs
to verify they are plate crops, not full vehicle frames. It also runs the real
stopped-vehicle service path with the real models, asserts no OCR during the
settle period, verifies frozen-snapshot/crop handoff, and forbids camera OCR
queries. Hardware access and final parking dispatch are mocked in this test.
These sample plates are test expectations only, never production fallback text.
This is not a measurement of the connected Windows cameras or their accuracy.

### Follow-up after the SDK-connected Windows retest

The existing UI layout and recognition engine are retained. The retest confirmed
SDK connectivity and gate assignment, so these changes address downstream code
paths rather than replacing the camera connection or recognition library:

- The SDK JPEG drain waited until up to eight native reads completed before
  publishing any picture. It now updates the same latest-frame cache after each
  successful read, before the next native call can block. Queue draining and
  separate per-camera threads remain in place.
- SDK state/event/GPIO polling constructed and destroyed HTTP clients on every
  poll in the service event loop. Those hot read paths now reuse a bounded pool,
  separate from live JPEG requests, with cleanup on service shutdown.
- Expired OCR results were correctly rejected for persistence, but returned as
  successful reads to the arrival controller. That controller could hold the
  visit despite no capture being saved. Rejected reads now remain retryable and
  do not mark the frame as successfully processed.
- A coil read returned early whenever any historical capture had plate text.
  It now skips fallback OCR only when this trigger produced a new capture, not
  when an old vehicle is still in the database.
- An SDK-capable camera with working video but no current SDK handle was excluded
  from software fallback solely by adapter type. The existing software-recognition
  policy now governs that path; native-only settings remain respected.
- The recognition outbox loaded a saved crop but passed empty bytes to capture
  persistence. The existing saved crop is now passed through.
- Current-vehicle state correctly expires, but this also prevented the desktop
  from loading last-vehicle evidence if its two-second poll missed that visit.
  The same plates endpoint now includes the latest saved evidence separately.
  Snapshot/crop downloads are deduplicated and guarded by camera, generation,
  and requested image so old responses cannot replace newer evidence. Historical
  images never revive an expired current plate or issue a barrier command.
- Detector failures retain their redacted cause rather than silently looking
  like an empty detection zone. Existing detail text displays recognition and
  evidence download errors; the layout and controls are unchanged.

The bundled detector and OCR models were loaded and exercised locally. These
smoke checks verify loading/decoding, not accuracy on the actual Windows camera
images. No real camera JPEG or Windows logs were supplied for accuracy testing.

### Earlier fixes retained

- Production refuses lane-selector ownership changes, while the desktop ignored
  those errors. An unassigned production node therefore recognizes no cameras.
  The desktop now reads ownership without changing it, reports request failures,
  and offers an explicit settings-authorized, confirmed assignment to one gate.
  The new assignment endpoint rejects all-gates selection and unknown gates,
  respects environment pinning, persists the choice, and writes an audit event.
- A process-local selection could override newer persisted node settings.
  Database-backed reads now use the persisted assignment, allowing independent
  service processes to observe the same owner after a change or restart.
- Refresh filled cameras only when BOTH panes were empty. Adding or restoring a
  second camera while the first pane was selected left the second pane blank.
  Missing panes now reconcile independently, preferring the selected gate pair.
- A clean stream EOF never requested reconnection. An unlimited read timeout also
  left stalled streams frozen indefinitely. Readers now signal EOF and timeouts,
  reject streams without complete frames, and reconnect per camera. Invalid
  multipart lengths no longer trap the parser waiting for impossible frames.
- The desktop made blocking, redundant watch/unwatch requests before opening
  each stream. The stream endpoint already owns that viewer lease; duplicate
  desktop leases are removed. Cancelled server-side startup now releases its
  acquired viewer. Stopping readers are retained until completion instead of
  being forcibly terminated or blocking normal camera selection.
- Delayed recognition/evidence responses could paint a previously selected
  camera's plate or picture. Responses are checked against the current camera;
  recognition polls additionally check the display generation. Camera changes
  clear held evidence before loading the new camera.
- A fixed live-picture height and image-dependent label sizing wasted the
  available workspace. A dedicated canvas now repaints the original frame on
  resize, with aspect-preserving Fit and explicitly optional cropped Fill.

## Maintainable desktop structure

- `app/desktop/main.py`: application entry point, page registration, other pages.
- `app/desktop/common.py`: shared formatting, task helpers, safe reader retirement.
- `app/desktop/streams.py`: one independent HTTP reader and mailbox per camera.
- `app/desktop/video.py`: rendering and detection-zone coordinate mapping only.
- `app/desktop/live_pane_ui.py`: camera pane composition and visibility controls.
- `app/desktop/live_pane.py`: per-camera lifecycle and recognition evidence.
- `app/desktop/live_cameras.py`: live page, device management, explicit assignment.
- Existing `shell.py`, `theme.py`, and `presentation.py`: navigation, appearance,
  accessibility, scalable typography, shared widget presentation.

The annotated-layout revision removes the Controls toggle. Compact manual
open/close buttons and a camera selector remain visible at the top of each pane.
Plate crops stay at the lower-right inside each live picture, and last-vehicle
snapshots stay below the picture. Gate/layout/ownership setup is on Devices,
not above the live video. Detection-zone editing and fit/overlay options are in
each camera's small video-options menu. No fictional demo telemetry is added.
F11 hides navigation/header/toolbar; Ctrl+M hides/restores the menu bar and Ctrl+K
restores navigation/menu access. Fit shows the complete image; Fill crops edges.

Seeding remains an administrator-only setup shortcut under Devices → Load example
cameras, with explicit confirmation (including `confirm_test_data=true` for API
requests in production). It adds editable example records, preserves existing
camera metadata, never connects cameras or assigns recognition ownership, and is
not run automatically. Production does not infer the test layout:
discovery starts with stored addresses and actual discovery results, an empty
result cannot import fallback cameras, and recognized test addresses do not imply
gate names, directions, controller IPs, or display IPs. Existing admin metadata is
not overwritten by rediscovery or repeated seeding. There is no older-client
fallback import. No existing site records or credentials are deleted by this change.

## Windows field acceptance

1. Install/update from the rebuilt USB kit using its normal installer. Preserve
   the existing site database and camera credentials; do not create a fresh site
   or enable all-gates recognition as a workaround.
2. Sign in with settings-management permission. In Live Gates → Devices, select the actual
   gate and use **Assign PC to this gate…**. If environment-pinned, verify the
   displayed gate instead; the UI cannot override that pin.
3. In Devices, confirm that both enabled cameras belong to that same gate, with
   one ENTRY and one EXIT direction, and connect both. Verify the configured
   recognition mode is **FastALPR** on both cameras for software-only reading,
   and that the site's recognition module/pipeline is enabled. An explicit
   native-only setting saved by an older installation remains native-only until
   an administrator changes it; installing a kit does not rewrite site choices.
4. Check both pictures concurrently, including lower-right crops and the snapshots
   below. Use the video-options menu for Overlays/Fill, resize the window, and use
   F11/Ctrl+M. Detection-zone edits still use
   camera-image coordinates in either scaling mode.
5. Disconnect/reconnect one camera. The other picture must keep updating and
   the disconnected pane must recover independently.
6. Drive a vehicle through ENTRY and EXIT separately. Check plate/crop accuracy,
   receipt/session behavior, latency, and no duplicate capture or gate commands.
   Then test a second vehicle without clearing the database: the first saved
   plate must not suppress its trigger. Last-vehicle pictures should remain
   available after the live plate clears, without being treated as a new read.
   Repeat after closing the UI and after restarting Windows: recognition must
   continue in the background and ownership must remain the same gate.

Automated checks exercise simulated stream failures/concurrency, production
ownership persistence and permissions, cancellation cleanup, pair reconciliation,
canvas scaling, keyboard focus, and collapsible controls. Physical Windows camera
acceptance remains necessary; automated success does not establish field latency
or recognition accuracy. Four pre-existing full-suite failures concern missing
legacy documentation, not camera or recognition assertions.

Validation before the annotated-layout revision: 669 tests and 3 subtests passed.
After the revision, 672 full-suite runtime tests and 3 subtests passed, with the
same four legacy-document checks explicitly deselected. The final focused layout,
keyboard, view-selection, and discovery checks passed 27 tests; a separate fresh
production-process check confirmed that no test cameras or gates are inferred.
Native Qt previews were rendered and inspected offscreen.

After restoring the explicit seed shortcut, 674 tests and 3 subtests passed,
with the same four pre-existing legacy-document checks deselected. The focused
camera/setup/desktop suite passed 39 tests, including production confirmation,
repeat-import metadata preservation, arbitrary replacement addresses, and UI
permission/cancellation checks. A fresh production process still inferred no
fixture cameras or gates; only the explicit seed loader returned examples.

After the SDK-connected video/recognition follow-up, 684 tests and 3 subtests
passed, with the same four pre-existing legacy-document checks deselected. The
focused suite passed 68 tests. New regressions exercise immediate SDK-frame
publication, pooled polling, stale-result retries, coil reads with historical
captures, recognition-outbox crop preservation, evidence ordering, and the real
capture/file-serving path with mocked detector/OCR output. No physical Windows
latency or plate-accuracy result is claimed by these automated checks.

The strict FastALPR/Windows-path follow-up passed 699 full-suite tests and
3 subtests, with the same four legacy-document checks deselected. After the
final parking-event URL normalization and camera-mode label update, the release
focused suite passed 65 tests (one known missing-document check deselected).
These checks include real bundled ONNX inference on sample vehicle photographs,
not only mocked OCR output. Compilation and changed-file whitespace checks passed.
