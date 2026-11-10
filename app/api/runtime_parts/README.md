# Site Service runtime parts

These files are loaded in lexical order by `app/api/runtime.py` into one
runtime namespace. The shared namespace is deliberate: it preserves the
existing `app.api_main` compatibility surface while keeping each subsystem
small enough to navigate and review.

| File | Responsibility |
| --- | --- |
| `01_bootstrap.py` | imports, startup/lifespan, health, auth, nodes, modules, topology |
| `02_camera_registry.py` | camera CRUD, site imports, camera serialization |
| `02_camera_connections.py` | discovery, SDK/RTSP/ONVIF connection and stream setup |
| `02_camera_recognition.py` | native/local recognition helpers and capture payloads |
| `02_camera_routes.py` | camera management route handlers |
| `03_recognition.py` | ALPR, recognition engine, AI review, model/correction endpoints |
| `04_media.py` | live media, snapshots, previews, camera presence |
| `05_scope.py` | recognition ownership and gate scope endpoints |
| `05_recognition_ingest.py` | capture persistence and recognition event ingestion |
| `05_background_tasks.py` | recognition/background loops and watchdog tasks |
| `05_lane_runtime.py` | lane-side payload and gate progression helpers |
| `06_parking.py` | lanes, gates, tariffs, sessions, settings, simulation, developer tools |
| `07_payments.py` | payment compatibility endpoints, public receipt/payment flows, QR exit |
| `08_admin.py` | reports, backups, dashboard, printers, subscribers, users, route composition |

Do not import a part directly. Use `app.api_main` for the stable application
surface or `app.api.runtime` when working on the composed runtime.
