# SmartPark Edge

SmartPark Edge is a **plate-first parking system** for a Windows site PC. Cameras read number plates, the Site Server opens or holds the barrier, casual drivers get a receipt, and registered plates (season, VIP, staff) can open automatically.

Desktop and web are clients. Parking logic, cameras, gates, receipts, and payments run in the Site Service. A small **32-bit Windows process** talks to the camera vendor SDK so the main app can stay 64-bit.

Install on the parking PC from `dist/SmartParkEdge-Install` (or the USB zip). Sign in `admin` / `SmartPark1!`. How to help, and what is still open, is in [CONTRIBUTING.md](CONTRIBUTING.md). How the pieces fit is in [ARCHITECTURE.md](ARCHITECTURE.md) and [docs/00-START-HERE.md](docs/00-START-HERE.md).

## Perspective

The plate is the identity. Paper, QR, and future cards are helpers — they are not a second ticket system.

Hardware is behind **adapters**. Today the live cameras and barriers use the HVX / QY NetSDK path. A later vendor, a camera you build yourself, or a paper printer you plug in USB, should register next to that path — not replace the parking core.

The site must keep running if one camera dies, the UI is closed, or FastALPR is not used. Native camera plates are the default. Local OCR is optional.

## What it is built from

| Layer | What |
|---|---|
| Site Service | Python 3.11+, FastAPI, SQLite (Postgres only if `SMARTPARK_DATABASE_URL` is set) |
| Desktop | PySide6 |
| Web | Static UI served by the same API (`http://127.0.0.1:8760`) |
| Camera SDK | 32-bit `hvx_sdk_host` loading `NetSDK.dll` (port **30000**) |
| Optional OCR | FastALPR + ONNX; OpenCV only to improve a JPEG for that OCR |
| Receipts | USB thermal ESC/POS (58/80 mm), file-only, or LAN ESC/POS |
| Gates | Camera GPIO + Board* TCP + LED UDP, wrapped by `GateController` |

Ubuntu can run the API and UI for development. The vendor SDK host is **Windows x86 only**.

## How flexible it is

**Yes — without tearing out the engine**, if you stay on the adapter and settings seams:

- **Another camera vendor** — implement `CameraAdapter` (`connect`, `snapshot`, `live_sources`, `capabilities`) and register it in `app/infrastructure/hardware/cameras/`. Parking (`handle_plate_event`) does not import `Net_*`.
- **A camera you design** — if it speaks this site’s NetSDK login, keep `adapter_id=hvx`. If it is RTSP/HTTP JPEG, extend the existing RTSP adapter. If it is a new DLL, add a **new sidecar** like `hvx_sdk_host`; do not load that DLL inside the 64-bit API.
- **Python / packages** — bump versions in `requirements.txt` and `packaging/windows/requirements-windows.txt`, run tests, then run `./packaging/make_windows_kit.sh` if the parking PC install must pick up new wheels. Keep the 32-bit host on a ctypes-only 32-bit Python; do not pull PySide or FastALPR into it.
- **Printers** — Settings picks a USB thermal receipt printer (ESC/POS). Simulation uses the same path.
- **Payments** — kiosk cash is live; a mobile-money provider plugs into `PaymentProvider` without changing the boom.

**What you must not do:** rewrite `tools/hvx_sdk_host/`, `app/services/hvx_client.py`, or `app/services/gates.py`, or make ONVIF/RTSP the default while this site’s cameras are HVX. Unknown `adapter_id` falls back to `hvx`.

## What it does

- SDK login on port 30000, live JPEG, native plate callbacks
- Connect-all skips dead cameras so the rest still log in
- Registered plates open the gate; casuals print then open (default policy)
- USB thermal receipt print from Settings; Simulation uses the same printer
- Site-wide sessions (enter 1#, leave 2# is valid)
- System Health, bounded queues, logon tasks for Site Service + HVX host
- Roles: Admin, Operator, Kiosk Operator

## What it does not

- Treat ping, HTTP 80, or RTSP-open as “camera connected”
- Load `NetSDK.dll` in 64-bit Python
- Run FastALPR on every live frame
- Invent a mobile payment from a browser “success” page
- Require PostgreSQL, Edge Agents, or ONVIF for the current site
- Emulate a vendor **SoftDog** USB license dongle (if the SDK needs one, plug it into the PC that runs the 32-bit host)

## Windows install

Copy `dist/SmartParkEdge-Install` onto a USB stick. On the parking PC, double-click **Install-SmartPark.bat**. Then **Add site cameras** → **Connect all**. Camera login is typically `admin` / `admin` on port 30000. Register plates under **Vehicles**.

Close any other SDK client first. First hardware pass: [FIRST_TEST_WINDOWS.md](FIRST_TEST_WINDOWS.md).

## Developers

64-bit Python 3.11+:

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.desktop.launch
```

Or API only: `uvicorn app.api_main:app --host 127.0.0.1 --port 8760`.

32-bit Python is required only for the HVX host (`tools/hvx_sdk_host/run_hvx_host.bat`). Vendor DLLs live in `OcxConfig/`.

USB kit (from this tree):

```bash
./packaging/make_windows_kit.sh
```

## Docs

| Doc | Topic |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Processes, adapters, data flow |
| [docs/00-START-HERE.md](docs/00-START-HERE.md) | Map of `docs/` |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute, gaps, what not to touch |
| [FIRST_TEST_WINDOWS.md](FIRST_TEST_WINDOWS.md) | First real-camera test |
