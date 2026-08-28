# SmartPark Edge — HVX Reuse Verdict & Exact Integration Plan

**Status:** Replace prior blind/generic camera work with this evidence-based plan.

## Verdict

**YES — the existing HVX cameras are realistically reusable.**

The uploaded Windows vendor package contains a complete 32-bit camera SDK stack, not merely a viewer.

Static inspection of the actual uploaded binaries shows all of the following:

- `NetSDK.dll` is PE32/x86 and exposes camera discovery, connection, image, LPR event, HTTP push, whitelist, parking and GPIO/gate-related APIs.
- `OcxConfig.ocx` is PE32/x86 and imports the vendor SDK extensively.
- `OcxConfigClient.exe` is PE32/x86 and directly uses `NetSDK.dll`.
- `RtspRecvSdk.dll` contains a separate RTSP client implementation.
- `PlaySdk.dll` and `DecodeSdk.dll` provide video-frame/JPEG/plate-region processing.
- `DevSearchHelper.dll` exposes `GetDevList`, `ModifyDevIp`, `ShowDevList`.
- the registration batch file uses `regsvr32 OcxConfig.ocx`, confirming the OCX is an ActiveX/COM component.

Do not replace the four cameras yet.

---

# 1. Critical Finding: Everything Is 32-bit Windows

The actual files are PE32 / Intel i386.

The verified bindings specify:

```text
architecture: x86
calling convention: stdcall
```

Therefore:

**A normal 64-bit Python process cannot directly load this NetSDK.dll.**

This is likely one reason generic/current integration attempts discover IP addresses but cannot actually operate the camera.

Create a dedicated Windows x86 helper:

```text
smartpark-hvx-sdk-host.exe
```

Possible implementation technologies:

- 32-bit Python + ctypes for early proof
- C++ Win32 x86
- .NET Framework x86 P/Invoke after signatures are fixed

Do not make the whole SmartPark application 32-bit.

Architecture:

```text
64-bit SmartPark
      │ localhost IPC/HTTP
      ▼
32-bit HVX SDK Host
      │
      ▼
NetSDK.dll
      │
      ▼
HVX camera
```

---

# 2. Vendor Client Reveals the Real Connection Sequence

Static disassembly of the uploaded `OcxConfigClient.exe` shows this sequence:

```text
Net_AddCamera(IP)
↓
returns camera handle
↓
Net_ConnCamera(handle, 30000, 5)
```

The client treats:

```text
handle == -1       → AddCamera failed
Net_ConnCamera != 0 → connection failed
Net_ConnCamera == 0 → connection succeeded
```

Therefore the vendor camera control/service port used by this client is:

```text
30000
```

and the example timeout argument is:

```text
5
```

Do not confuse:
- camera web HTTP port
- RTSP port
- vendor SDK service port

They are separate.

The current Hardware Library discovering `192.168.1.x` does NOT prove it is connecting to the HVX control service.

---

# 3. Authenticated Connection Exists Too

The uploaded `OcxConfig.ocx` calls:

```text
Net_ConnCameraEx(
    handle,
    configured_port,
    3,
    username,
    password
)
```

and treats return value `0` as success.

The verified binding is:

```c
Net_ConnCameraEx(
    int handle,
    unsigned short port,
    int timeout,
    char* username,
    char* password
) -> int
```

For the initial real-camera test:

```text
Net_Init()
Net_AddCamera(camera_ip)
Net_ConnCameraEx(handle, 30000, 3, configured_username, configured_password)
Net_QueryConnState(handle)
```

The port must remain configurable because firmware/site configuration could differ, even though the uploaded vendor client uses 30000.

---

# 4. Native Plate Recognition Is Definitely Available

This is not speculation.

`NetSDK.dll` contains an internal LPR reporting message string:

```text
MSG_R_LPRINFO_EXT Plate=%s
```

and exports:

```text
Net_RegReportMessEx
```

The OCX actually registers that callback:

```text
Net_RegReportMessEx(handle, callback, user_context)
```

The verified bindings identify this as the `plate_event` function.

Therefore SmartPark should receive native plate events through the SDK host instead of attempting to infer them from screenshots.

First callback milestone:

```text
real vehicle passes
→ HVX camera recognizes/captures
→ Net_RegReportMessEx callback fires
→ SDK host logs raw callback metadata
→ SmartPark receives normalized event
```

Do not build parking-session logic until this callback is proven.

---

# 5. Native Image Callback Exists

The OCX imports and calls:

```text
Net_RegImageRecvEx2
```

in the form:

```text
Net_RegImageRecvEx2(handle, callback, context)
```

This strongly indicates the vendor SDK can deliver camera/image data through callbacks.

Also available:

```text
Net_ImageSnap
Net_GetImage
Net_SaveJpgFile
Net_SaveImageToJpeg
Net_QueryImageById
```

Initial image proof should use the simplest verified path first:

```text
Net_ImageSnap(handle)
```

plus the vendor save/callback path.

Do not reverse-engineer complex video structures before proving snapshots/events.

---

# 6. RTSP Is Also Reusable

Static inspection of the actual uploaded `RtspRecvSdk.dll` reveals literal vendor stream templates:

```text
rtsp://<ip>/av0_0&user=<username>&password=<password>
rtsp://<ip>/av0_1&user=<username>&password=<password>
```

and alternate templates:

```text
RTSP://<ip>:<port>/video
RTSP://<ip>:<port>/subvideo
```

The DLL exports:

```text
Rtsp_Init
Rtsp_AddCamera
Rtsp_StartVideo
Rtsp_GetVideoFrame
Rtsp_QueryVideoState
Rtsp_ReConnVideo
Rtsp_StopVideo
Rtsp_UNinit
```

Cursor must test these vendor-derived stream patterns with the **actual configured credentials**, using FFprobe/VLC first.

Do not hard-code the `admin/admin` sample embedded in the old DLL.

Recommended approach:

```text
1. Test RTSP externally with ffprobe.
2. If one URL works, store that exact profile.
3. Use go2rtc/FFmpeg for SmartPark live view.
4. Do not spend time on ONVIF if native RTSP works.
```

---

# 7. Plate Display/Decode Stack Is Included

`PlaySdk.dll` exposes:

```text
Play_GetFrameData
Play_GetJpgBuffer
Play_OpenCamera
Play_QueryVideoState
Play_ShowPlateRegion
Play_UpdatePlateRegion
```

`DecodeSdk.dll` exposes:

```text
Decode_GetFrameData
Decode_GetJpgBuffer
Decode_GetVideoSize
Decode_ShowPlateRegion
Decode_StreamOpenEx
Decode_StreamPlayEx
Decode_StreamASaveJpgFile
```

Therefore the vendor package contains the complete media pipeline used by the viewer.

SmartPark does not need to duplicate these DLL decoders unless RTSP/FFmpeg fails. Prefer standard FFmpeg for our own UI once RTSP URL is proven.

---

# 8. Camera Discovery Is Reusable

Available vendor paths include:

```text
Net_FindDevice
Net_FindDeviceEx
Net_FindDeviceIp
Net_FindDeviceMac
```

and `DevSearchHelper.dll` exports:

```text
GetDevList
ModifyDevIp
ShowDevList
```

This explains why discovery is currently easy.

But discovery must be separated from **connection**.

Required statuses:

```text
DISCOVERED
SDK_CONNECTING
SDK_CONNECTED
VIDEO_CONNECTED
NATIVE_EVENTS_CONNECTED
```

Do not label a discovered IP as "camera connected."

---

# 9. HTTP Push Is Still Valuable

Actual SDK exports include:

```text
Net_SetHttpPushSetup
Net_QueryHttpPushSetup
Net_SetPushTargetSetup
Net_QueryPushTargetSetup
Net_HttpUpImageMode
Net_QueryHttpUpImageMode
```

and the existing camera UI already exposes HTTP Push configuration.

Keep the HTTP receiver implementation.

Use SDK callbacks + HTTP Push as two independent native-event integration choices:

```text
HVX SDK callback
        or
HVX HTTP Push
```

Whichever proves more reliable at the real site can become the primary event path.

---

# 10. FTP Is Supported but Secondary

The OCX imports:

```text
Net_FTPSetup
Net_QueryFTPSetup
```

and contains FTP-related implementation.

Use FTP only for:
- optional evidence/archive upload
- OCR dataset collection
- image fallback

Do not use FTP as the main real-time parking event bus if SDK callback/HTTP Push works.

---

# 11. Existing Barrier Hardware Is Very Likely Reusable

The SDK contains multiple independent gate/I/O capabilities:

```text
Net_ReadGPIOState
Net_WriteGPIOState

Net_SetParkOpenManual
Net_QueryParkOpenManual

Net_ControlGateQueue
Net_QueryControlGateQueue

Net_SetGateAutoOpen
Net_QueryGateAutoOpen

Net_ParkGatePulseSetup
Net_QueryParkGatePulse

Net_GateSetup
Net_GateSetupEx
```

The verified bindings specifically map:

```text
relay_open → Net_WriteGPIOState
```

This strongly supports the conclusion that the existing camera/controller can participate in opening the current boom.

However:

**Do not implement or issue raw GPIO writes until the correct output channel/state mapping is verified on the real hardware by an authorized technician in a controlled commissioning environment.**

SmartPark should first implement only the software interface:

```python
BarrierAdapter.open()
BarrierAdapter.read_state()
```

and keep the real HVX implementation disabled/UNVERIFIED until physical commissioning.

---

# 12. ActiveX/OCX Is an Additional Fallback

`OcxConfig.ocx` contains automation methods such as:

```text
SetIP
AutoLogin
AutoLoginEx
AutoLoginEx1
IsConnected
GetVersion
```

and has ProgID:

```text
OCXCONFIG.OcxConfigCtrl.1
```

The supplied batch file registers it with:

```text
regsvr32 OcxConfig.ocx
```

This gives us another Windows-only integration route.

Cursor should create a one-time developer tool to inspect the registered OCX type library/IDispatch metadata and enumerate:
- method names
- parameter types
- return types

Do not make ActiveX the primary production architecture unless it proves substantially easier than NetSDK.

---

# 13. Windows Dependency Problem Must Be Solved Explicitly

`NetSDK.dll` imports dependencies including:

```text
CommModule.dll
PlaySdk.dll
Log.dll
MSVCR80.dll
urlmon.dll
WS2_32.dll
```

Therefore the x86 SDK host must:

1. run as 32-bit
2. load DLLs from a controlled vendor SDK directory
3. verify all dependencies before trying camera connection
4. provide an error such as:
   - SDK_ARCH_MISMATCH
   - SDK_DEPENDENCY_MISSING
   - SDK_LOAD_FAILED
5. never silently fall back and report generic "camera unavailable"

The vendor SDK folder should be deployed intact.

---

# 14. Exact Cursor Work Order — Stop Blind Development

## Phase A — Build a tiny Windows x86 HVX proof host

No desktop UI.

Expose commands:

```text
sdk-info
add-camera
connect-camera
query-state
snapshot
listen-events
disconnect
```

Inputs:

```text
IP
service port (default 30000, configurable)
username
password
```

Acceptance:

```text
192.168.1.49
→ Net_AddCamera succeeds
→ Net_ConnCameraEx returns 0
→ QueryConnState confirms connection
```

Nothing else matters until this succeeds.

---

## Phase B — Prove native event callback

Register:

```text
Net_RegReportMessEx
```

Log:
- callback received
- camera handle
- raw message type
- plate if safely decoded
- timestamp

Acceptance:

```text
drive one real vehicle
→ callback fires
```

---

## Phase C — Prove image acquisition

Use:
- snapshot and/or image callback

Acceptance:

```text
SmartPark SDK host saves a real current camera JPEG
```

---

## Phase D — Prove RTSP independently

Using the stream templates found in `RtspRecvSdk.dll`, test with FFprobe/VLC.

Acceptance:

```text
real live video visible without OcxConfigClient
```

Then use:
- RTSP → go2rtc → SmartPark desktop

---

## Phase E — Integrate host with SmartPark

Only after A-D.

SmartPark API talks to:

```text
localhost HVX SDK Host
```

The desktop must never load NetSDK directly.

---

## Phase F — All four cameras

Configure dynamically:

```text
Camera 1 → Gate A Entry
Camera 2 → Gate A Exit
Camera 3 → Gate B Entry
Camera 4 → Gate B Exit
```

Do not hard-code IPs or count.

---

## Phase G — Barrier adapter

Implement software boundary but keep physical output disabled until verified commissioning.

No automatic production gate opening during development.

---

# 15. What Cursor Should Remove/Stop Doing

Stop:
- treating IP discovery as successful camera integration
- repeatedly guessing ONVIF endpoints
- guessing random RTSP paths
- loading NetSDK from 64-bit Python
- implementing the whole parking UI before hardware proof
- reporting "connected" when only ping/discovery works
- trying to replace existing cameras before the vendor SDK proof is complete

---

# 16. Revised Hardware Lab States

Each camera card must show:

```text
Network Discovery       ✓
Vendor SDK Loaded       ✓
SDK Control Connection  ✓ / ✕
Native LPR Callback     ✓ / ✕
Snapshot                ✓ / ✕
RTSP Video              ✓ / ✕
HTTP Push               ✓ / ✕
Local OCR               ✓ / ✕
Barrier Control         UNVERIFIED / VERIFIED
```

This will expose the exact failure instead of one vague "not working."

---

# Final Decision

**Do not buy four replacement cameras yet.**

The uploaded vendor package demonstrates that these cameras have:
- a real Windows x86 SDK
- camera connection API
- native LPR callbacks
- image acquisition
- RTSP media
- HTTP Push configuration
- FTP
- whitelist/parking functions
- GPIO/gate functions

The present problem is not that the cameras are unusable.

The present problem is that SmartPark has not yet implemented the vendor's actual Windows x86 connection path correctly.

Prove `Net_AddCamera → Net_ConnCameraEx → Net_RegReportMessEx` in an x86 Windows helper before making any replacement-hardware decision.
