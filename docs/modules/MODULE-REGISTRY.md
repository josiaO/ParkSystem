# Module Registry

Definitions: `app/domain/modules.py`  
Runtime: `app/services/modules.py`  
Persistence: `site_settings` key `modules`

## Module IDs

| ID | Name |
|----|------|
| `core.identity` | Identity & RBAC |
| `core.sites` | Sites & Configuration |
| `core.devices` | Device Registry |
| `core.audit` | Audit |
| `media.streaming` | Media Streaming |
| `camera.management` | Camera Management |
| `recognition.alpr` | Plate Recognition |
| `security.watchlists` | Watchlists |
| `security.alerts` | Alerts & Incidents |
| `access.gates` | Gate Access |
| `parking.sessions` | Parking Sessions |
| `parking.tariffs` | Tariffs |
| `parking.subscribers` | Subscribers & Vehicles |
| `payments.core` | Payments |
| `payments.kiosk` | Kiosk Payments |
| `payments.public_web` | Public Payment Web |
| `kiosk` | Kiosk |
| `reports` | Reports |
| `notifications` | Notifications |

## API

- `GET /modules` — list with enablement
- `PUT /modules/profile` — apply deployment profile
- `PUT /modules/enabled` — custom enablement
- `GET /modules/navigation` — nav for current user
- `GET /modules/health` — per-component health (disabled = neutral)
