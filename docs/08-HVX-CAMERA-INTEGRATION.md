# HVX camera integration

## Purpose

Document the QY/HVX path used on this site so other vendors wrap beside it, not over it.

## Runtime

- Windows x64 app talks HTTP to localhost `hvx_sdk_host` (port 8765)
- Host is 32-bit Python loading PE32 `NetSDK.dll` from `OcxConfig/`
- SDK control port is **30000**, not HTTP 80
- Timeout is **seconds** (`3` / `5`), not milliseconds
- Success is `rc == 0`
- Native plates: `Net_RegImageRecvEx` / `Ex2` after a real login
- Live view: SDK JPEG (`Net_GetJpgBuffer`), not RTSP
- Connect-all probes TCP on `{camera_ip}:30000` for about 1s first. A dead camera is marked `SDK_FAILED` and skipped so the rest still log in. HTTP to the 32-bit host waits up to 20s. The UI connects one camera at a time so a slow camera cannot close the app.

## Adapter wrap

`HVXCameraAdapter` calls `HVXHostClient.connect` with the same arguments the API uses. Preview, captures, and GPIO keep using `HVXHostClient` directly.

## Do not

- Treat TCP/80, ONVIF identify, or RTSP-open as connected
- Load `NetSDK.dll` in 64-bit Python
- Change default `adapter_id` away from `hvx`

Commissioning: [FIRST_TEST_WINDOWS.md](../FIRST_TEST_WINDOWS.md) and [README.md](../README.md). If the vendor SDK needs a USB license dongle, see [16-OPENCV-AND-SOFTDOG.md](16-OPENCV-AND-SOFTDOG.md).
