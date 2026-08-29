# Camera adapters

## Purpose

Talk to cameras through `CameraAdapter`. Parking never imports NetSDK or ONVIF directly.

## What owns this

- Contract: `app/domain/cameras.py`
- Registry: `app/infrastructure/hardware/cameras/__init__.py`
- HVX wrap: `app/infrastructure/hardware/cameras/hvx.py` → `HVXHostClient`

## Default

`adapter_id=hvx`. Unknown ids fall back to HVX. `dahua` / `hikvision` / `ipcam` map to the RTSP adapter.

## Capabilities

Adapters declare capabilities (NATIVE_ALPR, RTSP, SNAPSHOT, …). Do not infer capability from the vendor name alone.

## Camera vs stream

The `cameras` row is the device. MAIN/SUB/LIVE/DETECT/EVIDENCE live in `cameras.stream_profiles` JSON.

## Adding a vendor

See [ADDING-A-CAMERA-VENDOR.md](ADDING-A-CAMERA-VENDOR.md) and [10-ADDING-A-NEW-CAMERA-VENDOR.md](10-ADDING-A-NEW-CAMERA-VENDOR.md).
