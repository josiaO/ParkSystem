# SmartPark streaming baseline

Date: 2026-11-03 (Africa/Dar_es_Salaam)

This baseline is intentionally split between software-only evidence and
measurements that require the installed Windows cameras. No camera-to-screen
latency or ALPR accuracy claim is inferred from local buffer age.

## Software baseline

The current software path has these bounded defaults:

| Metric | Current default / observable field |
|---|---|
| LIVE buffer | one latest frame per camera (`StreamSession.live`) |
| DETECT buffer | one latest frame per camera (`StreamSession.detect`) |
| Recognition mailbox | one latest frame per camera (`CameraRecognitionLane.mailbox`) |
| Worker model concurrency | `settings.recognition_max_concurrency`, default 4; one in-flight lane per camera |
| Worker sampling | `SMARTPARK_RECOGNITION_SAMPLE_FPS`, default configured in settings; admission drops stale frames |
| Stale admission limit | `settings.recognition_stale_frame_ms` |
| Media reconnect | per-camera circuit with exponential backoff and jitter |
| Media generation | increments on decoder recovery; old buffers, preview state, and late publishes are invalidated |
| Event idempotency | event ID, visit ID, capture identity, parking entry claim, and database uniqueness |

The following fields are exposed by `/media/gateway`, `/health/details`, and
the camera lab: source/decoded/display/inference counts, frame age, interval
percentiles, queue depth, dropped frames, codec/resolution, decoder PIDs,
reconnects, decoder restarts, recognition ownership, worker state, and native
callback/JPEG telemetry when the SDK host supplies it.

## Reproducible software checks

Run from the repository root:

```text
.venv/bin/python -m compileall app tools
.venv/bin/python -m pytest -q
.venv/bin/python -m tools.camera_lab --camera <id> --duration 60 --recognition --latency
.venv/bin/python -m tools.camera_lab_replay benchmark <recorded-video> --duration 300 --recognition --output baseline.json
```

The first two commands are regression checks. The camera-lab commands are
measurements and must be run on the Windows target with the real deployment
profile. A replay result must include labeled vehicle passages to calculate
precision, recall, missed-vehicle rate, and duplicate-session rate.

## Measurement record

| Measurement | Result | Status |
|---|---|---|
| Focused streaming/recognition regression suite | 67 passed, 1 warning in 6.06 s (`tests/test_realtime_field_failures.py`, `tests/test_media_acquisition.py`, `tests/test_media_gateway.py`, `tests/test_production_stabilization.py`) | Software-only |
| Full repository regression suite | Began successfully; local run was interrupted after 109 tests while the first parametrized camera-diagnostics test stalled during setup; cause not established | Must be rerun in CI/Windows-like environment before release |
| Synthetic bounded-buffer and stale-result checks | Covered by automated tests | Software-only |
| Source codec/FPS per installed camera | Not available in this environment | Windows field measurement required |
| Camera-to-screen p95 | Not measured; local frame age is insufficient | Physical LED/timestamp procedure required |
| Recognition admission/completion latency | Instrumented, no field sample attached | Windows replay/field sample required |
| Precision/recall/missed vehicles | No labeled field dataset supplied | Labeled replay required |
| Duplicate sessions | Regression tests exercise idempotency; no field rate claimed | Field soak required |
| 24-hour soak | Not run | Acceptance gate |

## Performance interpretation

The target values in `CODEX ENGINEERING TASK.md` are acceptance targets, not
results. Report p50/p95/max, sample counts, and the source of each timestamp.
If a camera has no synchronized clock, label camera-to-screen latency as
**unverified** and use the LED/visible-timestamp procedure instead.

