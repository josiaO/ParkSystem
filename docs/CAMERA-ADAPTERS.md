# Camera adapters

## Purpose

Talk to cameras through `CameraAdapter`. Parking never imports NetSDK or ONVIF directly.

## What owns this

- Contract: `app/domain/cameras.py`
- Registry: `app/infrastructure/hardware/cameras/__init__.py`
- HVX wrap: `app/infrastructure/hardware/cameras/hvx.py` → `HVXHostClient`

## Default

`adapter_id=hvx` remains the legacy default for existing databases. `qy` is the
explicit vendor name for the same OcxConfig/NetSDK camera family; both IDs use
the isolated Windows native host. Unknown ids fall back to HVX for backwards
compatibility, while new vendor adapters must be registered explicitly.

## Capabilities

Adapters declare capabilities (NATIVE_ALPR, RTSP, SNAPSHOT, …). Do not infer capability from the vendor name alone.

## Camera vs stream

The `cameras` row is the device. MAIN/SUB/LIVE/DETECT/EVIDENCE live in `cameras.stream_profiles` JSON.

The media engine also carries `adapter_id` in `CameraLiveSpec`. Adapter identity
controls ownership before a connection handle exists: QY/HVX cameras never
silently become generic RTSP cameras. An unconnected QY camera reports a
native-adapter error until the NetSDK host supplies a handle.

## Adding a vendor

See [CAMERA-ENGINE-MIGRATION.md](CAMERA-ENGINE-MIGRATION.md),
[ADDING-A-CAMERA-VENDOR.md](ADDING-A-CAMERA-VENDOR.md), and
[10-ADDING-A-NEW-CAMERA-VENDOR.md](10-ADDING-A-NEW-CAMERA-VENDOR.md).

