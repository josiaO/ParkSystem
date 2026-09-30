# Navigation matrix

Sidebar groups are fixed. Items appear only when the module navigation payload includes them and the user has the permission.

| Group | Nav id | Page | Default label |
| --- | --- | --- | --- |
| Overview | dashboard | dashboard | Dashboard |
| Overview | cameras | cameras | Live Gates (API may say Live Cameras) |
| Operations | plates | detections | Detections (API label Plate Engine is renamed in the client) |
| Operations | sessions | sessions | Parking Sessions |
| Operations | alerts | alerts | Alerts |
| Operations | incidents | incidents | Incidents |
| Operations | payments | payments | Payments |
| Operations | vehicles | vehicles | Vehicles |
| Operations | watchlists | watchlists | Watchlists |
| Management | fees | fees | Tariffs & Schedules |
| Management | reports | reports | Reports |
| Management | onboarding | onboarding | Setup Wizard |
| System | gates | gates | Gates |
| System | users | users | Users & Roles |
| System | health | health | System Health |
| System | settings | settings | Settings |
| System | hardware | hardware | Hardware Lab |
| System | sim | sim | Testing & Simulation |

Groups with no visible buttons are hidden. The sidebar collapses to icons.

Disabled modules are omitted by the API. The UI does not render an empty page for them.
