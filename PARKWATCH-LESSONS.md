# ParkWatch lessons applied to SmartPark

The HVX host now checks SDK connection state during background native-event polling, at most once per second. After an observed disconnected/trying state returns to connected, it re-registers the existing report and image callbacks. Initial image-registration failures are retried as well. Retry delays grow from one to eight seconds. Callback objects are retained across re-registration to keep the existing ctypes ABI and references valid.

The SDK state response includes `recognition.ready`, `image_recv_rc`, `retry_pending`, `rearms`, and `last_error`. Ready means the SDK is connected and image registration succeeded; it does not prove a recent vehicle was recognized or measure recognition accuracy. Recognition recovery does not restart the video stream, request a snapshot, or operate a gate. It runs from Site Service event consumption even when the UI is closed. Disconnect marks the recovery session closed before releasing the camera.

The existing one-frame AI mailbox, persistent decoders, separate HVX live pumps, native recognition events, and bounded event queues remain the architecture. Parking rules continue consuming the existing normalized events. No ParkWatch payment rules, country corrections, callback layouts, or relay mappings were copied.

Verification: mocked SDK regression cases cover reconnect recovery, bounded polling, registration retry backoff, stable callback lifetimes, queued-event preservation on SDK errors, and separate connection/recognition health. These tests do not load the Windows DLL. Physical testing must verify recognition after unplug/reconnect, video continuity, callback delivery with the UI closed, and real plate accuracy. Transient disconnects that occur entirely between polls may not be observed; a verified vendor connection callback would be needed to guarantee detection of those transitions without speculative callback bindings.

The existing installer-script and documentation deletions were preserved. The changes do not regenerate or restore those deleted files.

Validation on 7 October 2026: compilation passed; 15 focused HVX tests passed. The full suite completed with 589 passed, 3 subtests passed, and 9 failures, all referencing pre-existing missing documentation or Windows installer source files. The updated host was copied into the existing install folder and USB ZIP; archive integrity, host content, and the payload verifier passed. Other bundled files were preserved, so this was not a complete rebuild from the current source tree.

## Windows installer decoder

The USB kit bundles the Windows x64 FFmpeg 7.1 binary from imageio-ffmpeg 0.6.0, including
licenses and a provenance notice. The build verifies the archive against
a pinned SHA-256 checksum. Recognition and snapshot capture resolve the bundled
`vendor/ffmpeg/bin/ffmpeg.exe` relative to the installed application before trying
PATH on Windows. Linux continues to use its system FFmpeg.

Installer support files deleted from this working tree were recovered from HEAD
only in a temporary staging directory for this build; they must be available to
reproduce the kit. Windows installation and physical camera/printer/gate tests
remain separate acceptance steps.

## Windows field follow-up — 7 October 2026

- Continuous cameras watch a per-camera detection zone, wait for a steady plate
  box, then crop and OCR it. Known boxes are reused instead of detecting twice.
  Native HVX callback crops keep their established event-triggered path.
- Failed OCR retries in bounded bursts with a cooldown; a brief detector miss
  preserves the visit identity so parking's durable visit deduplication applies.
- Live Gates exposes Set detection zone, Detection focus, Save zone, and View
  zoom. Detection focus changes the search crop; View zoom only magnifies the
  operator picture. Neither creates optical detail absent from the source.
- The desktop consumes incoming HTTP chunks immediately and keeps one queued
  display notification. It cannot build an unbounded GUI frame queue.
- Installer requests administrator elevation before changes and fails if
  background task registration fails. Tasks use the full Windows account name.
  Web and desktop shortcuts are supplied; desktop no longer auto-starts at logon.
- OcxConfig contains the 32-bit vendor client/DLLs and binding information, not
  a live export of each camera's codec, bitrate, exposure, FPS, or lens setting.
  SDK ports and verified callbacks/GPIO mappings are unchanged.

Validation on Ubuntu cannot establish Windows Task Scheduler permissions,
real camera stream latency, night plate accuracy, printer output, or barrier
movement. Use a stopped-car test on the Windows installation for acceptance.

## Live recognition follow-up — 8 October 2026

Hardware Lab success with empty Live Gates exposed an acquisition gap: an open
WebRTC viewer could prevent the Site Service from starting its detection
consumer, while native-capable HVX cameras were excluded from the separate
software worker. Software recognition policy now selects HVX cameras as well;
NATIVE_ONLY remains native-only. Detection runs independently of browser frames
and SDK/GPIO polling failures. Accepted in-memory detections produce plate crop
evidence even when debug-image saving is disabled. Healthy empty lanes refresh
the worker heartbeat without running OCR or causing idle restart loops.

Regression tests exercise these paths with synthetic frames and mocked camera
interfaces; they do not establish physical Windows camera performance.

The older Windows screenshot also revealed a desktop shutdown/switch race:
queued frame callbacks could have both sender and current stream set to None.
The slot now ignores an absent sender as well as a replaced stream. A regression
test runs the actual slot for destroyed, replaced and active streams. The font
warning in that screenshot has not been reproduced or attributed to this fault.
