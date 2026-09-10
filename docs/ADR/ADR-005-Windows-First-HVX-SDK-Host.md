# ADR-005 — Windows-first HVX SDK host

## Status

Accepted.

## Decision

Keep a 32-bit Windows sidecar for `NetSDK.dll`. The 64-bit API never loads the vendor DLL in-process. Linux/macOS run the Site Service and **browser UI** as the multiplatform operator path; SDK status is `UNAVAILABLE` there and is not treated as a hard failure for readiness. Desktop (PySide) remains Windows-only.

## Consequences

- Production packaging still ships the x86 host for HVX parking sites
- Generic IP cameras use `rtsp` / `dahua` / `hikvision` + FastALPR on any OS
- PostgreSQL, edge agents, and ONVIF can be added later without moving this boundary
- `python -m app.web.launch` / `./scripts/run_dev_linux.sh` is the supported non-Windows entry