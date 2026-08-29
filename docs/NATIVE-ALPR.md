# Native ALPR

## Purpose

Document the working HVX/QY onboard plate path so it never has to be reverse-engineered again.

## Runtime

32-bit `hvx_sdk_host` loads `NetSDK.dll`. Control port **30000**. Timeouts are **seconds**.

Sequence:

1. `Net_Init`
2. `Net_AddCamera`
3. `Net_RegReportMessEx`
4. `Net_ConnCamera` / `Net_ConnCameraEx` (username/password)
5. `Net_RegImageRecvEx` / `Ex2`
6. `Net_StartVideo` (substream for live JPEG)

Plate payload: `CAM_PlateInfo.szPlateText` / `T_ImageUserInfo.szLprResult`, score 0–100.

Coil: `Net_ReadGPIOState` on GPIO IN (learned 1–7). Rising edge → `Net_ImageSnap` if the camera did not already push a plate JPEG.

## Adapter

`HVXNativeALPRProvider` maps that callback through `native_from_sdk_capture`. It does not open gates and does not run FastALPR.

Live JPEG is `Net_GetJpgBuffer` on the host. The Site Service MediaGateway polls it. FastALPR is a separate DETECT consumer.

Disable native fusion only with `native_alpr_enabled=false` (rollback/debug). Default is on.

Full connect notes: [08-HVX-CAMERA-INTEGRATION.md](08-HVX-CAMERA-INTEGRATION.md).
