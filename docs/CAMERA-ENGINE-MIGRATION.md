# Camera engine migration

## Current boundary

Zirp owns parking, FastALPR, gate policy, payments, and the operator UI. Camera
hardware is selected through `adapter_id` and media is carried through
`CameraLiveSpec` into the bounded `LocalMediaGateway`.

The installed adapters are:

- `qy`: QY/OcxConfig/NetSDK, Windows-only native host, latest-frame video,
  native events, GPIO, and detection-zone queries.
- `hvx`: legacy persisted alias for existing installations.
- `rtsp`: generic RTSP/HTTP camera; FastALPR remains application-side.
- `onvif`: ONVIF discovery and profile metadata; vendor analytics remain
  optional and device-specific.
- `simulated`: test-only adapter.

QY is deliberately not treated as generic RTSP. When `adapter_id=qy`, the
camera must first obtain a native SDK handle. If it does not, the media gateway
reports the native adapter error and does not open a competing RTSP reader.

## What was migrated

1. Adapter identity now travels from the camera row into `CameraLiveSpec`.
2. Native-stream ownership is selected from adapter identity, not only from a
   populated SDK handle.
3. QY is a first-class registry entry while `hvx` remains backwards compatible.
4. The common adapter contract now includes connection, health, snapshot, live
   sources, disconnect, detection zones, and event draining.
5. The media health payload reports `adapter_id`, `stream_backend`, native-stream
   requirement, frame sequence, queue depth, and reconnect state.
6. `GET /camera-adapters` exposes the installed adapter catalog for onboarding
   and future developer tooling.

## Future C++ engine

The C++ engine should implement the same host contract rather than replacing
Zirp. It can replace the Python/ctypes QY host behind the existing local HTTP
boundary:

```text
Zirp 64-bit process
    -> stable local camera-engine API
        -> QY 32-bit native worker
        -> other vendor workers
```

The vendor boundary should use a versioned C ABI or local IPC; STL objects and
vendor pointers must not cross the boundary. This allows the QY worker to use
the vendor DLLs safely while Zirp remains unchanged. The Python host remains a
working reference and rollback path until the C++ worker has been tested on the
real Windows barrier cameras.

## Adding another vendor

1. Add a vendor adapter module under `app/infrastructure/hardware/cameras/`.
2. Register its ID in the adapter registry.
3. Declare only capabilities the SDK really supports.
4. Add a media source mapping and keep frame delivery latest-only.
5. Add adapter contract tests and a Windows soak test if native DLLs are used.
6. Keep FastALPR independent unless the vendor's native plate events are
   explicitly enabled for that camera.
