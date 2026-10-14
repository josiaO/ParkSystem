from pathlib import Path
import json
D=Path(__file__).resolve().parent
intro='Investigation date: 14 October 2026. Static Windows-binary analysis on Linux; no live camera, DLL execution, gate operation, or physical latency measurement. Addresses are preferred virtual addresses (ASLR may relocate them). QY means `VideoDrivers/IPC_QY/IPC_QY.dll`, not the different QY1 copy.\n\n'
reports={
'PARKWATCH_BINARY_INVENTORY.md':'''# Binary inventory
351 files with EXE/DLL/OCX suffixes were inventoried recursively, including SHA-256, size, architecture, ordinary imports, import-slot addresses, and named exports. 349 parsed as PE: 286 x86 and 63 x64; 17 have CLR headers. Two suffix-matching files did not parse: DUCP_DLL.dll is reported as data by `file`; System.ocx as text. Neither should be assumed loadable.

Park.exe is a native x86 Windows GUI executable, preferred base 0x400000. A folder containing x64 libraries does not mean its x86 process can load them. The deployment's actual module list is still needed.

Machine-readable evidence: `evidence/inventory.json`. Reproduce with `python3 research/parkwatch/analyze.py` from the repository root (Python standard library and GNU objdump). The script never executes target files. Disassembly and import references are in `evidence/*.asm` and `*.calls.json`. The parser covers ordinary imports, not delay imports or dynamically resolved dependency closure. Hashes establish artifact identity, not publisher authenticity.

Confirmed static links: Park.exe imports DVNETSDK.DLL capture/device/stream functions. QY imports NetSDK.dll and AppBase thread functions; QY exports the CAM_* adapter interface. QY1 exposes a similar interface but differs in code and callback registration. Do not interchange the copies on filenames alone.

Park.exe also dynamically loads SimpleLPRDevAgent.dll: 0x4249ff pushes its string; 0x424a04 calls LoadLibraryA through thunk 0x8975ba / IAT 0x9436a4; 0x424a27 resolves LPR_LoadApis through GetProcAddress thunk 0x8974b2 / IAT 0x9435f4; 0x424a3f invokes it. This is stronger evidence than library presence alone.

Supporting files include CamAPI.h, LPRHelper.cpp/.h, SimpleLPRDev*.h, QY Net_Interface.h and Net_Setup.h, multiple vendor adapters, decoding libraries, SQL/configuration files and logs. Their presence alone does not establish use. No Ghidra project was created: GNU disassembly sufficed for the documented call paths. The entire application and every dynamic dependency have not been decompiled.
''',
'PARKWATCH_CAMERA_PROTOCOL.md':'''# Camera connection and recognition transport
The QY adapter's connection path contains these calls, in instruction order with success/error branches:

1. Net_AddCamera at 0x10005819; rejects handle -1.
2. Net_RegReportMessEx at 0x10005845; callback 0x10006c40, user context supplied.
3. Net_ConnCamera at 0x10005889; pushes timeout 5 and the configured port as an unsigned short. This inspected path uses ConnCamera, not ConnCameraEx.
4. On connection success, Net_RegOffLineClient at 0x100058ba.
5. Net_RegImageRecvEx at 0x10005908; callback 0x10006c80.
6. Net_RegOffLineImageRecvEx at 0x10005956; callback 0x10006cc0.
7. Additional whitelist report/control callbacks at 0x100059a4 / 0x100059f2.

Net_DisConnCamera is called at 0x10005b5b. Net_Init and Net_SetSynTimePeriod occur at 0x10005608 / 0x10005647. QY1 has different call sites and does not import the offline image callback found in QY.

The supplied UTF-16 Net_Interface.h documents ConnCameraEx as establishing control signaling and image reception with SDK reconnect after first success (lines 1923–1933). It explicitly requires image callback registration for every connection (2240–2258). The decoded review copy is `evidence/Net_Interface.utf8.h`. These are documented vendor semantics, not measured reconnect performance. QY's report callback 0x10006c40 appears to log and return; no callback rearm was identified in that short function.

SmartPark already uses AddCamera → report callback → authenticated ConnCameraEx (ConnCamera fallback) → state query → offline registration → image registration. It retains ctypes callbacks and rearms after an observed disconnected-to-connected transition, with bounded retry backoff (`tools/hvx_sdk_host/hvx_sdk.py`, `_refresh_recognition`). Polling can miss a brief transition. Registering successfully is not evidence that a new vehicle result has arrived.

Still unverified: which adapter the deployed Park.exe actually selects; actual camera/firmware/port; packet-level transport and authentication; transient disconnect behavior; whether both image callback versions produce duplicate delivery. No discovery probes or network configuration changes were performed.
''',
'PARKWATCH_VIDEO_PIPELINE.md':'''# Video, capture, and latency
QY calls Net_StartVideo at 0x10005bd9 and Net_StopVideo at 0x10005c47. The header defines StartVideo(handle, streamType, HWND), so this path is SDK-managed playback into a Windows window. Net_ImageSnap at 0x10005cc8 is a separate snapshot operation. Its header says image information is delivered through the registered capture callback. Calling a snapshot is not a continuous video strategy.

CamAPI.h exposes CAM_StartStream separately from CAM_SetCaptureCallback/CAM_Capture. QY's native image callback 0x10006c80 forwards metadata and picture pointers to 0x10006d40; it does not obtain plate text by scraping displayed video. Underlying RTSP versus proprietary transport, decoder buffering, frame-discard policy and measured latency are unresolved. Bundled RtspRecvSdk/DecodeSdk do not by themselves prove the active transport or zero buffering.

SmartPark already implements bounded latest-frame buffers (`app/services/latest_frame.py`), a one-notification GUI mailbox (`app/desktop/frame_mailbox.py`), a persistent local MediaMTX decoder (`app/services/recognition_decoder.py`), and asynchronous OCR dispatch (`app/recognition_worker.py`). The decoder reads only local port 8554, selects the newest complete JPEG in accumulated bytes, and times out when no complete frame arrives. These protections do not measure delay already accumulated at the camera or upstream decoder.

Critical measurement distinction: FrameSample.received_at is assigned at buffer insertion. A freshly received old camera frame can have low local age. Host receive-age alone cannot certify low glass-to-glass latency. Preserve camera timestamp/PTS where available and use a filmed clock or LED test at the scene to establish actual delay.

Acceptance proposal, not measured performance: target live p95 <=500 ms on the site LAN, recognition p95 <=1 s from a readable plate, recovery <=10 s after a brief disconnect, with no increasing delay over a 30-minute run. Record actual distributions before accepting or revising targets. Test both lanes, empty lanes, stationary vehicles, slow OCR and UI open/closed. Separate native event delay, decoder delay, OCR duration and display delay. Tune bitrate/GOP/FPS only after measuring; lower resolution can reduce OCR accuracy.
''',
'PARKWATCH_OCR_ARCHITECTURE.md':'''# Recognition architecture
Evidence supports both camera-native recognition and a host OCR integration path, but does not establish which is enabled for each deployed lane.

Camera path: QY registers Net_RegImageRecvEx at 0x10005908. Callback 0x10006c80 calls 0x10006d40. That processor reads plate text at metadata +0x8 (0x10006e1d), confidence at +0x40 (0x10006f14), box coordinates at +0x18/+0x1a/+0x1c/+0x1e (0x10006f21 onwards), and timestamp text at +0x26 (0x10006f59). These offsets match T_ImageUserInfo. It passes image information onward at 0x100070ca. This is application-adapter consumption of recognized metadata, not just SDK exports.

Host path: Park.exe has the verified dynamic SimpleLPRDevAgent loader described in the inventory. Supplied LPRHelper.cpp loads LPR_LoadApis, creates one static engine and calls apis.Recognize/RecognizeAll on image filenames, returning plate text, confidence and a box. This proves available host recognition code; the actual runtime branch, input selection and native/host fusion policy remain unverified. The helper's one-shot initialization flags are set before success, so its retry behavior is not a pattern to copy blindly.

Strategies to evaluate on the same labeled local day/night captures:

- Camera primary: lowest expected host CPU and independent of browser video; depends on camera OCR quality, firmware and callback reliability. Confidence scales require calibration.
- FastALPR primary: consistent host pipeline across vendors; needs readable frames and sufficient compute. Measure inference contention and dropped frames.
- Hybrid: native candidate plus bounded host fallback/validation; may improve coverage but needs event/image correlation and conflict handling. Never interpret two engines disagreeing as permission to open a gate.

Keep the existing FastALPR implementation while benchmarking exact-plate accuracy, missed vehicles, false accepts, CPU and p95 latency. No accuracy claim can be made from binary inspection.

SmartPark registers both Ex and Ex2 using the same callback reading T_ImageUserInfo. The header's Ex2 structure has the same initial fields and additional tail data, so this is not by itself proof of a memory-layout fault. Full Ex2 typing and double-delivery behavior need validation against the exact deployed DLL.
''',
'PARKWATCH_EVENT_PROCESSING.md':'''# Event processing and capture identity
CamAPI.h provides recognition source, capture timestamp, plate confidence and nRecInterval (documented same-plate minimum interval in seconds). This does not establish Park.exe's database transaction or deduplication behavior. QY online and offline callbacks both forward to 0x10006d40, passing different online/offline flags. Offline replay therefore deserves explicit handling, not automatic treatment as a current arrival.

Confirmed SmartPark defect under synthetic input: `_on_image` stores media by `(handle, image_id)` while retaining multiple event rows. The vendor callback documentation says image_id=0 can identify realtime results, rather than a unique capture. Two such callbacks overwrite the same media entry. `event_jpeg_for` and `event_crop_for` also return the latest media when an explicitly requested event cannot be found. This can associate another capture's image with a result.

Reproduction: `.venv/bin/python research/parkwatch/reproduce_media_collision.py`. Result: `evidence/media-collision.txt`. It invokes the real Python callback/storage functions with synthetic metadata and bytes; no vendor DLL or device is used. The HTTP host exposes these lookups at hvx_host.py:139–150; the client passes image IDs at hvx_client.py:153–162. Physical frequency and downstream consequences are not yet measured.

Also, `_on_image` assigns captured_at_epoch from host time and does not preserve acSnapTime, uiVehicleId or ucSnapshotIndex in its output row. This loses evidence useful for replay detection and timing. Bounded deque(maxlen=64) drops oldest events silently when full; this bounds memory but is not a durable capture guarantee.

Proposed event envelope: camera identity + connection generation + host capture sequence; preserve original vendor ID, vehicle ID, camera timestamp and host receive monotonic time separately. Store immutable metadata/media together. Missing event evidence must be explicit. Keep frame dropping separate from transaction-event retention.

SmartPark already has visit-scoped session lookup, durable claims and unique constraints in parking_sessions.py and migration 0007_visit_idempotency.py. Preserve these. Test repeated stationary detections, zero/reused vendor IDs, reconnect, offline replay, concurrent arrivals and a later legitimate visit by the same plate. Plate text alone is not an event identity.
''',
'PARKWATCH_GATE_CONTROL.md':'''# Gate control
Static QY call references show Net_GateSetup at 0x10005ed4, 0x10005f15 and 0x10005f56; QY1 has a different implementation with a call at 0x10005f6a. CamAPI.h defines OPEN_RELAY=100, CLOSE_RELAY=101 and PULSE_RELAY=102 at the adapter command level. These constants must not be equated to physical GPIO indices or SDK state bytes without tracing each mapping.

Net_TransRS485HexDataEx is called at 0x1000635e, indicating a serial-output path. Presence of a successful SDK return does not establish barrier movement, sensor state, interlock satisfaction or transaction commitment.

SmartPark already has gate adapters and audited parking decisions. This investigation made no gate or printer changes. Retain existing hardware mappings and use simulated actuators for event tests. Before any physical acceptance test, explicitly arrange a supervised test lane. Retry only with verified semantics: repeated relay pulses are not inherently idempotent. End-to-end Park.exe database-to-gate sequencing, acknowledgment interpretation and safety interlocks remain unresolved.
''',
'PARKWATCH_DISCOVERED_CAPABILITIES.md':'''# Additional capabilities and confidence
Confirmed static adapter calls (not live acceptance): QY time synchronization via Net_SetSynTimePeriod at 0x10005647; whitelist deletion/setup/send at 0x1000454c/0x10004809/0x10004852; offline client/image registration at 0x100058ba/0x10005956; snapshots at 0x10005cc8; serial writes at 0x1000635e; SDK video at 0x10005bd9.

Documented metadata: plate confidence, box, vehicle attributes, timestamp, vehicle ID and capture index in Net_Interface.h; capture source and generic plate fields in CamAPI.h. Ex2 adds processing time and further attributes. Firmware support and population of these fields are not established.

Present but not validated for the active system: other vendor camera adapters, native/host OCR choice, HTTP push configuration APIs, firmware/remote configuration APIs. Unknown: active exposure settings, night recognition quality, buffer policy, real decoder queue depths, exact loaded DLL versions and camera transport. None is declared unsupported solely because it was not observed.

Highest-value next capabilities are per-camera separate connection/video/recognition health, immutable capture evidence, source timestamp preservation and explicit offline replay handling. Avoid adding push transports or remote configuration writes until an observed requirement justifies them.
''',
'SMARTPARK_GAP_ANALYSIS.md':'''# SmartPark gaps against inspected evidence
The existing system already incorporates much of the desired architecture. PARKWATCH-LESSONS.md describes earlier changes; this review also inspected the implementing code rather than assuming those notes were proof of field success.

Already present: callback lifetime retention and reconnect rearming; bounded native event queues; latest-frame buffers; local persistent decoding; bounded GUI notifications; worker OCR offloading and stale-result checks; visit-scoped database idempotency. Do not rebuild these features.

P0: event-media identity is unsafe for repeated vendor IDs and missing-media fallback (synthetically reproduced). Queue overflow can silently discard events. Camera timestamp and vehicle identity are not retained in native callback rows.

P1: current local frame age cannot quantify upstream camera/decoder latency. Physical camera quality, resolution, exposure and native-vs-host recognition accuracy have not been benchmarked. A healthy connection does not prove image callbacks or OCR results are healthy.

P2: polling-based reconnect recovery can miss short transitions. Ex/Ex2 registration behavior and the selected vendor DLL need live validation. Inventory shows multiple architectures and adapter versions, making deployed artifact identity important.

Verification: 15 tests passed in 2.90 seconds across test_hvx_reconnect.py, test_display_mailbox.py, test_live_plate_freshness.py and test_visit_dropout.py. `evidence/focused-tests.txt` contains results. A broader seven-file run emitted 18 passing progress markers then stalled; it was interrupted. It is not counted as a completed run and the stuck test was not isolated. These tests are mocked/synthetic, not Windows DLL compatibility or camera performance tests.

No production source was modified. Scope is the relevant camera/media/OCR/event pipeline; this is not a complete audit of all repository modules or all Park.exe business logic.
''',
'SMARTPARK_IMPROVEMENT_PLAN.md':'''# Prioritized improvement and validation plan
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
'''
}
for name,body in reports.items():(D/name).write_text(body.split('\n',1)[0]+'\n\n'+intro+body.split('\n',1)[1])
(D/'README.md').write_text('''# ParkWatch investigation

Read [SmartPark gap analysis](SMARTPARK_GAP_ANALYSIS.md) and [improvement plan](SMARTPARK_IMPROVEMENT_PLAN.md) first.

The principal actionable finding is a synthetically confirmed event/image association defect in SmartPark. ParkWatch supports a camera-native recognition path and contains an actual host OCR loader; the deployed per-lane selection remains unknown. Static analysis cannot certify camera accuracy or live stream latency.

'''+''.join(f'- [{n[:-3].replace("_"," ")} ]({n})\n' for n in reports)+'''
Evidence includes a recursive binary inventory with hashes, disassembly with addresses, callback documentation decoded from UTF-16, a no-hardware defect reproduction and focused test results. No production code or devices were changed. Instructions in the supplied mission document were treated as investigation context rather than independent authority to install tools, modify code or operate hardware.
''')
