# Screen specifications

Shared behavior: each page has a title and a one-line purpose. Primary actions sit in the page toolbar. Loading copy is inline. Errors say what failed and what to do next. Empty tables are not blank.

## Keyboard shortcuts

Same keys in the web UI and the desktop Actions menu. The key is printed on the button (and on the desktop Actions menu), so operators do not have to guess. They follow the current page and do not run while typing or while a dialog is open. F1 opens the full list.

| Key | Action |
| --- | --- |
| Ctrl+N (⌘N) | Add camera, gate, vehicle, or user |
| Ctrl+E | Edit the selected row |
| Delete | Delete the selected row |
| F5 | Refresh this page (not a full browser reload) |
| F8 | Open **only** the highlighted live camera, selected Devices row, or armed gate side (1 = entry, 2 = exit). Never both sides. |
| F9 | Close that same armed side |
| 1–9 | Arm that live camera. On Gates, 1 = entry and 2 = exit |
| F1 | Shortcut help |

Close uses the existing `/cameras/{id}/barrier/open` and `/gates/{id}/open` endpoints with `action: "close"`. GPIO remains a pulse; board TCP close is used when a controller is configured.

## Dashboard

- Purpose: site status for the signed-in deployment.
- Roles: anyone with dashboard access.
- Module: follows profile.
- Primary action: open Live.
- Loading: “Loading…”. Error: dashboard message in the summary line.
- Empty: “No lanes yet” with a prompt to add a camera.
- Responsive: stat band wraps; lane cards use a 280px minimum.

## Live Gates

- Purpose: watch lanes for a shift.
- Primary actions: layout 1 / 2 / All, refresh.
- Each card: name, online chip, video, plate, confidence, check-plate or plate-read, camera / video / recognition / last detection, snapshot, plate crop, manual open, manual close, correct plate.
- Operators do not see frame age, codec, or stream URL.
- Degraded: “No video” chip and a short recovery sentence.
- Empty camera: “Choose a camera to start live video.”

## Devices

- Same cameras page, Devices tab (`data-sub="ips"`).
- Operator columns: name, location, direction, health.
- Technician columns: id, address, controller, display, SDK, detail.
- Empty: “No cameras configured” and Add Camera.
- Add Camera: address, username, password, direction, gate, recognition in plain language. Advanced holds SDK port, adapter, RTSP, and transport.

## Detections

- Purpose: recent plate reads from `GET /captures`.
- Columns: time, plate, camera, lane, confidence, source, status.
- Empty: “No detections yet.”
- Detail: image, crop, plate, confidence, time, camera, source.
- Filter: plate text, Enter to apply.

## Setup wizard

- Purpose: first-time site setup in business language.
- Steps keep the existing 8-step API. Labels: Purpose, Site, Hardware, Recognition, Features, Users, Readiness, Activate.
- Site step collects name, timezone, currency, language, and plate-format check with full names.
- Feature list hides module ids unless the user is a technician.

## Sessions and payments

- Sessions show plate, kind, payment chip (UNPAID, PENDING, PAID, or the raw open status when nothing is owed), entry, due, paid.
- Amounts use `currency` from the row, then the site currency.
- Payment method labels: Cash, Card, Mobile Money. Provider id is technician-only.
- Kiosk: Payment kiosk hides the sidebar and the session table. Escape or Exit kiosk leaves it.

## Watchlists, alerts, incidents

- Shown only when navigation includes them.
- Empty states explain the business outcome. They do not call APIs that do not exist yet.

## System Health

- Visible with `hardware.view`.
- Disabled stays neutral. Technical detail stays inside the existing disclosure.

## Hardware Lab and Testing & Simulation

- Technician pages. Hardware Lab names connection, streaming, recognition, gate I/O, and logs. Engine terms are allowed here.
