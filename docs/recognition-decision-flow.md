# From camera to stored read: every decision, when and why

This is the path a car takes through Zirp, from the camera's picture to a
stored read and a parking decision. Each step says what decides, when, and
where the code is. Measurements come from one live site with four QY HVX
plate cameras (two entry, two exit) running Zirp in shadow mode.

## 1. The camera

The QY camera does three things for Zirp:

* **Live video.** The camera host (`tools/hvx_sdk_host`) decodes the camera's
  sub-stream (704 × 576) through the vendor SDK into JPEG frames. MediaMTX is
  not used for these cameras. The live picture on Live Gates and Zirp's own
  trigger both use these frames.
* **Snapshots.** When the camera is triggered, by its own video detector, by
  another parking system's I/O, or by Zirp (`/snapshot-trigger`), it sends
  one image callback: a 1920 × 1080 picture, a second "vehicle picture",
  its own plate text, score and plate rectangle, a vehicle id and a snapshot
  index (`_on_image_inner`, `hvx_sdk_parts/20_connection.py`).
* **Its own calibration.** OcxConfig stores a four-corner plate recognition
  area, a "best pixel" stop line, a capture mode, plate widths (80–400 px) and
  capture intervals. Zirp reads these (`query_video_detect`) and never writes
  them.

What we measured: the camera's own plate reader is set to Chinese plates
(default province "all of China"). Over 67 hours it read **no** plate: every
callback said "no plate", with an empty rectangle and the same small
placeholder "vehicle picture" on all four cameras. So the camera is a picture
source and a trigger; Zirp reads every plate. The camera's recognition area
ends above the plate of a car that pulls up close, which is why searching
only inside it is **off** by default (Settings → Recognition).

## 2. Who triggers the picture

Settings → Recognition → **Who triggers the pictures**:

| Choice | What happens |
|---|---|
| external | Only the camera's own or another system's triggers make pictures. Zirp reads them. |
| zirp | Zirp watches the live video and commands the camera's snapshot. |
| both | Both. One car can then give several pictures. |

**Zirp's trigger** (`_video_arrival_ready`, `05_recognition_ingest.py`;
`CaptureGate.observe`, `capture_calibration.py`):

1. Every sampled live frame (4 a second per camera): a tiny thumbnail of
   the lane (the calibration zone, extended towards where cars come from) is
   compared with the previous one (`motion_gate.py`). The plate detector
   (~80-90 ms of CPU) runs only when the lane moved, a plate was seen in the
   last 3 s, or 2 s passed; Settings → Recognition can switch this off.
   When it runs, it searches the whole picture,
   and each plate box is judged against the camera's calibration
   (`capture_calibration.evaluate_frame`). The gate tracks where the nearest
   plate is from frame to frame, and keeps the last frame whose plate the
   calibration accepts.
2. With `zirp`/`both`, the read is the camera's full-resolution snapshot,
   which the camera takes some time after it is asked (0.32–0.75 s, median
   0.57 s, measured; learned per camera from every snapshot that comes back,
   `zirp_trigger.lead_seconds`). So the gate fires **early by that delay**:
   as soon as the plate is inside the calibration, or the plate's track says
   it will be when the snapshot is taken (aimed 0.2 s short of the delay, so
   an early snapshot still finds it inside). A plate that has stopped before
   the zone never fires.
3. The snapshot comes back through the normal camera-picture path (sections
   3–7): detect, calibration, crop at full resolution, OCR. It is matched to
   Zirp's request (`zirp_trigger.claim`).
4. If that snapshot has no plate, or its plate is outside the calibration, or
   no snapshot arrives within 1.5 s, the last live frame whose plate was
   inside the calibration is read instead (`_zirp_snapshot_missed`): a smaller
   crop (704 px sub-stream), but the right moment. With no such frame the gate
   may fire once more; it allows two tries per car.
5. Without Zirp's trigger (`external`), the gate collects in-zone live frames
   for up to 3 frames or 0.8 s and reads the best one itself.

## 3. One camera picture: find the plate

`_drain_camera_events` (`05_recognition_ingest.py`), per picture:

1. Fetch the snapshot. The camera's "vehicle picture" is dropped when the
   camera says "no plate".
2. The camera sent no plate rectangle, so Zirp's detector runs on the whole
   snapshot (`locate_plate_boxes`). Boxes below the detector floor
   (`alpr_detector_confidence`, 0.26) or not plate-shaped (`plate_box_ok`:
   size, and width/height between 1.0 and 8.0) are dropped. Two-line plates
   are about 1.1 wide per 1 tall.
3. No box → outcome `no_plate_box`, picture kept under `media/misses`. On the
   site, 80% of these pictures had no plate at all: the camera snapped after
   the car had passed or while it waited beyond the camera.
4. The boxes go through the calibration (`plates_to_read`). Only a plate the
   calibration accepts is boxed and cropped on the live view.

## 4. The calibration decides which plate may be read

`capture_calibration.evaluate_frame`, applied **before** OCR and again before
storing (`check_capture`):

| Rule | A plate is refused when… |
|---|---|
| Capture zone | its centre is outside the zone, off to the side (another lane, a parked car) |
| Zone: not there yet | it is still approaching the zone (off: the start line decides) |
| Zone: already through | it has driven past the zone (off: the end line decides) |
| Start line | it is inside the zone but not yet past the start line |
| End line | it is inside the zone but past the end line |
| Minimum plate size | it is narrower or shorter than set (on the calibrated picture's scale) |
| Detector confidence | the detector is less sure than set |
| Picture quality | the crop is too blurred, dark, bright or clipped |
| Recognition confidence | the OCR result is less sure than set (after reading) |

A rule that is switched off never refuses, but still ranks frames. Before the
two zone switches existed, a plate still **above** the zone was always a
start-line question, so with the start line off it was read; on one entry
lane 74 of 113 stored reads had the plate above the zone. Both switches are on
by default; switching "not there yet" off brings that behaviour back.

If every plate is refused, nothing is read: outcome `calibration_refused`,
and Live Gates shows **NOT STORED** with the reason.

## 5. The read budget decides whether to read at all

`read_budget.allow` (`02_camera_recognition.py`): one read per car, a second
only when the first was below `read_budget_confident` (0.90). "The car" is
the stream of pictures until the lane has been quiet for
`read_budget_quiet_seconds` (4 s), at most `read_budget_max_seconds` (20 s).
A picture with no plate does not count and does not extend the quiet window.

Measured: the cameras re-snap a waiting car every 4–6 s, so the quiet window
runs out and the car is read again. 75% of same-car re-reads came 4–20 s
after the previous one; each car was stored about twice.

## 6. Crop and OCR

`recognize_arrival_bytes` → `_hits_from_detections` (`app/services/alpr`):

1. The best remaining box (detector confidence, then size) is cropped from the
   **full-resolution** snapshot with 18% padding.
2. The crop is rectified (perspective) when a plate quadrilateral is found,
   upscaled to 320 px wide, and enhanced in low light.
3. OCR (fast-plate-ocr). A weak or rejected result is retried once on the
   enhanced crop; a rejected rectified crop falls back to the plain crop.
4. The text goes through the country profile (Settings → Site → Plate
   validation; Tanzania fixes digit/letter positions) and `accept_ocr_plate`:
   at least 5 characters, not empty-scene text, a likely plate for the site's
   plate rule, and at least `alpr_min_ocr_confidence` (0.40; 0.28 for a
   plate-shaped result).

Clear plates read at 0.99–1.00. Bad reads come from the picture (plate too
far, blurred, cut off, or not there), not from the crop.

## 7. Storing the read and the parking decision

`_persist_capture_event` (`05_scope.py`) → `persist_event`
(`captures/30_repository.py`):

1. A clearly different plate on the same visit is a new car (new visit).
2. The same car read again: the better read wins (`visit_reads`); two reads
   that disagree by a character can change the stored plate
   ("plate corrected").
3. Final checks: the calibration again (`check_capture`), plate shape,
   the site's plate rule (a doubtful plate is held for an operator).
4. The parking controller decides: new session, same stay, payment due, or
   no session at the exit.

## Where the time and the misses go (measured)

| Finding | Effect | Status |
|---|---|---|
| Plates above the zone were read | early reads, wrong frame | fixed: zone refuses them (per-camera switch, on by default) |
| Two-line plates dropped as "not plate-shaped" | readable plates missed | fixed |
| Camera-area search (when on) dropped plates of close cars | readable plates missed | off by default, a setting |
| Calibration refusals counted as "no plate" | refusals hidden | fixed: `calibration_refused` |
| Zirp's snapshot arrives ~0.57 s after firing, after a 0.8 s window | picture taken after the plate moved | fixed: fires early by the learned delay; falls back to the in-zone live frame |
| Waiting car re-read when the 4 s quiet window ends | ~2 stored reads per car | open |
| Database work on the event loop (up to 2.5 s) | live video hitches | open |
| Detector ran 16 times a second on empty lanes (~1.4 cores) | Site Service ~1.7 cores | fixed: runs only when the lane moves (~30% of samples measured) |
| Two database reads and a camera-host call every 0.25 s per camera | load on the LAN database and the host | fixed: cached camera row; read only when the gate fires |

## Settings: one place each

Values shown on a settings screen live in the site database. `zirp.env`
holds install values and secrets only. At startup the Site Service moves any
line for an on-screen setting out of `zirp.env` into the site settings
(keeping a value already saved on screen) and removes the line
(`runtime_settings.adopt_env_file`; the old file is kept as `zirp.env.bak`).
`SMARTPARK_ALPR_COUNTRY` becomes Settings → Site → Plate validation.
