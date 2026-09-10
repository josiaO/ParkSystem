# Architecture

SmartPark Edge is a modular monolith: one API process, one optional Windows desktop, one 32-bit camera SDK host (Windows only).

```text
Operator (Desktop on Windows, or browser on any OS)
          |
          | HTTP 127.0.0.1:8760
          v
   Site Service  (FastAPI, SQLite, parking, receipts)  ← any OS
          |
          | HTTP 127.0.0.1:8765
          v
   HVX SDK Host  (32-bit Python + NetSDK.dll)  ← Windows only
          |
          v
   Cameras (port 30000)  +  Board* TCP  +  LED UDP
```

## Why the SDK is a separate process

The vendor library is 32-bit Windows. The UI and API are 64-bit. Isolating `NetSDK.dll` means a camera crash does not take down parking logic, and Linux/macOS can still run the API and browser UI. Desktop does not ship for non-Windows.

## Adapters

Parking code talks to:

- `CameraAdapter` — default `hvx` (wraps `HVXHostClient`); use `rtsp`/`dahua`/`hikvision` for generic IP cams
- `GateController` — GPIO + Board* + LED (`app/services/gates.py`)
- `PrinterAdapter` — simulated files, USB thermal ESC/POS, or LAN ESC/POS

Unknown camera `adapter_id` falls back to HVX. RTSP and ONVIF are registered extras; they are not the HVX site default.
## Connection states

```text
UNKNOWN → DISCOVERED → SDK_CONNECTING → SDK_CONNECTED
                              └→ SDK_FAILED
```

`SDK_CONNECTED` means `Net_ConnCameraEx` / `Net_ConnCamera` returned `0` on port 30000. Ping and HTTP 80 are not a login.

## Parking flow

1. Plate from native callback (or Simulation)
2. Normalize plate → entitlement (registered vs casual)
3. Short SQLite transaction (session row)
4. Print receipt if policy says so
5. Pulse gate (unless policy holds for paper-taken)
6. Audit `access_decisions` / `gate_commands`

Sessions are site-wide. Payment is a ledger; the boom reads local SUCCEEDED totals.

## Processes

| Process | Role | OS |
|---|---|---|
| Site Service | API, events, receipts | Any |
| Browser UI | Operator client | Any |
| Desktop | Operator client (optional) | Windows |
| HVX host | NetSDK | Windows x86 |

On Windows the installer can register Site Service and HVX host as logon tasks.
## Further reading

- [docs/03-SYSTEM-ARCHITECTURE.md](docs/03-SYSTEM-ARCHITECTURE.md)
- [docs/07-HARDWARE-ADAPTER-ARCHITECTURE.md](docs/07-HARDWARE-ADAPTER-ARCHITECTURE.md)
- [docs/10-ADDING-A-NEW-CAMERA-VENDOR.md](docs/10-ADDING-A-NEW-CAMERA-VENDOR.md)
- [docs/06-SESSION-STATE-MACHINE.md](docs/06-SESSION-STATE-MACHINE.md)
