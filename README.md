Zirp

Zirp is a **plate-first parking system**. Cameras read number plates, the Site Server opens or holds the barrier, casual drivers get a receipt, and registered plates (season, VIP, staff) can open automatically.

The **desktop app and Site Service** run on Windows and Linux. On Windows, a small **32-bit OcxConfig/NetSDK host** owns the explicit `qy` camera adapter and native callbacks while the main app stays 64-bit. The historical `hvx` camera ID remains supported for existing databases. That host cannot run on Linux. FastALPR remains application-side and reads the newest JPEG delivered by the host; generic IP cameras use RTSP/HTTP.

For a real site, install the approved SmartPark Windows package and follow the production documentation in [docs-site/index.html](docs-site/index.html). The portable/USB package is a maintainer test artifact. First-run authentication is created by the deployment wizard; this repository does not define a production default password.

## Perspective

The plate is the identity. Paper, QR, and future cards are helpers — they are not a second ticket system.

Hardware is behind **adapters**. Today QY is one registered camera vendor using the OcxConfig/NetSDK path on Windows. A later vendor, a camera you build yourself, or a paper printer you plug in USB, should register next to that path — not replace the parking core. See [camera-engine migration](docs/CAMERA-ENGINE-MIGRATION.md).

The site must keep running if one camera dies, the UI is closed, or FastALPR is not used. OcxConfig/NetSDK is the Windows HVX video backend. Native camera plates are optional; FastALPR can read the fresh host JPEG when native plate text is empty. Local OCR is also used for generic IP cameras.

## Platform matrix

| Piece | Windows | Linux / macOS |
|---|---|---|
| Site Service (API + parking) | Yes | Yes |
| Browser UI (`http://127.0.0.1:8760`) | Yes | Yes |
| Desktop (PySide6) | Yes | Yes (`python -m app.desktop.launch`) |
| HVX NetSDK host (port 30000 cameras) | Yes (32-bit) | No |
| Generic IP cams (`rtsp` / `dahua` / `hikvision`) | Yes | Yes + FastALPR |

## What it is built from

| Layer | What |
|---|---|
| Site Service | Python 3.11+, FastAPI, SQLite (Postgres only if `SMARTPARK_DATABASE_URL` is set) |
| Desktop | PySide6 (Windows and Linux) |
| Web | Static UI served by the same API (`http://127.0.0.1:8760`) — **any OS** |
| Camera SDK | 32-bit `hvx_sdk_host` loading the matched OcxConfig `NetSDK.dll` family (port **30000**) — **Windows only** |
| Optional OCR | FastALPR + ONNX; OpenCV only to improve a JPEG for that OCR |
| Receipts | USB thermal ESC/POS (58/80 mm), file-only, or LAN ESC/POS |
| Gates | Camera GPIO + Board* TCP + LED UDP, wrapped by `GateController` |

## How flexible it is

**Yes — without tearing out the engine**, if you stay on the adapter and settings seams:

- **Another camera vendor** — implement `CameraAdapter` (`connect`, `snapshot`, `live_sources`, `capabilities`) and register it in `app/infrastructure/hardware/cameras/`. Parking (`handle_plate_event`) does not import `Net_*`.
- **A camera you design** — if it speaks this site’s NetSDK login, use `adapter_id=qy` on a Windows host. Existing `adapter_id=hvx` rows remain compatible. If it is RTSP/HTTP JPEG, use the RTSP adapter. If it is a new DLL, add a **new sidecar** like `hvx_sdk_host`; do not load that DLL inside the 64-bit API.
- **Python / packages** — bump versions in `requirements.txt` and `packaging/windows/requirements-windows.txt`, run tests, then run `./packaging/make_windows_kit.sh` if the parking PC install must pick up new wheels. Keep the 32-bit host on a ctypes-only 32-bit Python; do not pull PySide or FastALPR into it.
- **Printers** — Settings picks a USB thermal receipt printer (ESC/POS). Simulation uses the same path.
- **Payments** — kiosk cash is live; a mobile-money provider plugs into `PaymentProvider` without changing the boom.

**What you must not do:** bypass the OcxConfig/NetSDK host, load its 32-bit DLLs in the 64-bit API, or make ONVIF/RTSP the default while this site’s cameras are HVX. Unknown `adapter_id` falls back to `hvx`.

## What it does

- SDK login on port 30000, OcxConfig live JPEG, detection overlays, and native plate callbacks (Windows + HVX host)
- Connect-all skips dead cameras so the rest still log in
- Registered plates open the gate; casuals print then open (default policy)
- USB thermal receipt print from Settings; Simulation uses the same printer
- Site-wide sessions (enter 1#, leave 2# is valid)
- System Health, bounded queues, logon tasks for Site Service + HVX host
- Roles: Admin, Operator, Kiosk Operator

## What it does not

- Treat ping, HTTP 80, or RTSP-open as “camera connected” for HVX
- Load `NetSDK.dll` in 64-bit Python or on Linux
- Run FastALPR on every desktop repaint
- Invent a mobile payment from a browser “success” page
- Require PostgreSQL, Edge Agents, or ONVIF for the current site
- Emulate a vendor **SoftDog** USB license dongle (if the SDK needs one, plug it into the PC that runs the 32-bit host)

## Windows install (full HVX site)

Use the approved Windows installer package on the Site Server, select **Site Server** in Deployment Configuration, configure the approved database and create the first administrator. Then add cameras, connect them and complete the field acceptance checks. Camera credentials are site-specific and must not be copied from this repository. Register plates under **Vehicles**.

Close any other SDK client first. First hardware pass: [FIRST_TEST_WINDOWS.md](FIRST_TEST_WINDOWS.md).

## Any OS — web UI (Linux / macOS / Windows)

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
./scripts/run_dev_linux.sh  # or: python -m app.web.launch
```

Opens `http://127.0.0.1:8760`. Create the first administrator through the deployment wizard; do not rely on a repository default password.

For **normal (non-LAPR) IP cameras**, set Adapter to **rtsp** (or dahua/hikvision), then Connect. FastALPR reads plates. Install `ffmpeg` on the PATH for RTSP snapshots.

HVX LAPR cameras and camera GPIO still need a **Windows** machine running the 32-bit SDK host on the camera LAN.

API only: `uvicorn app.api_main:app --host 127.0.0.1 --port 8760`.

## Windows desktop (operators on the parking PC)

```bash
python -m app.desktop.launch
```

32-bit Python is required only for the HVX host (`tools/hvx_sdk_host/run_hvx_host.bat`). Vendor DLLs live in `OcxConfig/`.

USB kit (from this tree):

```bash
./packaging/make_windows_kit.sh
```

## Docs

| Doc | Topic |
|---|---|
| [docs/SYSTEM-GUIDE.md](docs/SYSTEM-GUIDE.md) | End-to-end guide: streaming, OcxConfig/QY, recognition, capture/crop, sessions, payments, developer mode, and site time |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Processes, adapters, data flow |
| [docs/00-START-HERE.md](docs/00-START-HERE.md) | Map of `docs/` |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute, gaps, what not to touch |
| [FIRST_TEST_WINDOWS.md](FIRST_TEST_WINDOWS.md) | First real-camera test |
| [docs/ADR/ADR-005-Windows-First-HVX-SDK-Host.md](docs/ADR/ADR-005-Windows-First-HVX-SDK-Host.md) | Why SDK stays Windows |
