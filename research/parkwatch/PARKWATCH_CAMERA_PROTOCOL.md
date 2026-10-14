# Camera connection and recognition transport

Investigation date: 14 October 2026. Static Windows-binary analysis on Linux; no live camera, DLL execution, gate operation, or physical latency measurement. Addresses are preferred virtual addresses (ASLR may relocate them). QY means `VideoDrivers/IPC_QY/IPC_QY.dll`, not the different QY1 copy.

The QY adapter's connection path contains these calls, in instruction order with success/error branches:

1. Net_AddCamera at 0x10005819; rejects handle -1.
2. Net_RegReportMessEx at 0x10005845; callback 0x10006c40, user context supplied.
3. Net_ConnCamera at 0x10005889; pushes timeout 5 and the configured port as an unsigned short. This inspected path uses ConnCamera, not ConnCameraEx.
4. On connection success, Net_RegOffLineClient at 0x100058ba.
5. Net_RegImageRecvEx at 0x10005908; callback 0x10006c80.
6. Net_RegOffLineImageRecvEx at 0x10005956; callback 0x10006cc0.
7. Additional whitelist report/control callbacks at 0x100059a4 / 0x100059f2.

Net_DisConnCamera is called at 0x10005b5b. Net_Init and Net_SetSynTimePeriod occur at 0x10005608 / 0x10005647. QY1 has different call sites and does not import the offline image callback found in QY.

The supplied UTF-16 Net_Interface.h documents ConnCameraEx as establishing control signaling and image reception with SDK reconnect after first success (lines 1923–1933). It explicitly requires image callback registration for every connection (2240–2258). The decoded review copy is `evidence/Net_Interface.utf8.h`. These are documented vendor semantics, not measured reconnect performance. QY's report callback 0x10006c40 appears to log and return; no callback rearm was identified in that short function.

SmartPark already uses AddCamera → report callback → authenticated ConnCameraEx (ConnCamera fallback) → state query → offline registration → image registration. It retains ctypes callbacks and rearms after an observed disconnected-to-connected transition, with bounded retry backoff (`tools/hvx_sdk_host/hvx_sdk.py`, `_refresh_recognition`). Polling can miss a brief transition. Registering successfully is not evidence that a new vehicle result has arrived.

Ghidra on the QY1 adapter (`FUN_10005750` at 0x10005750) confirms the same shape: `Net_AddCamera` of the address at device+0x58, `Net_RegReportMessEx` with callback 0x10006bf0, `Net_ConnCamera(handle, port at +0xd8, timeout 5)`, then offline-client, `Net_RegImageRecvEx` (callback 0x10006c30), whitelist report, and control callback registration. This path calls `Net_ConnCamera`, not `Net_ConnCameraEx`.

The QY `NetSDK.dll` control connection is TCP. `Net_ConnCamera` at 0x1001b2c0 calls `DCCConn` (`FUN_10002a40` in the newer OcxConfig NetSDK, same log strings in the QY build). That helper calls `DCSocket(1)` then `DCConnect`. `DCSocket` at CommModule 0x10001730 passes address family 2 and socket type 1, which is TCP. `DCConnect` at 0x10001860 fills an AF_INET address, sets non-blocking mode, and waits with select. If the caller passes port 0, both `Net_ConnCamera` and `Net_ConnCameraEx` substitute 30000; a zero timeout becomes 3. The OcxConfig client and a short OCX helper call `Net_ConnCamera(handle, 30000, 5)` and then disconnect. `ParkWatch.ini` also has `IPPort=80`; this investigation did not prove that value is the port stored at device+0xd8.

`Net_ConnCameraEx` (OcxConfig NetSDK 0x100272d0) is the authenticated variant. It copies the caller-supplied account into the camera slot and passes it to `DCCConnEx`. The OCX persistent session at 0x10013bb0 registers the report callback, calls `Net_ConnCameraEx` with the configured port and timeout 3, then registers `Net_RegImageRecvEx2`. `Net_ConnCameraEx` tries the connect twice. The unauthenticated `Net_ConnCamera` used by the QY adapter does not have that second attempt. Account literals from the SDK and from `ParkWatch.ini` are not copied here; the checked-in account is a factory default and should be rotated.

`Net_RegImageRecvEx` only stores the callback. In the OcxConfig NetSDK the Ex callback is at slot+0x60 and the user pointer at +0x64; Ex2 uses +0x68 and +0x6c. `Net_QueryConnState` returns 0 when slot byte +1 is 2. Discovery is separate: `Net_FindDevice` at 0x10025f20 loads the sibling `DevSearchHelper.dll` and calls `GetDevList`. That helper sends a broadcast and the SDK walks records of 0x184 bytes, at most 100. No discovery packets were sent.

This configuration selects the QY adapter, as recorded in the inventory. Firmware, the live port, and whether Ex and Ex2 can both deliver one vehicle remain unverified. No discovery probes or network configuration changes were performed.
