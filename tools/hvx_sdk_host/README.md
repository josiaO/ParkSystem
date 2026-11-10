# HVX SDK Host

This process exists because the camera vendor SDK is **32-bit Windows x86** while SmartPark stays a normal 64-bit application.

It uses only the Python standard library and `ctypes` so the 32-bit environment stays small.

## Vendor files

```text
OcxConfig/NetSDK.dll
OcxConfig/CommModule.dll
OcxConfig/PlaySdk.dll
OcxConfig/Log.dll
OcxConfig/RtspRecvSdk.dll
OcxConfig/DecodeSdk.dll
```

`hvx_host.py` loads that directory automatically. Override with `SMARTPARK_HVX_VENDOR_DIR` if needed. `vendor/` is only a fallback.

If the vendor requires a USB license dongle (SoftDog / SuperDog), plug it into this PC. See [docs/16-OPENCV-AND-SOFTDOG.md](../../docs/16-OPENCV-AND-SOFTDOG.md).

## Run

```powershell
py -3.11-32 hvx_host.py
```

The process refuses to start if Python is not 32-bit.

The QY live preview is independent from MediaMTX. Recognition callbacks keep
their native camera resolution, while the operator preview uses a bounded
display-only JPEG profile so the 32-bit bridge does not encode unnecessary
pixels. Defaults are 1280px maximum width, quality 78, and 15 FPS. Override
these for a Windows field test with `SMARTPARK_HVX_JPEG_MAX_WIDTH`,
`SMARTPARK_HVX_JPEG_QUALITY`, and `SMARTPARK_HVX_JPEG_FPS`.

While a camera is live, inspect `http://127.0.0.1:8765/video-status/<handle>`.
The normal path reports `capture_mode=sdk_draw_data` and
`draw_data_primary=true`. `capture_mode=play_sdk_hwnd` means the slower
PrintWindow/BitBlt compatibility path is active; inspect `window_capture_ms`
before changing the preview profile.

## SDK sequence

```text
Net_Init()
Net_AddCamera(ip)
Net_RegReportMessEx(handle, cb)   # before connect
Net_ConnCameraEx(handle, port=30000, timeout_seconds, user, pass)
Net_ConnCamera(handle, port, timeout)  # fallback
Net_QueryConnState(handle)             # 0 is connected in the supplied NetSDK; 2 is accepted too
Net_FuntionListRsp(handle, 800-byte buffer)
                                       # select stream 4/3/2/1/0 from +0x04 capability bits
Net_RegOffLineClient(handle)
Net_StartVideo(handle, selected_stream, hidden message-pumped HWND)
Net_RegImageRecvEx2 then Net_RegImageRecvEx
Net_SetDrawDataOut(handle, cb)        # primary decoded-frame callback
Net_GetJpgBuffer(handle)               # compatibility fallback sampler
Net_FindDeviceIp(cb)  # optional; needs WinPcap
Net_ImageSnap(handle, T_DCImageSnap*)
Net_DisConnCamera / Net_DelCamera
```

Timeout is **seconds** (`unsigned short`). Port `0` means 30000. Success is `rc == 0`.

Physical GPIO: `POST /gpio/pulse` runs `Net_GateSetup` (1 = open) then `Net_WriteGPIOState` on a connected camera handle.
