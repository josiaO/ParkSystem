# SmartPark Edge — Agent Instructions

## Mission

Build SmartPark Edge as a reliable, modular, low-latency vehicle intelligence and parking platform. Prefer correctness, observability, bounded resource usage, and graceful degradation over adding features quickly.

## Non-negotiable invariants

1. Do not break the working HVX/QY camera path.
   - Keep the 32-bit Windows SDK host isolated from the 64-bit Site Service.
   - Do not guess undocumented NetSDK callback layouts, GPIO channels, or relay states.
   - Preserve working SDK login, native ALPR callbacks, snapshots, and verified gate control.

2. One subsystem owns each responsibility.
   - MediaMTX owns network video fan-out.
   - SmartParkMediaService is the only process allowed to start/stop MediaMTX.
   - Site Service owns application/API/domain orchestration.
   - Recognition workers own software ALPR inference.
   - HVX SDK host owns vendor DLL calls.
   - UI is a client; closing it must not stop parking, recognition, or payment handling.

3. Real-time video must never build a backlog.
   - Latest-frame-wins for AI.
   - No unbounded queues.
   - No per-frame process spawning.
   - No 25 fps HTTP snapshot polling as a live transport.
   - Do not run WebRTC and snapshot polling simultaneously for the same pane.
   - Prefer camera substream for LIVE/DETECT and main stream for evidence snapshots.

4. Recognition must be independent from operator viewing.
   - A hidden/closed UI must not stop plate detection.
   - Generic RTSP/ONVIF cameras use software recognition.
   - HVX may use native recognition, software verification, or hybrid policy.
   - Slow inference must drop stale AI frames, never delay live display or gate decisions.

5. Country behavior is policy, not hard-coded product behavior.
   - Default normalization is country-neutral.
   - Tanzania-specific OCR corrections/validation must only run when a Tanzania site profile explicitly enables them.
   - Never silently mutate globally valid plates according to Tanzania positions.

6. Safety and gate control.
   - Do not invent hardware mappings.
   - Preserve commissioning/shadow/production modes and physical_control_verified.
   - Gate commands require durable audit records and idempotency.
   - A media/AI failure must not crash the Site Service.

7. Payments.
   - PaymentTransaction is the financial authority.
   - Browser redirect/success UI is never proof of payment.
   - Provider callbacks must be authenticated and idempotent.
   - Use Decimal or integer minor units for money; avoid float in financial calculations.

## Target runtime architecture

Camera
  -> MediaMTX (one upstream per stream role)
      -> WebRTC/HLS for browser/operator live view
      -> local RTSP detect stream for Recognition Worker
      -> evidence/main stream for snapshots when required

HVX camera
  -> 32-bit hvx_sdk_host
      -> native ALPR event / SDK image / verified GPIO

Recognition Provider
  -> normalized PlateRecognized event
      -> parking/access/security core
          -> session/payment/access decision
              -> gate adapter

## Media migration

DIRECT_LEGACY remains a rollback path until MediaMTX passes soak tests. Do not maintain two active live transports for one UI pane.

The authoritative provider seam is:
- app/infrastructure/media/registry.py

No application module should make independent provider-selection decisions outside this boundary.

## Required verification for every meaningful change

Run the narrowest relevant tests first, then the complete suite.

At minimum:
- python -m compileall app tools
- pytest -q tests/test_media_gateway.py
- pytest -q tests/test_migration_architecture.py
- pytest -q tests/test_stability.py
- pytest -q tests/test_alpr.py
- pytest -q tests/test_modules.py
- pytest -q

If a Windows/HVX change cannot be exercised in the current environment, state exactly what remains hardware-dependent. Never claim it was verified when it was not.

## Performance acceptance targets

On a normal LAN with healthy cameras:
- live operator frame age should normally remain <500 ms
- AI input frame age should normally remain <1000 ms
- no growing frame queues
- no unbounded FFmpeg child count
- one upstream stream per required camera/role, not one per viewer
- memory should stabilize during a multi-hour soak
- reconnect attempts use backoff and do not create process storms

## Change discipline

- Prefer small coherent commits.
- Add regression tests for every fixed architectural bug.
- Do not delete the legacy path until the replacement is tested.
- Do not introduce Redis/Celery merely for speed. Add external infrastructure only when a concrete distributed durability/throughput requirement justifies it.
- Keep docs synchronized with the code.
