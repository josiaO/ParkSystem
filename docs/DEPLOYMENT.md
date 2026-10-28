# Zirp Production Deployment

This is the technician runbook for a real site. Obtain Zirp through the approved software-distribution process. The portable/USB package is a maintainer testing artifact and is not the production installation contract.

## Install Site Server

1. Install Zirp from the approved Windows installer package.
2. Select **Site Server** in Deployment Configuration.
3. Review the server requirements and LAN address.
4. Install the approved PostgreSQL prerequisite, create the dedicated Zirp database/login, select PostgreSQL for production, or acknowledge SQLite for testing/evaluation. Follow [POSTGRESQL-PREREQUISITE.md](POSTGRESQL-PREREQUISITE.md).
5. Test the database. Apply initializes or migrates the schema.
6. Create the first administrator.
7. Sign in and configure the site, gates and cameras using the existing Zirp hardware screens.
8. Test camera connectivity, live video, recognition, printer and gate hardware. A gate test never raises a barrier automatically.
9. Configure and test the site backup procedure.
10. Apply the configuration and verify `/health/ready`, `/health/database` and the startup check.

The server binds the API to `0.0.0.0:8760` after configuration so a separate workstation can reach it. Use a stable server address or DHCP reservation. Do not edit Python, `.env` or SQL for a normal installation.

## Download the installer from the Site Server

After the Site Server is installed, a node or another PC can open `http://SERVER_IP:8760/`
on the private LAN and select **Download the Zirp installer for a node or another PC** on
the login page. Extract `Zirp-Installer.zip`, then run `Install-SmartPark.bat`.
The downloaded archive is assembled from the installed runtime and excludes the
database, media, logs, credentials and deployment identity. It is equivalent to
the approved installation package; it does not copy the server's site data to
the new PC.

Keep this download endpoint on the private site LAN. It is intended for
provisioning another Zirp computer, not for publishing the installer to the
public Internet.

PostgreSQL is an external managed prerequisite in this release. Zirp does not bundle PostgreSQL binaries, install the PostgreSQL service, or create the database role automatically. The technician should use the official [PostgreSQL Windows installer](https://www.postgresql.org/download/windows/) or the site’s approved offline installer, then use Zirp’s **Test Database** check.

The default offline kit registers restartable Windows scheduled tasks at user logon for Site Service, recognition, MediaMTX and the optional HVX host. This is the currently supported startup path because vendor SDK behavior under a non-interactive Windows service still needs validation on the target gate PC. `Install-SmartParkWinService.ps1` is available only for a site that has completed that hardware validation.

On first boot or after an upgrade, Site Service may take up to two minutes while it migrates the database and warms the bundled FastALPR models. Do not start a second copy during this window. If it still does not become ready, inspect `C:\ProgramData\SmartParkEdge\logs\site-service.log`, `site-service-launch.log` and `launch.log` before retrying.

HVX/NetSDK is conditional hardware. If the 32-bit HVX host does not answer on `127.0.0.1:8765` during installation, the installer records a warning and continues for RTSP, ONVIF, Dahua and Hikvision sites. Repair the vendor runtime before commissioning HVX/QY cameras; this warning must not be confused with a Site Service or FastALPR failure.

## Recognition preflight and troubleshooting

The Site Service performs an offline FastALPR preflight before it starts camera recognition. The detector and OCR models are copied to the shared SmartPark data directory (`C:\ProgramData\SmartParkEdge\model-cache` on the default Windows installation), so the scheduled Site Service task and the technician desktop do not depend on a particular user's profile cache or an Internet connection.

Use these checks in order when live video works but the pane shows `detector-unavailable`:

1. Open the technician hardware/recognition status and confirm FastALPR is installed, the detector and OCR model files are ready, and the engine is loaded.
2. Check `C:\ProgramData\SmartParkEdge\logs\site-service.log` for `FastALPR preflight ready` or `FastALPR preflight failed`.
3. Check the camera's recognition mode. `NATIVE_ONLY` requires a valid native camera plate event; choose the FastALPR/software mode when the camera supplies video/JPEG but not plate text.
4. Confirm the camera is assigned to this Site Server's recognition gate and that the camera is in scope.
5. Restart the Site Service after correcting the package, model files, or recognition mode. Do not install model files into `Program Files` manually.

The live pane now displays the underlying import, DLL, ONNX, or missing-model error. Record that message together with `site-service.log`, `recognition-worker.log`, and the redacted `/health/details` or `/alpr/status` response when escalating. A live picture proves only that the camera/stream path works; it does not prove that the detector or OCR runtime is ready.

If the log contains `onnxruntime_pybind11_state` with `MSVCP140.dll` or `MSVCP140_1.dll` missing, reinstall the current approved Zirp package. Those 64-bit Microsoft C++ runtime DLLs are part of the package and are checked by the installer; do not download random DLLs or copy them into `System32`.

## Install Operator Workstation

1. Install the approved SmartPark package on the workstation.
2. Select **Operator Workstation**.
3. Enter the Site Server address, for example `http://smartpark-server:8760`.
4. Test the connection and confirm **Server identity VERIFIED**.
5. Finish setup and sign in with a site user.

The workstation does not run PostgreSQL, Alembic, Site Service, MediaMTX, FastALPR, HVX/NetSDK, camera connections or gate hardware. It must not create a local `smartpark.db`.

## Network and firewall

| Port | Purpose | Reachable from operator PCs? |
|---|---|---|
| TCP 8760 | SmartPark API | Yes, private LAN only |
| TCP 8889 | MediaMTX WebRTC signaling | Yes, when WebRTC is enabled |
| UDP/TCP 8189 | WebRTC ICE media | Yes, when WebRTC is enabled |
| TCP 5432 | PostgreSQL | No; normally localhost only |
| TCP 8554 | Internal RTSP | No; localhost only |
| TCP 9997/9998 | MediaMTX control/metrics | No; localhost only |
| TCP 8765 | HVX SDK host | No; Site Server only |

The Windows service setup creates Private-network/LocalSubnet inbound rules for the API and bundled WebRTC ports. It does not open public-network rules or PostgreSQL.

## Acceptance checks

Use two PCs: PC A is the Site Server and PC B is the Operator Workstation. From B verify login, sessions, camera views and recognition data. Confirm B has no local database and no server worker processes. Disconnect B: parking and recognition on A must continue. Close B: A must continue. Reboot A and verify the configured background startup path.

Do not report two-PC, real-camera or real-gate acceptance as passed until it has actually been performed on the target hardware. Use the separate maintainer test package only when a release or field test requires its bundled runtimes and diagnostic scripts.

## Recovery

Keep the previous `deployment.json` and database backup before changing an existing site. If Apply fails, leave the site in recovery/unconfigured state, restore the previous deployment file and database only after verifying the backup, then restart the Site Server. Never wipe or recreate an existing production database as a troubleshooting step.
