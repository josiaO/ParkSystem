SmartPark Edge — flash drive install
====================================

This kit is the SmartPark Edge Windows install.
Copy this whole folder onto a USB stick. On the parking PC:

  1. Open the USB folder
  2. If this PC already ran SmartPark, wipe data first (not only close the window):
       double-click  Wipe-SmartPark.bat
     Type YES. That deletes the database, media, logs, FastALPR cache, and the old app.
  3. Double-click  Install-SmartPark.bat
  4. Open the Desktop shortcut  SmartPark Edge

The installer copies the app, then sets user environment variables
(SMARTPARK_HOME, PATH for Python/Qt/SDK DLLs, QT_PLUGIN_PATH).
It also places a Startup shortcut so the app opens at Windows logon.
Re-run Install-SmartPark.bat if a previous install did not start.

If the window never opens, run Start-SmartPark.bat from the install
folder and check %ProgramData%\SmartParkEdge\logs\launch.log

No Python install. No copying the source tree. No internet.

Sign in:  admin
First-run password: open %ProgramData%\SmartParkEdge\bootstrap_password.txt
(The old note admin / SmartPark1! is not the password this installer creates.)
Cameras:  Add site cameras  then  Connect all
Camera login: admin / admin   SDK port 30000
Onboard wizard: Live Gates → IPs → Onboard wizard (HVX first, then ONVIF/RTSP)

MediaMTX (optional, bundled, OFF by default)
--------------------------------------------
The kit includes vendor\mediamtx\mediamtx.exe. Three background tasks start
at logon: Site Service (API), HVX Host (SDK), Media Service (MediaMTX
supervisor). MediaMTX does nothing until you enable it.

Staged rollout (one camera first — 2# Entry = camera id 3):

  1. Install + Connect all as usual (native HVX plates unchanged).
  2. Probe RTSP on camera 3: Live Gates → IPs → RTSP probe (optional).
  3. Soak test (10+ min smooth local proxy):
       powershell -ExecutionPolicy Bypass -File MediaMTX-SoakTest.ps1 -CameraId 3
     Watch rtsp://127.0.0.1:8554/cam3 in VLC/ffplay. If it stutters, fix
     camera/network — do not change SmartPark decode.
  4. Enable parallel MediaMTX:
       powershell -ExecutionPolicy Bypass -File Enable-MediaMTX.ps1 -CameraId 3
  5. After soak, switch live view for that camera only:
       powershell -ExecutionPolicy Bypass -File Enable-MediaMTX.ps1 -CameraId 3 -LiveView

Rollback: set SMARTPARK_LIVE_VIEW_PROVIDER=DIRECT_LEGACY in user env, or
PATCH /settings/migration in the API.

ffmpeg must be on PATH for RTSP soak tests and generic IP cameras.

Vehicles: Register plate so that plate opens the gate
Snapshot: Cameras -> Capture snapshot
Receipts: Settings → pick your thermal receipt printer (58 mm or 80 mm roll,
USB or network). A detected car prints the ticket, then the gate opens.
Simulation uses the same printer. If no printer is selected, the receipt is
stored as a text file (and backup image) on disk.

Each numbered lane (1# / 2#) is entry + exit.
Each side is camera + controller (Board*) + display (IpAddr*).
Only camera IPs are SDK-connected. Connect all is camera-only.

Close any other camera SDK client first so this app can log into the cameras
and receive plate events. Live video can work while plates stay empty if
another program still owns the camera callback.

FastALPR (local JPEG OCR) is bundled in this kit, including ONNX models, so it
does not need internet on the parking PC.

Camera picture test (no cars required)
---------------------------------------
After Connect all, and with SmartPark still open, open the install folder
(the same folder as Start-SmartPark.bat) and double-click Run-CameraLab.bat.
That watches every camera for 15 minutes and writes a log under
%ProgramData%\SmartParkEdge\logs\camera_lab_*.txt

One camera for 10 minutes, from that same folder:

  powershell -ExecutionPolicy Bypass -File .\Run-CameraLab.ps1 -Camera 1 -Duration 600

This only checks that the pictures stay fresh. It does not open the gate
or print a ticket. Send the log file back.

Field acceptance (run while cars pass)
--------------------------------------
After Connect all, double-click  Run-FieldAcceptanceTest.bat
or:

  powershell -ExecutionPolicy Bypass -File Run-FieldAcceptanceTest.ps1 -Minutes 8 -ExpectedCars 6

Leave it running for 8 minutes and send cars through all four lanes. It writes
PASS/FAIL to %ProgramData%\SmartParkEdge\logs\field_acceptance_*.txt

Expected PASS:
  Site Service live, DB ready, login, cameras SDK_CONNECTED
  pending queue <= 1, live not OFFLINE, FastALPR/native reads increase
  one stalled camera does not freeze the others
  empty lane does not keep a plate
  one visit does not create two ParkingSessions

If reinstall fails because a file is in use, the installer now stops
the previous SmartPark process and retries.

Wipe ALL site data before a clean install (database, media, logs, FastALPR
cache, scheduled tasks, and the installed app). Stopping the Desktop is not
enough. From this USB folder, or from the install folder after install:

  double-click  Wipe-SmartPark.bat

or:

  powershell -ExecutionPolicy Bypass -File .\Wipe-SmartPark.ps1

Type YES. Then run Install-SmartPark.bat. To keep the program files and only
delete SQLite/media/cache:

  powershell -ExecutionPolicy Bypass -File .\Wipe-SmartPark.ps1 -KeepApp -Force

Requires 64-bit Windows 10 or 11. The kit includes both 64-bit SmartPark and a
32-bit camera SDK helper (NetSDK needs 32-bit Python). This is normal — you do
not choose between them. Old 32-bit-only PCs are not supported.

COMMISSIONING mode pulses the live barrier (GPIO + Board* + LED). Confirm the
lane in the UI before you press Open.

The installer registers Site Service, HVX host, and Media Service as logon tasks
and starts them immediately. The Desktop is a client. Live video decodes only
while Cameras is visible; Live Gates shows car snapshots.
