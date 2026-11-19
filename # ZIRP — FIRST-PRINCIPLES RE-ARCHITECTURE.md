# ZIRP — FIRST-PRINCIPLES RE-ARCHITECTURE, HIGH-THROUGHPUT ENGINEERING AND END-TO-END PRODUCT COMPLETION

## 1. MISSION AND ENGINEERING OWNERSHIP

You are the principal software architect, distributed-systems engineer, database architect, computer-vision engineer, hardware integration engineer and technical owner of ZIRP.

You are working inside an existing, actively developed codebase.

Your responsibility is to understand the complete product, challenge its existing architecture, eliminate unnecessary complexity, improve its performance and complete its implementation into a production-ready parking management system.

Do not treat this as a new prototype.

Do not blindly preserve previous architectural decisions.

Do not blindly rewrite existing functionality.

Your objective is to produce the simplest reliable architecture capable of handling the real operational workload.

You are expected to make and justify ordinary engineering decisions independently.

When physical hardware, credentials or external authorization are unavailable, implement everything that can safely be implemented and clearly document the dependency.

---

## 2. UNDERSTAND THE REAL BUSINESS AND OPERATIONAL ENVIRONMENT

ZIRP is an intelligent, plate-first parking management and automated vehicle access-control system.

Its first production deployment is Rock City Mall, Mwanza, Tanzania.

The existing parking operation has approximately:

- More than 1,500 vehicles entering daily.
- On some days, approximately 2,000 or more vehicles.
- More than 800 daily paying visitors.
- More than 300 daily VIP, season and other specially authorized vehicles.
- Periods where approximately 20 vehicles enter or exit consecutively.

These are initial operational estimates. Measure actual traffic distributions and peak concurrency before finalizing capacity.

ZIRP must not be engineered like a small CRUD application.

It must be engineered as a high-throughput operational system where vehicle identification, access decisions, physical barriers, financial transactions and auditability must work together.

The system must remain responsive during concentrated arrivals and departures.

It must not introduce unnecessary latency through sequential database lookups, competing recognition engines, blocking user interfaces or remote dependencies.

### Primary business objectives

1. Identify entering and exiting vehicles.
2. Recognize Tanzanian registration plates.
3. Classify vehicles according to their access and payment policies.
4. Manage VIP, season and authorized vehicles.
5. Manage special government and exceptional vehicles without requiring permanent vehicle registration.
6. Create parking sessions for casual visitors.
7. Generate unique QR receipts.
8. Calculate fees using configurable tariffs and grace periods.
9. Accept and verify Tanzanian mobile money payments.
10. Support authorized cash collection.
11. Authorize physical barriers correctly.
12. Operate multiple cameras, lanes, gates, nodes and kiosks.
13. Maintain accurate financial records.
14. Provide comprehensive operational reporting.
15. Recover safely from hardware, power, network and service failures.

## 3. FIRST-PRINCIPLES PROJECT AUDIT

Before implementing architectural changes:

- Inspect the current branch and HEAD.
- Compare local work against GitHub.
- Inspect uncommitted and untracked files.
- Identify the actual version deployed at Rock City.
- Identify the latest working streaming implementation.
- Identify the actual recognition engines and configurations.
- Inspect the entire database schema and migration history.
- Inspect every runtime process and communication channel.
- Identify all hardware integrations.
- Inspect the existing kiosk and payment implementations.
- Run existing tests and establish a baseline.
- Identify mocked functionality presented as production functionality.

Create a complete implementation inventory.

Classify each subsystem:

KEEP: Necessary and working.

FIX: Necessary but defective.

CONSOLIDATE: Duplicate or competing implementations.

REPLACE: Fundamentally unsuitable implementation.

REMOVE: Verified dead, obsolete or unnecessary code.

VERIFY: Requires physical hardware or production evidence.

Do not delete files merely because they look unused.

Check imports, runtime loading, dynamic execution, packaging, installers, tests, migrations and dependencies before removing anything.

Preserve working changes and create a dedicated working branch.

Never erase production data or overwrite existing user work.

## 4. TARGET ARCHITECTURE: DISTRIBUTED, HIGH-THROUGHPUT PARKING PLATFORM

Use a hybrid centralized and edge-computing architecture.

### Central Site Server

Owns:

- Authoritative PostgreSQL database.
- Parking sessions.
- Vehicle registry.
- Entitlements.
- Temporary special authorizations.
- Tariffs.
- Payment ledger.
- Financial reconciliation.
- Users and permissions.
- Node registration.
- Access policies.
- Reports.
- Audit records.
- Site-wide configuration.

### Edge Nodes

Each Edge Node owns its assigned physical lanes and cameras.

Responsibilities:

- Camera discovery and connection.
- Camera SDK sessions.
- Video acquisition.
- Recognition processing.
- Local access-decision execution.
- Gate hardware communication.
- Local event journal.
- Local configuration snapshots.
- Heartbeats and health reporting.
- Reconnection and synchronization.

### Other clients

- Operator desktop application.
- Android autopay kiosk.
- Administrative interface.
- Public mobile payment portal.

A Site Server may also operate as an Edge Node in a small deployment.

Multiple Edge Nodes must work against the same authoritative Site Server without competing for physical hardware ownership.

Do not distribute business logic unnecessarily.

The central server owns financial truth and authoritative parking state. Edge Nodes own physical hardware and execute authorized local decisions.

## 5. VEHICLE CLASSIFICATION ENGINE

This is a foundational subsystem.

Do not process every vehicle through the same generic registration and payment workflow.

Implement four explicit vehicle classifications.

### CLASS A — PERMANENTLY REGISTERED VEHICLES

Includes:

- VIP.
- Season.
- Staff.
- Other registered authorized vehicles.

Maintain persistent vehicle identity and entitlement records.

An entitlement must include:

- Vehicle identity.
- Entitlement type.
- Status.
- Effective date.
- Expiration date.
- Applicable site.
- Permitted gates or restrictions.
- Access policy.
- Administrative audit history.

An expired or suspended entitlement must not authorize entry.

### CLASS B — CASUAL PAYING VISITORS

Create a parking session when the vehicle enters.

Associate:

- Normalized plate.
- Entry timestamp.
- Entry gate and lane.
- Camera evidence.
- Vehicle image.
- Recognition evidence.
- Receipt token.
- Parking status.

At exit:

- Retrieve the active session.
- Calculate the amount due.
- Check authoritative payment status.
- Apply the correct tariff.
- Authorize exit only when the financial conditions are satisfied.

### CLASS C — GOVERNMENT AND SPECIAL VEHICLES

Some government and exceptional vehicles cannot be registered in the permanent vehicle registry.

Do not force these vehicles into the VIP or season registry.

Implement temporary special-access authorization.

The workflow must support:

1. Detect vehicle.
2. Capture plate and image evidence.
3. Request authorized verification.
4. Record the approving operator or approved credential.
5. Create a temporary authorization linked to the current visit.
6. Apply the configured payment exemption or special tariff.
7. Authorize access according to policy.
8. Retrieve the authorization at exit.
9. Close the visit and authorization.
10. Preserve an audit trail.

A government-looking plate must not automatically grant free parking.

Special-access rules must be configurable and auditable.

Do not retain a permanent government vehicle registry merely to support temporary authorization.

Apply appropriate data-retention rules to temporary vehicle evidence.

### CLASS D — UNKNOWN OR UNVERIFIED VEHICLES

Examples:

- Unrecognized plate.
- Invalid recognition confidence.
- Expired entitlement.
- Unverified special status.
- Missing payment.
- Conflicting active session.

Provide manual verification or denial according to the configured policy.

Do not silently grant access.

### Classification output

Every classification operation must produce a structured result containing:

- Vehicle classification.
- Normalized plate.
- Recognition confidence.
- Applicable entitlement or session.
- Applicable policy.
- Decision.
- Reason code.
- Evidence references.
- Timestamp.
- Processing node.

Do not allow the recognition engine itself to operate the barrier.

It produces evidence and classification inputs. The access decision engine authorizes the physical action.

## 6. HIGH-PERFORMANCE ACCESS DECISION ENGINE

The access decision engine is one of the most important components.

Its purpose is to produce a fast, deterministic and auditable decision for every vehicle.

### Entry decision

Evaluate:

- Registered vehicle entitlement.
- Active validity.
- Special-access authorization.
- Existing active session.
- Duplicate entry conditions.
- Applicable site and lane policy.

For casual visitors, initiate a new parking session.

For registered and specially authorized vehicles, apply the corresponding access policy.

### Exit decision

Evaluate:

- Active parking session.
- Vehicle identity.
- Payment status.
- Payment verification.
- Entitlement.
- Special authorization.
- Outstanding amount.
- Previous exit authorization.
- Duplicate passage events.

The result must be one of:

ALLOW, DENY, PAYMENT_REQUIRED, OPERATOR_APPROVAL_REQUIRED, or TEMPORARILY_UNAVAILABLE.

Every decision must have a recorded reason.

### Performance requirements

Do not implement multiple sequential database requests for one decision when a single optimized query or preloaded read model can supply the necessary information.

Implement:

- Normalized plate lookup.
- Indexed entitlement lookup.
- Indexed active-session lookup.
- Efficient payment-state lookup.
- Local read models for authorized vehicle entitlements.
- Versioned policy snapshots.
- Bounded database operations.
- Controlled concurrency.
- Explicit timeouts.
- Safe fallbacks.

Do not let image upload, dashboard rendering or report generation block access decisions.

## 7. HIGH-THROUGHPUT CAMERA AND RECOGNITION ARCHITECTURE

Preserve the recently improved streaming implementation.

Do not destabilize it.

First benchmark it and identify the reason for its improved performance.

### Camera requirements

Support:

- QY/HVX cameras.
- Generic IP cameras.
- RTSP.
- ONVIF where supported.
- Multiple vendors.
- One or multiple cameras.
- Entry and exit directions.
- Multiple lanes and gates.

Rock City currently has four primary lane cameras:

- Gate 1 entry.
- Gate 1 exit.
- Gate 2 entry.
- Gate 2 exit.

The actual IP addresses, credentials, protocols and ownership must be discovered and configured.

Do not use example devices as real production cameras.

### Camera connection workflow

1. Discover reachable cameras.
2. Identify vendor and protocol.
3. Select the appropriate adapter.
4. Configure credentials.
5. Test authentication.
6. Test streaming.
7. Test snapshots.
8. Assign Edge Node.
9. Assign gate and lane.
10. Assign entry or exit direction.
11. Save only after validation.

One authoritative acquisition owner per physical camera.

Do not allow competing processes to open the same camera unnecessarily.

### Recognition pipeline

Camera acquisition → Frame processing → Plate detection → Crop → Preprocessing → OCR → Validation → Confidence evaluation → Vehicle event.

Support:

- Native camera recognition.
- FastALPR.

Do not create duplicate recognition paths.

Define exactly how combined recognition works.

Prevent duplicate sessions when multiple recognition methods identify the same vehicle.

Recognition must run concurrently across cameras.

A failure on one camera must not block other cameras.

### Throughput

Implement per-camera and per-lane isolation.

Use bounded queues and backpressure.

Prevent stale frames from accumulating.

Do not let uncertain recognition results block unrelated vehicles.

Keep critical vehicle and financial events durable even under processing overload.

Measure:

- Frame age.
- Recognition latency.
- Recognition accuracy.
- Dropped frames.
- Queue depth.
- CPU and memory use.
- Camera reconnect time.
- Vehicle event throughput.

## 8. HIGH-PERFORMANCE DATABASE ARCHITECTURE

PostgreSQL is the authoritative production database.

SQLite is for development or explicitly supported single-machine operation.

Inspect the existing schema before introducing new tables.

### Logical data domains

- Vehicles.
- Entitlements.
- Special authorizations.
- Parking sessions.
- Payments.
- Access decisions.
- Gates and lanes.
- Nodes.
- Cameras.
- Vehicle evidence.
- Receipts.
- Audit events.

Reuse existing equivalent models rather than creating duplicate structures.

### Required optimization

1. Normalize vehicle registration plates consistently.
2. Index site and normalized plate lookups.
3. Optimize active-session lookup.
4. Enforce one active session per vehicle per site where applicable.
5. Index payment references and session relationships.
6. Optimize valid entitlement lookup.
7. Avoid N+1 queries.
8. Avoid unnecessary table scans.
9. Avoid broad transactions.
10. Lock only records requiring coordination.
11. Use controlled database connection pooling.
12. Evaluate PgBouncer based on measured workload.
13. Monitor slow queries.
14. Maintain appropriate database statistics.
15. Evaluate partitioning for large append-only event tables.
16. Establish backup and restoration procedures.

### Transaction integrity

Handle concurrent operations correctly.

Examples:

- Two cameras recognizing the same vehicle.
- Entry and exit events occurring close together.
- Two payment callbacks for one transaction.
- Payment confirmation and exit authorization arriving simultaneously.
- Two operators approving the same exception.

Use:

- Database transactions.
- Appropriate isolation.
- Row-level locking where necessary.
- Unique constraints.
- Idempotency keys.
- Optimistic concurrency where appropriate.
- Explicit state machines.

Never rely on frontend checks for financial or session integrity.

### Financial correctness

A payment must never be credited twice.

A parking session must never be closed twice.

A payment callback must not create an unrelated session.

An HTTP success response must not be treated as proof of payment.

The authoritative payment ledger must contain the verified transaction and its reconciliation history.

## 9. FAST CONCURRENT PROCESSING

Do not use one global queue for all cameras and lanes.

Use independent processing paths for each assigned camera and lane.

Independent operations should run concurrently.

Implement:

- Bounded queues.
- Per-lane processing.
- Backpressure.
- Durable event journals.
- Idempotent event consumers.
- Asynchronous evidence storage.
- Asynchronous dashboard updates.
- Controlled worker pools.
- Explicit resource limits.
- Recovery after worker failure.

A recognition delay at Gate 1 must not stop Gate 2.

A kiosk payment must not block recognition.

A dashboard refresh must not block a barrier command.

A database report must not block operational queries.

The system must process concentrated arrivals and departures without allowing one event to hold unrelated events hostage.

## 10. EVENT-DRIVEN TRANSACTION ARCHITECTURE

Use explicit business events where they improve decoupling.

Examples:

- VehicleDetected.
- PlateRecognized.
- VehicleClassified.
- ParkingSessionCreated.
- ReceiptIssued.
- PaymentInitiated.
- PaymentVerified.
- AccessDecisionCreated.
- GateCommandIssued.
- VehiclePassed.
- ParkingSessionClosed.
- SpecialAccessApproved.

Events must have unique identifiers, timestamps, site, node and correlation identifiers.

Implement an appropriate transactional outbox for events that must be published reliably after database commits.

Consumers must be idempotent.

Do not introduce Kafka, RabbitMQ or other infrastructure without evidence that the operational workload requires it.

Use the simplest reliable event transport suitable for the deployment.

## 11. EDGE NODE AND OFFLINE OPERATION

Each node must have:

- Unique identity.
- Site assignment.
- Gate ownership.
- Secure credentials.
- Heartbeat.
- Health reporting.
- Versioned configuration.
- Local event journal.
- Reconnection.
- Synchronization.
- Controlled update mechanism.

Maintain a local, versioned snapshot of authorized vehicle entitlements and access policies.

Define how stale snapshots are detected and invalidated.

A node may continue processing approved operations according to explicit offline policies.

Never treat an unverified mobile payment as paid.

A previously verified, securely issued, appropriately scoped access grant may be honored offline according to its expiry, revocation and reconciliation rules.

Unknown vehicles and uncertain exceptions must follow the offline operator policy.

Avoid duplicate gate controllers.

## 12. ANDROID AUTOPAY KIOSK

Investigate the existing Rock City autopay machine before proposing replacement.

Its Android version was previously reported as 7.1.2, but verify the actual device.

Inspect:

- Manufacturer and model.
- Android version and API level.
- Processor architecture.
- USB ports.
- USB Host/OTG support.
- RFID reader interface.
- Printer.
- Network.
- Installed application.
- Kiosk lockdown.
- Ability to install or configure another application.

### Preferred QR solution

Test a USB HID 2D QR scanner first.

It should send scanned content as keyboard input to the existing ZIRP kiosk page.

If HID is unsuitable, evaluate Android USB Host integration.

Do not develop another Android application unless required.

### Kiosk workflow

1. Scan unique parking receipt.
2. Retrieve parking session.
3. Display vehicle image.
4. Display plate.
5. Display entry time.
6. Display duration.
7. Display outstanding amount.
8. Initiate mobile money.
9. Show provider verification status.
10. Show successful payment only after verification.

The kiosk must not independently mark sessions paid or operate barriers.

Handle repeated scans, timeouts, invalid receipts and disconnected network.

## 13. MOBILE MONEY INTEGRATION

Inspect existing ClickPesa and other payment infrastructure.

Identify actual working production integrations versus simulations.

Support the required Tanzanian mobile money providers through an appropriate payment abstraction.

Implement:

- Payment intents.
- Unique references.
- Provider authentication.
- Secure webhooks.
- Signature validation.
- Server-side verification.
- Idempotency.
- Duplicate callback protection.
- Pending states.
- Late payment success.
- Failed payments.
- Underpayment.
- Reconciliation.
- Reversal handling.
- Financial audit history.

The system must distinguish initiated, pending, verified, failed, reversed and reconciled transactions.

Do not use the browser redirect as payment authority.

Do not expose merchant credentials to kiosks or Edge Nodes.

Keep test and production environments completely distinguishable.

## 14. PHYSICAL GATE AND SENSOR INTEGRATION

Identify the actual installed:

- Camera relays.
- QY/HVX SDK controls.
- GPIO.
- KF Board controllers.
- Boom mechanisms.
- Passage sensors.
- Boom-position feedback.
- Receipt printer.
- Printer sensors.

Separate:

1. Gate command requested.
2. Command accepted.
3. Physical boom opened.
4. Vehicle passed.
5. Transaction completed.

Use safe timeouts and idempotent commands.

Avoid repeated pulses.

Never physically test or modify live barriers without authorization and coordination with Rock City operators.

## 15. SPECIAL ATTENTION TO SECURITY AND REVENUE

ZIRP controls access to a revenue-generating physical facility.

Prioritize:

- Accurate financial records.
- Tamper-resistant audit logs.
- Role-based authorization.
- Separation of duties.
- Secure node credentials.
- Secure kiosk credentials.
- Camera credential protection.
- Payment webhook validation.
- Protection against QR replay and duplication.
- Prevention of duplicate sessions.
- Prevention of unpaid exits.
- Operator approval history.
- Special-access auditability.
- Database backup.
- Tested restoration.
- Clock synchronization.
- Log rotation.
- Service recovery.

Manual overrides must record the approving person, reason, vehicle evidence and time.

No privileged action should disappear without an audit trail.

## 16. PERFORMANCE BENCHMARKING

Create repeatable load tests based on the stated Rock City operating profile.

Initial test scenarios:

### Scenario A: Normal operations

Simulate 2,000 daily vehicle entries and corresponding exits.

### Scenario B: Consecutive traffic

Simulate 20 consecutive arrivals and 20 consecutive departures.

### Scenario C: Concurrent lanes

Process simultaneous events across all four primary camera lanes.

### Scenario D: Payment concurrency

Process multiple simultaneous payment intents and callbacks.

### Scenario E: Database contention

Simulate simultaneous plate lookup, session creation, payment updates and session closure.

### Scenario F: Failure recovery

Disconnect nodes, restart workers, interrupt network and simulate database reconnection.

### Scenario G: Recognition stress

Feed multiple camera streams and measure recognition latency and resource consumption.

### Initial performance objectives

These are targets requiring validation, not assumed existing performance:

- Local entitlement lookup: p95 below 20 ms.
- Validated-plate access decision: p95 below 200 ms.
- Database plate/session lookup: p95 below 50 ms.
- No duplicate parking sessions.
- No duplicate payment credits.
- No lost committed financial events.
- Independent lane operation.
- Bounded memory usage.
- Recoverable event processing.

Measure camera recognition, barrier hardware response and end-to-end vehicle processing separately.

Do not optimize one metric by compromising financial correctness or access security.

## 17. OBSERVABILITY

Implement structured operational monitoring.

Expose:

- Vehicles detected.
- Plates recognized.
- Recognition failures.
- Current active sessions.
- Vehicles processed per minute.
- Average and p95 decision latency.
- Database query latency.
- Database connection usage.
- Queue depth.
- Camera connectivity.
- Node connectivity.
- Gate health.
- Payment status.
- Payment reconciliation.
- Offline events awaiting synchronization.

Provide useful logs with correlation IDs.

Avoid excessive repetitive logs and misleading success messages.

The operator dashboard must show real operational states, not mock values.

## 18. IMPLEMENTATION PHASES

PHASE 1 — Project and operational audit.

PHASE 2 — First-principles architecture and data-flow reconstruction.

PHASE 3 — Dead-code removal and subsystem consolidation.

PHASE 4 — Database and transaction optimization.

PHASE 5 — Vehicle classification and access decision engine.

PHASE 6 — Camera and recognition integration.

PHASE 7 — Edge Node registration and synchronization.

PHASE 8 — Physical gate and sensor integration.

PHASE 9 — Android kiosk and QR scanner integration.

PHASE 10 — Real mobile payment integration.

PHASE 11 — Multi-node concurrency and offline operation.

PHASE 12 — Performance benchmarking and production hardening.

PHASE 13 — Windows deployment and Rock City pilot.

Do not attempt a giant rewrite in one operation.

Maintain a working application after each phase.

## 19. ACCEPTANCE CRITERIA

ZIRP is not complete merely because it launches.

Demonstrate:

1. Real camera discovery and connection.
2. All four primary Rock City cameras configured.
3. Smooth video with bounded frame age.
4. Concurrent recognition.
5. Correct vehicle classification.
6. Valid VIP and season access.
7. Temporary government and special access.
8. Casual vehicle session creation.
9. Unique QR receipt generation.
10. QR kiosk lookup.
11. Accurate tariff calculation.
12. Real payment initiation.
13. Verified payment credit.
14. Correct exit authorization.
15. Different entry and exit gates.
16. Multiple simultaneous lanes.
17. Safe handling of 20 consecutive vehicles.
18. Multi-node operation.
19. Safe offline operation.
20. Duplicate-event protection.
21. Physical barrier feedback.
22. Complete audit records.
23. Database backup and restoration.
24. Clean Windows installation.
25. Repeatable performance benchmarks.

Distinguish clearly between:

- Automated tests.
- Simulations.
- Local runtime tests.
- Physical hardware tests.
- Production payment tests.

Never claim hardware or financial functionality is verified when it has only been simulated.

## 20. REQUIRED DOCUMENTATION

Maintain documentation that matches the actual implementation:

1. ZIRP_PRODUCT_REQUIREMENTS.md
2. ZIRP_SYSTEM_ARCHITECTURE.md
3. ZIRP_HIGH_THROUGHPUT_ARCHITECTURE.md
4. ZIRP_DATABASE_AND_PERFORMANCE.md
5. ZIRP_VEHICLE_CLASSIFICATION.md
6. ZIRP_CAMERA_AND_RECOGNITION.md
7. ZIRP_NODE_AND_GATE_INTEGRATION.md
8. ZIRP_ANDROID_KIOSK_INTEGRATION.md
9. ZIRP_PAYMENT_INTEGRATION.md
10. ZIRP_SECURITY_AND_RELIABILITY.md
11. ZIRP_PERFORMANCE_TEST_REPORT.md
12. ZIRP_INSTALLATION_AND_OPERATIONS.md

Do not maintain duplicate documents with contradictory architectures.

## 21. ENGINEERING OPERATING RULES

- Think from first principles.
- Understand before modifying.
- Prefer reliable simplicity.
- Preserve working camera improvements.
- Eliminate duplicate business logic.
- Avoid unnecessary microservices.
- Avoid unnecessary infrastructure.
- Do not use the database as an unbounded message queue.
- Do not use Redis as the source of financial truth.
- Do not use the UI as the source of access authority.
- Do not trust simulated payment success.
- Do not treat unverified government status as authorization.
- Do not block camera acquisition with database operations.
- Do not let one lane block another.
- Never sacrifice transaction integrity for speed.
- Never lose committed financial events.
- Make incremental, reviewable commits.
- Run regression tests after every meaningful change.
- Preserve production data.
- Never perform unauthorized physical hardware operations.

## 22. DEFINITION OF SUCCESS

ZIRP must reliably manage the complete lifecycle of every vehicle.

A vehicle enters, is identified and classified, receives the applicable access decision, and is recorded.

A casual visitor receives a QR receipt, pays through an authorized payment channel and exits after verified payment.

A season or VIP vehicle receives access through its valid entitlement.

A government or exceptional vehicle receives access through an appropriately approved temporary authorization without requiring permanent vehicle registration.

The system must support concentrated arrivals, multiple simultaneous lanes, multiple Edge Nodes, an Android autopay kiosk and centralized financial management.

It must remain responsive, recoverable, auditable and financially accurate.

**The objective is not to make the software bigger. It is to make ZIRP process more vehicles, more reliably, with less operational friction and fewer opportunities for error or revenue leakage.**

Start with Phase 1. Establish the actual project state, understand the working implementation and produce the architecture audit.

Then proceed systematically through implementation and verification.

Do not stop at documentation or recommendations. Deliver the working product.
