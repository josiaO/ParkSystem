# SmartPark gaps against inspected evidence

Investigation date: 14 October 2026. Static Windows-binary analysis on Linux; no live camera, DLL execution, gate operation, or physical latency measurement. Addresses are preferred virtual addresses (ASLR may relocate them). QY means `VideoDrivers/IPC_QY/IPC_QY.dll`, not the different QY1 copy.

The existing system already incorporates much of the desired architecture. PARKWATCH-LESSONS.md describes earlier changes; this review also inspected the implementing code rather than assuming those notes were proof of field success.

Already present: callback lifetime retention and reconnect rearming; bounded native event queues; latest-frame buffers; local persistent decoding; bounded GUI notifications; worker OCR offloading and stale-result checks; visit-scoped database idempotency. Do not rebuild these features.

P0: event-media identity is unsafe for repeated vendor IDs and missing-media fallback (synthetically reproduced). Queue overflow can silently discard events. Camera timestamp and vehicle identity are not retained in native callback rows.

P1: current local frame age cannot quantify upstream camera/decoder latency. Physical camera quality, resolution, exposure and native-vs-host recognition accuracy have not been benchmarked. A healthy connection does not prove image callbacks or OCR results are healthy.

P2: polling-based reconnect recovery can miss short transitions. Ex and Ex2 are stored at different callback slots, and double delivery is still untested. This tree's `ParkWatch.ini` selects vendor type 3 (`IPC_QY.dll`); a running process list is still the right check on a machine. Inventory shows multiple architectures and adapter versions, making deployed artifact identity important.

Verification: 15 tests passed in 2.90 seconds across test_hvx_reconnect.py, test_display_mailbox.py, test_live_plate_freshness.py and test_visit_dropout.py. `evidence/focused-tests.txt` contains results. A broader seven-file run emitted 18 passing progress markers then stalled; it was interrupted. It is not counted as a completed run and the stuck test was not isolated. These tests are mocked/synthetic, not Windows DLL compatibility or camera performance tests.

No production source was modified. Scope is the relevant camera/media/OCR/event pipeline; this is not a complete audit of all repository modules or all Park.exe business logic.
