# ParkWatch notes

ParkWatch is the vendor parking program Zirp replaced on our first site. We
studied its binaries to learn how the QY cameras, the loop boards and the
barriers are driven. These notes are reference material for camera and gate
work; Zirp doesn't load or call anything from ParkWatch.

Ghidra 12.1.4 headless output is in `evidence/ghidra/` and `project/`. Control connections are TCP. Display video is a separate RTSP session. Host OCR reads image files under a mutex. See the protocol, video, OCR, and gate notes for addresses.

- [binary inventory](PARKWATCH_BINARY_INVENTORY.md)
- [camera protocol](PARKWATCH_CAMERA_PROTOCOL.md)
- [video pipeline](PARKWATCH_VIDEO_PIPELINE.md)
- [ocr architecture](PARKWATCH_OCR_ARCHITECTURE.md)
- [event processing](PARKWATCH_EVENT_PROCESSING.md)
- [gate control](PARKWATCH_GATE_CONTROL.md)
- [discovered capabilities](PARKWATCH_DISCOVERED_CAPABILITIES.md)

The `evidence/` folder has the binary inventory with hashes, disassembly with
addresses, and callback documentation decoded from UTF-16. This was static
analysis only: no devices were touched while studying ParkWatch.
