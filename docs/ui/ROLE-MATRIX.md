# Role matrix

Roles are enforced by permissions already returned from `/auth/me`. The UI does not invent a second permission model.

| Capability | Operator | Admin (`*`) | Technician (`hardware.view`) |
| --- | --- | --- | --- |
| Dashboard, Live | Yes | Yes | Yes |
| Detections | When recognition navigation is returned | Yes | Yes |
| Sessions, payments, tariffs | When those modules are enabled | Yes | If permitted |
| Users, settings | No, unless granted | Yes | Settings view if granted |
| System Health, Hardware Lab | No | Yes | Yes |
| Testing & Simulation | No | If `simulation.run` | If `simulation.run` |
| Test Video, Discover Streams, Test Recognition, Disconnect camera | Hidden | Visible | Visible |
| Stream profile, address, SDK columns | Hidden | Visible | Visible |
| Manual barrier open | If `gates.open` | Yes | If permitted |

`Disabled` health is a neutral chip (`c-mut`), not a danger state.

Destructive actions that already confirm: delete camera, delete gate, delete user, delete vehicle, barrier pulse, camera disconnect.
