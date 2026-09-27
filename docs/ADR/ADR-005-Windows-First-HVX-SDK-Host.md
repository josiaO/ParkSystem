# ADR-005 — Windows-first HVX SDK host

## Status

Accepted.

## Decision

Keep a 32-bit Windows sidecar for `NetSDK.dll`. The 64-bit API never loads the vendor DLL in-process. Linux/macOS run the Site Service, the PySide desktop, and the browser UI. SDK status is `UNAVAILABLE` there and is not treated as a hard failure for readiness. The HVX host remains Windows-only.

## Consequences

- Production packaging still ships the x86 host for HVX parking sites
- Generic IP cameras use `rtsp` / `dahua` / `hikvision` + FastALPR on any OS
- PostgreSQL, edge agents, and ONVIF can be added later without moving this boundary
- `python -m app.desktop.launch` is the desktop on Windows and Linux. `python -m app.web.launch` opens the browser. The HVX host does not start on Linux.