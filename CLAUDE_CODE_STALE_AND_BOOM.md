# Task: find and fix stale camera display, stale recognition, and slow boom opening

You are working on the local checkout of `josiaO/ParkSystem` (SmartPark / Zirp). Read this whole file before acting.

## 1. How we work (this changes what you can and cannot do)

- **I develop on Ubuntu with you.** You can edit, run unit tests and run anything that does not need the hardware.
- **I test on a separate Windows PC** that has the real ALPR cameras (HVX/QY family) and working boom barriers. The camera vendor SDK is 32-bit Windows-only DLLs, so **you cannot run the camera host or any hardware path on Ubuntu**.
- Therefore every hardware claim must be settled by a script I run on Windows. For each experiment you must:
  1. write a small script (PowerShell or Python 3.11 32-bit for the host side) that needs no editing,
  2. make it write its results to one file (JSON or CSV) in a known folder,
  3. write the exact commands and "what to send back" into `docs/WINDOWS-TEST-PROTOCOL.md`,
  4. then **stop and wait** for me to run it. Do not guess results, and do not claim a fix works until I report data from Windows.
- Anything you can test on Ubuntu (logic, queues, timing code, report tools) must be tested there, using a fake SDK or recorded data. If no fake HVX SDK exists, create one under `tests/` with deterministic frame timing and failure injection.
- I move code between machines with git. Do not push, force-push or rewrite history without asking.

## 2. Symptoms I observe on the Windows rig

1. The **camera live display goes stale** (frozen or lagging picture).
2. **Some cars get stale recognition**: a result that looks like it belongs to an earlier moment or an earlier car.
3. After the system sends the open signal, the **boom takes a few seconds to open**.

I am considering replacing the 32-bit Python camera host (`tools/hvx_sdk_host/hvx_host.py`) with C# or C++. **I have not proven that the host is the cause.** Your job is to find out first, fix the cheap causes, and only recommend a rewrite if the data supports it.

## 3. What the code looks like today (verify, don't trust)

- The 32-bit host `tools/hvx_sdk_host/hvx_host.py` (about 390 lines, standard library plus `ctypes`) listens on `127.0.0.1:8765`. It serves live JPEGs (`/live-jpeg/<handle>` with a long-poll `wait_ms` and `after_seq`), event JPEGs and plate crops (`/event-jpeg`, `/event-crop` with `capture_token`), GPIO (`/gpio/pulse`, `/gpio/write`), and status. It uses a bounded thread pool and a request-slot semaphore.
- The **boom is opened through the same host**: `app/services/gates.py` calls `app/services/hvx_client.py:gpio_pulse`, which POSTs `/gpio/pulse` to the host, which calls the SDK to pulse the camera's GPIO relay. `gpio_pulse_ms` defaults to 500 and `gate_command_timeout_seconds` to 3.0.
- So **live video, plate events and the boom command all share one 32-bit Python process, one HTTP server and one SDK instance.** This is a plausible common cause for symptoms 1 and 3, but that is only a hypothesis.
- Recent commits mention stale-replay fixes (`2ca77da Prevent QY stale replay and dead recovery pumps`, `4277298 corrected Excessive JPEG sampling and repeated decoder restarts`). Read them first so you do not redo that work.
- The recognition worker reads the MediaMTX DETECT path with FFmpeg (scale to 960 wide, JPEG, decode again) and also receives native plate events with a `capture_token`.
- Prior audit note: gate open must stay idempotent. Also, `exit_open_command_uuid` is never cleared when the barrier command fails (`app/application/exit_lane.py`). That bug is tracked separately, so only touch it if it affects this work.

## 4. Ranked hypotheses to test

| # | Hypothesis | Affects |
|---|---|---|
| H1 | Control calls (`/gpio/pulse`) queue behind long-poll frame requests, so the bounded pool or slots are saturated and the pulse waits or is retried | boom |
| H2 | The SDK frame callback does too much work (copy, JPEG encode, locking) on the vendor thread, so frames back up or the GIL is held | display, recognition |
| H3 | Display falls back to the slow capture mode (`capture_mode=play_sdk_hwnd`, PrintWindow/BitBlt) instead of `sdk_draw_data` | display |
| H4 | The decision path waits before opening: fusion/consensus timeout, grace windows, printer or entry-claim waits | boom |
| H5 | The camera's relay or the boom controller itself has an intrinsic delay (not software) | boom |
| H6 | A consumer (worker, UI, browser, MediaMTX) reads an old frame: unbounded queue, reused `capture_token`, a replayed event, or an old image attached to a new car | display, recognition |
| H7 | CPU or disk starvation on the Windows PC (ONNX, FFmpeg, antivirus, logging) | all |
| H8 | Python/GIL stalls inside the 32-bit host | all |

Do not assume any of these. Instrument and measure.

## 5. Phase A: instrument end to end (Ubuntu work, then I run it on Windows)

1. Add a **trace id** and **monotonic timestamps** (`time.monotonic_ns()` plus a wall-clock for correlation) at every stage, logged as one JSON line per event to `logs/latency-trace.jsonl` with rotation:
   - camera frame: SDK callback received, frame stored, frame served by the host, frame received by the worker or UI
   - recognition: native plate event received, worker OCR start/end, fusion decided, decision made
   - gate: command created, HTTP request sent, host request received, SDK call start, SDK call returned, HTTP response received
2. Record, per decision, **frame age at decision** (decision time minus the capture time of the frame or event used) and the `capture_token`/frame sequence used. Flag any decision using a frame older than a configurable limit (default 500 ms for frames, 2 s for native events).
3. Add host self-metrics at `/metrics` or in `/video-status`: request queue depth, rejected requests (slot semaphore), p50/p95 handler time per endpoint, callback duration, **event-loop/thread lag** (a heartbeat thread measuring scheduling delay), frames received, frames dropped, current `capture_mode`.
4. Write `tools/latency_report.py` that reads the JSONL and prints, per stage and per camera: count, p50, p95, p99, max, and the worst 10 events with their full trace. It must run on Ubuntu against sample data.
5. Write `tools/windows/Run-LatencyCapture.ps1` (no edits needed) that starts a timed capture, runs a scripted sequence (N open commands spaced apart, with live viewers connected, and then with viewers disconnected), and saves the files into one folder I can zip and send back.
6. Add a `--fake-sdk` mode so the same instrumentation runs on Ubuntu in tests.

## 6. Phase B: measure the boom physically

Software timestamps stop at "SDK returned", not at "boom moved". In the Windows protocol, include a method I can do with a phone: record slow-motion video with a visible clock or a clap/LED marker at the moment of the command, and note when the boom starts moving. Also document how to read the camera's GPIO input state if the SDK allows, so one log line can mark the relay edge. Ask me which of these I can do. The comparison tells us how much of the "few seconds" is software (H1, H4) and how much is hardware (H5).

## 7. Phase C: cheap fixes in the current Python host (only after Phase A data)

Apply only what the data supports, one commit per fix, each with a test:

- Give **control endpoints their own lane**: a separate small thread pool or a second listener port for `/gpio/*`, `/health`, `/video-status`, so frame long-polls can never delay a boom command. Cap `wait_ms` and the number of concurrent live viewers per camera.
- Keep the SDK callback minimal: copy or hand off the buffer and return. Encode JPEG off the callback thread, and keep one bounded latest-frame slot per camera (drop old, never queue).
- If `capture_mode` falls back to `play_sdk_hwnd`, find out why and fix or flag it loudly in the UI.
- Use a pooled HTTP client in `hvx_client.py` instead of creating one per call, and add a hard deadline with a clear error.
- Make sure display consumers cannot receive an old frame: sequence numbers must be monotonic and a repeated sequence must not be shown as new.
- For recognition: bind each decision to the exact `capture_token` and frame sequence, reject a native event or image older than the limit, and prevent an old image being attached to a new car (generation/epoch check). Add regression tests with injected delays.
- Do not add a sleep or a retry that hides delay. If the decision path waits on purpose (H4), make each wait explicit, configurable and logged.

## 8. Phase D: decision gate, a report before any rewrite

After I send back Windows data, write `docs/HVX-HOST-DECISION.md` with:
- the measured contribution of each stage to display staleness, recognition staleness and boom delay,
- which hypotheses are confirmed or rejected, with numbers,
- the fixes applied and the before/after,
- a **clear recommendation**: stay on Python, or build a native host. Recommend a rewrite only if, after Phase C, the data still shows the host process itself as the bottleneck (for example, GIL or scheduling stalls that cannot be fixed inside Python, or callback time that cannot be reduced).

If, and only if, I approve a rewrite:
- Build a **C# (.NET, x86, self-contained single file) host** in `tools/hvx_sdk_host_dotnet/`. It is easier to keep stable than C++ for this job. It must keep the **exact same HTTP contract** as the Python host, so nothing else in the app changes, and it must be selectable by a setting with the Python host remaining the default until my Windows A/B tests prove it better.
- You can build it on Ubuntu with `dotnet publish -r win-x86`, but **you cannot run it against the real SDK**, so write a contract-test suite that runs against both hosts (the fake SDK for Python, a stub for C#) and a Windows protocol for the real run.
- Take the SDK call signatures, calling conventions and struct layouts from the existing `hvx_host.py`/`hvx_sdk.py` and from `research/` notes. Do not invent them. Pin delegates so the garbage collector cannot free callbacks. Ask me if a signature is unclear.
- Ask me for the Windows version on the test PC and on the site PCs before choosing the .NET version.

## 9. Rules

1. Do not rewrite the recognition pipeline, MediaMTX setup, fusion logic or payment code. Do not make ONVIF/RTSP the default for HVX sites.
2. Tests first for bugs. Run the full suite after each phase and report before/after counts. Never weaken a test to make it pass.
3. Small commits with clear messages. No secrets in git. Do not print camera passwords.
4. If the repo does not import on a fresh clone (the `.gitignore` `models/` line ignoring `app/models/`), fix that first, as in `CLAUDE_CODE_TASK.md` Phase 0.
5. Ask before schema changes, history rewrites, or anything that changes live hardware behaviour. Keep the boom command idempotent and never open on a stale or uncertain match.
6. When blocked on Windows data, stop and tell me exactly which script to run.

## 10. Reporting

After each phase reply with: what changed (files, one line each) and commit hashes; tests before and after; the exact Windows commands for me to run and what to send back; open questions as a numbered list. Begin with Phase A.
