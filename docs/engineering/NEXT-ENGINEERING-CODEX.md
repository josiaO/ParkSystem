# SmartPark Edge — Next Engineering Phase Prompt for Codex

## Role

You are the principal engineer for SmartPark Edge.

You are responsible for turning the current repository into a production-grade, low-latency, modular vehicle-intelligence and parking platform.

Do not ask the product owner to choose ordinary engineering implementation details that can be decided from evidence, tests, architecture, or official documentation. Make the safest technically sound decision, document it, implement it incrementally, test it, and keep rollback paths.

Read `AGENTS.md` before doing anything else.

Also read:
- `ARCHITECTURE.md`
- `docs/STABILIZATION-REMEDIATION-PROMPT.md`
- `docs/MEDIA-ARCHITECTURE.md`
- `docs/MEDIAMTX-INTEGRATION.md`
- `docs/FASTALPR-PIPELINE.md`
- `docs/NATIVE-ALPR.md`
- `docs/CAMERA-ONBOARDING.md`
- `docs/MIGRATION-AND-ROLLBACK.md`
- `docs/modules/OVERVIEW.md`
- `docs/modules/DEPENDENCY-GRAPH.md`

The working HVX/QY integration, native ALPR callbacks, x86 SDK host, and verified boom-gate control are valuable production assets. Do not rewrite them unless a failing test or measured defect requires a change.

---

# 1. Mission for this phase

Complete the transition from an experimental multi-path implementation to one coherent architecture:

```text
PHYSICAL CAMERA
     |
     +---- vendor/ONVIF control adapter
     |
     +---- video stream
              |
              v
           MediaMTX
          /        \
         /          \
        v            v
  operator live   detect stream
   WebRTC/WHEP       RTSP
                       |
                       v
             Recognition Worker
                       |
                 FastALPR / native
                       |
                       v
            Normalized Recognition Event
                       |
          +------------+------------+
          |                         |
          v                         v
      Security                   Parking
          |                         |
          v                         v
      Alerts                  Access decision
                                    |
                                    v
                              Gate Adapter
```

The system must continue working when any optional subsystem fails.

---

# 2. Engineering principles

1. MediaMTX owns network video distribution.
2. SmartParkMediaService is the sole owner of the MediaMTX process.
3. Recognition is independent from live viewing.
4. The desktop/browser must not poll JPEG snapshots as a live-video transport.
5. FastALPR must not consume every display frame.
6. Video and AI queues are bounded; stale frames are dropped.
7. Business truth is stored in PostgreSQL/SQLite, not Redis or process memory.
8. Camera/gate vendors are adapters, never business logic.
9. Country-specific plate behavior is policy, never global default logic.
10. Payment verification changes financial state; browser redirects do not.
11. Cloud/LLM AI is optional enhancement, never a critical dependency for gate operation.
12. All external integrations have timeouts, retries/backoff, circuit breakers, metrics and explicit degraded states.

---

# 3. First action: establish and repair the baseline

Before adding features:

1. Rebase onto the latest `main`.
2. Inspect the current stabilization PR/branch.
3. Run:
   - `python -m compileall app tools`
   - `pytest -q`
4. Fix import/collection failures before any new implementation.
5. Record current:
   - failing tests
   - warnings
   - number of FFmpeg children
   - media provider state
   - module state
6. Do not suppress errors merely to make tests green.
7. Add a `docs/engineering/PHASE-2-BASELINE.md` with the exact baseline.

---

# 4. Complete the MediaMTX architecture

## 4.1 One provider-selection boundary

All provider selection must go through:

```text
app/infrastructure/media/registry.py
```

No controller, UI, recognition worker or route should independently decide between MediaMTX and legacy direct streaming.

Create/finish contracts such as:

```python
class MediaProvider(Protocol):
    async def register_source(...)
    async def unregister_source(...)
    async def live_endpoint(...)
    async def detect_endpoint(...)
    async def evidence_endpoint(...)
    async def health(...)
    async def metrics(...)
```

Keep `DIRECT_LEGACY` only as a rollback provider until the MediaMTX path passes soak tests.

---

## 4.2 MediaMTX process ownership

Only:

```text
SmartParkMediaService
```

may start/stop/restart MediaMTX.

Other processes must determine health through the local MediaMTX Control API.

Enable and use:
- MediaMTX Control API
- MediaMTX metrics endpoint

Keep them localhost/private.

Do not infer system-wide process health from a Python module-level `_process` variable.

---

## 4.3 Stream roles

Model streams by role:

```text
MAIN
LIVE
DETECT
EVIDENCE
```

Recommended behavior:

### MAIN/EVIDENCE
- highest useful quality
- used for explicit evidence/snapshot capture
- may be on-demand when not otherwise required

### LIVE
- camera substream when available
- H.264 preferred for broad browser compatibility
- typical 10–15 fps

### DETECT
- enough pixels to read the plate
- configurable 3–8 fps starting range
- continuously available only when software recognition is enabled

Do not assume one physical stream is required for every role. Allow roles to point to the same source when a camera exposes only one stream.

Use MediaMTX `sourceOnDemand` only where appropriate. Do not put a software-recognition detect source on demand if that would stop recognition when no operator is viewing.

---

## 4.4 Web live view

For browsers, use MediaMTX WebRTC/WHEP as the preferred low-latency path.

Prefer a real `<video>` integration using the supported MediaMTX WebRTC reader rather than a permanent iframe if authentication, lifecycle control, telemetry or dynamic switching is required.

Required behavior:
- one live transport per pane
- stop old reader before switching camera
- no simultaneous `snapshot.jpg` loop
- no HLS primary path for gate operators unless WebRTC cannot be used
- HLS can be a compatibility fallback
- display clear `LIVE / DEGRADED / OFFLINE`

Handle codec realities:
- H.264 is preferred
- H.265 browser support varies
- H.264 streams containing B-frames may not work with browser WebRTC
- report codec incompatibility instead of silently falling back to high-CPU transcoding
- if transcoding is necessary, make it explicit, measured and per-profile

---

## 4.5 Media telemetry

Pull MediaMTX metrics into SmartPark health.

Capture per camera/path where available:
- connected state
- current readers
- inbound/outbound bytes
- RTP packets
- RTP packet loss
- RTP packet errors
- RTP jitter
- reconnect count
- codec
- stream role
- estimated frame age
- last frame time

Expose these in Hardware Lab.

Do not spam logs with healthy-frame messages.

---

# 5. Replace fake process isolation with real Recognition Worker isolation

The Recognition Worker must not read another process's in-memory `LocalMediaGateway`.

Implement:

```text
MediaMTX local RTSP detect endpoint
          |
          v
SmartParkRecognitionWorker
          |
 persistent decoder
          |
 latest-frame buffer (1–2)
          |
 FastALPR
```

Use one persistent media reader per enabled software-recognition camera.

Preferred implementations:
1. GStreamer RTSP pipeline when installed and stable, or
2. one persistent FFmpeg subprocess per detect stream, or
3. PyAV/FFmpeg bindings if proven stable.

Do not create a new FFmpeg process per frame.

The worker must:
- load FastALPR models once
- warm models once
- reuse them
- reconnect with capped exponential backoff
- drop old frames
- publish normalized events
- expose health
- survive individual camera failures

If Recognition Worker dies:
- native ALPR still works
- live video still works
- Site Service remains alive

---

# 6. Improve plate recognition scientifically

Do not improve OCR by random heuristics.

## 6.1 Build an evaluation harness

Create:

```text
tools/evaluate_alpr.py
tests/fixtures/alpr/
docs/engineering/ALPR-EVALUATION.md
```

The harness must measure:
- plate exact-match accuracy
- character accuracy
- detection recall
- false positive rate
- false acceptance rate for gate-relevant decisions
- mean/p50/p95 inference latency
- results per camera
- results per daylight/night condition
- results per plate country/profile where labels exist

Keep a fixed validation set that training/tuning code never modifies.

---

## 6.2 Temporal consensus

A vehicle may be visible in multiple frames.

Do not create a parking event from every frame.

Build a recognition track/consensus layer:

```text
frame 1 -> T285DQP
frame 2 -> T285DOP
frame 3 -> T285DQP
frame 4 -> T285DQP

=> one track
=> consensus T285DQP
=> one PlateRecognized event
```

Inputs may include:
- normalized text
- OCR confidence
- character similarity
- timestamp
- bounding box overlap / vehicle track
- native ALPR candidate
- FastALPR candidate

Do not treat an LLM's self-reported confidence as a calibrated probability.

---

## 6.3 Native + FastALPR fusion

Modes:

```text
NATIVE_ONLY
FASTALPR_ONLY
HYBRID
```

HYBRID policy should:
- immediately accept strong agreement
- use native-only or FastALPR-only when the other provider is unavailable
- hold disagreements for temporal consensus or operator review
- never produce two parking sessions for the same physical vehicle event

---

## 6.4 Country-neutral plate policy

Refactor any Tanzania-specific OCR correction from the neutral path.

Create explicit policies:

```text
NeutralPlatePolicy
TanzaniaPlatePolicy
KenyaPlatePolicy
SouthAfricaPlatePolicy
UAEPlatePolicy
...
```

Default must be neutral.

Neutral policy must not:
- force `T` prefix
- force digit/letter positions
- use East African plate shape scoring as a global rule

Country policy is selected from Site configuration.

Add tests proving non-Tanzanian plates are not silently transformed.

---

# 7. ONVIF and universal camera support

Implement capability-driven ONVIF support.

For compatible cameras use Media2:
- `GetProfiles`
- `GetStreamUri`
- `GetSnapshotUri`

Never guess RTSP URLs when a valid ONVIF stream URI is available.

If a camera supports ONVIF Profile M:
- detect actual capabilities
- consume vehicle/license-plate metadata/events when the device advertises them
- do not assume every Profile M device supports license-plate recognition
- normalize metadata into the same SmartPark recognition contract

Maintain manual RTSP entry as fallback.

Camera onboarding should work for:
- HVX/QY native ALPR
- Hikvision
- Dahua
- generic ONVIF
- generic RTSP
- HTTP/MJPEG
- USB/UVC where supported

---

# 8. Mobile payments: make the workflow real

## 8.1 Keep the provider abstraction

Use:

```python
class PaymentProvider(Protocol):
    async def create_intent(...)
    async def initiate_collection(...)
    async def verify_webhook(...)
    async def query_status(...)
    async def refund(...)
```

Provider selection belongs to site configuration.

Keep:
- `SimulatedPaymentProvider`
- `ManualKioskPaymentProvider`

Add:
- `FlutterwavePaymentProvider`
- `ClickPesaPaymentProvider`

Do not hard-code Tanzania providers into the parking core.

---

## 8.2 First real test provider: Flutterwave TEST MODE

Implement Flutterwave first for integration testing because its official Tanzania mobile-money documentation supports test mode and Tanzania test mobile-money transactions can be automatically authorized after a short delay.

Requirements:
- TEST keys only by default
- provider-specific config isolated from business logic
- TZS mobile-money request
- unique `tx_ref`
- return `PENDING` after initiation
- webhook handler
- HMAC/signature verification according to current Flutterwave docs
- server-side transaction verification after webhook
- verify:
  - status
  - expected reference
  - amount
  - currency
- write `PaymentTransaction(SUCCEEDED)` only after verification
- duplicate webhook => same transaction, no duplicate credit
- pending reconciliation job polls transaction verification as backup

Never open a barrier directly from the webhook handler.

Webhook updates the ledger; normal local exit authorization then reads committed payment state.

---

## 8.3 Tanzania production candidate: ClickPesa

Implement ClickPesa behind the same provider interface after Flutterwave test integration passes.

Support only APIs proven by current ClickPesa documentation:
- authorization token
- mobile-money USSD-PUSH
- hosted checkout where useful
- payment status query
- webhooks/callbacks
- optional BillPay/Control Number later
- optional TanQR/Lipa Namba later

Important:
- current ClickPesa documentation says there is no sandbox/testing environment
- therefore do NOT activate ClickPesa live by default
- add a `LIVE_PROVIDER_CONFIRMATION_REQUIRED` safety setting
- test with small real amounts after merchant/KYC setup
- keep provider reconciliation and webhook idempotency

Do not guess provider signing/checksum behavior; implement only from the current official documentation.

---

## 8.4 Public internet exposure

Do not expose:
- cameras
- MediaMTX RTSP
- PostgreSQL
- gate APIs
- HVX SDK host
- admin APIs

Only expose a narrow public surface such as:

```text
GET  /p/{opaque_token}
POST /api/public/payment-intents
POST /api/webhooks/flutterwave
POST /api/webhooks/clickpesa
GET  /api/public/payment-status/{opaque_token}
```

A practical initial ingress option is Cloudflare Tunnel because it establishes outbound-only connections from the site and can publish a local HTTP service without opening inbound firewall ports.

Treat this as an optional `PublicIngressProvider`, not a permanent business-logic dependency.

The public hostname must route only the public payment endpoints. Protect admin/internal routes from public ingress.

---

## 8.5 Payment safety rules

1. Never trust browser success/redirect.
2. Never store mobile-money PIN.
3. Normalize phone numbers to E.164.
4. Use `Decimal` or integer minor units for money.
5. Every provider request gets an idempotency key/reference.
6. Every provider transaction ID is unique.
7. Webhooks are idempotent.
8. Verify amount, currency and reference before crediting.
9. Reconciliation runs for stale PENDING intents.
10. Store raw provider event metadata in a bounded/auditable form with secrets redacted.
11. Mobile payment failure must not break local parking.
12. Kiosk cash remains available offline when configured.

---

# 9. Optional AI integration

AI is useful, but it must not become the primary plate engine or a hard dependency.

Create:

```python
class AIReviewProvider(Protocol):
    async def review_vehicle_event(...)
    async def summarize_incident(...)
```

Initial provider:
- `GeminiAIReviewProvider`

Use environment/config:
```text
SMARTPARK_AI_ENABLED=false
SMARTPARK_AI_PROVIDER=gemini
SMARTPARK_AI_MODEL=gemini-2.5-flash-lite
```

Do not call the API for every frame.

Use AI only for:
- low-confidence plate crop second opinion
- native/FastALPR disagreement
- vehicle color/type description
- security incident summary
- optional natural-language operator assistant

Do NOT use cloud AI to:
- directly open a gate
- mark a payment successful
- modify tariff configuration without confirmation
- override verified native/FastALPR recognition automatically in production

---

## 9.1 Gemini test integration

Gemini is suitable for testing because Google currently offers a free Gemini Developer API tier for certain models, including free input/output usage subject to limits, and the API supports image input plus JSON-schema structured outputs.

For development only, use a small/free model such as:

```text
gemini-2.5-flash-lite
```

Make model ID configurable because model availability changes.

Send only:
- cropped plate image where possible
- optionally a downscaled vehicle image when vehicle attributes are requested

Request strict JSON:

```json
{
  "readable": true,
  "plate_candidate": "ABC1234",
  "vehicle_type": "car",
  "vehicle_color": "white",
  "notes": "..."
}
```

Do not ask the model to output an artificial confidence score and then treat it as probability.

Fusion rule example:

```text
FastALPR candidate == AI candidate
    -> supporting evidence

FastALPR candidate != AI candidate
    -> temporal consensus / operator review

AI unavailable / timeout
    -> normal FastALPR/native flow continues
```

Set:
- short timeout
- circuit breaker
- concurrency limit
- daily budget/request cap
- no retries that block the gate path

Important privacy requirement:
Google's free Gemini API tier currently states that submitted content may be used to improve Google products. Therefore free-tier AI must be used only with test/synthetic/non-sensitive imagery unless the deployment has explicitly accepted that data treatment. For real customer production imagery, use an appropriate paid/privacy configuration or keep AI local.

---

# 10. Module enforcement

Continue the modular-product refactor.

A module being disabled must disable:
- navigation
- API router
- background jobs
- scheduled jobs
- module health expectations

Use router-level module dependencies where possible.

Examples:

```text
LPR_ONLY:
core + cameras + media + recognition + reports

SECURITY:
core + cameras + media + recognition + watchlists + alerts

PARKING:
core + cameras + media + recognition + parking + access + tariffs + payments
```

No payment code should run for an LPR-only customer.

---

# 11. Database and migrations

Introduce Alembic if not already complete.

Production recommendation:
```text
PostgreSQL
```

Keep SQLite for:
- tests
- demo
- local development
- very small evaluation deployments

Fix multi-site constraints:
- camera name unique within site, not globally
- gate name unique within site
- access plans site-scoped
- registered vehicles site/fleet-scoped according to domain rules
- operational tables queryable by site without ambiguous joins

Do not perform ad-hoc production schema changes through manual `ALTER TABLE` logic once Alembic is active.

---

# 12. Secrets

Introduce a SecretStore.

Windows production implementation:
- DPAPI and/or Windows Credential Manager

Database stores:
```text
credentials_ref
```

not raw passwords.

Redact:
- RTSP passwords
- API keys
- webhook secrets
- mobile-provider credentials
- Gemini API key

from:
- API responses
- logs
- exception messages
- generated diagnostics bundles

---

# 13. Tests required in this phase

## Media
- MediaMTX healthy/unhealthy selection
- WebRTC path does not also poll snapshot endpoint
- no new FFmpeg process per rendered frame
- camera switch closes old media reader
- one broken stream does not affect other cameras
- MediaMTX restart recovery
- bounded frame buffers

## Recognition
- generic camera recognition continues with UI closed
- slow FastALPR drops stale frames
- temporal consensus
- native/FastALPR agreement
- disagreement hold
- neutral plate policy
- Tanzania policy only when selected
- duplicate event suppression

## Payments
- simulated provider
- Flutterwave test initiation
- invalid webhook signature rejected
- duplicate webhook does not duplicate ledger
- successful webhook still requires transaction verification
- wrong amount rejected
- wrong currency rejected
- wrong reference rejected
- reconciliation converts valid PENDING -> SUCCEEDED exactly once
- provider unavailable leaves local parking functional
- cash payment remains local

## AI
- AI disabled => zero calls
- AI timeout => normal recognition continues
- low-confidence event may call provider
- high-confidence event does not waste API call
- invalid JSON rejected
- AI disagreement cannot auto-open gate

## Modules
- disabled payments router unavailable
- disabled security workers not started
- LPR_ONLY works with zero gates

---

# 14. Observability

Hardware Lab should display, per camera:

```text
Network           Online
Media             Streaming
Live transport    WebRTC
Codec             H264
Resolution        1280x720
Source FPS        10
Live frame age    120 ms
RTP loss          0
RTP jitter        ...
Recognition       Ready
AI FPS            5
Inference p95     140 ms
Last plate        2 sec ago
Reconnects        0
```

Payments health:

```text
Provider           Flutterwave Test
Webhook            Healthy
Pending intents    2
Last verified      ...
Reconciliation     Healthy
```

Optional AI:

```text
AI review          Disabled / Healthy / Rate Limited
Provider           Gemini
Calls today        ...
Failures           ...
```

---

# 15. Windows/site acceptance checklist

After software tests pass, produce exact instructions for Cursor/local technician.

Do not claim hardware verification from cloud tests.

Required real tests:

1. Start Windows.
2. Background Site Service starts.
3. x86 HVX host starts.
4. Media Service/MediaMTX starts.
5. All existing HVX cameras reconnect.
6. Native ALPR still reports plates.
7. Browser WebRTC view is smooth.
8. Desktop live view is smooth.
9. No 4+ second repeated backlog.
10. Recognition continues after closing UI.
11. Generic Hikvision/Dahua camera works through ONVIF/RTSP + FastALPR.
12. Pull one camera network cable; other cameras continue.
13. Kill Recognition Worker; native ALPR and video continue.
14. Kill MediaMTX; Site Service remains alive.
15. Restart MediaMTX; streams recover automatically.
16. Trigger gate only through the existing verified adapter path.
17. Test Flutterwave TEST payment end-to-end.
18. Duplicate test webhook does not duplicate payment.
19. Run 24-hour soak.
20. Run 72-hour soak.

Record:
- CPU
- RAM
- thread count
- FFmpeg child count
- MediaMTX readers
- frame age
- packet loss
- reconnects
- AI inference p95
- payment callback/reconciliation failures

---

# 16. Definition of done

This engineering phase is complete only when:

- one coherent MediaMTX-based media path exists
- legacy direct media is rollback only
- Recognition Worker uses real process-safe stream IPC
- FastALPR does not accumulate stale frames
- plate quality is measured with an evaluation dataset
- country behavior is policy-based
- ONVIF discovery uses standard media profiles/URIs
- generic cameras can do FastALPR without affecting live view
- mobile payment works in Flutterwave test mode
- ClickPesa adapter is implemented safely but live-disabled until merchant testing
- payment callbacks are verified and idempotent
- optional Gemini integration works only as a non-critical reviewer
- module disabling affects backend and UI
- secrets are not stored/logged as plaintext
- automated tests pass
- real Windows/HVX acceptance is documented
- 24–72 hour soak shows no process/memory growth or multi-second video backlog

Do not add unrelated features until this definition of done is met.
