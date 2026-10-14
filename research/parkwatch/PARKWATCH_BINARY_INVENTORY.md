# Binary inventory

Investigation date: 14 October 2026. Static Windows-binary analysis on Linux; no live camera, DLL execution, gate operation, or physical latency measurement. Addresses are preferred virtual addresses (ASLR may relocate them). QY means `VideoDrivers/IPC_QY/IPC_QY.dll`, not the different QY1 copy.

351 files with EXE/DLL/OCX suffixes were inventoried recursively, including SHA-256, size, architecture, ordinary imports, import-slot addresses, and named exports. 349 parsed as PE: 286 x86 and 63 x64; 17 have CLR headers. Two suffix-matching files did not parse: DUCP_DLL.dll is reported as data by `file`; System.ocx as text. Neither should be assumed loadable.

Park.exe is a native x86 Windows GUI executable, preferred base 0x400000. A folder containing x64 libraries does not mean its x86 process can load them. The deployment's actual module list is still needed.

Machine-readable evidence: `evidence/inventory.json`. Reproduce with `python3 research/parkwatch/analyze.py` from the repository root (Python standard library and GNU objdump). The script never executes target files. Disassembly and import references are in `evidence/*.asm` and `*.calls.json`. The parser covers ordinary imports, not delay imports or dynamically resolved dependency closure. Hashes establish artifact identity, not publisher authenticity.

Confirmed static links: Park.exe imports DVNETSDK.DLL capture/device/stream functions. QY imports NetSDK.dll and AppBase thread functions; QY exports the CAM_* adapter interface. QY1 exposes a similar interface but differs in code and callback registration. Do not interchange the copies on filenames alone.

Park.exe also dynamically loads SimpleLPRDevAgent.dll. Ghidra decompiled that loader at 0x4249f4: LoadLibraryA of `SimpleLPRDevAgent.dll`, GetProcAddress of `LPR_LoadApis`, then a direct call. This matches the earlier objdump site at 0x424a04.

Ghidra 12.1.4 headless projects are in `research/parkwatch/project` (ParkGhidra) and `research/ocxconfig/project` (OcxVendor). Summaries and decompiler output are under `evidence/ghidra/`. Reproduce with `bash research/parkwatch/run_ghidra.sh`. The saved `IPC_QY.dll.*` decompilation is the QY1 binary; a copy is `evidence/ghidra/QY1_IPC_QY.dll.summary.txt`. The QY adapter call sites remain the objdump evidence in `evidence/VideoDrivers_IPC_QY_IPC_QY.dll.calls.json`.

DVNetSDK.dll, not Park.exe, chooses the vendor DLL. `FUN_100016d0` at 0x100016d0 maps the integer: -1 `IPC_SIM.dll`, 0 or 1 `IPC_ZS.dll`, 2 `IPC_HX.dll`, 3 `IPC_QY.dll`, 6 `IPC_DH.dll`, 7 `IPC_TVT.dll`. `FUN_10001060` then LoadLibrary's that name and resolves the CAM_* table. Park.exe writes the integer at 0x4520ee from the `[Communication]` / `CameraType` setting. `ParkWatch.ini` in this tree sets `CameraType=3`, so this configuration selects `IPC_QY.dll`. That is configuration evidence, not a captured process module list.

Supporting files include CamAPI.h, LPRHelper.cpp/.h, SimpleLPRDev*.h, QY Net_Interface.h and Net_Setup.h, multiple vendor adapters, decoding libraries, SQL/configuration files and logs. Their presence alone does not establish use. The whole application and every dynamic dependency have not been decompiled.
