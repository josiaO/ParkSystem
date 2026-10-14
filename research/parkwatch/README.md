# ParkWatch investigation

Read [SmartPark gap analysis](SMARTPARK_GAP_ANALYSIS.md) and [improvement plan](SMARTPARK_IMPROVEMENT_PLAN.md) first.

The principal actionable finding is a synthetically confirmed event/image association defect in SmartPark. ParkWatch supports a camera-native recognition path and contains an actual host OCR loader. This tree's `ParkWatch.ini` sets `CameraType=3`, which DVNetSDK maps to `IPC_QY.dll`. Static analysis cannot certify camera accuracy or live stream latency.

Ghidra 12.1.4 headless output is in `evidence/ghidra/` and `project/`. Control connections are TCP. Display video is a separate RTSP session. Host OCR reads image files under a mutex. See the protocol, video, OCR, and gate notes for addresses.

- [PARKWATCH BINARY INVENTORY ](PARKWATCH_BINARY_INVENTORY.md)
- [PARKWATCH CAMERA PROTOCOL ](PARKWATCH_CAMERA_PROTOCOL.md)
- [PARKWATCH VIDEO PIPELINE ](PARKWATCH_VIDEO_PIPELINE.md)
- [PARKWATCH OCR ARCHITECTURE ](PARKWATCH_OCR_ARCHITECTURE.md)
- [PARKWATCH EVENT PROCESSING ](PARKWATCH_EVENT_PROCESSING.md)
- [PARKWATCH GATE CONTROL ](PARKWATCH_GATE_CONTROL.md)
- [PARKWATCH DISCOVERED CAPABILITIES ](PARKWATCH_DISCOVERED_CAPABILITIES.md)
- [SMARTPARK GAP ANALYSIS ](SMARTPARK_GAP_ANALYSIS.md)
- [SMARTPARK IMPROVEMENT PLAN ](SMARTPARK_IMPROVEMENT_PLAN.md)

Evidence includes a recursive binary inventory with hashes, disassembly with addresses, callback documentation decoded from UTF-16, a no-hardware defect reproduction and focused test results. No production code or devices were changed. Instructions in the supplied mission document were treated as investigation context rather than independent authority to install tools, modify code or operate hardware.
