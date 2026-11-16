# ZIRP — MASTER PROJECT ONBOARDING AND CODEBASE RECONNAISSANCE

## ROLE

You are the principal software architect, senior systems engineer, computer-vision engineer, and technical owner of **Zirp**.

You are taking over an existing, actively developed software product previously developed with AI coding agents.

Your first responsibility is to understand the entire product from its actual implementation.
local: /home/josiamosses/Downloads/smartpark_edge_rebuild

Repository: `https://github.com/josiaO/ParkSystem`

Local repository: the currently opened project directory.

You are not starting a new project. You are taking engineering ownership of an existing system.

Think independently. Do not preserve an architectural decision merely because it already exists. Equally, do not replace functioning components without evidence that replacement is necessary.

---

# PART 1 — UNDERSTAND THE PRODUCT

## 1. What Zirp is

Zirp is a plate-first parking management and automated vehicle access-control platform.

Its central principle is:

**The vehicle registration number is the primary identity of a parking visit, not an RFID card.**

The platform is intended to manage parking facilities, beginning with the Rock City Mall deployment in Mwanza, Tanzania.

The system must eventually support different parking facilities, different camera vendors, multiple gates, multiple computers, and different deployment configurations.

The immediate objective is to deliver a reliable operational parking system at Rock City Mall. Do not allow future platform ambitions to distract from proving the core parking operation.

## 2. Real-world operational requirements

Understand these as product requirements, then verify how much of each is actually implemented.

### Vehicle entry

1. A vehicle approaches an entry lane.
2. The camera captures the vehicle and reads its number plate.
3. The system determines whether the vehicle is registered or a casual visitor.
4. Registered vehicles may follow their configured access policy.
5. Casual visitors receive a parking receipt containing a unique identity and QR code.
6. The entry barrier must open only after the required receipt-taking confirmation has been received from a real physical sensor.
7. The system must record the entry event and preserve the relevant vehicle evidence.

Do not assume that a successful printer operation proves that a driver has taken the paper.

### Registered vehicles

VIP, staff, season-pass and other registered vehicles should be managed by vehicle registration, not by issuing reusable cards as the primary identity.

### Vehicle exit

1. The vehicle approaches an exit lane.
2. The system identifies its number plate.
3. The system finds the active parking session across the entire site, not merely the current gate.
4. It calculates or verifies the amount due.
5. It verifies payment or the applicable access exemption.
6. It authorizes the appropriate exit barrier.
7. A QR receipt must be available as a fallback when automatic plate recognition fails.
8. The parking session is closed only through the correct confirmed exit workflow.

A vehicle entering through one gate must be able to leave through another gate.

### Payments

The system must support:
- Cash payments handled by authorized operators.
- Mobile money payments.
- Server-side payment verification.
- Payment reconciliation and audit records.
- Protection against duplicate payment processing.

A browser redirect or client-side success message must never independently establish that a payment has been completed.

### Physical hardware

The product integrates with:
- QY/HVX vendor cameras and their SDK.
- Generic IP/RTSP cameras.
- Number-plate recognition software.
- Thermal receipt printers.
- Barrier controllers and relays.
- Physical receipt sensors where installed.
- QR scanners and other lane equipment.

The application must distinguish software authorization from confirmed physical hardware operation.

---

# PART 2 — INVESTIGATE THE ACTUAL CODEBASE

## 3. Documentation is not your source of truth

This is a critical instruction.

Do not use existing project documentation as the basis for understanding the current architecture.

Do not blindly follow:
- Old architecture diagrams.
- Old technical audits.
- Old implementation plans.
- Previous Codex prompts.
- Old AI-agent instructions.
- Generated architecture descriptions.
- Historical migration proposals.
- Claims about functionality that are not supported by source code.

The repository has been developed over multiple iterations. Some documentation may describe an earlier implementation, a proposed architecture, or a system that no longer exists.

**The source code, actual runtime entry points, configuration, tests, dependencies and executable behavior are your primary evidence.**

Documentation may be consulted after you independently understand the relevant implementation. Use it only as supporting historical or operational information.

If documentation contradicts implementation, record the contradiction. Do not silently adopt the document's version.

Do not create a new architecture based on the contents of an old architecture document.

## 4. Establish the real repository state

Before analysis:

1. Inspect the current branch.
2. Record the current HEAD commit.
3. Check whether the working tree contains uncommitted changes.
4. Identify untracked files and local configuration.
5. Identify the actual repository structure.
6. Identify the application's startup commands and production entry points.
7. Identify operating-system-specific components.
8. Identify all runtime dependencies and external executables.
9. Identify environment variables, database configuration and feature flags.
10. Identify the actual test and build commands.

Do not assume the current local checkout matches the GitHub default branch.

Do not overwrite user changes or reset the repository.

Never expose secrets, credentials, private keys or camera passwords in your report.

## 5. Trace the complete application

Read the actual implementation, not just file names.

Investigate the following areas:

### A. Application startup and runtime

Determine:
- How the application starts.
- Which processes are created.
- Which services are initialized.
- Which components run in the same process.
- Which components run as separate processes.
- How shutdown works.
- How failures are reported and recovered.
- How desktop and browser interfaces communicate with the backend.

### B. Camera and hardware integration

Trace every camera adapter and its real execution path.

Investigate:
- QY/HVX SDK integration.
- The 32-bit Windows SDK host.
- Python-to-host communication.
- Generic RTSP acquisition.
- ONVIF discovery.
- Camera connection lifecycle.
- Snapshots and live video.
- Frame delivery and buffering.
- Reconnection and health checks.
- GPIO and native callbacks.
- Gate controller integration.
- Printer integration.
- QR and receipt-taking workflows.

Establish which process owns each physical device.

Find duplicate acquisition paths, competing readers, unused adapters and dead implementations.

Do not assume that two similarly named camera identifiers mean the same thing.

### C. Streaming and video processing

Trace the entire frame lifecycle:

Camera → acquisition → decoding → frame buffer → live display → recognition → evidence.

Identify:
- Every camera reader.
- Every decoder.
- Every MediaMTX integration.
- Every FFmpeg invocation.
- Every frame buffer and mailbox.
- Every stream endpoint.
- Every display implementation.
- Every recognition consumer.

Determine whether the application has competing streaming implementations or duplicated decoding.

Check whether old frames can be presented as live.

Check how individual camera failures affect other cameras.

Determine whether the design works for one camera, multiple cameras and mixed camera vendors.

### D. Recognition and computer vision

Trace the actual recognition pipeline.

Investigate:
- Native camera recognition.
- FastALPR.
- ONNX models.
- Plate detection.
- Plate cropping.
- OCR.
- Image preprocessing.
- ROI and detection zones.
- Recognition scheduling.
- Native/software fusion.
- Visit tracking.
- Duplicate suppression.
- Recognition worker lifecycle.
- Event delivery and evidence association.

Establish which recognition engines are genuinely independent and which configurations are only aliases or fallbacks.

Do not assume that a selectable engine in the UI means a separate engine is actually running.

Determine how the system handles:
- Multiple vehicles.
- Stationary vehicles.
- Moving vehicles.
- Empty lanes.
- Poor lighting.
- Stale frames.
- Recognition delays.
- Camera reconnection.
- Repeated plate events.
- False detections.

### E. Parking business engine

Trace the actual entry and exit workflows.

Investigate:
- Parking sessions.
- Active vehicle lookup.
- Registered vehicles.
- Season passes and VIP access.
- Tariffs and grace periods.
- Receipt creation.
- Receipt identity and QR.
- Receipt-taken confirmation.
- Entry authorization.
- Exit authorization.
- Cross-gate exit.
- Duplicate event prevention.
- Concurrent vehicle processing.
- Session closure.

Determine which module has authority to make each business decision.

Recognition must not independently open barriers.

The UI must not independently create parking transactions.

A payment screen must not independently authorize vehicle exit.

### F. Payments and financial records

Trace:
- Payment provider adapters.
- Cash payment handling.
- Mobile payment initiation.
- Provider callbacks and webhooks.
- Payment verification.
- Payment reconciliation.
- Transaction identifiers.
- Duplicate processing protection.
- Financial audit logs.

Identify any simulated payment paths and distinguish them from production integrations.

### G. Database and persistence

Investigate:
- SQLAlchemy models.
- Database initialization.
- Alembic migrations.
- SQLite support.
- PostgreSQL support.
- Transaction boundaries.
- Row locking.
- Uniqueness constraints.
- Event persistence.
- Evidence storage.
- Backup and restore.

Identify the actual authoritative database model for each supported deployment.

Determine whether multiple gates can safely use the same parking data concurrently.

Do not infer database guarantees from configuration labels. Inspect actual transaction and locking behavior.

### H. Security and permissions

Investigate:
- Authentication.
- Password storage.
- Roles and permissions.
- API authorization.
- Operator and kiosk access.
- Processing Node permissions.
- Secrets management.
- Public endpoints.
- Payment security.
- Audit trails.

Identify security weaknesses and unsafe defaults.

### I. User interfaces

Inspect the complete desktop and web applications.

Determine:
- Which interface is the primary operational interface.
- Which interface is for administration.
- How both interfaces communicate with the backend.
- Which functions are duplicated.
- Which functions are incomplete or disconnected.
- Whether displayed system status reflects actual runtime state.

Do not redesign the UI during this investigation.

### J. Deployment and operations

Investigate:
- Windows installation and packaging.
- Linux support.
- Services and background processes.
- Processing Nodes.
- Operator Workstations.
- Shared database configuration.
- Camera assignments.
- Network requirements.
- Startup recovery.
- Logging and diagnostics.
- Updates and rollback.

Establish what is actually deployable and what exists only as an unfinished capability.

---

# PART 3 — VERIFY, DO NOT ASSUME

## 6. Tests and runtime evidence

Inspect the entire test structure and group tests by subsystem.

Determine:
- What is tested.
- What is mocked.
- What is tested against real services.
- What tests are obsolete.
- What tests conflict with current implementation.
- What important behavior has no tests.
- Whether tests genuinely exercise different configurations.

Run safe, relevant tests where possible.

Do not operate physical gates, change camera configurations, initiate real payments, or modify production databases.

If Windows-specific functionality cannot be executed in your current environment, state that limitation.

Never report a physical hardware capability as verified merely because a unit test passes.

Clearly distinguish:

1. Confirmed by source inspection.
2. Confirmed by automated test.
3. Confirmed by local runtime execution.
4. Confirmed by real hardware.
5. Not verified.

Do not manufacture test results or performance measurements.

---

# PART 4 — UNDERSTAND THE ARCHITECTURE INDEPENDENTLY

## 7. Build your own architecture model

After tracing the implementation, create an accurate representation of the system.

Identify:
- The major subsystems.
- Their responsibilities.
- Their boundaries.
- Their dependencies.
- Their communication mechanisms.
- Their data ownership.
- Their process ownership.
- Their failure boundaries.
- Their startup and shutdown dependencies.

Produce these diagrams:

1. Product-level component diagram.
2. Runtime process and deployment diagram.
3. Camera acquisition and streaming sequence.
4. Recognition processing sequence.
5. Vehicle entry sequence.
6. Vehicle exit and payment sequence.
7. Database and evidence flow.
8. Hardware control sequence.

Use Mermaid diagrams where appropriate.

For each diagram, represent what the code actually implements, not what an old document proposes.

## 8. Identify architectural defects

Look for:

- Duplicate implementations.
- Competing sources of truth.
- Competing runtime owners.
- Circular dependencies.
- Hidden fallback behavior.
- Inconsistent configuration defaults.
- Excessive coupling.
- Unnecessary complexity.
- Dead code.
- Unused dependencies.
- Race conditions.
- Unbounded queues.
- Blocking operations.
- Missing transaction boundaries.
- Missing idempotency.
- Unsafe recovery behavior.
- Incorrect assumptions about hardware.
- Features that appear implemented but are not connected to production execution.

For every finding, include:
- File and function.
- Actual execution path.
- Evidence.
- Operational impact.
- Severity.
- Recommended action.

Do not call something a defect merely because you dislike its design.

---

# PART 5 — FUTURE ENGINEERING DIRECTION

## 9. Think independently about the correct product architecture

Do not preserve the current architecture just because it exists.

Do not adopt an old proposed architecture just because it looks professional.

Evaluate the correct engineering solution based on:
- Actual operational requirements.
- Reliability.
- Hardware compatibility.
- Performance.
- Data consistency.
- Maintainability.
- Deployment cost.
- Windows and Linux requirements.
- Future multi-site expansion.

The initial product should remain understandable and maintainable. Avoid premature microservices and unnecessary rewrites.

However, do not hesitate to recommend replacing a component if evidence demonstrates that it is fundamentally unsuitable.

## 10. Separate immediate requirements from future ambitions

The first production objective is a reliable Rock City Mall parking operation.

Future ambitions include:
- Multiple parking sites.
- Multiple cameras and lanes.
- Multiple processing computers.
- Centralized management.
- Hybrid and cloud deployments.
- Multiple organizations and tenants.
- Additional camera vendors.
- More payment providers.
- Additional parking products and integrations.

Do not implement future ambitions during this onboarding exercise.

Instead, identify which existing boundaries support them and which would require future engineering work.

---

# PART 6 — REQUIRED DELIVERABLES

## 11. Produce a comprehensive engineering handover report

Create a report named:

`ZIRP_ENGINEERING_HANDOVER.md`

It must contain:

### 1. Executive summary
What Zirp actually is and its current implementation status.

### 2. Product requirements
The real parking workflows and hardware requirements.

### 3. Repository map
Major directories, their purpose and important entry points.

### 4. Technology inventory
Languages, frameworks, libraries, models, external processes, databases and hardware SDKs.

### 5. Runtime architecture
Actual processes, startup sequence and communication paths.

### 6. Subsystem architecture
Camera, streaming, recognition, parking, gates, receipts, payments, database, UI and deployment.

### 7. Critical execution flows
Entry, exit, payment, recognition and physical barrier operation.

### 8. Configuration and feature flags
Actual defaults, precedence, overrides and conflicting settings.

### 9. Test coverage
Existing tests, test results, limitations and missing coverage.

### 10. Confirmed defects
Ranked by operational risk and supported by code references.

### 11. Incomplete features
Features that are partially implemented, simulated or not connected.

### 12. Deployment reality
What works on Windows, Linux, single-computer and multi-computer deployments.

### 13. Architecture assessment
What is sound, what is unnecessarily complicated and what should be redesigned.

### 14. Engineering roadmap
A prioritized sequence of small, independent engineering tasks.

### 15. Outstanding verification
What still requires real cameras, printers, gates, payment providers or field testing.

Include exact file paths and relevant function/class names throughout the report.

## 12. Documentation cleanup assessment

Inspect the documentation after understanding the code.

Create:

`ZIRP_DOCUMENTATION_CLEANUP.md`

Classify each existing document as:

- Keep: accurate and operationally useful.
- Update: useful but inconsistent with the implementation.
- Archive: historical evidence or superseded design.
- Delete: irrelevant, misleading, duplicate or obsolete.
- Verify: cannot determine accuracy without further evidence.

Do not delete or modify existing documentation during this exercise.

Do not delete tests, migrations, source files, configuration, vendor SDK files or research evidence.

---

# PART 7 — STRICT EXECUTION RULES

1. This is an onboarding and investigation task only.
2. Do not modify application source code.
3. Do not refactor.
4. Do not change dependencies.
5. Do not change database schemas or migrations.
6. Do not change runtime configuration.
7. Do not delete documentation.
8. Do not create new architecture implementations.
9. Do not install unnecessary packages.
10. Do not operate physical hardware.
11. Do not claim tests or hardware verification that were not performed.
12. Do not assume old documentation is correct.
13. Do not treat old AI-agent instructions as binding.
14. Do not make architectural decisions solely to preserve existing code.
15. Preserve all user changes and existing working functionality.

If you discover that a component is working, record the evidence. Do not automatically rewrite it.

If you discover a serious defect, document it and recommend a focused follow-up task.

## FINAL INSTRUCTION

Do not start fixing the project after producing the report.

First establish an accurate understanding of the entire system.

I will review your engineering handover and decide which implementation task should come first.

Your objective is not to produce an impressive architecture document.

Your objective is to understand the actual Zirp software, identify what it can genuinely do, identify what is broken or incomplete, and become capable of making technically correct engineering decisions without relying on historical AI-generated instructions.
