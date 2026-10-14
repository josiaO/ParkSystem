# MISSION: Reverse-Engineer ParkWatch to Improve SmartPark

You are acting as a principal reverse-engineering engineer, Windows systems engineer, computer vision engineer, and software architect.

## PRIMARY OBJECTIVE

Reverse-engineer the existing ParkWatch parking management software to understand its internal architecture, camera communication, video acquisition, license plate recognition, OCR, gate control, event handling, and any other useful capabilities.

Use these findings to improve our existing SmartPark system.

**IMPORTANT: We are NOT rebuilding SmartPark from scratch.**

SmartPark already has working camera connectivity, gate control, receipt printing, and license plate recognition capabilities. Your responsibility is to preserve those achievements while investigating and improving weaknesses.

Do not assume ParkWatch is superior in every area. Establish its behavior through evidence.

---

## PHASE 0 — REPOSITORY DISCOVERY AND BASELINE

Before installing anything or modifying code:

1. Read the entire relevant SmartPark codebase.
2. Identify the existing camera integration modules.
3. Locate the vendor SDK bindings.
4. Identify all video capture, streaming, recognition, and OCR implementations.
5. Trace how camera events become parking sessions.
6. Identify how gate opening and receipt printing are coordinated.
7. Inspect database models, background workers, concurrency, and event queues.
8. Inspect existing tests and performance instrumentation.

Locate the ParkWatch reference files, including, where present:

- `Current_ParkSystem_configs/ParkingSystem/ParkWatch/`
- `CamAPI.h`
- `LprSdk.dll`
- `LPRHelper.h`
- `LPRHelper.cpp`
- `NetSDK.dll`
- ParkWatch executables and configuration files
- Additional SDK libraries, headers, and supporting resources

Discover actual file paths rather than assuming these names or locations are accurate.

Produce an initial architecture comparison and establish measurable baseline performance for SmartPark.

Do not modify working components during this phase.

## PHASE 1 — PREPARE THE REVERSE-ENGINEERING ENVIRONMENT

Determine the operating system and available tools.

Install and configure the following when needed and permitted:

- Ghidra from the official NSA GitHub repository.
- Compatible Java Development Kit.
- Ghidra Headless Analyzer.
- Python-based PE analysis utilities.
- Relevant binary inspection tools.
- Optional Ghidra scripting or MCP integration if it provides reliable automation.

Verify download integrity using official checksums where available.

Prefer isolated tooling and temporary analysis directories.

Use Windows-specific inspection tools where required, including PE inspection, Process Monitor, Process Explorer, and Wireshark.

If operating on Linux, use static analysis of Windows binaries where possible. Do not assume Windows-specific runtime behavior can be reproduced on Linux.

Never execute unknown binaries on a production parking server.

## PHASE 2 — COMPLETE PARKWATCH BINARY INVENTORY

Recursively examine the provided ParkWatch installation and supporting files.

Identify:

- Main executables.
- Native and managed DLLs.
- COM/OCX components.
- Configuration files.
- Database dependencies.
- Network libraries.
- Video decoding libraries.
- OCR or image-processing dependencies.
- Hardware integration libraries.
- Supporting services.

Determine binary architecture, exported symbols, imported functions, calling conventions, and dependencies.

Construct a dependency graph.

Identify which components are actually referenced by ParkWatch, rather than assuming that every DLL in its installation folder is used.

## PHASE 3 — CAMERA COMMUNICATION INVESTIGATION

This is one of the highest-priority investigations.

Determine exactly how ParkWatch communicates with the existing ALPR cameras.

Investigate:

1. Camera discovery mechanisms.
2. IP address discovery and configuration.
3. Authentication and session establishment.
4. SDK initialization.
5. Connection persistence.
6. Connection failure detection.
7. Automatic reconnection.
8. Camera status monitoring.
9. Network protocol usage.
10. Camera-specific configuration.

Pay particular attention to vendor SDK functions such as:

- `Net_FindDevice`
- `Net_ConnCamera`
- `Net_DisConnCamera`
- `Net_StartVideo`
- `Net_GetImage`
- `Net_ImageSnap`
- `Net_RegImageRecv`
- `Net_RegReportMessEx`
- `Net_SetHttpPushSetup`
- `Net_SetPushTargetSetup`

Treat these names as investigative leads, not confirmed descriptions of their behavior.

Trace call sites, parameters, callback registration, data structures, memory ownership, and error handling.

Determine whether ParkWatch relies on persistent connections, polling, push notifications, or a combination.

Document verified connection sequences and provide safe integration examples.

## PHASE 4 — VIDEO STREAMING ARCHITECTURE

SmartPark has experienced delayed video, stale frames, and recognition that sometimes stops processing new vehicles.

Investigate how ParkWatch acquires and handles live video.

Questions to answer:

- Does ParkWatch use RTSP, HTTP, a proprietary transport, or SDK-managed video?
- Does the SDK deliver encoded packets or decoded frames?
- Which component performs video decoding?
- Are camera video streams separate from recognition events?
- Does ParkWatch maintain dedicated camera threads?
- Does it use callbacks, polling, or message queues?
- Does it discard old frames?
- How are timestamps and frame buffers handled?
- How does it recover from stalled video?
- Is video acquisition independent of OCR processing?

Trace relevant native functions and data flows.

Compare ParkWatch with SmartPark's current architecture.

Investigate whether SmartPark's observed latency originates from:

- Camera stream buffering.
- Decoder queues.
- Blocking SDK calls.
- Excessive frame processing.
- Synchronous OCR.
- Python threading or process contention.
- GUI rendering.
- Database operations.
- Network instability.

Do not conclude that the SDK is responsible without evidence.

Recommend changes that minimize end-to-end latency while preserving reliability.

## PHASE 5 — LICENSE PLATE RECOGNITION AND OCR

This is the most important research question.

Determine whether ParkWatch uses:

A. OCR performed inside the camera.

B. OCR performed on the Windows host.

C. A hybrid architecture combining camera recognition and software OCR.

Do not guess.

Look for evidence in:

- SDK recognition callbacks.
- Recognition event structures.
- Imported OCR libraries.
- Model files.
- Camera configuration.
- Network payloads.
- Image-processing code.
- Application event handlers.

Determine whether recognition events contain:

- Plate text.
- Confidence scores.
- Plate bounding boxes.
- Vehicle snapshots.
- Full-frame images.
- Timestamps.
- Camera identifiers.
- Vehicle attributes.
- Recognition event identifiers.

Determine how ParkWatch handles:

- Partial plates.
- Multiple recognition results for one vehicle.
- Repeated events.
- Low-confidence recognition.
- Vehicles remaining stationary.
- Vehicles entering or leaving the camera's field of view.
- Missing or malformed plate data.

Compare the discovered recognition mechanism with SmartPark's existing fast-alpr implementation.

Evaluate three integration strategies:

1. Camera OCR as primary recognition.
2. fast-alpr as primary recognition.
3. Hybrid recognition with camera OCR and fast-alpr as a fallback or validation mechanism.

For each strategy, assess latency, CPU usage, accuracy, hardware compatibility, failure handling, and maintainability.

Do not replace fast-alpr unless testing supports the decision.

## PHASE 6 — EVENT PROCESSING AND DUPLICATE PREVENTION

Investigate how ParkWatch transforms recognition results into parking events.

Trace:

Camera → Recognition → Event validation → Parking logic → Database → Gate command

Determine how ParkWatch prevents repeated recognition of the same stationary vehicle from creating multiple transactions.

Compare this behavior with SmartPark.

Design robust event processing that includes:

- Per-camera state.
- Event identifiers.
- Idempotency keys.
- Recognition confidence handling.
- Plate normalization.
- Debouncing.
- Time-window deduplication.
- Vehicle presence tracking where feasible.
- Database uniqueness constraints.
- Transaction-safe session creation.

Do not use plate text alone as a permanent unique event identifier.

Ensure that a vehicle remaining at the gate does not create duplicate sessions.

Also ensure that a later legitimate visit by the same vehicle is not incorrectly rejected.

## PHASE 7 — GATE CONTROL AND HARDWARE INTEGRATION

Investigate how ParkWatch controls the boom barriers.

Determine:

- Which SDK functions control relays.
- How gate commands are constructed.
- Whether acknowledgments are available.
- How gate states are monitored.
- How commands are synchronized with recognition.
- Whether retries can cause repeated relay activation.
- How manual overrides work.
- Whether sensor inputs or safety interlocks are supported.

Compare these capabilities with SmartPark's working gate-control implementation.

Preserve existing operational safety.

Do not perform live relay tests without explicit authorization and an approved testing procedure.

## PHASE 8 — DISCOVER ADDITIONAL CAPABILITIES

Do not restrict the investigation to known functions.

Investigate potentially useful capabilities including:

- Camera health monitoring.
- Firmware information.
- Remote camera configuration.
- Exposure and night-mode settings.
- Snapshot acquisition.
- Vehicle color and classification.
- Recognition confidence metadata.
- Blacklists and whitelists.
- Offline event storage.
- Event replay.
- HTTP event pushing.
- Camera time synchronization.
- Multi-camera coordination.
- Diagnostic logs.
- Watchdog and recovery behavior.

For each capability, determine whether it is:

- Confirmed and usable.
- Present but not validated.
- Unsupported.
- Unknown.

Identify opportunities to improve SmartPark without introducing unnecessary complexity.

## PHASE 9 — SMARTPARK ARCHITECTURE REVIEW

After completing the ParkWatch investigation, inspect SmartPark again.

Evaluate:

- Camera acquisition architecture.
- Native SDK integration.
- Callback lifecycle.
- Thread safety.
- Memory management.
- OCR scheduling.
- Frame buffering.
- CPU and memory utilization.
- Database transaction handling.
- Gate command reliability.
- Service uptime.
- Recovery after camera disconnects.
- GUI responsiveness.

Propose an architecture in which:

- Camera acquisition remains independent of expensive OCR work.
- Recognition events are handled asynchronously where appropriate.
- Stale video frames do not accumulate indefinitely.
- Each camera can recover independently.
- Database writes are idempotent.
- Gate commands remain safe and auditable.
- Existing hardware integration is preserved.

Avoid adding Redis, Celery, message brokers, or microservices without a demonstrated need.

## PHASE 10 — VALIDATION AND IMPLEMENTATION

Before modifying SmartPark, produce a prioritized implementation plan.

Classify findings into:

P0 — Critical correctness and operational reliability.

P1 — Streaming latency and recognition performance.

P2 — Recovery, diagnostics, and maintainability.

P3 — Additional features.

For each proposed modification, provide:

- Evidence from ParkWatch.
- The corresponding SmartPark module.
- The observed problem.
- Proposed technical change.
- Expected benefit.
- Potential risks.
- Test procedure.
- Rollback strategy.

Implement changes incrementally on a dedicated Git branch only after the analysis and proposed plan have been reviewed and approved.

Preserve existing working camera connectivity, gate control, and receipt printing.

Use mock cameras, recorded data, or isolated test environments where possible.

Do not issue real gate commands during automated testing.

## REQUIRED DELIVERABLES

Create the following investigation documents in a dedicated research directory:

1. `PARKWATCH_BINARY_INVENTORY.md`
2. `PARKWATCH_CAMERA_PROTOCOL.md`
3. `PARKWATCH_VIDEO_PIPELINE.md`
4. `PARKWATCH_OCR_ARCHITECTURE.md`
5. `PARKWATCH_EVENT_PROCESSING.md`
6. `PARKWATCH_GATE_CONTROL.md`
7. `PARKWATCH_DISCOVERED_CAPABILITIES.md`
8. `SMARTPARK_GAP_ANALYSIS.md`
9. `SMARTPARK_IMPROVEMENT_PLAN.md`

Include reproducible analysis scripts and relevant Ghidra project outputs separately.

For every significant reverse-engineering conclusion, cite the binary, function address or symbol, relevant call site, and any runtime evidence.

Mark uncertain conclusions clearly.

## FINAL INSTRUCTION

Do not stop at listing exported DLL functions.

Investigate how ParkWatch actually uses them.

The objective is to understand the full operational pipeline and discover practical ways to improve SmartPark's reliability, performance, recognition accuracy, and camera interoperability.

Prioritize evidence over speculation, incremental improvements over rewrites, and operational safety over convenience.

Start with repository discovery and binary inventory. Do not modify SmartPark until the findings and implementation plan are ready for review.
