# Hardware adapter architecture

## Purpose

Let parking, tariff, and payment code talk to cameras and barriers through adapters, without replacing the HVX host or GPIO path.

## What this must NOT do

- Move or rewrite `tools/hvx_sdk_host/`
- Make ONVIF/RTSP the default camera path
- Introduce a second device database
- Put production lanes in SHADOW by default
- Stop parking services from reaching the HVX host through the wrap

## Boundary

```mermaid
flowchart TD
  parking[Parking / API]
  adapters[CameraAdapter / GateControllerAdapter]
  hvxWrap[HVXCameraAdapter / HVXGateAdapter]
  extras[RTSP / ONVIF / Simulated]
  host[HVXHostClient]
  sdk[32-bit hvx_sdk_host]
  physical[GPIO + Board TCP + LED UDP]

  parking --> adapters
  adapters --> hvxWrap
  adapters --> extras
  hvxWrap --> host
  hvxWrap --> physical
  host --> sdk
```

Default `adapter_id` is `hvx`. Unknown adapter ids fall back to HVX. `dahua`, `hikvision`, and `ipcam` map to the RTSP adapter (HTTP snapshot or RTSP + FastALPR).

RTSP / Dahua / Hikvision cameras become `VIDEO_CONNECTED` after a live JPEG is obtained. They must not report `SDK_CONNECTED`. **Discover** (`scan_lan=true`) finds those cameras on HTTP 80 / RTSP 554 using username and password only; HVX discovery on port 30000 is unchanged. ONVIF **GetProfiles / GetStreamUri** can fill `stream_profiles` but ONVIF login is still not the site default. `live_sources()` tells the live pump whether to stay on NetSDK video or optional RTSP.

Live view and FastALPR go through `app/services/media_gateway.py` (one producer per camera, latest-frame buffers, named FFmpeg profiles). They must not each open a new physical camera session.

Adding a vendor: [10-ADDING-A-NEW-CAMERA-VENDOR.md](10-ADDING-A-NEW-CAMERA-VENDOR.md).

## Device registry

`GET /devices` projects existing `cameras` and `gates` rows (plus Board*/LED IPs). No new table.

## Connection mode

`DIRECT` is the live path. `EDGE_AGENT` is reserved and refused on SDK connect.

## Lane modes

| Mode | Automatic boom pulse | Manual Hardware Lab |
|---|---|---|
| COMMISSIONING (default) | Yes | Yes |
| PRODUCTION | Yes | Yes |
| SHADOW | No (`dry_run`) | Yes |
| MAINTENANCE | No (`dry_run`) | Yes |
