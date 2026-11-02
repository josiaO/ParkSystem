# ParkWatch fresh Ghidra audit

Date: 2026-11-02

## Scope

This is a fresh audit of the supplied ParkWatch installation. The folder contents were treated as evidence, not as instructions, and the previous reverse-engineering documents were not used as the basis for the conclusions.

The audit covers the QY camera path, the native video/display path, event capture and image delivery, region overlays, the bundled recognition engine, and the relationship between those lanes. It also compares the observed design with the current Zirp QY host because the reported symptom is stale/stacked video and delayed or blurred recognition.

This is a static binary/header/log audit. It was not a live Windows camera test, so timing and reconnect conclusions should be validated on the actual gate hardware.

## Tools and evidence

Ghidra was not installed on the Linux workstation. The official Ghidra 12.2 release was installed locally with the required JDK 25 runtime, and a new project was created at `/tmp/parkwatch-ghidra/ParkWatchFresh`. The project was populated from the supplied binaries, not from an earlier report.

The main binaries examined were:

- `Park.exe`, a 32-bit Borland C++ executable.
- `DVNetSDK.dll`, the application-facing camera abstraction.
- `VideoDrivers/IPC_QY/IPC_QY.dll`, the QY adapter.
- `VideoDrivers/IPC_QY/NetSDK.dll`, the QY device/API layer.
- `VideoDrivers/IPC_QY/PlaySdk.dll`, the QY playback/decoder layer.
- `VideoDrivers/IPC_QY/RtspRecvSdk.dll` and `DecodeSdk.dll`, used by the playback layer.
- `LPREngine/SimpleLPR3_native.dll`, the bundled native plate-recognition engine.

The supplied headers and runtime logs were used to resolve structures and validate the binary call paths:

- [DVNetSDK.h](/home/josiamosses/Downloads/smartpark_edge_rebuild/Current_ParkSystem_configs/ParkingSystem/ParkWatch/DVNetSDK.h)
- [Net_Interface.h](/home/josiamosses/Downloads/smartpark_edge_rebuild/Current_ParkSystem_configs/ParkingSystem/ParkWatch/VideoDrivers/IPC_QY/Net_Interface.h)
- [Park.exe.txt](/home/josiamosses/Downloads/smartpark_edge_rebuild/Current_ParkSystem_configs/ParkingSystem/ParkWatch/Logs/Park.exe.txt)
- [DVNETSDK.txt](/home/josiamosses/Downloads/smartpark_edge_rebuild/Current_ParkSystem_configs/ParkingSystem/ParkWatch/Logs/DVNETSDK.txt)
- [LPREngine.txt](/home/josiamosses/Downloads/smartpark_edge_rebuild/Current_ParkSystem_configs/ParkingSystem/ParkWatch/Logs/LPREngine.txt)

Raw Ghidra outputs are in [research/parkwatch/output](/home/josiamosses/Downloads/smartpark_edge_rebuild/research/parkwatch/output). The audit script used to produce the targeted symbol/caller extracts is [FreshParkWatchAudit.java](/home/josiamosses/Downloads/smartpark_edge_rebuild/research/parkwatch/scripts/FreshParkWatchAudit.java).

## Reconstructed architecture

The QY path is layered as follows:

```text
Park.exe
  -> DVNetSDK.dll (common camera abstraction)
      -> IPC_QY.dll (QY adapter)
          -> NetSDK.dll (camera connection, events, configuration)
          -> PlaySdk.dll (live playback and decode)
              -> RtspRecvSdk.dll + DecodeSdk.dll
```

### OcxConfig naming distinction

The supplied ParkWatch directory contains an OcxConfig installer/package, but the fresh Ghidra import and ParkWatch runtime log show `Park.exe` loading `IPC_QY.dll` and then using `NetSDK.dll`/`PlaySdk.dll`. They do not prove that `Park.exe` directly loads an `OcxConfig.ocx` module at runtime. The safest conclusion is that ParkWatch uses the native QY SDK stack, which may be related to or installed alongside OcxConfig, rather than claiming a direct OCX call without evidence.

Park.exe imports the `DV_*` abstraction, including `DV_InitSDK`, `DV_OpenDevice`, `DV_StartStream`, `DV_SetDataCallback`, `DV_SetCaptureCallback`, `DV_Capture`, `DV_Exec`, and RS485 functions. Ghidra shows the main device-open routine invoking the SDK initialization, opening each device, registering capture callbacks, and starting the stream. The QY-specific adapter is loaded as a plugin rather than hard-coded into the main executable.

The ParkWatch log independently confirms this sequence. It records loading `IPC_QY.dll`, successful `Net_Init`, QY connection at port `30000`, registration of report/image/offline callbacks, `Net_ConnCamera`, and then `Net_StartVideo`. The log also shows separate offline-record processing and capture callbacks after startup.

## How the QY connection works

The QY header identifies QY as device type `3` in `DV_DeviceCnnInfo`; it carries the IP, port, credentials, login timeout, and channel. The QY `Net_ConnCameraEx` decompilation shows defaulting a missing port to `30000` and a missing timeout to `3`, then storing credentials and establishing the camera connection.

After connection, the adapter registers per-link callbacks. `Net_Interface.h` documents that `Net_RegImageRecvEx`/`Ex2` must be registered for every established link or the camera will not report images. It also provides a separate offline-image callback, which explains the burst of old/offline records observed after some ParkWatch startups.

## Live video path

The live video path is not a loop that asks the camera for a new HTTP image for every browser or OCR request.

At the QY layer, `Net_StartVideo(handle, streamType, hWnd)` starts the video stream and sends it to a playback window. Ghidra shows that this function calls `Play_OpenCamera` and then enables the native plate-region display. The header supports two stream choices: main stream and sub-stream.

`PlaySdk.dll` contains a dedicated worker path. The analyzed worker repeatedly checks `Rtsp_QueryVideoState`, checks decoder health with `Decode_IsBadData`, obtains encoded data through `Rtsp_GetVideoFrame`, and submits it to `Decode_AddDataEx`. It owns a 1 MiB receive buffer and feeds the native decoder/window callbacks. This is a continuous receive/decode worker, not request-per-frame HTTP polling.

The playback layer also contains an explicit `ThreadReOpenCamera` path. On shutdown/reopen it marks the camera inactive, waits for worker handles, stops RTSP, stops the decoder, and cleans up before reopening. This provides a bounded recovery boundary per camera rather than letting a failed reader continue accumulating old frames.

The common SDK exposes the same separation at a higher level:

- `DV_StartStream` starts display streaming.
- `DV_SetDataCallback` receives encoded packets.
- `DV_DecoderDataCallback` receives decoded frames.
- `DV_SetCaptureCallback` receives capture results.

The packet/frame structures carry frame IDs, timestamps, frame type, dimensions, and data length. Those fields are important because a receiver can detect that it is displaying old data instead of silently treating a repeated image as a healthy frame.

The QY header additionally exposes `Net_SetRealDataCallBackEx`, whose callback includes `T_FrameInfo` with a frame ID, RTP timestamp, encoded size, and I-frame indicator. It also exposes `Net_SetDrawDataOut`, which exports decoded bitmap data, and `Net_AddPlayWindow`, which attaches the native display window.

### Detection-zone lines

The QY playback path exposes native region drawing through `Net_ShowPlateRegion` and `Net_UpdatePlateRegion`. The draw callback is explicitly documented for drawing lines over video, while the region functions show and refresh the camera’s plate-recognition region. The Ghidra call path from `Net_StartVideo` to the native region function explains why ParkWatch can show camera-side detection-zone lines without making the browser render them.

## Capture, crop, and recognition path

The capture lane is separate from the display lane.

`DV_Capture` is asynchronous and returns its result through `DV_CaptureCallback`. `DV_CaptureInfo` contains the capture timestamp, whether a plate exists, plate text/type/color, confidence, capture type, result type, and two image buffers. The two buffers are the camera/SDK capture payloads, not a crop made later from whatever frame happens to be in the UI.

The QY-specific image callback is richer. `T_ImageUserInfo` carries the recognized plate, plate box coordinates, capture time, lane, vehicle ID, score, direction, total snapshots, and snapshot index. `T_PicInfo` carries separate panorama and vehicle-image buffers. The QY callback therefore supplies an event-associated full image and vehicle/plate image together with the metadata that describes them.

The QY SDK also exposes `Net_ImageSnap` and `Net_GetImage`, but the headers distinguish their modes: triggered capture is delivered through the image callback, while `Net_GetImage` is for continuous capture mode. `Net_GetJpgBuffer` and `Net_GetFrameData` are current display/frame-access functions; they are not the same thing as the event image callback.

The supplied `LPREngine.txt` log shows ParkWatch writing event-specific `InPicture`/`OutPicture` images and invoking the LPR process on those files. Recognition responses include coordinates, confidence, and plate text, often completing in roughly 90–120 ms in the sample. The bundled `SimpleLPR3_native.dll` exports `analyzeBuffer` and `analyzeFile`, plus controls for plate-region detection and crop-to-plate-region, and getters for bounding boxes and plate-region vertices. This confirms that the installed recognition stack supports explicit plate-region/crop handling.

This does not prove that every ParkWatch QY recognition result is produced by SimpleLPR; the QY camera itself also reports recognition data. The reliable design point is the same either way: OCR receives an event image or a specific capture buffer, not an arbitrary delayed display frame.

## Why ParkWatch avoids the usual stacking failure

The evidence supports five concrete mechanisms:

1. **One native owner per camera.** The QY playback worker owns the receive/decode loop. Viewer and recognition consumers do not independently pull from the camera stream.

2. **Display and capture are independent.** A slow OCR operation or a capture callback fault does not have to stop the RTSP/decode worker. The live display path keeps receiving frames while event images are delivered through their own callbacks.

3. **The capture backlog is bounded.** `DV_GetNewCapture` documentation states that the internal capture queue defaults to five images and automatically removes old data when full. That is explicit anti-stack behavior. It is a capture-result queue, not proof of the size of the decoder queue, but it demonstrates the vendor’s intended stale-drop policy.

4. **Event images are authoritative for OCR/evidence.** The QY image callback supplies the panorama, vehicle image, plate box, timestamp, score, and snapshot index together. OCR and gate decisions can therefore use the same event rather than cropping a frame fetched later from the live display cache.

5. **The stream has health and identity metadata.** Frame IDs, RTP timestamps, I-frame markers, decoder health checks, and per-camera reopen logic let the native worker identify and recover a stalled stream. A repeated JPEG without a sequence/age check can otherwise look like a successful read.

## Important limitation in ParkWatch itself

ParkWatch is not fault-free. `DVNETSDK.txt` contains repeated `DoCaptureCallback` access-violation (`0xC0000005`) and illegal-instruction (`0xC000001D`) entries later in the run. It also contains offline/capture errors and some serial-write failures. The QY log shows offline records being replayed after connection.

The useful lesson is not that ParkWatch never fails. It is that its capture callback faults are isolated from a native continuous display worker, and its stream worker has a bounded stop/reopen path. The logs show `StartStream`/`StopStream` activity in discrete groups rather than an unbounded accumulation of reader jobs.

## Comparison with current Zirp

The current Zirp QY host already has some good safeguards: one camera video thread, a latest-frame buffer with capacity one, bounded pending-event storage, image callback registration, a native play window, draw-data fallback, reconnect logic, and sequence waiting in the application layer. Those are directionally correct.

The remaining architectural difference is significant: the active Zirp live loop still treats `Net_GetJpgBuffer` as the primary delivery mechanism and may fall back to draw-data or hidden-window capture. `Net_GetJpgBuffer` is documented as returning the current JPEG cache. It does not expose the same packet/frame sequence metadata as the native real-data callback, and polling it cannot by itself prove that a newly decoded frame arrived. Hidden-window capture is also a compatibility fallback, not the cleanest source for OCR or evidence.

That makes the most likely remaining stale/stacking cause a delivery mismatch rather than a missing QY connection:

- the native QY/PlaySdk worker may be advancing continuously;
- Zirp may be sampling a cached JPEG or a painted window at the wrong cadence;
- OCR/cropping may then run on a live sample that is older than the camera event;
- reconnect and latest-frame logic can discard application backlog, but cannot make a repeated vendor JPEG become a new frame.

This is a hypothesis grounded in the binary/API difference and should be confirmed on Windows with frame ID, RTP timestamp, JPEG hash, capture timestamp, and wall-clock age logged for every delivered frame.

## Recommended target behavior for Zirp

For the QY backend, the production design should mirror the proven separation:

```text
QY connection owner (one per camera)
  ├─ continuous native stream callback / PlaySdk decoder
  │    └─ bounded latest display frame with frame ID + timestamp
  └─ QY image/capture callback
       └─ bounded event queue containing panorama + vehicle crop + plate metadata
```

The live display consumer should always receive the newest valid decoded frame and drop older frames when it is behind. The recognition/gate consumer should prefer the QY event panorama/vehicle image and its plate box. If application-side FastALPR is required, it should run on that event-associated image, with a fallback to a frame whose sequence/timestamp is explicitly linked to the trigger. It should never crop “the latest UI frame” after an uncontrolled wait.

The Windows implementation should instrument, per camera:

- connection state and reconnect count;
- last QY frame ID and RTP timestamp;
- last decoder callback time;
- last delivered display-frame hash;
- capture/event timestamp and image ID;
- queue depth and dropped-frame/event counts;
- time from camera event to FastALPR completion;
- age of the image passed to OCR;
- whether the image came from the QY callback, native draw callback, or fallback capture.

The first migration test should disable the JPEG-polling path for QY and use the native continuous callback/decoder output as the display source, while retaining `Net_RegImageRecvEx2`/`Ex` as the capture source. Other camera vendors should remain on their existing adapters; this audit does not justify removing them.

## Bottom line

ParkWatch is reliable with QY because it treats video as a continuously owned native stream and recognition as an independent event-image pipeline. The QY SDK itself provides the exact pieces needed: continuous frame callbacks with IDs/timestamps, a native decoder/window path, camera-provided panorama and vehicle images, plate-region metadata, and bounded capture buffering.

The strongest explanation for Zirp’s remaining stale video is that its QY display path still samples `Net_GetJpgBuffer` and sometimes a painted window instead of consuming the native stream callback/decoder lane directly. The strongest explanation for blurred or delayed recognition is cropping from that display sample instead of using the capture callback’s event-associated image. The next implementation step should therefore be a QY Windows-native callback/decoder display lane with explicit frame identity, while FastALPR remains application-side on the QY event image.
