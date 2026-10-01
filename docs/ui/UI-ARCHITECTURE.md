# UI architecture

The canonical product interface is the web app in `app/web/index.html`. The Windows desktop client is a local shell with the same operator language: Devices instead of IPs, Detections instead of Plate Engine, and technician controls hidden unless the account can view hardware. Live video reconnect logic is unchanged.

## Layers

| Layer | Who | Examples |
| --- | --- | --- |
| Operator workspace | Day-to-day staff | Dashboard, Live, Detections, Sessions, Payments |
| Management | Supervisors | Vehicles, Tariffs & Schedules, Reports |
| System | Admins and technicians | Devices, Users & Roles, System Health, Settings |
| Technician | `hardware.view` | Hardware Lab, Testing & Simulation, stream profiles, SDK disconnect |

Navigation items come from `GET /auth/me` → `navigation`. The client only shows a sidebar button when that id is present (or, if navigation is missing, when the matching permission exists). Empty groups are hidden.

Technician-only controls use the class `tech-only`. The body gets `role-tech` when the signed-in user has `hardware.view`. Operators do not see RTSP, ONVIF, MediaMTX, FastALPR, SDK, or GOP controls.

## What this pass changed

- Grouped sidebar with a stable current page and collapse.
- Deployment-aware dashboard cards from the existing `/dashboard` payload.
- Live lane cards with plate, confidence, and business status.
- Camera add/edit keeps vendor fields under Advanced.
- Setup wizard uses currency, language, and plate-format names.
- Devices tab (same `ips` subview) uses health language for operators.
- Detections page reads `GET /captures`.
- Payment kiosk is a full-screen mode on the existing session lookup.
- Money formatting uses the session or site currency. It does not assume TZS.

## What stayed

Colors, type, HVX as the default camera path, and all API contracts. Backend, media, recognition, and payment code were not changed.
