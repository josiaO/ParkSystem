# Windows services and power-cut recovery

After a power cut the gate PCs must bring parking back **with nobody signed in**.
Windows scheduled tasks with an "at logon" trigger cannot do that, so SmartPark
runs as real Windows services.

## What is installed

The installer registers these services through the bundled NSSM
(`vendor\nssm\nssm.exe`, public domain) when it runs as administrator:

| Service | Process | Starts after |
|---|---|---|
| `SmartParkSiteService` | `python64 -m app.site_service` (API, parking decisions) | local PostgreSQL service, if any |
| `SmartParkMediaService` | `python64 -m app.media_service` (owns MediaMTX) | Site Service |
| `SmartParkRecognitionWorker` | `python64 -m app.recognition_worker` (FastALPR) | Media Service (or Site Service) |
| `SmartParkHvxHost` | `python32 tools\hvx_sdk_host\hvx_host.py` | — (only after the Session 0 test passes, see below) |

Every service:

* starts at boot as LocalSystem, with nobody signed in;
* is restarted by NSSM whenever its process exits; a process that dies within
  15 s is restarted after a growing delay, so a crash loop does not spin the CPU;
* has SCM recovery actions as a second line (restart after 5 s, 15 s, then every
  60 s) in case NSSM itself stops;
* logs to `%ProgramData%\SmartParkEdge\logs\services\<Service>.log`, rotated at 10 MB.

Interactive users may start and stop these services (the desktop's repair
action uses this); only administrators can change or delete them.

If the installer is **not** elevated, it falls back to the old logon tasks and
prints a warning. Fix it by running `Start-SmartPark-Admin.ps1` as administrator.

Useful commands (elevated PowerShell):

```powershell
Get-Service SmartPark*                  # state of every service
Restart-Service SmartParkSiteService    # restart one service
.\Install-SmartParkWinService.ps1       # re-register all services
```

## The HVX SDK host and Session 0

Windows services run in *Session 0*, which has no interactive desktop. The
32-bit HVX host uses a hidden, message-pumped window for the vendor
NetSDK/PlaySdk callbacks. Whether the vendor SDK works there has **not been
proven**, so by default the HVX host stays a scheduled task that starts when the
site account signs in. Everything else runs as a service.

### Test it on the site PC (once per SDK/firmware version)

1. Install the kit and connect at least one HVX/QY camera.
2. Open PowerShell **as administrator** in the install folder.
3. Run:

   ```powershell
   .\Test-HvxHostAsService.ps1 -CameraIp 192.168.1.144 -WaitForPlate
   ```

   Enter the camera password when asked, and drive a car past the camera when
   the script says so. The script never moves a barrier.
4. Read the verdict, and the report in
   `%ProgramData%\SmartParkEdge\logs\hvx-service-test-*.txt`.

**PASS** (SDK loaded, camera connected, live frames, native plate read):

```powershell
.\Install-SmartParkWinService.ps1 -HvxHostAsService
```

Then run the reboot test below. **FAIL**: keep the logon task and use the
auto-logon arrangement.

### Fallback: automatic sign-in for the HVX host

If the HVX host cannot run in Session 0, the PC must sign in by itself after a
reboot so the logon task starts the host:

1. Create a local standard (non-administrator) account used only for SmartPark,
   for example `smartpark-gate`, with a long password.
2. Install SmartPark while signed in as that account (the HVX logon task is
   registered for the account that installs it), or re-run
   `.\Install-SmartParkWinService.ps1` from that account's elevated prompt.
3. Enable automatic sign-in with Microsoft Sysinternals **Autologon**
   (`Autologon64.exe`). It stores the password as an LSA secret, not in plain
   text in the registry. Do not use the `DefaultPassword` registry value.
4. Lock the desktop after sign-in: set a screen-saver lock of 1 minute, and keep
   the PC in a locked room. The Site Service, Media Service and Recognition
   Worker do not depend on this sign-in; only HVX cameras do.

Record the account name, not the password, in the site handover notes.

## Reboot (power-cut) test

`tools\Test-RebootRecovery.ps1` checks that everything comes back without a
sign-in:

```powershell
.\tools\Test-RebootRecovery.ps1 -Arm -TimeoutMinutes 5    # schedules the check, then restarts the PC
# ... do NOT sign in. Wait 10 minutes, then sign in and run:
.\tools\Test-RebootRecovery.ps1 -Report
```

The check runs at boot as SYSTEM and records PASS/FAIL for: every SmartPark
service running, `/health/live` and `/health/ready` green, database reachable,
and (if the HVX host is a service) `http://127.0.0.1:8765/info` answering.

## Pipeline watchdog

"Process alive" is not enough. The Site Service runs a watchdog every 30 s
that checks that each enabled camera produced a fresh frame, that the database
answers, and that the HVX host (gate controller for HVX barriers) responds. On a
failure it restarts only the affected part (that camera's decoder or SDK
session) and writes a `watchdog.*` audit event. Thresholds and state are in
**System Health** and `/health/details` → `watchdog`.
