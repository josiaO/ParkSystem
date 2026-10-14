# Recognition architecture

Investigation date: 14 October 2026. Static Windows-binary analysis on Linux; no live camera, DLL execution, gate operation, or physical latency measurement. Addresses are preferred virtual addresses (ASLR may relocate them). QY means `VideoDrivers/IPC_QY/IPC_QY.dll`, not the different QY1 copy.

Evidence supports both camera-native recognition and a host OCR integration path, but does not establish which is enabled for each deployed lane.

Camera path: QY registers Net_RegImageRecvEx at 0x10005908. Callback 0x10006c80 calls 0x10006d40. That processor reads plate text at metadata +0x8 (0x10006e1d), confidence at +0x40 (0x10006f14), box coordinates at +0x18/+0x1a/+0x1c/+0x1e (0x10006f21 onwards), and timestamp text at +0x26 (0x10006f59). These offsets match T_ImageUserInfo. It passes image information onward at 0x100070ca. This is application-adapter consumption of recognized metadata, not just SDK exports.

Host path: Ghidra decompiled Park.exe `FUN_004249f4` at 0x4249f4, which loads `SimpleLPRDevAgent.dll` and calls `LPR_LoadApis`. `LPR_Recognize` at 0x10006910 rejects a null engine, path, or result, returns 0xc when the image file does not exist, and holds one mutex around the recognize call. `LPR_RecognizeAll` at 0x10006b30 has the same file check. The DLL imports OpenCV core and image codecs. This is file-based host OCR, not a camera-frame callback. The supplied LPRHelper.cpp matches that shape. Which Park.exe branch invokes the loader for a live lane, and whether its result is fused with the camera plate, remains unverified. The helper's one-shot initialization flags are set before success, so its retry behavior is not a pattern to copy blindly.

Strategies to evaluate on the same labeled local day/night captures:

- Camera primary: lowest expected host CPU and independent of browser video; depends on camera OCR quality, firmware and callback reliability. Confidence scales require calibration.
- FastALPR primary: consistent host pipeline across vendors; needs readable frames and sufficient compute. Measure inference contention and dropped frames.
- Hybrid: native candidate plus bounded host fallback/validation; may improve coverage but needs event/image correlation and conflict handling. Never interpret two engines disagreeing as permission to open a gate.

Keep the existing FastALPR implementation while benchmarking exact-plate accuracy, missed vehicles, false accepts, CPU and p95 latency. No accuracy claim can be made from binary inspection.

SmartPark registers both Ex and Ex2 using the same callback reading T_ImageUserInfo. The header's Ex2 structure has the same initial fields and additional tail data, so this is not by itself proof of a memory-layout fault. Full Ex2 typing and double-delivery behavior need validation against the exact deployed DLL.
