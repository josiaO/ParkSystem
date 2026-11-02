# Fresh OcxConfig Ghidra audit

Date: 2026-11-02  
Scope: `Current_ParkSystem_configs/Camera_config/OcxConfig/` and the current SmartPark video/recognition path.

## Executive conclusion

`OcxConfig` is a native Windows QY/HVX camera client stack. It can be used as a reliable Windows-side acquisition backend for QY cameras, but it is not itself a browser streaming engine and it is not suitable for direct loading into the Linux/FastAPI process. The correct integration boundary is a Windows host/agent that owns the vendor DLLs and exposes JPEG/frame data to SmartPark; the existing HVX host `/live-jpeg/<handle>` bridge is the appropriate seam.

The vendor avoids an ever-growing video backlog with a bounded per-camera receive queue. Its receive task drops a packet when the queue is full. SmartPark uses the same latency-oriented policy at a higher level: one producer per camera and latest-frame-wins buffers for live display and recognition. Apparent “skipping” is therefore expected when the consumer is slower than the camera; it prevents stale video from stacking.

The vendor also exposes native vehicle/detection events and a native overlay path for plate regions, stop lines, and prefix lines. It does not expose a browser URL or WebRTC stream in the supplied binaries.

## Method and provenance

This was a new analysis, independent of earlier reverse-engineering notes:

1. Verified that `ghidraRun` and `analyzeHeadless` were not installed.
2. Downloaded the official Ghidra 12.2 release and verified SHA-256 before use.
3. Ran a fresh headless Ghidra project over every supplied `*.dll`, `*.ocx`, and `*.exe`.
4. Decompiled the stream, decoder, overlay, callback, and recognition-related entry points.
5. Compared those findings with the current SmartPark media and recognition services.

Ghidra release: [Ghidra 12.2](https://github.com/NationalSecurityAgency/ghidra/releases/tag/Ghidra_12.2_build)  
Verified archive SHA-256: `2c2cd776db3c1f6a097ba418922378ac3649cadd5e844a6f5f088ae628a7be67`  
Fresh project: `/tmp/ocx-ghidra-fresh-20261102/project/OcxConfigFresh`  
Input hashes: `/tmp/ocx-ghidra-fresh-20261102/logs/input-sha256.txt`

Ghidra 12.2 requires JDK 25. The machine had JDK 21, so a private, non-system JDK 25 runtime was extracted under `/tmp/ocx-jdk25/` for this audit. No system package installation was performed.

## Binaries analyzed

The fresh project includes `OcxConfig.ocx`, `OcxConfigClient.exe`, `OcxConfig_Setup.exe`, `unins000.exe`, `NetSDK.dll`, `PlaySdk.dll`, `RtspRecvSdk.dll`, `DecodeSdk.dll`, `CommModule.dll`, `DevSearchHelper.dll`, `DevSearchHelperBatch.dll`, `Log.dll`, `QRGenerator.dll`, `Talk.dll`, and `ZlibHelper.dll`.

All supplied media binaries are 32-bit x86 PE files. Missing Windows system DLLs and absent PDB files produced normal static-analysis warnings; the supplied proprietary binaries imported and analyzed successfully.

## Video acquisition and why it does not stack

The control executable is not the stream implementation. Fresh analysis showed that `OcxConfigClient.exe` imports camera connect/disconnect functions, while `OcxConfig.ocx` imports and drives the video APIs.

The path is:

```text
OcxConfig.ocx
  -> Net_StartVideo / Net_AddPlayWindow / Net_SetDrawFunCallBack
  -> Play_OpenCamera
  -> Decode_StreamOpenEx + Decode_StreamPlayEx
  -> Rtsp_StartVideo
  -> bounded receive queue
  -> decoder worker threads
  -> native HWND, callback, JPEG, or raw-frame API
```

Important fresh findings:

- `Net_StartVideo` accepts a bounded per-handle state set (the decompiled check is `< 0x20`, i.e. up to 32 handles), serializes open/close operations with a critical section, opens the Play SDK camera, and retries the plate-region overlay setup up to three times.
- `Play_OpenCamera` obtains a decoder port, opens/starts the decoder, starts the RTSP receiver, and starts receive/network worker threads. It cleans up by joining/closing the receive thread before final camera close.
- `Rtsp_StartVideo` creates a per-camera ring queue with capacity `10` and frame storage size `0xc8000`, then starts the receive task.
- The RTSP receive task calls `rngQue_GetWritePtr`. If the queue is full, the write pointer is null and the packet is simply discarded. It does not block and does not append unbounded backlog.
- `Rtsp_GetVideoFrame` reads one item at a time with `rngQue_GetReadPtr`; an empty queue returns a no-data result. `Rtsp_StopVideo` deletes the task and queue and clears the state.
- `Play_CloseCamera` explicitly waits for the receive thread and then releases decoder state and window/callback records.

This is why the vendor path does not stack: it bounds both the producer queue and the lifetime of each camera task, dropping old work when the consumer cannot keep up.

## How video is exposed

The vendor binaries expose video in-process, not as a browser stream:

- Native window rendering: `Net_AddPlayWindow` -> `Play_AddPlayWindow` -> `Decode_StreamAddPlayWindow`, which attaches one or more Win32 `HWND` targets. The Play SDK stores up to ten window handles per camera.
- Frame callback: `Net_SetDrawFunCallBack` -> `Play_SetDrawFunCallBack` -> `Decode_SetDrawFunCallBack`.
- JPEG access: `Net_GetJpgBuffer` -> `Play_GetJpgBuffer` -> decoder JPEG conversion/copy helper.
- Raw frame access: `Net_GetFrameData` -> `Play_GetFrameData` -> decoder frame conversion/copy helper.
- Snapshot/file APIs: `Net_ImageSnap` and `Net_SaveJpgFile` are also imported by the OCX.

There is no evidence in these binaries of HTTP MJPEG, WebRTC, or a browser-facing URL. A browser cannot consume the native `HWND` path directly. A Windows host must pull JPEG/frame data and bridge it over HTTP/WebSocket/MediaMTX. SmartPark's existing Windows host and `/live-jpeg/<handle>` endpoint already implement that separation.

## Detection zones and line overlays

The vendor path does expose camera-side detection geometry:

- `Net_QueryVideoDetectSetup` sends the internal video-detection query command and copies the returned structure into cached state.
- The decompiled logging and field accesses identify four `PlateRegion` points, two `aStopLine` points, and two `tPrefixLine` points.
- `Net_ShowPlateRegion` queries the setup, converts the eight points to the overlay point array, then calls `Play_UpdatePlateRegion` and `Play_ShowPlateRegion`.
- `Play_ShowPlateRegion` delegates to `Decode_ShowPlateRegion`; the decoder accepts the eight-point overlay set.
- Related OCX imports include `Net_VideoDetectSetup`, `Net_QueryVideoDetectSetup`, `Net_DetectModeSetup`, and `Net_QueryDetectPlateType`.

This is a native decoder overlay and not merely a web canvas drawing. Static analysis confirms the data flow and point count, but it cannot prove the runtime colors, coordinate origin, camera resolution scaling, or whether a particular camera firmware returns all eight points. Those require a Windows camera acceptance test.

## Recognition behavior

The OCX imports/registers:

- `Net_RegImageRecvEx2` for an image callback and user context;
- `Net_RegReportMessEx` for report/event callbacks and user context;
- `Net_GetPresentVehInfoAsCSV` for current vehicle information;
- vehicle/detection setup and plate-type query functions.

This supports vehicle events and optional plate reports, but the supplied binaries do not show that they invoke SmartPark's `fastALPR`. The vendor recognition callback and FastALPR are separate recognition sources.

The current SmartPark recognition path is intentionally separate: it consumes the local MediaMTX RTSP path, uses one decoder per recognition lane, retains only the newest complete JPEG, applies a bounded admission clock, and performs detector/ROI/crop work before FastALPR. A vehicle event without a plate is therefore a valid partial result; it should not be treated as evidence that the video pipeline failed. The Windows host should continue to forward fresh JPEGs and native events, while FastALPR remains the plate fallback/authoritative application recognizer.

## Why Zirp can appear to stack or skip

The fresh vendor evidence shows that “no stacking” is achieved by dropping when a bounded queue is full. SmartPark's current code uses the same principle at the application boundary:

- one producer per camera;
- `LatestFrameBuffer`/`DisplayMailbox` with a one-frame live mailbox;
- old JPEGs are discarded before display or recognition;
- separate live and detection mailboxes;
- stale-frame protection and metrics for live/AI drops, duplicate frames, frame age, FPS, and reconnects.

This intentionally skips stale frames to keep latency low. It does not mean the camera is failing. If stacking is still visible in a deployment, inspect the live metrics and verify that no second reader is consuming the same camera path, no UI route is polling snapshots in parallel with WebRTC/direct MJPEG, and that the Windows host is not buffering more than one JPEG per handle. The vendor itself may also drop frames upstream; it simply does so before decode rather than after the browser queue.

## Can OcxConfig be used as the streaming engine?

Yes, with a boundary:

- Suitable: Windows QY/HVX host process using the vendor DLLs, one camera session per handle, JPEG/frame extraction through `Net_GetJpgBuffer`/`Net_GetFrameData`, and a bounded latest-frame bridge to SmartPark.
- Not suitable: loading the 32-bit Windows DLLs into the Linux app, using the native `HWND` renderer as a browser stream, or assuming the vendor DLLs provide WebRTC/MJPEG directly.

The existing `HVXHostClient`/`/live-jpeg/<handle>` integration is therefore the implementation direction supported by this audit. A direct ABI wrapper or replacement Windows host should only be implemented and accepted with the real 32-bit DLLs, camera credentials, and a Windows test machine; static decompilation cannot validate calling-convention details, callback lifetime, firmware compatibility, or frame ownership.

## Reproducibility

Fresh scripts added to the repository:

- `research/ocxconfig/scripts/FreshOcxAudit.java`
- `research/ocxconfig/scripts/FreshOcxDecompile.java`

The first enumerates imports, external references, functions, strings, and metadata. The second decompiles the stream, decoder, overlay, callback, and RTSP worker functions listed above. Raw output is in:

- `/tmp/ocx-ghidra-fresh-20261102/logs/audit-key-output.txt`
- `/tmp/ocx-ghidra-fresh-20261102/logs/decompile-output.txt`
- `/tmp/ocx-ghidra-fresh-20261102/logs/decompile-rtsp-output.txt`

## Verification status and Windows acceptance checklist

`python3 -m compileall -q app` completed successfully after the audit. The broad pytest command was attempted, but the selected test collection hung for more than three minutes before collecting any tests and was interrupted; it is not reported as a passing test run.

On Windows, acceptance should verify:

1. Two cameras start simultaneously without a second reader or unbounded memory growth.
2. A slow display consumer sees the newest frame, not an increasing delay.
3. `Net_GetJpgBuffer` frames have changing sequence/timestamps and correct JPEG boundaries.
4. Stop/restart joins the receive/decoder workers and does not leak handles.
5. Plate-region, stop-line, and prefix-line coordinates match the camera preview at both main and substream resolutions.
6. Native vehicle events and image callbacks continue when the plate field is empty.
7. FastALPR receives a fresh crop from the same current frame and is not fed stale/reused JPEG bytes.
8. The host bridge exposes one bounded latest JPEG per camera to SmartPark and does not buffer a FIFO of browser responses.

