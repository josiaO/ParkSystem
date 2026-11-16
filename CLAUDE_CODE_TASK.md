# SmartPark / Zirp: production-readiness work order

You are working on the parking system. Work through the phases below in order. Each phase ends with a commit that leaves the tests no worse than before it started.

## 1. Product goal (the behaviour every change must preserve)

A parking system for a mall with **two sites ("sides"), each with an entry lane and an exit lane**. The two sites are about 400 m apart. In total: 4 cameras, 4 booms, 2 receipt printers, 2 QR scanners.

- **Entry:** camera captures the plate, FastALPR (or the camera's native read) identifies it, a receipt prints with plate, entry time, entry side and a QR, then the boom opens.
- **Kiosk:** the driver scans the receipt QR and sees what they owe. The first period is free (about 45 min by day, 35 min by night, configurable in the tariff).
- **Mobile payment:** the driver scans the same QR with a phone and pays. The provider webhook updates the shared DB. The webhook is only a hint, and money is credited only after a server-side status check.
- **Exit:** camera reads the plate and the system checks the session. If paid, the boom opens. If not, it stays closed and shows the amount. A QR scanner at the gate is the fallback when OCR fails.
- **Cross-site:** a car may enter at A and leave at B. Sessions are site-wide, and one shared PostgreSQL holds them. Each gate PC (EDGE_NODE) owns its own cameras and hardware, and the Site Server is the parking authority.
- **Principle:** the plate is the identity. Recognition is evidence and never authority to open a barrier.

## 2. Rules of engagement

1. **Verify before you change.** My audit notes below were made by reading code, and some were not run. For each item, reproduce or confirm it first. If it is wrong, say so and skip it.
2. **Do not touch the working camera, recognition, MediaMTX, HVX or gate pipeline** except where a task below names it explicitly. In particular, do not rewrite `tools/hvx_sdk_host/`, `app/services/hvx_client.py` or `app/services/gates.py`. Do not make ONVIF/RTSP the default for HVX sites.
3. **Tests first for bugs.** Write the failing test, then the fix.
4. **Small commits**, one logical change each, with clear messages. Do not push, force-push, rewrite history or delete branches without asking me.
5. **Run the suite after every phase.** Report the pass/fail counts before and after. Never "fix" a test by weakening it. If a test asserts something obsolete, say so and explain.
6. **No secrets in git.** Never print or commit passwords, tokens or `.env` contents.
7. **Ask before** anything that changes the DB schema in a destructive way, removes a feature, or needs a decision about hardware behaviour. Add Alembic migrations for any schema change, and make them reversible where feasible.
8. When unsure whether something is intentional, search `git log -S` and the tests before deciding.

## 3. Phase 0: repair the repository (do this first, it blocks everything)

**Finding:** commit `2ffb14f` split `app/models.py` into a package `app/models/`. `.gitignore` contains a bare `models/` line (intended for FastALPR model files) which also ignores `app/models/`. So the package is untracked, and `app/models.py` in git is a 5-line stub. A fresh clone fails with `ImportError: cannot import name 'AccessPlan' from 'app.models'`. CI has been failing since that commit.

Tasks:
1. Confirm with `git check-ignore -v app/models/__init__.py` and `git status --ignored`. Check whether any other tracked-in-spirit directory is swallowed by `.gitignore`.
2. Change the pattern to anchored forms (for example `/models/` and `*.onnx`) so only the root FastALPR cache is ignored.
3. `git add app/models` and check the diff is the real package. Confirm no `__pycache__` or model binaries are added.
4. Prove it: clone the repo into a temp directory and run `python -c "import app.api_main"` and the test suite there.
5. Add a CI job that does a clean checkout and runs the import check before the tests. Also add a `windows-latest` job running at least import, compile and a fast test subset.
6. Remove committed junk: `:memory:.ses`, the duplicate `ParkWatchreverse-engineering.txt.md`, and any committed `__pycache__` or `.pyc`.

**Acceptance:** a fresh clone imports and the suite runs there. Report the numbers.

## 4. Phase 1: security fixes

Verify each, then fix with tests.

1. **`GET /auth/setup` leaks the admin password and user list** (`app/services/bootstrap.py`, `setup_status`). It is unauthenticated and returns `password` and `usernames`. Return the bootstrap password only to a loopback client during the first-run window, and only in the response that created it. Never return `usernames`.
2. **Default password strings.** `SmartPark1!` still appears in `scripts/Start-SmartPark.ps1` (it prints it), `tools/field_acceptance_test.py` and `tools/camera_lab.py`. Remove the print, and make the tools read the password from an env var or a prompt.
3. **No login throttling** on `/auth/login` and `/auth/token`. Add a per-IP and per-username limiter with backoff and a short lockout. Reuse the limiter in `app/services/public_ingress.py` if it fits, and add tests.
4. **Rate limits on the public payment surface:** `/p/*`, `/api/public/payment-intents`, `/api/public/payment-status/*`. Add a per-phone cooldown on payment prompts so nobody can spam arbitrary numbers.
5. **Session tokens in `?access_token=`** (`app/security.py`, `current_user`). Restrict query-token auth to the media endpoints that need it (`media_user`), and prefer short-lived media tokens.
6. **Camera passwords** default to the plaintext `db` secrets backend on non-Windows (`app/infrastructure/secrets`). Default to `file` (0600) or warn loudly. Keep DPAPI on Windows.
7. **`verify=False`** in `app/services/http_snapshot.py:53`. Make it a per-camera opt-in setting, not the blanket behaviour.
8. **Public receipt page** exposes the plate and the entry photo to anyone with the token. Make the photo opt-in or blurred, and keep the token at 256-bit.

## 5. Phase 2: correctness bugs that can strand paying drivers

1. **Stuck exit barrier.** In `app/application/exit_lane.py`, `_open_authorized` claims `exit_open_command_uuid` before commanding the boom. If the opener fails (`gate_unavailable`), the claim is never cleared, so every retry, including the QR fallback, returns `gate_command_in_progress`. Verify with a test where the opener fails once and then succeeds. Fix by releasing the claim (compare-and-clear on the same `command_uuid`) in the failure branch. Check for any other path that can leave the claim set.
2. **Tariff timezone.** `app/services/fee_engine.py` only converts to local time if `rules["timezone"]` exists. Default Car1 rules have none, and `site_timezone` defaults to `"UTC"`. Day is 05:05 to 23:05, so day/night boundaries are probably 3 hours wrong at a Tanzanian site. Confirm what a live tariff row contains. Fix: use `settings.site_timezone` as the fallback in `load_active_rules`, default new installs to `Africa/Dar_es_Salaam`, ask for the timezone in the setup wizard, and ensure `tzdata` is in the Windows requirements. Add tests with entry/exit across the boundary.
3. **Kiosk session expiry.** User sessions last 12 h (`create_session`), and kiosk payment needs a signed-in user. Give kiosks a revocable device credential (model it on the node credential) so they do not log out mid-shift.
4. **QR exit vs camera plate.** A receipt QR exit does not cross-check the camera's plate read. When both exist and disagree, record a mismatch flag and show it to the operator. Do not auto-deny.
5. **Near-match on exit.** Exit matching is exact. When there is no exact session but a close one exists (the plate similarity helper already exists in `app/core/plate.py`), show the operator a "did you mean" prompt. Never auto-open on a fuzzy match.
6. **Clock skew between PCs.** `/node/heartbeat` returns `server_time`. Compute skew on the node, warn above about 2 s, and show it in System Health. Entry/exit times should come from one authority where possible.

## 6. Phase 3: Windows supervision (power-cut recovery)

**Finding:** services run as Scheduled Tasks with an AtLogOn trigger, `RestartCount 3`, and an interactive account (`packaging/windows/Install-SmartParkServices.ps1`). `nssm.exe` is not in the kit, so the SCM installer is a no-op. After a power cut at night with nobody logged in, the gates stay down.

Tasks:
1. Bundle NSSM (or WinSW) in the kit with its license in `packaging/licenses`. Make real Windows services the default for Site Service, recognition worker, MediaMTX and the HVX host. They must auto-start at boot with no user logged in, restart indefinitely with backoff, write logs to files with rotation, and start in dependency order.
2. Check what each service needs from an interactive desktop. The HVX host uses a hidden message-pumped window, so confirm whether it works as a service or needs a different arrangement. If it cannot, document the limit and offer an auto-logon plus Startup fallback. Do not guess: test or ask me.
3. Add a **pipeline watchdog**: a check that goes beyond "process alive" and verifies that a camera produced a fresh frame, the DB answers, and the gate controller responds. On failure, restart the right component and write an event.
4. Add a reboot test script (`tools/`): kill power-equivalent (restart), do not log in, assert health endpoints go green within N minutes.

## 7. Phase 4: recognition path (measure first)

**Context:** the worker reads the local MediaMTX DETECT path with FFmpeg, scales to 960 px wide, encodes JPEG (`-q:v 8`), then decodes it again for OCR (`app/services/recognition_decoder.py`). The DETECT role may fall back to the substream (`rtsp_role(ROLE_DETECT, sub or live)` in `app/services/mediamtx_sources.py`). The region of interest is applied after the downscale. The default minimum plate width is 64 px (`alpr_min_capture_plate_width_px`).

1. **Measure before changing.** Write a tool that replays recorded gate footage per camera (extend `tools/camera_lab_replay.py`) and reports: plate width in pixels at the OCR input, read rate, and character accuracy. Ask me for the footage location if it is not in the repo.
2. If plates are under the minimum width at real gate distance, crop the region in FFmpeg before scaling, or raise the detect resolution, or send raw frames. Make it a per-camera setting, and keep the display stream untouched.
3. **Frame age and epoch.** Verify that frames carry a monotonic capture time and that results older than the current vehicle epoch are dropped. Expose per camera: frame age at consumption, buffer depth, decoder restarts, OCR milliseconds, drops. Alarm if frame age is over 300 ms or decoder restarts are not near zero.
4. **ONNX threads.** Check that `recognition_model_threads` is capped sensibly for 4 cameras on the actual PC, and consider a GPU provider only if measurements show the CPU is the limit.
5. Keep the native HVX plate callback independent from video, and keep fusion as is.

## 8. Phase 5: two-gate resilience (small, safe steps only)

Do **not** build offline session sync or UUID session IDs yet. Do these:

1. PostgreSQL connection settings for edge nodes: `connect_timeout`, `statement_timeout`, TCP keepalives, optional `sslmode`, and a short pool timeout so a dead link fails fast instead of hanging a lane.
2. A visible **"server link down"** state in the operator UI and lane status, with a clear fallback message (use the QR and call an operator). The lane must never hang silently.
3. Test the failure: simulate a dropped DB and a slow DB on an edge node, and show the lane stays responsive and reports state.
4. Write a short design note (`docs/OFFLINE-OPTIONS.md`) comparing a read replica at gate B for paid-status checks versus an outbox with UUID sessions. Do not implement either.

## 9. Phase 6: tests, docs and structure

1. Commit `README.md` and the runbooks that were deleted in `8a29f85` ("removed docs"), or update the tests that assert they exist. Tests currently asserting docs: `test_required_docs_exist`, `test_ui_docs_exist`, `test_module_docs_tree`. Technicians need DATABASE_CONFIGURATION, DEPLOYMENT, LANE-DEPLOYMENT, CAMERA-TROUBLESHOOTING and the PostgreSQL prerequisite at minimum.
2. Triage the failing tests (about 20 in my trial run, using an older `models.py` as a stand-in, so recheck after Phase 0). Groups: media registry and telemetry, hybrid fusion (2), node scope, Windows production discovery and packaging, `NullPool` check, stability metrics. For each: real bug, obsolete test, or environment issue. Fix real bugs, update obsolete tests with an explanation, and skip environment-only tests with a clear marker and reason.
3. Remove the 13 committed decompiled vendor files under `research/` (`*.decompiled.c`, `*.named.c`) from the working tree. Ask me whether to purge them from history, since that rewrites history.
4. **Replace `exec`-loaded parts.** `app/api/runtime.py` loads `app/api/runtime_parts/*.py` with `exec(compile(...))` into one namespace. Convert them into ordinary modules and FastAPI routers, one part at a time, keeping behaviour identical and tests green after each. Check whether `app/recognition_worker/` and other packages use the same loader and treat them the same way.
5. Split `requirements.txt` into runtime and dev, keeping the pinned file as a lockfile.
6. Add `ruff` (and `mypy` on the domain and application layers) to CI, non-blocking at first.
7. Add a 72-hour soak procedure and script (`tools/`): 4 cameras, tracking memory growth, decoder restarts, frame age, and gate command latency. Do not run it here. Produce the script and instructions.

## 10. Things that are good, so leave them alone

- The exit/entry controllers' idempotency and atomic command claiming, and the lifecycle state machine in `app/domain/parking_engine.py`.
- Webhook verification (constant-time HMAC) and "webhook is a hint, verify server-side" payment flow.
- Public-ingress path whitelist, Argon2 passwords, hashed session tokens, per-node revocable credentials, secrets kept out of `deployment.json`.
- The 32-bit HVX host as an isolated sidecar, the MediaMTX single source owner, bounded latest-frame buffers with generation checks, and the Site Server / Operator Workstation / Edge Node roles.

## 11. How to report

At the end of each phase, reply with:
- what changed (files, one line each) and the commit hashes,
- tests before and after (passed/failed/skipped),
- anything you verified as wrong or already fixed,
- decisions you need from me, listed as numbered questions.

Stop and ask if you hit anything that touches live hardware behaviour, a destructive migration, or a history rewrite. Begin with Phase 0.
