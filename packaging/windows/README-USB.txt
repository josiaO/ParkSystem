SmartPark Edge — flash drive install
====================================

This kit is the SmartPark Edge Windows install.
Copy this whole folder onto a USB stick. On the parking PC:

  1. Open the USB folder
  2. Double-click  Install-SmartPark.bat
  3. Open the Desktop shortcut  SmartPark Edge

The installer copies the app, then sets user environment variables
(SMARTPARK_HOME, PATH for Python/Qt/SDK DLLs, QT_PLUGIN_PATH).
It also places a Startup shortcut so the app opens at Windows logon.
Re-run Install-SmartPark.bat if a previous install did not start.

If the window never opens, run Start-SmartPark.bat from the install
folder and check %ProgramData%\SmartParkEdge\logs\launch.log

No Python install. No copying the source tree. No internet.

Sign in:  admin / SmartPark1!
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
If reinstall fails because a file is in use, the installer now stops
the previous SmartPark process and retries.

Requires 64-bit Windows 10 or 11. The kit includes both 64-bit SmartPark and a
32-bit camera SDK helper (NetSDK needs 32-bit Python). This is normal — you do
not choose between them. Old 32-bit-only PCs are not supported.

COMMISSIONING mode pulses the live barrier (GPIO + Board* + LED). Confirm the
lane in the UI before you press Open.

The installer registers Site Service, HVX host, and Media Service as logon tasks
and starts them immediately. The Desktop is a client. Live video decodes only
while Cameras is visible; Live Gates shows car snapshots.
