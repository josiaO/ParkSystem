# UI backend contract gaps

The web UI consumes current APIs. These shapes would let Codex finish the operator experience without the UI inventing data.

## Dashboard variants

- Screen: Dashboard
- Required data: counts that match the deployment, not only parking occupancy.
- Desired API: `GET /dashboard` adds optional fields and ignores them when the module is off.
- Current limitation: payload is parking-centric (`vehicles_inside`, `entries_today`, `exits_today`, `revenue_today`, `unpaid_active`, `subscribers_inside`, `cameras`, `sdk_connected`, `lanes`, `alerts` as strings).
- Suggested fields:
  - `vehicles_detected_today`
  - `unique_plates_today`
  - `recognition_health` (`healthy` | `degraded` | `offline` | `disabled`)
  - `watchlist_matches_today`
  - `active_alerts`
  - `access_events_today`, `authorized_today`, `denied_today`

## Detections

- Screen: Detections
- Required data: site-wide plate history with camera name and watchlist status.
- Desired API: `GET /detections?plate=&camera_id=&since=&confidence_min=`
- Current limitation: UI uses `GET /captures?limit=50`, which returns camera id, not camera name, and has no watchlist status or paging.
- Suggested fields: `camera_name`, `site_name`, `lane_name`, `watchlist_status`, `thumbnail_url`, `next_cursor`.

## Live lane decision

- Screen: Live card
- Required data: access or payment decision for the latest plate.
- Desired API: include `decision` on `GET /cameras/{id}/plates`.
- Current limitation: the client can show confidence and “Check plate” only.
- Suggested fields: `outcome` (`authorized` | `payment_required` | `denied` | `opening`), `amount_label`, `duration_label`, `parker_kind`.

## Camera onboarding result

- Screen: Add Camera wizard
- Required data: discovery summary after test.
- Desired API: onboard response already returns vendor detail; the dialog still shows raw JSON.
- Suggested fields for a summary card: `manufacturer`, `model`, `video_available`, `main_stream`, `sub_stream`, `builtin_lpr`.

## Watchlists, alerts, incidents

- Screens: Watchlists, Alerts, Incidents
- Required data: lists and acknowledge / open detection / create incident actions.
- Current limitation: navigation ids exist; there is no list or write API. Pages show empty states.
- Suggested: `GET/POST /watchlists`, `GET /alerts`, `POST /alerts/{id}/acknowledge`, `POST /incidents`.

## Devices inventory

- Screen: Devices
- Required data: cameras, barriers, kiosks, printers, sensors, edge agents in one list.
- Current limitation: `GET /devices` requires `hardware.view` and is a projection. Operators use `GET /cameras`.
- Suggested: `GET /devices` allowed for `cameras.view`, with `type`, `location`, `connection`, `function`, `health`, `last_seen`.

## Settings country

- Screen: Setup wizard site step
- Required data: country display name.
- Current limitation: site policy stores timezone, currency, language, and plate validation, not country. The wizard does not send a country field.

## Kiosk payment methods

- Screen: Payment kiosk
- Required data: enabled methods for this site.
- Current limitation: kiosk reuses session lookup and the existing pay actions. It does not yet branch Mobile Money vs Cash from a method catalog.
