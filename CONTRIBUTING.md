# Contributing to SmartPark Edge

Read [README.md](README.md) first for what this software is. This file is for people who will change code.

## Where work belongs

```text
app/api_main.py                 HTTP API
app/services/                   Parking, plates, preview, HVX client, gates
app/services/simulation.py      Shared live + Simulation entry/exit
app/infrastructure/hardware/    Camera / gate / printer adapters
app/domain/                     Protocols (CameraAdapter, …)
app/desktop/                    PySide UI
app/web/                        Browser UI
app/site_service.py             Production API process
tools/hvx_sdk_host/             32-bit NetSDK process — do not rewrite
packaging/windows/              USB installer
tests/                          unittest
docs/                           Architecture and ADRs
```

Parking decisions go through `handle_plate_event`. Hardware goes through adapters. Do not call `Net_*` from tariff or payment code.

## What not to touch (engine)

Do not relocate or rewrite:

- `tools/hvx_sdk_host/`
- `app/services/hvx_client.py`
- `app/services/gates.py`
- the port **30000** NetSDK connect sequence

Wrap them (`HVXCameraAdapter` already calls `HVXHostClient.connect`). Default `adapter_id` stays `hvx`. SQLite stays the live store unless `SMARTPARK_DATABASE_URL` is set. `DIRECT` is the live connection mode. Gate default stays `COMMISSIONING`.

## How to add a camera vendor

See [docs/10-ADDING-A-NEW-CAMERA-VENDOR.md](docs/10-ADDING-A-NEW-CAMERA-VENDOR.md). Short version: new class implementing `CameraAdapter`, register in `ADAPTERS`, set `adapter_id` on those cameras only. Do not switch the default away from HVX for this site.

## How to change Python or packages

1. Edit `requirements.txt` and `packaging/windows/requirements-windows.txt` together.
2. Run `python -m unittest discover -s tests`.
3. Keep `opencv-python-headless` only if FastALPR contrast boost still matters (see [docs/16-OPENCV-AND-SOFTDOG.md](docs/16-OPENCV-AND-SOFTDOG.md)).
4. Do not add FastAPI, PySide, or OpenCV to the 32-bit host (stdlib + ctypes only).
5. Run `./packaging/make_windows_kit.sh` if the parking PC install must pick up wheels.

A newer **64-bit** Python (3.11 → 3.12) is a packaging + test job. The **32-bit** host must still load PE32 `NetSDK.dll`.

## Gaps and needs

These are useful contributions. They are not excuses to replace the engine.

| Need | Why it is open |
|---|---|
| Full ONVIF adapter | Stub only; must not become default |
| Real RTSP live as equal to SDK JPEG | Probe exists; site live view is NetSDK JPEG |
| Mobile-money `PaymentProvider` | Ledger and kiosk cash exist; no live aggregator |
| PostgreSQL on a real site | Models are ready; SQLite is what we ship |
| Windows Service (SCM) | Logon scheduled tasks run Site Service + HVX host today |
| SoftDog / SuperDog | Vendor license USB; we do not emulate it — document site PCs that need the dongle |
| Edge Agent (`EDGE_AGENT`) | Reserved; DIRECT is live |
| Paper take-sensor | Policy `REQUIRE_TAKEN_BEFORE_OPEN` exists; no hardware sensor wired |
| More tariffs than Car1 | JSON rules on `tariffs`; extend the fee engine, not hard-coded constants |
| 24h soak on the parking PC | RAM/CPU/queue health; cannot be signed off from a laptop |

## Tests

```bash
python -m unittest discover -s tests
```

Add tests next to the seam you change (`tests/test_adapters.py` for a new camera adapter).

## Docs

Fill a `docs/` file when the feature exists. Do not empty-stub the rest of a long list. Keep language about **this product**, not about older trees or internal rewrites.

## Pull requests

Small diffs. State why. Do not bundle an HVX host rewrite with a UI tweak.
