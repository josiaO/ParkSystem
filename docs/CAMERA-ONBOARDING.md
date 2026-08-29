# Camera onboarding

## Flow

1. **Connection** — IP/hostname, credentials, optional port.
2. **Discover** — HVX port 30000, then ONVIF, RTSP probe, HTTP snapshot, manual URI.
3. **Profiles** — codec / resolution / FPS when known.
4. **Roles** — MAIN, LIVE, DETECT, EVIDENCE (see [STREAM-PROFILES.md](STREAM-PROFILES.md)).
5. **Recognition** — NATIVE_ONLY, FASTALPR_ONLY, HYBRID.
6. **Test** — short connect + snapshot (`POST /cameras/onboard/test`). 60s soak is a site step.
7. **Save** — last-known-working row on `cameras`.

## UI

Web: Live Gates → IPs → **Onboard wizard**. Desktop: same button.

## API

- `POST /cameras/onboard/probe`
- `POST /cameras/onboard/test`

HVX remains recommended when TCP/30000 is open. ONVIF/RTSP never replace a working NetSDK login.
