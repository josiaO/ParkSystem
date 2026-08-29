# Start here

This folder is the product documentation for **SmartPark Edge**. Begin with [README.md](../README.md). How to change code: [CONTRIBUTING.md](../CONTRIBUTING.md).

## Engine (wrap, do not replace)

| Piece | Location |
|---|---|
| 32-bit NetSDK host | `tools/hvx_sdk_host/` |
| Host HTTP client | `app/services/hvx_client.py` |
| Media gateway | `app/services/media_gateway.py` |
| Live JPEG / MJPEG | `app/services/preview.py` |
| GPIO + Board* + LED | `app/services/gates.py` |
| Site cameras / lanes | `app/services/site_cameras.py` |
| API | `app/api_main.py` |
| SQLite | `app/db.py` |

Connect sequence: `Net_Init` → `Net_AddCamera` → `Net_RegReportMessEx` → `Net_ConnCamera` / `Net_ConnCameraEx` on port **30000** (timeout in **seconds**) → `Net_RegImageRecvEx` → `Net_StartVideo`.

## Layout

```text
app/
  domain/                  protocols
  application/             use-cases
  infrastructure/hardware  camera, gate, printer adapters
  services/                live parking + HVX client
  api_main.py
  desktop/  web/
tools/hvx_sdk_host/
docs/
```

## Documents

| File | Topic |
|---|---|
| [01-PRODUCT-VISION.md](01-PRODUCT-VISION.md) | Plate-first product |
| [02-CURRENT-SITE-TOPOLOGY.md](02-CURRENT-SITE-TOPOLOGY.md) | Lanes, IPs, Board*, LED |
| [03-SYSTEM-ARCHITECTURE.md](03-SYSTEM-ARCHITECTURE.md) | API, host, clients |
| [04-DOMAIN-MODEL.md](04-DOMAIN-MODEL.md) | Entities |
| [05-DATABASE-SCHEMA.md](05-DATABASE-SCHEMA.md) | SQLite / Postgres |
| [06-SESSION-STATE-MACHINE.md](06-SESSION-STATE-MACHINE.md) | Session statuses |
| [07-HARDWARE-ADAPTER-ARCHITECTURE.md](07-HARDWARE-ADAPTER-ARCHITECTURE.md) | Adapters |
| [08-HVX-CAMERA-INTEGRATION.md](08-HVX-CAMERA-INTEGRATION.md) | NetSDK path |
| [09-HVX-GATE-INTEGRATION.md](09-HVX-GATE-INTEGRATION.md) | GPIO / Board / LED |
| [10-ADDING-A-NEW-CAMERA-VENDOR.md](10-ADDING-A-NEW-CAMERA-VENDOR.md) | New vendor without breaking HVX |
| [14-PAYMENT-ARCHITECTURE.md](14-PAYMENT-ARCHITECTURE.md) | Ledger |
| [15-PERFORMANCE-STABILITY.md](15-PERFORMANCE-STABILITY.md) | Processes, live video |
| [16-OPENCV-AND-SOFTDOG.md](16-OPENCV-AND-SOFTDOG.md) | OpenCV use; vendor dongle |
| [MEDIA-ARCHITECTURE.md](MEDIA-ARCHITECTURE.md) | Gateway vs FastALPR vs live view |
| [CAMERA-ADAPTERS.md](CAMERA-ADAPTERS.md) | Adapter contract |
| [MEDIAMTX-INTEGRATION.md](MEDIAMTX-INTEGRATION.md) | Optional sidecar |
| [FASTALPR-PIPELINE.md](FASTALPR-PIPELINE.md) | DETECT worker |
| [NATIVE-ALPR.md](NATIVE-ALPR.md) | HVX plate callbacks |
| [CAMERA-ONBOARDING.md](CAMERA-ONBOARDING.md) | Wizard |
| [STREAM-PROFILES.md](STREAM-PROFILES.md) | MAIN/SUB/LIVE/DETECT |
| [CAMERA-CAPABILITY-MATRIX.md](CAMERA-CAPABILITY-MATRIX.md) | Evidence, not slogans |
| [ADDING-A-CAMERA-VENDOR.md](ADDING-A-CAMERA-VENDOR.md) | New adapter |
| [ADDING-A-RECOGNITION-PROVIDER.md](ADDING-A-RECOGNITION-PROVIDER.md) | New OCR |
| [GATE-ADAPTERS.md](GATE-ADAPTERS.md) | Boom wrap |
| [MIGRATION-AND-ROLLBACK.md](MIGRATION-AND-ROLLBACK.md) | Feature flags |
| [CAMERA-TROUBLESHOOTING.md](CAMERA-TROUBLESHOOTING.md) | Operator vs lab |
| [ADR/](ADR/) | Decisions |

Write the next file when that feature is actually built.
