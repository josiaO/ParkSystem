# UI acceptance checklist

Manual checks for the web UI. Automated coverage is `tests/test_ui_productization.py` and `tests/test_live_gates_ui.py` (string-level). No browser harness was added.

Sign in as an operator, then as an admin or developer (`hardware.view`).

## Navigation

- [ ] LPR profile: no Sessions, Tariffs, Payments, or Gates.
- [ ] Security profile: no payment screens. Watchlists and Alerts appear only if those modules are on.
- [ ] Access-control profile: vehicles and gates, no billing pages.
- [ ] Parking profile: sessions, payments, tariffs, vehicles.
- [ ] A group with no items is not shown.
- [ ] Sidebar collapses and the current page stays marked.
- [ ] 1366×768: sidebar plus content fit without a horizontal page scroll.

## Roles

- [ ] Operator does not see Test Video, Discover Streams, Test Recognition, Disconnect camera, or stream profiles.
- [ ] Operator device table hides address, controller, display, and SDK columns.
- [ ] Admin or technician sees those controls.
- [ ] System Health is not in the operator sidebar.

## Onboarding

- [ ] Step 1 choices are business names.
- [ ] Step 2 shows “US Dollar (USD)” and “English”, not bare codes as the only label.
- [ ] Feature step does not show module ids for an operator.
- [ ] Next, Back, and Skip move steps. Activate lands on the dashboard.

## Cameras

- [ ] Add Camera asks for address, username, and password first.
- [ ] Advanced is closed by default and still saves SDK port and adapter.
- [ ] Empty device list explains how to add a camera.
- [ ] Delete camera asks for confirmation.

## Live

- [ ] A lane card shows plate, confidence, and camera / video / recognition / last detection.
- [ ] Low confidence or a held read shows Check plate.
- [ ] Operator status line does not include a stream URL.
- [ ] No-video state explains that recognition can continue.

## Other

- [ ] Detections empty state is explicit. A capture opens the detail card.
- [ ] Session amounts show the row currency, not a hard-coded TZS prefix.
- [ ] Payment states use a chip. Provider id is hidden from operators.
- [ ] Payment kiosk hides the sidebar. Escape exits.
- [ ] Disconnect camera asks for confirmation.
- [ ] Light and dark themes still use the existing teal accent.
- [ ] Disabled health is grey, not red.

Screenshots of a signed-in site were not captured in this pass because the shell requires a live site login.
