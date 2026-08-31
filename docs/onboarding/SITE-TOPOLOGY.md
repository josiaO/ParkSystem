# Site Topology

Model: **Site → Zone → Gate → Lane → devices**

| Entity | Table | Notes |
|--------|-------|-------|
| Site | `sites` | Locale, timezone, currency |
| Zone | `zones` | Optional area grouping |
| Gate | `gates` | Barrier controller |
| Lane | `lanes` | Direction: ENTRY, EXIT, BIDIRECTIONAL |
| Camera | `cameras` | `gate_id`, optional `lane_id`, `lane_direction` |

Supports:

- Zero-gate LPR (cameras only)
- 1 entry / 1 exit
- N gates, M lanes each
- Security cameras with no gate

API: `GET /topology`, `POST /topology/zones`, `POST /topology/lanes`

Legacy two-lane sites sync lanes from camera directions on startup.
