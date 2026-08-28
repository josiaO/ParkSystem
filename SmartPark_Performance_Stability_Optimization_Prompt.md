# SmartPark Edge — Performance, Stability & Smooth-Running Optimization Directive

**Audience:** Cursor / implementation agent  
**Priority:** CRITICAL  
**Objective:** Make SmartPark run continuously and smoothly on the real Windows parking server without early termination, UI freezing, unnecessary CPU/RAM usage, camera reconnect storms, database stalls, or gate latency.

This is an optimization/stability phase. Do not add unrelated features until the system passes the acceptance tests at the end.

## 1. Measure before changing
Add lightweight instrumentation first.

Per process:
- PID, uptime, CPU %, RAM/private working set
- thread count
- restart count
- last crash reason

Per camera:
- connection state
- reconnect count
- last event time
- event latency
- RTSP state
- SDK callback state
- queue depth

Per gate:
- command latency
- success/failure
- duplicate-command suppression

Database:
- pool usage
- query latency
- slow queries
- deadlock/retry count

Application:
- API latency
- outbox depth
- worker failures

Create an Admin/Technician `System Health` screen.

## 2. Separate processes by failure domain

A failure in one component must not terminate everything.

Use separate processes:

```text
SmartParkDesktop.exe
SmartParkSiteService.exe
SmartParkWorker.exe
SmartParkHVXHost32.exe
SmartParkMediaGateway.exe
SmartParkOCRWorker.exe
```

Do not run PySide UI, NetSDK, four RTSP decoders, OCR and business logic inside one Python process.

Each process must:
- expose health
- restart independently
- shut down gracefully
- log crashes

## 3. Run background components as Windows Services

Production background services should not depend on a logged-in operator.

Recommended:
- Site Service: Automatic
- Worker: Automatic
- HVX SDK Host: Automatic or Automatic (Delayed Start)
- Media Gateway: Automatic/Delayed as appropriate

Configure recovery:
- first failure -> restart
- second failure -> restart
- repeated failures -> back off and alert

The Desktop is only a client.

## 4. Fast startup

Do not connect every camera, initialize all RTSP streams and load OCR synchronously before the service reports healthy.

Use states:

```text
STARTING
READY_CORE
READY_HARDWARE
DEGRADED
```

Initialize hardware asynchronously.

## 5. Keep Qt GUI thread for UI only

Never run blocking:
- camera SDK calls
- RTSP decode
- DB queries
- HTTP calls
- OCR
- printing
- reports

inside the GUI thread.

Use workers/processes and Qt signals.

If one camera freezes, the UI must remain responsive.

## 6. Reduce live-video load

Do not decode four full-resolution streams continuously.

Rules:
- use substream for grid
- use main stream only for full-screen
- pause/stop decoding when Live Gates is not visible
- share one upstream stream through Media Gateway
- use latest image instead of continuous video where acceptable

## 7. Native ALPR first

If HVX native recognition works, do not continuously run heavy FastALPR on all four streams.

Modes:

```text
NATIVE_ONLY
NATIVE_WITH_LOCAL_VERIFY
LOCAL_ONLY
```

For verification mode, run local OCR only:
- on low/medium-confidence detections
- or on the plate crop

## 8. Queue policy must match data type

Video:
- queue size 1-3
- drop stale frames, keep newest

Parking events:
- durable
- never silently drop

Gate commands:
- unique UUID
- duplicate suppression

Payment callbacks:
- persistent/idempotent

## 9. Bounded queues and backpressure

Every queue needs:
- max size
- overflow policy
- metric
- alert threshold

Critical gate events have priority over analytics and notifications.

## 10. Timeouts everywhere

Explicit timeouts for:
- HVX SDK
- RTSP
- gate command
- DB pool acquire
- payment HTTP
- printing
- public web calls

Never wait forever.

## 11. Controlled reconnect

Use capped exponential backoff plus jitter:

```text
2s, 5s, 10s, 20s, 30s, 30s...
```

Do not let all four cameras reconnect in the same millisecond.

## 12. Circuit breakers

Repeatedly failing dependencies move:

```text
CLOSED -> OPEN -> HALF_OPEN
```

Avoid hundreds of doomed calls.

## 13. Stabilize the HVX SDK host

Treat vendor code as untrusted legacy code.

Rules:
- x86 process only
- one controlled connection per camera
- serialize SDK access unless thread-safety is proven
- callbacks do minimal copying/queueing and return
- no DB/OCR/UI work inside SDK callback
- restart only HVX host if it crashes

## 14. Keep gate critical path tiny

Entry:

```text
camera event
→ normalize
→ indexed entitlement/session lookup
→ short DB transaction
→ gate command
```

Exit:

```text
camera event
→ active session
→ local paid/access check
→ short transaction
→ gate command
```

Do not wait for:
- image storage
- SMS
- analytics
- receipts
- cloud sync
- payment-provider calls

## 15. PostgreSQL rules

- short transactions
- no external I/O while transaction is open
- consistent lock order
- safe deadlock retries for idempotent operations
- correct indexes
- server-side pagination
- no N+1 query loops
- slow-query telemetry

Critical indexes:
- normalized plate + active state
- public token
- provider transaction ID
- payment status
- camera event fingerprint
- subscriber plate + active period

## 16. Bounded DB pool

Use a bounded SQLAlchemy/PostgreSQL pool.

Do not create a connection per camera event.

Start small and measure.

PgBouncer is optional later if connection churn becomes a measured problem.

## 17. API workers

No `--reload` in production.

Hardware ownership must live outside API workers.

Start with 1 Site API worker on the real site, measure, then increase only if needed.

Do not let every Uvicorn worker open its own camera connections.

## 18. Image storage

Do not put large JPEGs in hot PostgreSQL tables.

Store files on disk/object storage; keep metadata/path/hash in DB.

Image persistence must be asynchronous relative to gate authorization.

Add configurable retention and disk-space monitoring.

## 19. Logging

Production:
- INFO by default
- rotating logs
- retention
- structured logs
- correlation IDs

Do not:
- log each video frame
- log binary images
- log secrets
- log healthy heartbeats continuously at INFO

## 20. Crash handling

Every executable must capture:
- process/module/version
- stack trace
- last operation
- timestamp
- correlation ID

After restart, restore from database and durable queues.

Never depend on in-memory globals for parking truth.

## 21. Graceful shutdown

On service stop/update:
1. stop new non-critical work
2. persist critical events
3. release camera subscriptions
4. stop workers
5. close DB pools
6. shut down SDK
7. exit within a bounded timeout

## 22. Health endpoints

Provide:

```text
/health/live
/health/ready
/health/details
```

Detailed health is Admin-only.

## 23. Prevent duplicate instances

Use Windows named mutex/service control/instance lock for:
- Site Service
- HVX host
- Media Gateway

Never let two HVX hosts issue commands to the same gates accidentally.

## 24. Gate command idempotency

Every gate command has:
- command UUID
- gate
- session
- reason
- timestamp

Duplicate retry must not create a new business action.

## 25. Camera-event deduplication

Use:
- vendor event ID
- camera ID
- plate
- timestamp
- image hash
- configurable dedup window
- active-session constraints

## 26. Efficient UI updates

Do not reload entire tables every second.

Use:
- WebSocket/event updates
- targeted row/card updates
- server pagination
- short-lived dashboard summaries

## 27. Reports must not slow gates

Large exports run in background.

Do not calculate all historical revenue every dashboard refresh.

## 28. Payment callback performance

On verified callback:

```text
verify
→ insert/update PaymentTransaction
→ commit
→ update local exit authorization
→ publish PAYMENT_CONFIRMED
→ return
```

Do email/SMS/analytics afterward.

## 29. Long-running soak tests

Before production:
- 8-hour
- 24-hour
- ideally 72-hour controlled test

Monitor RAM, CPU, threads, handles and queue depth.

Fail if memory/threads/processes grow continuously without stabilizing.

## 30. Burst tests

Test:
- four simultaneous camera events
- duplicate callbacks
- camera reconnect storm
- many payment callbacks
- switch outage/recovery

## 31. Failure drills

Deliberately:
- kill HVX host
- kill Media Gateway
- disconnect camera LAN
- stop PostgreSQL briefly
- lose internet
- restart Windows
- disconnect Gate B

Expected:
- unaffected components continue
- degraded state is visible
- recovery is automatic
- no duplicate sessions/payments

## 32. Startup recovery

After reboot:
- services auto-start
- DB readiness is checked
- outbox resumes
- SDK reconnects
- UI can be opened later

Parking must not require Desktop UI to be open.

## 33. Packaging

Production build:
- no dev reload
- pinned dependencies
- deterministic config/log directories
- x64 main app/services
- x86 HVX host only where required
- version displayed in diagnostics

## 34. Optimization acceptance criteria

Do not mark optimization complete until:

1. UI stays responsive during reconnects.
2. HVX host crash does not kill Site Service/UI.
3. HVX host restarts automatically.
4. No duplicate camera connections accumulate.
5. Hidden live-video views stop unnecessary decoding.
6. RAM/CPU stabilize during soak test.
7. All queues are bounded.
8. No parking/payment event is silently dropped.
9. Gate path waits only for critical local operations.
10. DB transactions remain short.
11. Deadlocks are handled safely.
12. Reconnect loops are backoff-controlled.
13. Windows reboot restores operation.
14. Internet outage does not break local parking.
15. Logs cannot fill disk.
16. Slow queries are observable.
17. Major processes expose health.
18. Operators see DEGRADED/OFFLINE instead of app termination.
19. One component failure does not take down the whole product.
20. A minimum 24-hour soak test passes before rollout.

---

# 35. PHP mobile-payment side is supported

The public/mobile-payment side may be built in PHP.

Recommended architecture:

```text
Customer Phone
      ↓ HTTPS
PHP/Laravel Public Payment App
      ↓
Mobile Money Provider
      ↓ webhook
PHP Payment Bridge
      ↓ signed private API
SmartPark Site Server on Windows
      ↓
PostgreSQL PaymentTransaction
      ↓
local exit authorization
```

Important boundaries:
- PHP handles public web/payment-provider integration.
- PHP never controls cameras or gates directly.
- PHP never contains HVX SDK credentials.
- PHP should not become a second authoritative parking database.
- SmartPark Site Server remains the local authority.
- kiosk and mobile payments end in the same `PaymentTransaction` ledger.

## Create-payment flow

```text
QR token
→ PHP asks SmartPark Site API for session/fee
→ customer chooses method
→ SmartPark creates PaymentIntent
→ PHP/provider adapter initiates collection
→ provider returns reference
```

## Callback flow

```text
provider webhook
→ PHP verifies provider authenticity
→ validate amount/reference
→ idempotency check
→ signed call to SmartPark Site API
→ SmartPark commits PaymentTransaction
→ local session becomes paid
→ PHP acknowledges provider
```

Never trust a browser redirect as payment confirmation.

## PHP framework

A mature PHP framework such as Laravel is appropriate if the team is comfortable with PHP.

Use:
- HTTPS
- environment/secret management
- rate limiting
- CSRF protection for browser forms
- provider webhook verification
- idempotency
- queues/background work for non-critical tasks
- structured logging

Do not expose the local PostgreSQL database directly to the public PHP server over the internet.

---

# Final Cursor instruction

For this phase, prioritize stability over new features.

Refactor so:
- hardware is process-isolated
- Qt remains responsive
- video is lazy/shared
- local OCR is only used where needed
- queues are bounded
- external calls have timeouts
- Windows services supervise background processes
- the gate path is minimal
- PostgreSQL transactions are short/indexed
- crashes recover automatically
- long-running behavior is measured

Do not "fix" early termination with one giant try/except around the whole program.

Find the failing component, isolate it, and allow the rest of SmartPark to continue running.
