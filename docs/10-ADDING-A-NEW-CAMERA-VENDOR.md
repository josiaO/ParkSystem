# Adding a new camera vendor

## Purpose

Add another camera brand (or a camera you manufacture) **without** rewriting the HVX host, parking core, or default site path.

## Dashboard vs code

**On the dashboard (Cameras → Add / Edit → Adapter)** you can:

- Add another **HVX / QY** camera (same SDK, port 30000) — leave Adapter as **hvx**. This is the normal site path. No code.
- Point a camera at an adapter that is **already in the product**: `hvx`, `rtsp`, `dahua`, `hikvision`, `onvif`, `simulated`.

**You cannot** invent a new brand from the dashboard alone. There is no “upload SDK” or plugin store. `onvif` will not log in as the site camera. It can discover RTSP URIs (GetProfiles / GetStreamUri) into `stream_profiles`. `rtsp` / `dahua` / `hikvision` connect over HTTP snapshot or RTSP (`VIDEO_CONNECTED`) and use **FastALPR** for plates. They must not report `SDK_CONNECTED` or native plates.

| What you want | Dashboard | Code |
|---|---|---|
| Another camera of this site’s type | Add camera, Adapter **hvx**, Connect | No |
| Same family, different IP | Add site cameras / Discover | No |
| Dahua / Hikvision / generic IP without onboard ALPR | **Discover**, camera username/password, **Add IP cameras & connect** | No — FastALPR reads the video |
| New protocol or new vendor DLL | After the adapter exists, pick it on the camera | Yes — implement `CameraAdapter` (and a sidecar if the DLL is 32-bit) |

Unknown adapter names fall back to **hvx**, so a typo does not switch the site to a stub.

## What owns this

- Contract: `app/domain/cameras.py` (`CameraAdapter`)
- Registry: `app/infrastructure/hardware/cameras/__init__.py` (`ADAPTERS`)
- Parking: `app/services/simulation.py` (`handle_plate_event`) — stays vendor-agnostic
- Local OCR: `app/services/alpr.py` (FastALPR) — vendor-independent; used when the camera has no native plate
- Coil / presence: `app/services/presence.py` — GPIO or HTTP rising edge, not OcxConfig
- UI: camera Adapter dropdown (desktop and web)

## What it must NOT do

- Change default `adapter_id` from `hvx` for this site
- Load a new vendor DLL inside 64-bit Python
- Treat ONVIF identify or RTSP TCP-open as `SDK_CONNECTED`
- Copy-paste `Net_*` into `handle_plate_event`

## How to add a vendor that is not in the list yet

1. Add `app/infrastructure/hardware/cameras/<vendor>.py` with `id`, `connect`, `health`, `snapshot`, `live_sources`, `capabilities`.
2. Register it in `ADAPTERS`.
3. Add the id to the Adapter dropdown (desktop + web).
4. Operators then choose it on **Cameras** — that part is dashboard-only.
5. If the vendor SDK is 32-bit Windows, add a **new** localhost host (same pattern as `hvx_sdk_host`), not a rewrite of the existing one.
6. Deliver plates into the same event path the API already polls (or HTTP push into `handle_plate_event`).
7. Tests in `tests/test_adapters.py`: HVX still has `sdk_login`; the new adapter must not claim HVX login.

## Own-hardware cameras and own ALPR

If your camera implements this site’s QY/NetSDK login (port 30000, plate callback), add it in the dashboard with Adapter **hvx**. If it only offers a web UI or RTSP (Dahua, Hikvision, and similar without onboard LAPR), click **Discover** — no RTSP URL is required. Enter the camera username and password (often `admin` / `admin`) and **Add IP cameras & connect**. Status becomes `VIDEO_CONNECTED` (never `SDK_CONNECTED`), live video streams, and FastALPR is the plate engine. HVX cameras on this site stay on NetSDK.

You do **not** need OcxConfig to run parking or FastALPR. To ship your own ALPR later, keep delivering a plate + JPEG into `handle_plate_event` / `persist_event` (same path FastALPR uses today).

## Python and packages

Bump wheels in `requirements.txt` and the Windows requirements file. Re-run tests. Do not pull OpenCV or FastALPR into the 32-bit host.

## Tests

`tests/test_adapters.py` must still assert ONVIF cannot replace SDK login, and that RTSP/Dahua/Hikvision connect as video + FastALPR with `sdk_login` false.
