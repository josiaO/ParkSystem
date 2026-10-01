# Module UX matrix

`deploymentKind()` reads `modules.profile` from `/auth/me`, then falls back to enabled module ids.

| Profile | Dashboard cards from current `/dashboard` | Navigation the operator should see |
| --- | --- | --- |
| LPR_ONLY | Cameras online, cameras configured, registered vehicles | Dashboard, Live Cameras, Detections, Reports, Devices, Settings. No sessions, tariffs, payments, or gates. |
| SECURITY | Cameras online, cameras configured, active notices | Dashboard, Live Cameras, Detections, Watchlists, Alerts, Incidents, Reports. No payment screens. |
| ACCESS_CONTROL | Registered vehicles, cameras online, devices configured | Dashboard, Live, Vehicles, Gates, Reports, Devices. |
| PARKING_LITE / PARKING_PRO / ENTERPRISE | Vehicles inside, entries, exits, revenue, unpaid sessions, subscribers inside | Parking sessions, payments, tariffs, vehicles, gates. |

The API still decides the real sidebar. If a module is off, its button is absent.

LPR and security dashboards do not invent “unique plates today” or “watchlist matches”. Those fields are listed in `UI-BACKEND-CONTRACT-GAPS.md`.
