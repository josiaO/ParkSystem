# SmartPark streaming and ALPR audit

Status: implementation audit for the current worktree. This document records
what is established by source inspection and automated tests, and what still
requires Windows hardware evidence. It is not a production-readiness claim.

## Runtime execution chain

| Source | Physical stream owner | LIVE consumer | DETECT/ALPR consumer | Evidence/event path |
|---|---|---|---|---|
| QY/HVX vendor camera | 32-bit `tools/hvx_sdk_host` through `HVXHostClient`; the Site Service owns one per-camera media session | `app/services/media_gateway.py::_sdk_frames`, then the bounded preview cache | Native callback stays in Site Service; software verification uses the configured worker/legacy owner | `app/api_main.py` native event drain → `app/services/captures.py::persist_event` → parking application |
| Generic RTSP | MediaMTX in the production profile; development/commissioning may use the bounded direct compatibility lane | Production uses MediaMTX WHEP/MJPEG; the direct gateway producer is not admitted in production | `app/services/recognition_decoder.py` reads the local MediaMTX DETECT path; `app/recognition_worker.py` owns model admission | worker outbox → Site Service fusion/persistence → parking application |
| ONVIF profile | ONVIF is discovery/configuration; the selected RTSP profile follows the generic RTSP path | Same as generic RTSP | Same as generic RTSP | Same normalized event path |
| Simulated/recorded | Test source or MediaMTX virtual camera | Same bounded LIVE path | Same DETECT path or replay harness | Test event path only; field commands are not issued |

The operator desktop reads `/cameras/{id}/live.mjpeg` and uses generation
checks in `app/desktop/live_pane.py`. The browser WHEP path is selected by
`app/infrastructure/media/registry.py`; it does not open a second vendor SDK
reader.

## Confirmed failure mechanisms and controls

| Area | Failure mechanism found during audit | Control now present | Evidence |
|---|---|---|---|
| Competing acquisition | SDK cameras could be misclassified before a native handle existed, allowing a generic reader to be selected | Adapter identity is checked before handle availability; native adapters never enter RTSP/HTTP acquisition | `tests/test_media_acquisition.py`, `tests/test_camera_delivery_diagnostics.py` |
| QY commissioning fallback | A reachable QY camera could be reported healthy by an ONVIF/RTSP/HTTP probe even though the runtime must use NetSDK | Vendor-SDK onboarding stops after the vendor probe; explicit `qy` rows cannot be rewritten to RTSP, and native snapshot resolution never falls through to HTTP/RTSP | `app/services/camera_onboard.py`, `app/api_main.py`, `app/services/preview.py`, `tests/test_ipcam_discover.py`, `tests/test_live_view.py` |
| Native scheduler overlap | An unconnected explicit QY row could enter the generic Site Service ALPR scheduler while a later caller used the native lane | The event scheduler and local ALPR helper both exclude explicit native adapters; QY recognition remains in the SDK callback/software-verification lane | `app/api_main.py`, `tests/test_live_view.py`, `tests/test_media_acquisition.py` |
| Unbounded frame growth | A slow display or model consumer can retain every decoded frame | LIVE, DETECT, and worker mailboxes are bounded latest-frame buffers; old frames are counted/dropped | `app/services/latest_frame.py`, `tests/test_media_acquisition.py` |
| Premature OCR / missing arrival point | A broad or implicit zone and the old timed far-plate escape could read a distant moving car before it reached the lane stop point | The effective per-camera/site zone is surfaced consistently; detector boxes are center-filtered; moving and undersized boxes remain detector-only until stable and readable | `app/services/camera_framing.py`, `app/services/alpr.py`, `app/recognition_worker.py`, `tests/test_arrival_framing.py` |
| Display/recognition interference | A display-only LIVE frame could be used as a recognition fallback, or slow consumers could accumulate frames | Automatic recognition admits only DETECT frames; LIVE and DETECT remain separate latest-frame buffers and the worker has its own mailbox | `app/api_main.py::_current_recognition_jpeg`, `app/services/media_gateway.py`, `tests/test_camera_load_regressions.py` |
| Evidence framing | OCR used a zone crop but persisted the full camera frame as the event snapshot | Worker and Site Service persistence now save the configured detection-zone view (with detection zoom); the plate crop still comes from the accepted plate box | `app/services/captures.py`, `app/recognition_worker.py`, `tests/test_arrival_framing.py` |
| Stale inference result | A slow model call can complete after a reconnect or after a newer frame | Per-camera generation, frame sequence, visit ID, and frame-age checks reject the result | `app/services/recognition_runtime.py`, `tests/test_realtime_field_failures.py` |
| Reconnect contamination | A cancelled decoder could return one late frame and repopulate the old preview | Media generations now invalidate the gateway buffers and preview cache; late-generation publishes are rejected | `app/services/media_gateway.py`, `app/services/preview.py`, `tests/test_media_acquisition.py` |
| Previous plate in live UI | A historical plate was separate from current live state only by age | `LaneVisit` controls current plate visibility; departure/EMPTY clears current plate while historical captures remain | `app/services/recognition_runtime.py`, `tests/test_realtime_field_failures.py` |
| Native/software double ownership | Native callbacks and worker results could both reach parking logic | Recognition mode, worker heartbeat, and hybrid fusion select one software owner; paired outcomes are persisted once | `app/services/hybrid_fusion.py`, `app/core/hybrid.py`, `tests/test_hybrid_fusion.py` |
| Duplicate session creation | Retries can occur after a database commit or outbox acknowledgement failure | Event/visit/capture uniqueness, entry claims, parking transaction checks, and durable outbox processed keys | `app/models.py`, `app/services/parking_sessions.py`, `app/services/queues.py`, `tests/test_production_stabilization.py` |
| False recovery | Repeated cached JPEG bytes were treated as source progress | Source sequence is preferred; byte equality does not refresh freshness unless a decoder source sequence advanced | `app/services/media_gateway.py`, `tests/test_media_acquisition.py` |
| Static-scene display stall | The preview cache waited only for a new JPEG sequence, so an unchanged but continuously arriving scene could make the Windows reader hit its no-frame watchdog and reconnect | Transport activity is tracked separately from pixel freshness; `/live.mjpeg` emits a bounded one-second heartbeat without incrementing the display sequence | `app/services/preview.py`, `app/desktop/streams.py`, `tests/test_detection_history.py` |
| Media owner race | A stale direct producer could be returned before the code checked whether MediaMTX was now authoritative; MediaMTX consumers also depended on preview's viewer counter | MediaMTX is checked first, stale direct producers are retired, and the gateway owns the synchronized viewer lease used by live/detect consumers | `app/services/preview.py`, `app/services/mediamtx_live.py`, `app/services/mediamtx_detect.py`, `tests/test_desktop_video_recovery.py` |
| Module coupling | The gateway imported preview and recognition directly during frame publish/reconnect | Optional frame/generation observer hooks let display and recognition subscribe without making the camera engine import them | `app/services/media_gateway/00_context.py`, `app/services/media_gateway/20_frames`, `app/services/media_gateway/10_state.py` |
| Async/event-loop blocking | ONNX and vendor bridge work can block the service loop | Model calls run in worker threads; native reads are isolated behind the host client and bounded waits | `app/infrastructure/recognition/fastalpr.py`, `app/services/hvx_client.py`, `tests/test_recognition_worker_runtime.py` |
| Silent background failure | A diagnostic loop could die while HTTP stayed alive | Lifespan wraps the diagnostic heartbeat in a restart supervisor; health reports camera freshness separately from process readiness | `app/api_main.py`, `app/services/health.py`, `docs/CAMERA-DELIVERY-DIAGNOSTICS.md` |

## Important non-findings

- A connected SDK session is not proof of continuous video. Native callback,
  JPEG production, and display freshness are separate measurements.
- A local buffer age is not camera-to-screen latency. Camera clocks and source
  timestamps are not guaranteed to be synchronized.
- A passing unit test is not proof that the QY DLL family, codec, camera
  firmware, exposure, or Windows desktop session works at a real site.
- Decoder failure is not vehicle departure. Departure is driven by presence or
  detector observations and a bounded absence interval.

## Software verification status

- VERIFIED: native QY/HVX ownership, production generic-camera fail-closed
  policy, bounded LIVE/DETECT/recognition buffers, generation invalidation,
  stale-result rejection, independent camera/display ownership, static-scene
  MJPEG heartbeats, and idempotent event/session paths are covered by source
  inspection and automated regression tests.
- TESTED WITH MOCKS: camera acquisition, reconnect, decoder, multi-camera,
  slow-consumer, UI, and production-configuration paths are covered by the
  repository test suites; the final focused run passed 147 tests with one
  warning.
- NOT TESTED ON HARDWARE: Windows DLL loading, physical camera codecs, real
  MediaMTX ingest, camera-to-screen latency, day/night recognition accuracy,
  recovery on the installed network, and 24-hour soak behavior.
- FAILED: none in the completed focused software verification runs. The full
  repository run reached 210 passes before it was manually stopped because
  the remaining long-running tests had not completed; it is therefore not a
  complete-suite sign-off.

## Remaining field questions

The code cannot establish these from Linux or from a still image: source codec,
camera FPS, camera-to-screen p95, night accuracy, missed-vehicle rate, and
24-hour stability. The field procedure in
`docs/engineering/windows-field-diagnostics.md` is required before accepting
those claims.

