# SmartPark streaming target architecture

This is the minimal target architecture for the current application. It keeps
the four-surface platform model from `ZIRP PLATFORM ARCHITECTURE.md` while
making camera/recognition ownership explicit.

```text
                 SITE SERVER / SITE SERVICE
       PostgreSQL • sessions • payments • RBAC • audit
                              │
                   authenticated private LAN API
                              │
              ┌───────────────┴───────────────┐
              │                               │
       EDGE NODE A                       EDGE NODE B
  one owner per camera                 one owner per camera
  QY/HVX host or RTSP                  QY/HVX host or RTSP
       │                               │
  LIVE latest frame ── display     LIVE latest frame ── display
  DETECT latest frame ─ worker     DETECT latest frame ─ worker
  native callback ───────┐        native callback ───────┐
                          └─ normalized event/outbox ─────┘
                              │
                         site decisions
                  boom • printer • QR • payment policy
                              │
                    controlled public boundary
                              │
                         DRIVER PORTAL
```

## Ownership rules

1. `LocalMediaGateway` owns one `StreamSession` per physical camera.
2. QY/HVX cameras are owned by the matched 32-bit SDK host. No speculative
   RTSP fallback is created for an explicit native adapter. This applies to
   commissioning probes, connect retries, snapshots, and Site Service
   recognition scheduling; a web/RTSP port does not override a saved `qy`
   adapter.
3. Generic RTSP/ONVIF cameras are distributed by MediaMTX when enabled. The
   recognition decoder reads only the local MediaMTX DETECT path.
4. LIVE, DETECT, and EVIDENCE are separate consumers. LIVE and DETECT use
   bounded latest-frame state; EVIDENCE stores immutable accepted-event media.
5. Recognition ownership is explicit: `NATIVE_ONLY`, `FASTALPR_ONLY`, or
   `HYBRID`. A worker heartbeat must be fresh before it claims software reads.
6. A media reconnect increments the camera generation and invalidates buffered
   frames, preview state, in-flight recognition tickets, and old display work.
7. A vehicle visit has a presence-scoped lifecycle. Plate history is never used
   as proof that a vehicle remains in the lane.
8. Parking state changes use stable event/visit IDs and database uniqueness;
   gate commands use an idempotent command UUID and never follow from OCR alone.
9. Recognition uses one effective detection zone per camera. The saved
   `FRAMING.detect_roi` wins, otherwise the site default is made explicit in
   the camera response. Detector boxes are center-checked against that zone;
   OCR is admitted only after a stable, readable-size box is inside it.
10. LIVE is display-only. Automatic recognition reads DETECT only, and LIVE,
    DETECT, and worker mailboxes are independent latest-frame buffers. A slow
    display cannot make the ALPR worker process a backlog or feed it display
    cache frames.
11. Persisted recognition snapshots are cropped to the same detection zone and
    optional detection zoom. Plate crops are then made from the accepted
    detector box, so evidence and OCR describe the same arrival point.

## Recovery boundaries

| Failure | Smallest recovery |
|---|---|
| Worker inference failure | Release that camera's recognition ticket; keep media acquisition alive |
| Worker decoder stall | Drain/close that camera's FFmpeg child and reconnect only that lane |
| RTSP path unavailable | MediaMTX/source retry with per-camera backoff |
| SDK JPEG/callback stall | Preserve native SDK session and restart the smallest host/media read boundary; do not open guessed RTSP |
| Preview consumer disconnect | Close only the display response; producer continues while another consumer owns it |
| Site Server unavailable | Retain local durable outbox; do not invent authoritative parking state at the edge |

## Rollout and rollback

Roll out one camera or gate at a time. Keep the existing direct provider and
native host bundle available. Disable `fastalpr_new_pipeline_enabled` to return
software reads to the Site Service, disable the per-camera MediaMTX flag to
return generic live delivery to the established direct path, and keep native
camera adapters on the SDK path. Preserve the database and outbox; do not wipe
or recreate them as a recovery step. See `docs/MIGRATION-AND-ROLLBACK.md`.

