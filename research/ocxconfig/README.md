# OcxConfig vendor connection investigation

Static analysis with Ghidra 12.1.4 headless. The Windows binaries were not executed, and no camera configuration was changed. Project: `project/OcxVendor`. Per-binary logs, call summaries, and decompiler output are in `evidence/`. Reproduce with `bash research/ocxconfig/run_analysis.sh`.

`NetSDK.dll` reports `SDK_3.2.3.6 build_20221129_1800` from `Net_Init` at 0x10026610. That is a newer build than the ParkWatch QY NetSDK (`SDK_3.2.2.5`). Do not treat the two DLLs as interchangeable. This SDK keeps 32 camera slots.

## Control connection

`Net_ConnCamera` at 0x10026a60 and `Net_ConnCameraEx` at 0x100272d0 both default a zero port to 30000 and a zero timeout to 3. The connect helper opens a TCP socket (`DCSocket` / `DCConnect` in CommModule.dll) and then negotiates a device port. `Net_ConnCameraEx` copies the caller-supplied account into the slot and retries once. Credential literals were redacted. `Net_QueryConnState` at 0x1002a9c0 returns 0 when the slot's connection byte is 2.

`OcxConfigClient.exe` uses short sessions, not a standing recognition connection. `FUN_00407e50` at 0x407e50 and `FUN_00407fb0` at 0x407fb0 call `Net_AddCamera`, `Net_ConnCamera(handle, 30000, 5)`, then either time setup plus `Net_FileUpdate` or `Net_BlackWhiteListSend`, then `Net_DisConnCamera` and `Net_DelCamera`.

The OCX keeps a longer session in `FUN_10013bb0` at 0x10013bb0: `Net_AddCamera`, `Net_RegReportMessEx`, `Net_ConnCameraEx` with the configured port and timeout 3, then `Net_RegImageRecvEx2` (callback 0x10010620). A second path, `FUN_10013ec0` at 0x10013ec0, uses `Net_ConnCamera2(handle, 30000, 5)` for an auxiliary camera. Teardown in `FUN_10012090` stops video before disconnecting.

## Video, discovery, and configuration

`Net_StartVideo` at 0x1002ac90 calls `Play_OpenCamera`. It does not decode plates. `Net_RegImageRecvEx` at 0x1002bad0 only stores the callback at slot+0x60. `Net_FindDevice` at 0x10025f20 loads `DevSearchHelper.dll` and calls `GetDevList`, which broadcasts and returns device records. The OCX walks those records in `FUN_100b4fb0` at 0x100b4fb0.

The OCX also calls `Net_SetHttpPushSetup`, `Net_SetPushTargetSetup`, `Net_ParkGatePulseSetup`, and many display setup exports. Those calls show that the configuration UI can send them. They do not show that ParkWatch enables them. `Net_GateSetup` at 0x10029370 checks the control connection and submits one gate command; the return is not a sensor reading. No relay was operated.
