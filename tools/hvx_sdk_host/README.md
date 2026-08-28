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

## SDK sequence

```text
Net_Init()
Net_AddCamera(ip)
Net_RegReportMessEx(handle, cb)   # before connect
Net_ConnCameraEx(handle, port=30000, timeout_seconds, user, pass)
Net_ConnCamera(handle, port, timeout)  # fallback
Net_QueryConnState(handle)
Net_RegOffLineClient(handle)
Net_RegImageRecvEx2 then Net_RegImageRecvEx
Net_FindDeviceIp(cb)  # optional; needs WinPcap
Net_ImageSnap(handle, T_DCImageSnap*)
Net_DisConnCamera / Net_DelCamera
```

Timeout is **seconds** (`unsigned short`). Port `0` means 30000. Success is `rc == 0`.

Physical GPIO: `POST /gpio/pulse` runs `Net_GateSetup` (1 = open) then `Net_WriteGPIOState` on a connected camera handle.
