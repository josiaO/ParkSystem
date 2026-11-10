# SmartPark application boundaries

The repository uses four layers:

```text
HTTP/API routers        app/api/
        |
Application workflows   app/application/
        |
Domain policy           app/domain/ and app/core/
        |
Infrastructure          app/infrastructure/ and app/services/
```

`app/api_main.py` is only the compatibility entry point (`uvicorn
app.api_main:app`). The implementation is composed by
`app/api/runtime.py` from the bounded files in `app/api/runtime_parts/`.
The compatibility module aliases the runtime module so the desktop client and
older tests can keep importing and patching legacy symbols. The current
boundaries are:

| Subsystem | HTTP boundary | Workflow/domain code | Provider/hardware code |
| --- | --- | --- | --- |
| Recognition | `app/api/recognition.py` | `app/application/live_parking.py`, `app/domain/recognition*.py` | `app/infrastructure/recognition/`, `app/services/alpr/` |
| Payments | `app/api/payments.py` | `app/services/public_pay.py`, `app/services/mobile_payments.py` | `app/infrastructure/payments/` |
| Parking/lane control | `app/api/runtime_parts/06_parking.py` | `app/application/entry_lane.py`, `exit_lane.py`, `parking.py` | `app/services/gates.py` |
| Camera/media | `app/api/runtime_parts/02_camera_*.py`, `04_media.py` | camera services and capture persistence | `app/infrastructure/hardware/cameras/`, `infrastructure/media/` |

The other large boundaries follow the same compatibility-facade pattern:

- `app/services/media_gateway/` separates stream state, frame consumers, and
  upstream producers behind `app.services.media_gateway.gateway`.
- `app/services/captures/` separates validation, media files, persistence, and
  query projections.
- `app/services/simulation/` separates parking settings, sessions, entry, and
  exit/payment workflows.
- `app/models/` groups SQLAlchemy models by identity, topology, parking,
  billing, and capture/access context while preserving `app.models` imports.
- `app/desktop/main/` groups desktop pages and the window shell; `main.py`
  remains the stable import path.
- `app/desktop/setup_parts/` groups deployment wizard initialization, pages,
  validation, and navigation; `setup.py` remains the stable import path.
- `tools/hvx_sdk_host/hvx_sdk_parts/` separates vendor types/protocol,
  connection, capture, video, and GPIO concerns; `hvx_sdk.py` remains the
  source-visible compatibility shim used by packaging checks.
- `app/web/assets/` contains the browser styles and ordered core/live/API/page/
  boot scripts; `index.html` is now markup only and the API serves assets from
  the constrained assets directory.

## Boundary rules

1. A router owns HTTP paths, authentication dependencies, request/response
   translation, and public exposure. It must not contain provider SDK logic.
2. Recognition may publish a normalized event or capture candidate. It must
   not settle a payment or open a barrier directly.
3. Payments may create and reconcile ledger entries. Provider callbacks must
   be verified server-side and never open a barrier.
4. Gate decisions belong to the parking/lane application workflows and consume
   persisted recognition and payment state.
5. Provider-specific code stays behind the corresponding infrastructure
   package. Routes should call a service/facade, not a vendor adapter.

## Compatibility migration

The runtime split keeps one shared execution namespace intentionally. Several
legacy handlers call helpers from neighboring sections, and production tests
patch those helpers through `app.api_main`. Loading the bounded files into the
runtime namespace preserves that behavior while removing the 6.8k-line file.
Future domain extraction can move individual workflows into
`app/application/<subsystem>/` without changing the public ASGI target.
