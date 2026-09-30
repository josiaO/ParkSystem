# SmartPark Edge — Stabilization and Production Remediation Prompt

You are the principal engineer responsible for this repository. Do not ask the product owner to choose implementation details that can be decided from engineering evidence. Inspect the repository, current tests, and working hardware seams, make the safest technically sound decisions, implement them incrementally, and prove each change with tests.

## Primary objective

Turn the current SmartPark branch into a smooth, long-running, modular vehicle-intelligence/parking product with reliable camera streaming and strong number-plate recognition, without breaking the working HVX SDK and gate-control implementation.

Do not redesign from scratch. Consolidate the architecture already present.

## Phase 0 — Establish a reproducible baseline

1. Read:
   - README.md
   - ARCHITECTURE.md
   - AGENTS.md
   - docs/COMPREHENSIVE-PROJECT-GUIDE.md
   - docs/MEDIA-ARCHITECTURE.md
   - docs/FASTALPR-PIPELINE.md
   - docs/MIGRATION-AND-ROLLBACK.md
   - FIRST_TEST_WINDOWS.md
2. Run compileall and the entire test suite.
3. Record:
   - failing tests
   - missing imports/files
   - warnings
   - process architecture
   - camera/media code paths
4. Do not proceed by hiding failures. Fix collection/import failures first.

## Phase 1 — Finish the media migration

### 1.1 Single provider seam

Use app/infrastructure/media/registry.py as the only provider-selection boundary.

It must expose at least:
- get_live_endpoint(camera_id, db=None)
- get_detect_endpoint(camera_id, db=None)
- register_camera_source(camera_id, source_config, db=None)
- unregister_camera_source(camera_id)
- mediamtx_live_active(camera_id, db=None)
- mediamtx_detect_active(camera_id, db=None)

DIRECT_LEGACY is fallback only.

### 1.2 Single MediaMTX owner

SmartParkMediaService is the only process that starts/stops MediaMTX.

Site Service must:
- detect MediaMTX health through its local API
- register/reload camera source configuration
- never terminate a MediaMTX process owned by Media Service
- remain functional if MediaMTX is unavailable

Avoid process-local state being mistaken for system-wide service state.

### 1.3 Remove duplicate live transports

Browser:
- When provider=MEDIAMTX and WebRTC is healthy, use WebRTC only.
- Do not run snapshot polling at the same time.
- Snapshot.jpg is for an explicit still/fallback, not continuous video.

PySide desktop:
- Use a continuous MJPEG/WebRTC/native media client, not GET /snapshot.jpg every 40 ms.
- Keep snapshot polling only as a deliberately low-rate compatibility fallback.
- Ensure switching panes/cameras releases previous consumers.

### 1.4 No per-frame FFmpeg spawning

Find every path that starts ffmpeg for a single frame.

Rules:
- live video: persistent decoder or MediaMTX transport
- AI: persistent local RTSP decoder, latest-frame-wins
- explicit one-off snapshot: a one-shot process is acceptable only when no cached/live frame is available
- never spawn ffmpeg repeatedly from a UI timer

Add a regression test ensuring the MediaMTX live UI path does not call continuous snapshot capture.

### 1.5 Process-safe recognition

RecognitionWorker cannot read another process's Python LocalMediaGateway object.

Replace this with an actual IPC/media boundary:
- Recognition Worker consumes MediaMTX local RTSP detect stream directly, OR
- Site Service owns inference until a real worker transport is implemented.

Do not claim process isolation while sharing only process-local Python globals.

For the production target, prefer:
Camera -> MediaMTX -> local detect RTSP -> Recognition Worker -> normalized event.

## Phase 2 — Recognition quality

### 2.1 Recognition provider contract

Keep HVX native and FastALPR providers behind one normalized event contract.

Every recognized event should include:
- event_id
- site_id
- camera_id
- lane_id
- timestamp
- raw plate
- normalized plate
- provider
- confidence
- bounding box when available
- image/crop reference
- country/region only when known
- validation result
- model/provider version when possible

### 2.2 Do not infer on every display frame

For software ALPR:
- detect stream: preferably 3–8 fps configurable
- latest-frame-wins
- stale frames dropped before inference
- no inference backlog
- optional presence/motion/loop trigger should reduce unnecessary inference where reliable
- recognition must continue when no UI viewer exists

### 2.3 Country-neutral core

Refactor Tanzania-specific logic from app/core/plate.py and app/services/captures.py into an explicit country policy.

Create something like:
app/domain/plate_policies/
  base.py
  neutral.py
  tanzania.py

Neutral default:
- uppercase/normalize only according to configured normalization
- no TZ positional substitutions
- no TZ confidence bonus
- no mandatory East-African letter/digit pattern

Tanzania policy may apply:
- T + numeric/letter positional corrections
- local validation patterns
- local confidence heuristics

Only activate it from site policy.

Add tests proving:
- generic international plates are unchanged under neutral policy
- Tanzania correction works only when TZ policy is selected

### 2.4 Consensus and duplicate suppression

Preserve/strengthen temporal consensus:
- same plate across nearby frames raises confidence
- do not create repeated parking events while the same vehicle remains in the trigger zone
- dedupe on event/image/camera/time window
- operator correction never destroys raw OCR evidence

## Phase 3 — Runtime stability

1. Enumerate every long-running task/process:
   - Site Service
   - HVX host
   - Media Service
   - Recognition Worker
   - FFmpeg children
2. Every task needs:
   - cancellation behavior
   - bounded queues
   - backoff
   - timeout
   - health state
   - last error
3. Child-process lifecycle:
   - terminate on camera removal/provider switch/service shutdown
   - no orphan ffmpeg.exe
   - bounded child count
4. Add metrics:
   - live frame age
   - detect frame age
   - source fps
   - display fps
   - AI fps
   - inference duration
   - reconnect count
   - frame drops
   - current child PIDs
   - MediaMTX health
   - queue depth
5. Run soak-oriented tests where possible.

## Phase 4 — Modular API

Break app/api_main.py into APIRouter modules without changing external URLs.

Suggested layout:
app/api/
  app.py
  dependencies.py
  routers/
    auth.py
    modules.py
    topology.py
    cameras.py
    media.py
    recognition.py
    gates.py
    parking.py
    tariffs.py
    subscribers.py
    payments.py
    kiosk.py
    reports.py
    settings.py
    health.py

Move one vertical slice at a time.

Every feature endpoint must enforce:
1. module entitlement
2. RBAC permission

A module disabled by deployment profile must not merely disappear from navigation; its feature APIs/background jobs should be disabled as well.

## Phase 5 — Persistence and security

### Database
- Add Alembic migrations.
- Keep SQLite for local/dev/evaluation.
- Make PostgreSQL the recommended production database.
- Fix uniqueness for multi-site operation, e.g. site-scoped gate/camera names.
- Add direct site ownership where needed for robust queries.

### Secrets
Introduce a SecretStore abstraction.
- Windows production: DPAPI/Credential Manager
- database stores secret reference, not raw camera password
- redact credentials from logs and diagnostics
- avoid long-lived bearer token in media query strings; use header/cookie or short-lived media tokens

### Payments
- Keep immutable/idempotent PaymentTransaction ledger.
- Use Decimal or integer minor units, not float, for financial calculations.
- Mobile provider callback is authoritative only after signature/provider verification.
- Kiosk/mobile/web payment must all settle through the same ledger API.

## Phase 6 — Camera universality

Treat universality as capability-based adapters, not vendor conditionals.

CameraAdapter capabilities should cover:
- discovery
- authentication/connect
- live sources
- snapshot
- native ALPR events
- digital input/presence
- relay/GPIO
- stream profiles
- health

Implement/finish:
- HVX adapter: preserve working behavior
- generic RTSP adapter
- ONVIF discovery + stream URI/profile discovery
- explicit Dahua/Hikvision convenience only as adapter/profile aliases, not hard-coded core logic

Unknown vendors with standard ONVIF/RTSP should still function for video + FastALPR.

## Phase 7 — Acceptance gates

Do not call the migration complete until these pass.

### Automated
- compileall clean
- complete pytest clean
- new media-registry tests
- no missing package/import paths
- module-disabled API tests
- country-neutral plate tests
- process lifecycle tests
- money/ledger idempotency tests

### Windows real-site acceptance
Do not fake these in unit tests. Produce a checklist for a technician:
1. 4 HVX cameras connect through x86 host
2. native plate callbacks continue
3. gate open still works with verified wiring
4. live views remain smooth for all active panes
5. close UI: recognition and parking continue
6. kill one camera: other lanes continue
7. kill MediaMTX: parking/gates/native events continue, live view degrades cleanly
8. restart MediaMTX: streams recover without restarting whole product
9. generic Hikvision/Dahua/RTSP camera: video + FastALPR work
10. run 24h then 72h soak and capture memory/CPU/reconnect/frame-age stats

### Performance targets
- typical LAN live frame age <500 ms
- typical AI frame age <1000 ms
- no continually increasing memory
- no continually increasing child processes
- no unbounded queue
- no 4+ second video backlog
- gate decision path is independent from UI frame rendering

## Working style

- Make the decisions yourself from engineering evidence.
- Do not ask the owner whether to keep obviously broken duplicate paths.
- Preserve verified working hardware code.
- Use feature flags for risky migrations.
- Make small commits with tests.
- After every phase, update documentation with the actual implemented architecture, not aspirational claims.
- If hardware verification is impossible in your environment, explicitly mark the item HARDWARE-VERIFICATION-REQUIRED and continue with everything that can be proven in software.
