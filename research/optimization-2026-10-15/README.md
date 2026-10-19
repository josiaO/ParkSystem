# ParkWatch comparison and SmartPark repair

This was targeted reverse engineering, not a complete reconstruction of ParkWatch. Fresh Ghidra 12.1.4 headless imports and named-function decompilations succeeded for the following binaries; logs and decompilations are in `evidence/`.

- ParkWatch `VideoDrivers/IPC_QY/IPC_QY.dll`, SHA256 `7fde1cc437d249d15554cf8d7f770d838a1e197e0789e1f805d6f1d177f3d02e`: `CAM_StartStream` (10005230) is separate from callback registration `CAM_SetCaptureCallback` (10005270). `FUN_10006d40` and `FUN_100063c0` build and forward capture metadata and image data to the registered callback.
- OcxConfig `NetSDK.dll`, SHA256 `f22592075627bd6f822845942312b31a9c275cfe1997cb995d370c2f40272055`: `Net_StartVideo` (1002ac90) invokes Play_OpenCamera; `Net_GetJpgBuffer` (1002b0b0) invokes Play_GetJpgBuffer. Recognition callback registration is separate at `Net_RegImageRecvEx` (1002bad0) and `Net_RegImageRecvEx2` (1002bb60). Connection and connection-state functions were also decompiled.

These functions support separating video, capture and recognition. They do not prove end-to-end ParkWatch latency, full internal queue behavior or Windows runtime stability. The previous reports in `research/parkwatch` and `research/ocxconfig` cover additional binaries and paths.

## Gaps found in the SmartPark checkout

Historical display rectangles were reused as current detection coordinates; cached last-car state could maintain occupancy. Native media indexed by reused vendor ID zero could be overwritten or fall back to another event. Desktop fetched crops repeatedly; rolling evidence URLs did not change with content. Web CSS hid snapshot/crop panels. Software detector boxes were interpreted as native vehicle evidence and could bypass confidence/shape checks. Some of these defects were already committed, others were in the uncommitted Cursor edits; attribution to a particular Cursor session is not established.

The later video review found an SDK first-frame wait with no deadline, stale SDK JPEGs served indefinitely, configured RTSP URLs demoted below guessed paths, synchronous desktop watch/unwatch calls, no reconnect on clean MJPEG EOF, and possible competing MediaMTX/direct JPEG producers. These paths were repaired without altering vendor login or relay APIs.

## Validation

The first integrated recognition/capture suite passed 126 tests before the later desktop/video changes. The later integrated desktop/video suite passed 89 tests; see `evidence/desktop-video-tests.txt`. The bundled ONNX model smoke test loaded in 1.06 seconds; after warmup blank-frame detector calls were about 47–63 ms on this Linux machine, with peak process RSS about 152 MiB. This is not Windows performance or plate accuracy validation. The crop regression uses real image pixels with mocked OCR output to verify that OCR receives the plate crop, not the full car.

`live-layout.png` is a static rendered layout fixture, not a connected-camera screenshot. No real camera, gate or printer was operated. Windows field and prolonged-run acceptance remain required. See `docs/MEDIA-ARCHITECTURE.md` and `docs/MIGRATION-AND-ROLLBACK.md` for the current structure and deployment procedure.
