# Zirp (SmartPark Edge)

Plate-first parking and lane control for a site with entry and exit lanes.
A camera reads the plate, a receipt with a QR is printed at entry, drivers pay
at a kiosk or by mobile money, and the exit barrier opens only for a paid or
free visit. The plate is the identity; recognition is evidence, never authority
to open a barrier.

## Processes

| Process | Command | Role |
|---|---|---|
| Site Service | `python -m app.site_service` | FastAPI API and every parking decision (port 8760) |
| Media Service | `python -m app.media_service` | Owns MediaMTX (RTSP in, WebRTC/RTSP out) for generic cameras |
| Recognition Worker | `python -m app.recognition_worker` | FastALPR on generic cameras' DETECT streams |
| HVX SDK host | `python32 tools/hvx_sdk_host/hvx_host.py` | 32-bit QY/HVX vendor SDK: native plates, video, GPIO (Windows only) |
| Desktop | `python -m app.desktop.launch` | PySide6 operator/admin app (primary UI) |

Data lives in SQLite (single PC) or PostgreSQL (Site Server shared with Edge
Nodes). Roles: **Site Server**, **Edge Node** (one gate PC using the Site
Server's database), **Operator Workstation** (UI only).

## Run locally (Linux, development)

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
scripts/run_dev_linux.sh            # Site Service + browser UI on http://127.0.0.1:8760
```

The first-run administrator password is shown once on the local sign-in page and
stored in `bootstrap_password.txt` in the data folder
(`~/.local/share/smartpark-edge` or `%ProgramData%\SmartParkEdge`).

## Tests

```bash
QT_QPA_PLATFORM=offscreen XDG_DATA_HOME=$(mktemp -d) pytest -q
node tests/whep-player.test.cjs
```

## Windows site installation

Build the offline kit with `packaging/make_windows_kit.sh`, then follow:

* [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md): Site Server, Edge Node and Operator Workstation
* [docs/POSTGRESQL-PREREQUISITE.md](docs/POSTGRESQL-PREREQUISITE.md) and [docs/DATABASE_CONFIGURATION.md](docs/DATABASE_CONFIGURATION.md)
* [docs/LANE-DEPLOYMENT.md](docs/LANE-DEPLOYMENT.md): gates, cameras and node ownership
* [docs/WINDOWS-SERVICES.md](docs/WINDOWS-SERVICES.md): boot-time services, HVX Session 0 test, reboot test
* [docs/CAMERA-TROUBLESHOOTING.md](docs/CAMERA-TROUBLESHOOTING.md) and [docs/RECOGNITION-MEASUREMENTS.md](docs/RECOGNITION-MEASUREMENTS.md)
* [docs/OFFLINE-OPTIONS.md](docs/OFFLINE-OPTIONS.md): what happens when a gate loses the database link
* [docs/SOAK-TEST.md](docs/SOAK-TEST.md): 72-hour soak procedure and pass criteria

