# Capture-zone and plate-distance calibration: technical report

Date: 2026-11-19. Spec: `ZIRP_CAMERA_CAPTURE_ZONE.md`.

## What was there before

* Detection: FastALPR's plate detector (`locate_plate_boxes`) on sampled
  DETECT frames, in two places: the Site Service for HVX/SDK cameras
  (`app/api/runtime_parts/05_recognition_ingest.py`, `_video_arrival_ready` /
  `_maybe_watch_local_alpr`), and the Recognition Worker for generic RTSP
  cameras (`app/recognition_worker/30_camera_worker.py`). On this site all four
  cameras are HVX/SDK, so the Site Service path is the one in use.
* Snapshot trigger: `ArrivalGate` in `app/services/camera_framing.py` fired
  when the plate box reached a capture width (default 64 px, one value for
  the whole site unless overridden), or after lingering, or when the car left
  ("departed" fallback read of the widest frame). With `capture_trigger=zirp`
  the firing commands a camera snapshot; this site runs `external`, so the live
  frame is read. Camera hardware triggers (native events) bypass the gate.
* Cropping: the detector box, padded, then OCR (`recognize_arrival_bytes`).
* Zone: one rectangle (`detect_roi`, site default `0.06,0.18,0.94,0.92`) and a
  digital "detection zoom" cropped the picture *before* the detector.
* Duplicates: per-lane visit state (`runtime.lane(...).visit`), plate
  consensus (`PlateTrack`), capture identity keys in `persist_event`, and
  hybrid fusion (one fused capture per vehicle).

## What changed

Removed (they did not work across cameras):

* the ZIRP detection zone, detection zoom and capture distance (`FRAMING`
  values and the old top-level `detect_roi`/`detect_zoom` keys). Migration
  `0020_clear_legacy_capture_zones` deletes the stored values; the recognition
  decode width is kept. `framing_from_profiles` now always reports the whole
  picture. The site-wide default zone is `off`.
* `ArrivalGate`, `best_arrival_box`, the "departed" widest-frame read and the
  lingering fallback.
* the desktop "Detection zone…" dialog and the web live view's zone editor.
  `PUT /cameras/{id}/framing` now only sets the decode width (410 for zones).

Added:

* `app/services/capture_calibration.py`
  * per-camera record in `site_settings` (`capture_calibration:{camera_id}`):
    camera, site, gate, lane, direction, zone polygon (normalised, 3-16
    points), trigger line (y + side), minimum plate width/height (px),
    minimum detector confidence, minimum recognition (OCR) confidence,
    sharpness, brightness range, glare/black share, best-of-N window,
    `version`, `updated_at/by`. Saves are versioned with a conflict check.
  * `evaluate_frame`: per detector box — size, area, relative width, in zone,
    past line, detector confidence; the crop is decoded and measured
    (Laplacian variance, mean grey, clipped share) only for boxes that pass
    geometry, so far plates cost nothing extra.
  * `CaptureGate`: far plates are tracked but return `far`; eligible frames are
    collected (`collecting`) and the best one (size × sharpness × exposure ×
    confidence) is chosen (`ready`) after N frames / T seconds or when the car
    leaves the eligible area. One fire per car; `held` after a published read;
    queued cars detected; max 2 OCR attempts per passage.
  * calibration test mode (expires, max 4 h).
* Integration (no new decoder, no new engine): both admission points call the
  detector on the whole picture, then `evaluate_frame` + `CaptureGate`, and
  OCR the **selected** frame through the existing crop + OCR path. A FastALPR
  read below the camera's minimum recognition confidence is not stored and the
  gate tries a later frame.
* Test mode choke point: `persist_event` returns before writing a capture row
  for a camera in test mode (camera triggers and ZIRP reads alike), so no
  parking session and no barrier decision can follow. The read is shown in
  the calibration window instead.
* API (`app/api/capture_calibration_routes.py`): `GET/PUT/DELETE
  /cameras/{id}/calibration` (edit needs `cameras.manage`, audited),
  `PUT …/calibration/test-mode`, `GET …/calibration/live`,
  `GET …/calibration/snapshot.jpg`.
* Desktop: `app/desktop/calibration.py`, opened from Cameras → "Calibrate
  capture…" or a live pane's ⋯ menu. Live picture; draw/move a rectangle or
  polygon zone; place a trigger line; plate boxes (green eligible, red not)
  with width×height; eligibility reasons; plate size / sharpness / brightness;
  the chosen frame; latest read and confidence; Save (per camera, versioned),
  Revert, Reset to uncalibrated, Test mode.

Uncalibrated camera (all cameras right after the migration): whole picture,
no size or quality limits, best-of-3 still on. Plate sizes are pixels on that
camera's picture: a relative distance cue, not metres.

Not available: vehicle bounding boxes. The installed detector finds plates
only; adding a vehicle detector would be a second recognition model, which the
spec rules out. The window says so.

Enforced on every path: `persist_event` (where any read becomes a capture,
then a session or barrier decision) checks the read's plate box against the
camera's calibration: zone, trigger line, minimum width/height and detector
confidence. Camera-triggered 1920×1080 snapshots are scaled to the live
picture the calibration was set on (`reference_width`); quality limits apply
only at that size. A read that fails, or a read with no plate box, is not
stored; the refusal is logged and shown in the calibration window. Only an
explicit operator action (`force`) bypasses it. Uncalibrated cameras are not
blocked.

Desktop: the Live Gates panes draw each camera's zone, trigger line and plate
boxes (green = will be read, red = not) read-only; editing is in Settings →
Camera calibration. Tariffs moved to Settings → Tariffs.

## Tests

`tests/test_capture_calibration.py` (21 tests, synthetic frames through the
real quality code):

| scenario | result |
|---|---|
| far plates approaching | detected, `far`, no OCR |
| entering the zone | best of the window chosen (not the first frame) |
| moving through quickly | read from the frame(s) seen before leaving |
| slow vehicle | window closes by frame count |
| stopping in the zone | read once, then `held` |
| repeated detections | no second read |
| several vehicles | only the eligible (near, in-zone) plate counts |
| small plate / partly hidden | rejected by min width / height |
| motion blur | rejected by sharpness |
| poor lighting | rejected as too dark |
| trigger line side | honoured |
| independent cameras, versions, conflict | yes |
| test mode | `persist_event` writes nothing, read shown |
| migration | old zone values removed, decode width kept |
| API | registered, refuses anonymous callers |

Updated tests that targeted the removed mechanism: `test_virtual_loop.py`
(ported to the new gate), `test_windows_video_recognition_regressions.py`,
`test_recognition_decoder.py`, `test_recognition_worker_runtime.py`,
`test_live_pipeline_regressions.py`, `test_recognition_measure.py`,
`test_capture_zone_and_streams.py`, `test_desktop_presentation.py`;
`test_arrival_framing.py` was removed (it tested only the old gate and zone).

## Before / after measurement

Replay of `TestingData/Video Project.mp4` (177 s, 1080p, one lane camera,
cars approaching from far) at 5 fps through the **real** FastALPR detector
and OCR on this PC (CPU), dry run. Script:
`tools/capture_calibration_replay.py <out.json>` (run with the installed 64-bit Python). The "calibrated" zone and
sizes were drawn by me from sample frames of this clip; they are not a field
calibration of the site's four cameras.

| gate | OCR calls | reads with text | empty reads | mean OCR conf. | median plate width at read | median first sighting → read | median OCR |
|---|---:|---:|---:|---:|---:|---:|---:|
| old (site zone, 64 px) | 26 | 25 | 1 | 0.902 | 67 px | 1.0 s | 90 ms |
| new, uncalibrated | 35 | 23 | 12 | 0.771 | 53 px | 0.4 s | 85 ms |
| new, calibrated | 22 | 21 | 1 | 0.895 | 134 px | 2.8 s | 94 ms |

Detector: median 163 ms per 1080p frame (unchanged by this work).

Reading the numbers honestly:

* **Accuracy could not be measured**: `TestingData/ground_truth.json` has no
  labels, so there is no truth to score against. Confidence and empty-read
  counts are proxies only.
* Calibrated capture reads at about twice the plate width and spends fewer
  OCR calls, with confidence on par with the old gate. It reads later (by
  design: closer to the camera), here 2.8 s after the plate is first seen.
  My rough zone missed the first three cars of the clip, whose framing differs.
* **Uncalibrated is worse than the old shared setting** (12 empty OCR calls,
  lower confidence): it reads as soon as a plate appears. Each camera must be
  calibrated after this change; until then reads come earlier and are weaker.
* Field accuracy and latency on the four real cameras still need measuring
  after each camera is calibrated (run test mode per camera and compare the
  shown reads with the cars).

## Update: start/end lines, full enforcement, latency (19 Nov, evening)

Start and end of reading. Each camera can have a start (trigger) line and an
end line. A plate is read only between them; past the end line nothing is
read, so a car moving out cannot be read a second time. Both lines are drawn
in Settings → Camera calibration and shown on Live Gates.

Enforced on every read path (`persist_event`, tested per setting in
`tests/test_capture_calibration.py` with 1920×1080 camera snapshots): zone,
start line, end line, minimum width and height, detector confidence,
recognition confidence, sharpness, brightness range and glare. Snapshots are
scaled to the calibrated live-picture width before sizes and sharpness are
measured, so each limit means the same thing on every path. Not applicable to
the camera-trigger path: best-of-N frame selection (the camera sends its own
snapshots).

Tried and withdrawn: a time/position heuristic that treated a different plate
seen soon after a read, further along the path, as the same car leaving. On
live traffic it refused real cars at 1# Entry (T850BCR, T159EAP and others at
19:32-19:35) and was removed within minutes. The end line is the guard
against re-reads instead.

Recognition latency, last 6 h before these changes (2,040 cars, camera
snapshot to decision): median 0.84 s, p90 1.4 s, p99 3.3 s, worst 12.7 s.
Slow cases are dominated by the wait before the camera event is picked up
(median 256 ms, p99 1.1 s) and OCR spikes (p99 1.6 s, worst 11.6 s). Fixed:
the video path no longer OCRs a passage the camera trigger already read
(duplicate CPU work, and a source of second reads); folder checks run once
instead of on every media write. Not fixed yet: event-loop stalls of up to
11 s while live frames are fetched from the HVX host (`hvx_client.live_jpeg`);
moving that fetch off the event loop is the next latency step.

Follow-up (19:50): live frames from the HVX host are now fetched on a small
dedicated thread pool (one connection per camera) instead of the Site
Service event loop (`app/services/hvx_client.py`). Measured on live traffic:
event-loop stalls 48/hour → 4/hour (none during frame fetch);
camera-snapshot-to-decision median 925 → 725 ms, p90 1.74 → 1.06 s,
p99 4.4 → 2.3 s. Caveat: 4.7 h before (1,484 cars) vs 15 min after
(64 cars, lighter evening traffic). OCR still has rare multi-second spikes
(worst 5.4 s after the change).

## Update: lane 2# stored no sessions; stuck snapshot/crop (19 Nov, night)

**What happened.** 2# Entry (camera 3, calibration v5) had *Brightness to* saved as
2 on the 0–255 scale. Every plate is brighter than 2, so every read was refused as
"too bright" (273 refusals in the log, no capture stored, so no entry session). The
Live Gates pane kept showing the plate text of each new read, but the snapshot and
crop came from the last *stored* capture, so they looked frozen on an old car.

**Guard rails.** Settings that would refuse most or all cars can no longer be saved
(Site Server and the calibration window's spin boxes both enforce it):
brightness to ≥ 150, brightness from ≤ 100, glare/black allowed ≥ 0.20, detector and
recognition confidence ≤ 0.90, minimum plate ≤ 160 × 40 px on the live picture,
and at least 8 % of the picture between the start and end lines. Values saved before
these limits are not applied (defaults are used) and are listed as ignored in the
calibration window and the Settings → Camera calibration tab, until saved again.

**Warnings.** When a calibrated camera refuses 3 or more cars within 10 minutes and
stores none since, the lane shows a plain warning with the top reasons (Live Gates
pane, calibration window, Settings tab; also `warning` in
`GET /cameras/{id}/calibration` and `calibration_warning` in `/cameras/{id}/plates`).

**Refused car shown, not the old one.** A refused read keeps its picture. For two
minutes, or until a car is stored, the Live Gates pane shows that car's snapshot and
plate crop marked **NOT STORED** with the reason
(`GET /cameras/{id}/calibration/rejected.jpg[?part=crop]`). The kiosk still shows
stored evidence only, because only stored captures create sessions.

**Tests.** `test_settings_that_would_refuse_every_car_cannot_be_saved`,
`test_unsafe_value_saved_before_the_limits_is_ignored_and_reported`,
`test_refused_reads_warn_the_lane_and_show_the_refused_car` (persist_event through to
the warning, refused images and plates payload), and
`test_refused_read_replaces_the_old_stored_car_marked_not_stored` (desktop pane).
