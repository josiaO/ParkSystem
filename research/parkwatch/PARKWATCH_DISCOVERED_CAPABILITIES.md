# Additional capabilities and confidence

Investigation date: 14 October 2026. Static Windows-binary analysis on Linux; no live camera, DLL execution, gate operation, or physical latency measurement. Addresses are preferred virtual addresses (ASLR may relocate them). QY means `VideoDrivers/IPC_QY/IPC_QY.dll`, not the different QY1 copy.

Confirmed static adapter calls (not live acceptance): QY time synchronization via Net_SetSynTimePeriod at 0x10005647; whitelist deletion/setup/send at 0x1000454c/0x10004809/0x10004852; offline client/image registration at 0x100058ba/0x10005956; snapshots at 0x10005cc8; serial writes at 0x1000635e; SDK video at 0x10005bd9.

Documented metadata: plate confidence, box, vehicle attributes, timestamp, vehicle ID and capture index in Net_Interface.h; capture source and generic plate fields in CamAPI.h. Ex2 adds processing time and further attributes. Firmware support and population of these fields are not established.

Ghidra moved several of those items. Confirmed in this tree: `CameraType=3` selects `IPC_QY.dll`; control traffic is TCP through CommModule; display video is RTSP through PlaySdk, RtspRecvSdk and DecodeSdk, with a 0xFA000 decode buffer and a 10 by 0xC8000 receive ring; host OCR is a separate file API. The OCX, not the QY adapter, calls `Net_SetHttpPushSetup` and `Net_SetPushTargetSetup`. QY NetSDK identifies itself as `SDK_3.2.2.5 build-1710231600`; the OcxConfig NetSDK is the later `SDK_3.2.3.6 build_20221129_1800` and is not a drop-in substitute.

Still not validated on a live lane: which stream URL is selected, exposure and night settings, whether old decode frames are discarded, firmware fields, and whether Park.exe actually calls the host OCR loader during a visit. None is declared unsupported solely because it was not observed.

Highest-value next capabilities are per-camera separate connection/video/recognition health, immutable capture evidence, source timestamp preservation and explicit offline replay handling. Avoid adding push transports or remote configuration writes until an observed requirement justifies them.
