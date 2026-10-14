# Prioritized improvement and validation plan

Investigation date: 14 October 2026. Static Windows-binary analysis on Linux; no live camera, DLL execution, gate operation, or physical latency measurement. Addresses are preferred virtual addresses (ASLR may relocate them). QY means `VideoDrivers/IPC_QY/IPC_QY.dll`, not the different QY1 copy.

## P0 — Bind evidence to one capture
Evidence: callback ID 0 semantics in Net_Interface.h:2247; reproduced collision and fallback in hvx_sdk.py:298–347,501–516. Change the SDK host, HTTP host, client and native event consumers to carry a host-generated capture token, scoped to camera and connection generation. Preserve vendor ID and original metadata. Resolve exact immutable media by token; return explicit unavailable on misses. Benefit: plate and photo stay associated. Risk: host/client version mismatch; version the event schema and deploy together. Test two ID=0 callbacks, repeated IDs, missing images, eviction, reconnect and interleaved cameras. Rollback: restore matched host/client release; keep evidence export for diagnosis.

## P0 — Make event loss and replay visible
Evidence: native queue maxlen=64 and discarded vendor capture time/vehicle ID; ParkWatch QY has an offline callback path. Add overflow counters and explicit replay/age fields; decide whether a bounded disk spool is required from measured event rates. Keep stale replay from triggering fresh entry decisions. Benefit: detectable gaps and safer reconnect recovery. Risks: clock drift and duplicate replay. Test overflow, invalid timestamps, clock reset, process restart and offline batches using simulated gates. Rollback: retain old envelope reader while disabling new replay ingestion; do not bypass existing session claims.

## P1 — Establish a physical latency and OCR baseline
Modules: recognition_decoder.py, recognition_worker.py, latest_frame.py, media gateway and desktop mailbox. Preserve separate acquisition/OCR/display paths. Add or consolidate stage timestamps, callback counts, queue drops, decode FPS and OCR durations; distinguish source age from receive age. Benefit: identify the actual bottleneck before tuning. Risk: telemetry overhead or sensitive evidence retention; bounded local diagnostics suffice. Test 30-minute runs with both cameras, slow OCR, GUI closed/open, stationary and moving cars, day/night samples and disconnect recovery. Proposed targets are in VIDEO_PIPELINE; report p50/p95/max and errors, not only averages. Rollback: disable extra tracing and restore measured codec/profile settings.

## P2 — Validate reconnect and native ABI
Modules: hvx_sdk.py and packaging/vendor manifest. Record DLL SHA-256, bitness and firmware per deployment. Verify callback delivery after short and long disconnects; check whether Ex plus Ex2 duplicates callbacks. Use correctly declared structures and add a verified connection callback only if supported by the matched header/DLL. Benefit: predictable native recognition recovery. Risk: ABI mismatch can crash the host. Test with a Windows harness first and retain the current host release for rollback. Do not restart video or activate a gate as a recognition-health probe.

## P3 — Evaluate optional capabilities
Compare native-only, FastALPR-only and hybrid on one labeled dataset before policy changes. Enable offline replay, time synchronization, whitelist management or HTTP push only when needed and separately validated. Risks include incorrect time and remote configuration changes. Export configuration first and restore it if acceptance fails. No engine replacement is supported by current evidence.

## Field evidence needed to close the investigation
Capture the running Park.exe module list, selected camera adapter and sanitized camera settings; record both video and native callbacks for a supervised vehicle sequence. Correlate timestamps and ground-truth plates. Test actual Windows DLL compatibility. Observe parking/session decisions with gate outputs simulated. These are the remaining prerequisites to claim reliable real-world camera connection, OCR and low-latency streaming.

This is an investigation and reviewable plan, not authorization inferred from the attached document to deploy or change application behavior. No implementation was made in this research pass.
