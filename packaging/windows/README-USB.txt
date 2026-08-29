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
MediaMTX is optional and off by default. Native HVX plates and boom control stay on.
Vehicles: Register plate so that plate opens the gate
Snapshot: Cameras -> Capture snapshot
Receipts: Settings → pick the USB A4 printer. A detected car prints, then the
gate opens. Simulation uses the same printer. If no printer is selected, the
slip is stored as an A4 PNG + text file.

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

The 32-bit camera SDK host is included. COMMISSIONING pulses the live barrier
(GPIO + Board* + LED). Confirm the lane in the UI before you press Open.

The installer registers Site Service and HVX host as logon tasks and starts them
immediately. The Desktop is a client. Live video decodes only while Cameras is
visible; Live Gates shows car snapshots.

