SmartPark Edge — Windows installer
==================================

This package has one installer. Copy the complete folder to the Windows PC
and double-click Install-SmartPark.bat. The installer asks which role this
computer will use:

  SITE_SERVER       central API, database, web UI, and local gate runtime
  EDGE_NODE         local cameras, gates, and recognition paired to a Site Server
  OPERATOR_CLIENT   operator UI only; no local cameras, gates, or services

You do not install three different products. The role is selected inside the
single installer and can be changed later by running the same installer again.
Keep the payload and support folders beside the installer. Do not run a
PowerShell file from inside those folders as the normal installation path.

For an upgrade, keep the existing database and configuration. Do not run
support\Wipe-SmartPark.bat unless a deliberate site reset is intended.
Wiping deletes cameras, gate assignments, parking records, media, and logs.

After installation, use the Zirp desktop shortcut. The installer creates the
required background tasks for a Site Server or Edge Node. An Operator Client
receives only the desktop/browser client and connects to its Site Server.

If the window never opens, run Start-SmartPark.bat from the installed folder
and check %ProgramData%\SmartParkEdge\logs\launch.log.

The installer copies the app, configures the bundled Python/Qt/SDK runtime,
and installs packages offline from the USB payload. No Python installation or
internet connection is required on the parking PC.

Support and diagnostics are in the support folder. They are not alternate
installers. Use them only after the main installation:

  Run-StartupCheck.bat          verify startup, video, recognition, and gates
  Run-FieldAcceptanceTest.bat   test live vehicle flow
  Run-CameraLab.bat             check camera picture freshness
  Open-SmartParkLogs.bat        open service logs
  Wipe-SmartPark.bat            deliberate factory reset

Sign in with the administrator credentials created during Deployment
Configuration. On a first install, the bootstrap password is in
%ProgramData%\SmartParkEdge\bootstrap_password.txt.

Cameras: Add site cameras, then Connect all.
Camera login: admin / admin, SDK port 30000.
Onboard wizard: Live Gates -> IPs -> Onboard wizard.

MediaMTX is bundled for generic RTSP cameras. SDK cameras retain their direct
SDK path. Use the detailed camera and migration procedures in
documentation\index.html for commissioning and rollback.

Each numbered lane (1# / 2#) is entry plus exit. Each side is camera plus
controller (Board*) plus display (IpAddr*). Only camera IPs are SDK-connected.

FastALPR and its local ONNX models are bundled. Recognition does not need
internet access on the parking PC.

Requires 64-bit Windows 10 or 11. The kit also includes the 32-bit camera SDK
helper because NetSDK requires a 32-bit Python host; this is automatic.

On a Site Server, the installer registers Site Service, HVX host, Media
Service, and Recognition Worker as logon tasks. On an Edge Node, those local
gate services run against the paired Site Server. On an Operator Client, no
local parking services are started.

The installer preserves existing administrator accounts and passwords during
upgrades. Use support\Wipe-SmartPark.bat only when the site data is backed up
and a full reset is intentional.
