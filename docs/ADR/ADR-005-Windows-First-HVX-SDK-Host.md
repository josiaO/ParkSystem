# ADR-005 — Windows-first HVX SDK host

## Status

Accepted.

## Decision

Keep a 32-bit Windows sidecar for `NetSDK.dll`. The 64-bit API never loads the vendor DLL in-process. Ubuntu remains a development UI/API host; SDK status is `UNAVAILABLE` there.

## Consequences

- Production packaging still ships the x86 host
- PostgreSQL, edge agents, and ONVIF can be added later without moving this boundary
