# ONVIF Media2 and Profile M (capability-driven)

Phase 2 §7. ONVIF is a *discovery and metadata* path for generic cameras. It
never replaces the HVX/QY NetSDK login (`adapter_id=hvx` stays the default)
and never guesses RTSP URLs when the device returns valid stream URIs.

## Files

| Piece | File |
| --- | --- |
| Discovery (GetServices → Media2/Media1 → GetProfiles/GetStreamUri/GetSnapshotUri → GetEventProperties) | `app/services/onvif_discover.py` |
| Profile M event parsing + pull-point client + per-camera poller | `app/services/onvif_events.py` |
| Poller supervisor (start/stop from DB every 5 s) | `app/services/onvif_runtime.py` |
| Persisting discovery on `Camera.onvif_profile` / `media_capabilities` | `app/services/onvif_profile.py` |
| Adapter (`snapshot()` from GetSnapshotUri, `health()`) | `app/infrastructure/hardware/cameras/onvif.py` |
| Routes | `POST /cameras/{id}/onvif/discover`, `PATCH /cameras/{id}/onvif/events`, `POST /cameras/{id}/onvif/events/pull` |

## Discovery order

1. `GetServices` on the device service (`/onvif/device_service`, then the
   usual alternates). Falls back to `GetCapabilities`. Result: XAddr per
   namespace — `ver20/media` (Media2), `ver10/media` (Media1), `ver10/events`,
   `ver20/analytics`.
2. If Media2 is advertised: `tr2:GetProfiles(Type=All)`, then per profile
   `tr2:GetStreamUri(RtspUnicast)` and `tr2:GetSnapshotUri`. Otherwise the
   Media1 equivalents (`trt:*`). Codec / resolution / fps / GOP / bitrate come
   from the encoder configuration; `has_metadata` marks profiles that carry a
   metadata configuration.
3. If an Events service exists: `tev:GetEventProperties` → topic set.
   Topics matching `licence/license plate | plate | lpr | anpr | vehicle`
   become `plate_topics`.

All SOAP requests carry a WS-Security `UsernameToken` with `PasswordDigest`
(plus HTTP Basic for devices that use it). Stream/snapshot URIs are used
as-is; credentials are only injected when the device omitted them, and every
API response redacts them (`uri_redacted`, `snapshot_uri_redacted`).

## Capability summary

```json
"capabilities": {
  "media2": true, "media1": true, "events": true, "analytics": true,
  "profile_m": true,          // Media2 + Events + Analytics present
  "plate_metadata": true,     // at least one plate-like topic advertised
  "plate_topics": ["RuleEngine/LicensePlateDetector/LicensePlate"]
}
```

`profile_m` **never** implies `plate_metadata`. A Profile M camera without a
plate topic keeps software recognition (FastALPR via the Recognition Worker)
and the events toggle is refused (`409`).

`Camera.media_capabilities` gains `ONVIF`, `ONVIF_MEDIA2`, `ONVIF_EVENTS`,
`ONVIF_PROFILE_M`, `ONVIF_PLATE_METADATA` as advertised. The full snapshot is
in `Camera.onvif_profile` (new JSON column; `ensure_schema` adds it to
existing SQLite files) and summarised as `camera.onvif` in the API.

## Profile M plate events → recognition contract

```mermaid
sequenceDiagram
  participant Cam as ONVIF camera
  participant Poll as ONVIFEventPoller (Site Service)
  participant Core as _persist_capture_event / hybrid_fusion
  Poll->>Cam: CreatePullPointSubscription (PT60S, topic filter when single)
  loop every PullMessages (PT5S, ≤20 msgs)
    Cam-->>Poll: NotificationMessage(LicensePlate, Confidence, Country)
    Poll->>Poll: normalise → capture{plate, confidence, source=onvif_profile_m, image_id}
    Poll->>Cam: GET snapshot URI (evidence, best effort)
    Poll->>Core: same path as an HVX native read
  end
  Poll->>Cam: Renew every 40 s; Unsubscribe on stop
```

- Normalisation (`onvif_events.parse_notification_messages`) reads
  `SimpleItem` names `LicensePlate | PlateNumber | Plate | NumberPlate | LPR |
  ANPR | VehiclePlate` for the text, `Confidence | Likelihood | Score |
  Probability` (0–1 or 0–100) and `Country | Region` as a hint. Everything
  else (motion, digital input) is ignored.
- The capture dict is exactly what `camera_lpr.native_from_sdk_capture`
  accepts, so Profile M reads reuse plate normalisation, site plate policy,
  dedup (`camera_events.seen` on a stable per-read `image_id`), session /
  gate decisions, and HYBRID fusion when a Recognition Worker also serves the
  camera. No second pipeline.
- Bounded: one in-flight pull per camera, latest read per plate text within a
  pull, no queue. Failures back off with `ReconnectPolicy` (2→30 s + jitter);
  the poller never raises into the Site Service loop and unsubscribes on cancel.
- Supervisor (`onvif_runtime.reconcile`) runs every 5 s: a poller exists only
  for `enabled` cameras with `adapter_id=onvif`, `events_enabled`, an events
  URL and `plate_metadata`. HVX cameras never get a poller.

Default: `events_enabled` is **on** when the device advertises plate topics
and can be switched off with `PATCH /cameras/{id}/onvif/events {"enabled": false}`;
the operator's choice survives re-discovery.

## Hardware Lab diagnostics

- `POST /cameras/{id}/onvif/discover` — full discovery; response and stored
  profile are credential-free.
- `POST /cameras/{id}/onvif/events/pull` — one subscribe → pull (3 s) →
  unsubscribe round trip; returns raw normalised events plus the capture each
  would produce. Use this to confirm a vendor's topic/item names before
  trusting `plate_metadata`.
- `/health/details` → `domains.recognition.onvif_events` (pollers, pulls,
  messages, plates, errors, last error per camera); `camera.onvif.poller`.

## Fallbacks and rollback

- Media2 absent → Media1. Events absent → no poller, software ALPR only.
  ONVIF unreachable → vendor RTSP candidates → manual RTSP entry
  (`stream_discover.discover_camera_streams`, unchanged order).
- Disable per camera with the events toggle, or set `adapter_id` back to
  `rtsp`. Removing the `onvif_profile` column is not required for rollback;
  older builds ignore it.

## Hardware-verification-required

Everything above was exercised against a fake SOAP device
(`tests/test_onvif_media2.py`). Still to be proven on real cameras: vendor
topic names and `SimpleItem` labels for plates (Hikvision, Dahua, Axis),
WS-Security clock-skew tolerance, Media2 `GetSnapshotUri` auth mode (Basic vs
Digest), pull-point renew behaviour across firmware, and the H.265 main
stream in browsers (see `MEDIAMTX-INTEGRATION.md` codec notes).
