# Gate control

Investigation date: 14 October 2026. Static Windows-binary analysis on Linux; no live camera, DLL execution, gate operation, or physical latency measurement. Addresses are preferred virtual addresses (ASLR may relocate them). QY means `VideoDrivers/IPC_QY/IPC_QY.dll`, not the different QY1 copy.

Static QY call references show Net_GateSetup at 0x10005ed4, 0x10005f15 and 0x10005f56. Ghidra of QY1 `FUN_10005f20` at 0x10005f20 maps the adapter command before `Net_GateSetup`: 100 becomes gate state 1, 101 becomes state 2, and 102 becomes one plus the following byte. The header enum is unknown=0, open=1, close=2, stop=3. Command 201 is a whitelist update, not a gate command.

Every located Park.exe `DV_Exec` site, fourteen of them, the first at 0x4b1bda, writes command 102 and a following value 1000, and only calls when the device handle at object+0x3d24 is non-zero. With a zero following byte, the QY1 mapping turns 102 into state 1 (open). `Net_GateSetup` (OcxConfig NetSDK 0x10029370) rejects a null control block, checks that the control connection is up, and submits one command on that connection (`DCCGateSetup` at 0x10008d60). The return code is not a barrier-sensor reading. A repeated command can pulse the relay again.

Net_TransRS485HexDataEx is called at 0x1000635e, indicating a serial-output path. Presence of a successful SDK return does not establish barrier movement, sensor state, interlock satisfaction or transaction commitment.

SmartPark already has gate adapters and audited parking decisions. This investigation made no gate or printer changes. Retain existing hardware mappings and use simulated actuators for event tests. Before any physical acceptance test, explicitly arrange a supervised test lane. Retry only with verified semantics: repeated relay pulses are not inherently idempotent. End-to-end Park.exe database-to-gate sequencing, acknowledgment interpretation and safety interlocks remain unresolved.
