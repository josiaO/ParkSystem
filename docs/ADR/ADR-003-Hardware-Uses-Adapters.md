# ADR-003 — Hardware uses adapters

## Status

Accepted.

## Decision

Parking and payment code must go through `CameraAdapter` / `GateControllerAdapter`. Production cameras wrap the HVX host client and `GateController`. Additional adapters (RTSP, ONVIF, future vendors) register beside HVX and must not become the default.

## Consequences

- `app/services/hvx_client.py` and `tools/hvx_sdk_host/` stay
- Device registry is a projection, not a second inventory
- Unknown `adapter_id` falls back to `hvx`
