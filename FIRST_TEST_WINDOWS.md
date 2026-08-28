# First Windows Hardware Test

Copy `dist/SmartParkEdge-Install` or `dist/SmartParkEdge-USB.zip` onto a USB stick. On the parking PC, double-click **Install-SmartPark.bat**, then open the Desktop shortcut **SmartPark Edge**.

You do not copy the source tree, and you do not install Python yourself. Re-run the installer if a previous copy installed but never opened — it now writes user environment variables (`SMARTPARK_HOME`, Qt plugin paths, SDK/Python on `PATH`) and a `Start-SmartPark.bat` shortcut.

If the window still does not open, run `Start-SmartPark.bat` from `%LOCALAPPDATA%\Programs\SmartPark Edge` and check `%ProgramData%\SmartParkEdge\logs\launch.log`.

## Goal

Prove a **real HVX SDK connection**, live camera view, and number-plate reading on the parking PC.

A camera is **SDK Connected** only after the 32-bit host logs in with `Net_ConnCameraEx` / `Net_ConnCamera` (`rc == 0`) on **port 30000**. TCP open, ping, or HTTP port 80 is not a login. `CONN_STATE_UNKNOW` right after a successful login is normal on this site.

**Close any other camera SDK client before Connect all.** Two programs cannot own the same QY login. Controller IPs (`.61` / `.65` / `.67` / `.69`) and display IPs (`.62` / `.66` / `.68` / `.70`) are barrier/LED devices — do not add them as cameras. Live view uses SDK JPEG (and the camera HTTP still on port 80). RTSP / `ffprobe` is not required.

## 1. One-command start

From the repo root in PowerShell:

```powershell
.\scripts\Start-SmartPark.ps1
```

Or double-click `scripts\Start-SmartPark.bat`.

That script:

1. Starts the 32-bit HVX host (`http://127.0.0.1:8765`) if 32-bit Python is installed
2. Starts the API (`http://127.0.0.1:8760`)
3. Opens the web UI

### First-time Python (once)

64-bit app:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

32-bit HVX host (required for camera login):

```powershell
py -3.11-32 -c "import struct; print(struct.calcsize('P') * 8)"
```

Must print `32`. Then you can also start the host alone with `tools\hvx_sdk_host\run_hvx_host.bat`.

Confirm the host:

```text
http://127.0.0.1:8765/info
```

Expected: `"available": true`, `"python_bits": 32`.

## 2. Sign in

The first start creates an admin. The login page is prefilled:

```text
Username: admin
Password: SmartPark1!
```

You no longer need `python -m app.cli create-admin` for a first test.

## 3. Add the site cameras (1# and 2# lanes)

On **Cameras**, click **Add site cameras**.

Each numbered lane (`1#`, `2#`) is an entry+exit pair, and each side has three devices:

```text
1# Entry  camera 192.168.1.144   controller 192.168.1.61   display 192.168.1.62
1# Exit   camera 192.168.1.145   controller 192.168.1.69   display 192.168.1.70
2# Entry  camera 192.168.1.49    controller 192.168.1.65   display 192.168.1.66
2# Exit   camera 192.168.1.50    controller 192.168.1.67   display 192.168.1.68
```

Only **camera** IPs use SDK port **30000** (`admin` / `admin`). Do not SDK-connect controller (`Board*`) or display (`IpAddr*`) IPs. Do not use port 80 for SDK. **Connect all** is camera-only.

## 4. Connect

Click **Connect all** (or select one camera and **SDK Connect**). Cameras are tried one at a time. If a camera has no TCP on port 30000, it is **skipped** after about one second so the others still connect. A slow camera that is reachable is given about 20 seconds. The app stays open — it no longer times out and closes because one camera hung.

Wait until status is:

```text
SDK_CONNECTED
```

Skipped cameras show `SDK_FAILED` with “No TCP … skipped SDK login”. Connect those later when they are powered and on the LAN.

If it fails, the Error column shows the SDK return code. Also record:

- HVX host `/info`
- `connect_rc` / `connect_rc_name`
- camera IP and SDK port **30000**
- whether `OcxConfigClient.exe` still connects from the same PC

## 5. Live view and plates

Select a connected camera.

- Live view uses SDK JPEG (and the camera HTTP still). RTSP / ffprobe is not required.
- **Native plates** come from the QY cameras themselves after SDK login (`T 285 DQP` style). The camera already does ANPR and sends `szLprResult` on `Net_RegImageRecvEx`. Live video without plates usually means another SDK client still owns that callback — close it and Connect all again.
- **FastALPR** is a second, local OCR on a live JPEG or a simulation upload. The USB kit now bundles FastALPR wheels and ONNX models so it works offline.
- **Capture snapshot** saves one live JPEG from the selected camera.

## 6. Registered plates

On **Vehicles**, click **Register plate**. Monthly / Annual / Staff / VIP / Contractor plates **open the barrier** when the live camera (or Simulation ENTRY) reads that plate. Casual unknown plates get a receipt. In **Settings**, pick a USB A4 printer so entry prints then the gate opens. **Sessions → Show / print receipt** reprints. File-only slips live under the SmartPark media folder.

## Gate / LED / fees

**Open barrier** pulses the live camera GPIO (`Net_GateSetup` then `Net_WriteGPIOState`), sends Board* TCP on port 5000, and writes the IpAddr* LED over UDP 6666. Connect cameras first so GPIO has an SDK handle. Confirm in the UI before you press it. Registered-plate entry uses the same pulse in COMMISSIONING mode.

Fees use the Car1 tariff on local SQLite. PostgreSQL later: `SMARTPARK_DATABASE_URL=postgresql+psycopg://user:pass@host/smartpark`.
