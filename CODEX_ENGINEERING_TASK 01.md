## Consolidate Camera Acquisition and Live Streaming

### Mission

Act as the principal engineer responsible for the Zirp parking system.

Your assignment is to make camera connection, frame acquisition, stream distribution and live display reliable and deterministic.

The system must support:

- One camera.
- Multiple cameras.
- All four Rock City cameras operating simultaneously.
- QY/HVX vendor cameras.
- Generic RTSP cameras.
- Independent camera failures and reconnections.
- Stable operator live display.
- Continuous operation without one camera blocking another.

This task concerns camera acquisition and live streaming ONLY.

Do not implement recognition changes, parking workflow changes, payment changes, database redesign, gate-control changes or UI redesign in this task.

---

### 1. Repository investigation rules

Before modifying anything:

1. Inspect the actual Git repository and current checked-out branch.
2. Establish the current HEAD commit.
3. Inspect the complete camera runtime, not just individual files.
4. Trace every camera connection entry point.
5. Trace every frame acquisition path.
6. Trace every stream registration and distribution path.
7. Trace the operator UI's actual live-display endpoint selection.
8. Trace camera reconnection, timeout, restart and health-reporting mechanisms.
9. Inspect all configuration sources and determine their precedence.
10. Inspect callers, tests, installation scripts and deployment configuration.

Search the entire repository for:

- Camera connection functions.
- QY/HVX SDK calls.
- NetSDK host processes.
- RTSP connection creation.
- FFmpeg processes.
- MediaMTX registration and path management.
- MJPEG endpoints.
- WebRTC/WHEP endpoints.
- Snapshot endpoints.
- Frame buffers.
- Camera health checks.
- Reconnection loops.
- Legacy camera providers.
- Media migration flags.
- Camera configuration defaults.

### 2. Documentation and instruction restrictions

Treat the actual source code, runtime behaviour and tests as the evidence.

Do NOT follow old project documentation, old architecture descriptions, old agent instructions, old implementation plans or obsolete generated files as authoritative instructions.

Do not allow old documentation to determine the architecture.

You must independently establish what the software actually does and choose the correct implementation.

Do not recreate or rely on deprecated architecture merely because old documentation describes it.

If old documentation contradicts the source code or the target requirements in this task, ignore it.

### 3. Establish one authoritative camera ownership model

Implement the following ownership boundaries.

**QY/HVX cameras**

- The existing vendor SDK integration is the hardware acquisition authority.
- Preserve the working 32-bit SDK host and Python bridge unless you establish a specific, reproducible defect.
- Do not introduce a second direct RTSP connection to a QY/HVX camera.
- Do not introduce another process that competes with the SDK host for camera ownership.
- Ensure SDK callbacks and acquired frames enter the canonical camera frame interface.
- Ensure camera identity, timestamp and frame-generation information are preserved.

**Generic RTSP cameras**

- MediaMTX must own the physical RTSP acquisition and distribution.
- Do not create independent FFmpeg physical-camera readers for display and recognition.
- FFmpeg may be used as a bounded downstream decoder when required, but it must consume the canonical MediaMTX stream.
- Camera reconnection must be managed by the canonical media owner.

**Common camera interface**

Both camera types must expose a normalized camera interface to the rest of the application.

The interface must provide:

- Camera identity.
- Connection state.
- Latest frame.
- Frame timestamp.
- Frame age.
- Frame generation or sequence identity.
- Actual frame rate.
- Reconnection state.
- Error state.
- Health status.

The camera-specific implementations must not leak vendor-specific behaviour into the business application.

### 4. Enforce one canonical live-stream path

Inspect the current operator display implementation and determine exactly which endpoint it uses.

Establish one authoritative production display path.

The display must:

- Show the correct camera.
- Display fresh frames.
- Detect frozen frames.
- Detect disconnected cameras.
- Recover after camera reconnection.
- Avoid silently displaying old frames as live.
- Avoid multiple competing stream providers.
- Avoid opening additional physical camera connections merely to display video.

Use the existing MediaMTX integration where appropriate.

Do not add go2rtc, Frigate, Agent DVR or another media server.

Do not create a replacement media subsystem before proving that the existing one cannot be corrected.

### 5. Frame lifecycle and isolation

Implement and enforce:

- Independent connection lifecycle for each camera.
- Independent recovery for each camera.
- Bounded frame buffers.
- No unbounded frame queues.
- No uncontrolled FFmpeg process creation.
- No stale frame being represented as current.
- No camera blocking another camera's acquisition.
- Correct cleanup of disconnected streams and processes.
- Correct handling of repeated reconnect attempts.
- Frame generation tracking so frames from an old connection cannot contaminate a new connection.

A camera failure must not terminate the entire camera service or application.

A recovered camera must resume without requiring a complete application restart.

### 6. Configuration consolidation

Inspect every configuration source affecting camera acquisition and live streaming.

Identify conflicting defaults, legacy flags, database overrides and environment variables.

Establish one deterministic production configuration.

Do not allow different modules to independently choose conflicting media providers.

Remove obsolete or competing production selection paths only after verifying that they are no longer needed.

Do not silently change deployment settings in a way that disconnects the installed Rock City cameras.

Provide explicit validation for invalid or incomplete production camera configuration.

Development and simulated operation must be clearly distinguishable from real hardware operation.

### 7. Reliability and observability

Expose measurable per-camera health information:

- Connected/disconnected.
- Last successful frame time.
- Frame age.
- Measured FPS.
- Stream startup duration.
- Reconnection count.
- Time since last reconnection.
- Frozen-frame detection.
- Decoder/process health where applicable.
- Last error.
- Current stream generation.

Do not report a camera as healthy merely because its configuration exists or its process is running.

A camera is operational only when fresh frames are actually arriving.

### 8. Tests required

Add or correct tests for:

1. One QY/HVX camera connection.
2. Multiple QY/HVX cameras.
3. One generic RTSP camera.
4. Multiple generic RTSP cameras.
5. Mixed QY/HVX and generic RTSP cameras.
6. One camera disconnecting while others remain operational.
7. Camera reconnection.
8. Frozen frames.
9. Stale frames from an earlier connection generation.
10. Stream endpoint selection.
11. MediaMTX unavailable.
12. Decoder process termination.
13. Repeated reconnect attempts.
14. Resource cleanup after shutdown.
15. Invalid production configuration.

Use mocks and controlled fixtures for automated tests. Do not pretend mocked tests prove physical hardware reliability.

### 9. Performance constraints

- No unbounded queues.
- No uncontrolled background tasks.
- No duplicate physical camera acquisition.
- No unnecessary database polling in frame-delivery loops.
- No slow external operation blocking camera acquisition.
- No unnecessary image copies.
- No resource leak after repeated reconnects.

Measure performance rather than inventing FPS or latency claims.

### 10. Implementation restrictions

Do not:

- Rewrite the QY/HVX SDK host without a proven defect.
- Rewrite the gate-control implementation.
- Modify recognition algorithms.
- Modify parking session logic.
- Modify payment logic.
- Change database schemas.
- Introduce a new language.
- Introduce a new media server.
- Build a second camera manager.
- Replace existing working components without evidence.
- Perform unrelated refactoring.
- Delete files merely because their names look old.
- Claim physical hardware verification without performing it.

### 11. Required delivery

After implementation, provide:

**A. Before-and-after architecture**

Show the actual old runtime paths and the resulting canonical paths.

**B. Camera ownership table**

For each camera type, identify the single acquisition owner, distribution owner and display consumer.

**C. Files changed**

List every modified, added and removed file with the reason.

**D. Competing paths removed or disabled**

Identify the exact old paths and explain why removing them is safe.

**E. Tests**

List commands executed, results, failures and tests not executed.

**F. Performance evidence**

Report measured frame rate, frame age, reconnect time and resource use where the test environment permits.

**G. Deployment impact**

Identify configuration changes, environment variables, installation changes and rollback instructions.

**H. Remaining hardware verification**

Clearly state which behaviours still require testing against the actual four Rock City cameras.

### Completion criteria

This task is complete only when:

1. Every camera has one authoritative acquisition owner.
2. Every camera has one predictable frame-distribution path.
3. The operator display uses the canonical stream path.
4. One camera failure does not interrupt other cameras.
5. Reconnection does not require restarting the entire application.
6. Old frames cannot masquerade as fresh frames after reconnection.
7. All automated tests for this task pass.
8. The deployment configuration is deterministic.
9. No unrelated subsystem has been rewritten.

Do not start Task 02 (recognition engine) after completing this task. Stop, report the evidence and wait for the next engineering assignment.
