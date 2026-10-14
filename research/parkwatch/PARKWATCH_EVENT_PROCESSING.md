# Event processing and capture identity

Investigation date: 14 October 2026. Static Windows-binary analysis on Linux; no live camera, DLL execution, gate operation, or physical latency measurement. Addresses are preferred virtual addresses (ASLR may relocate them). QY means `VideoDrivers/IPC_QY/IPC_QY.dll`, not the different QY1 copy.

CamAPI.h provides recognition source, capture timestamp, plate confidence and nRecInterval (documented same-plate minimum interval in seconds). This does not establish Park.exe's database transaction or deduplication behavior. QY online and offline callbacks both forward to 0x10006d40, passing different online/offline flags. Offline replay therefore deserves explicit handling, not automatic treatment as a current arrival.

Confirmed SmartPark defect under synthetic input: `_on_image` stores media by `(handle, image_id)` while retaining multiple event rows. The vendor callback documentation says image_id=0 can identify realtime results, rather than a unique capture. Two such callbacks overwrite the same media entry. `event_jpeg_for` and `event_crop_for` also return the latest media when an explicitly requested event cannot be found. This can associate another capture's image with a result.

Reproduction: `.venv/bin/python research/parkwatch/reproduce_media_collision.py`. Result: `evidence/media-collision.txt`. It invokes the real Python callback/storage functions with synthetic metadata and bytes; no vendor DLL or device is used. The HTTP host exposes these lookups at hvx_host.py:139–150; the client passes image IDs at hvx_client.py:153–162. Physical frequency and downstream consequences are not yet measured.

Also, `_on_image` assigns captured_at_epoch from host time and does not preserve acSnapTime, uiVehicleId or ucSnapshotIndex in its output row. This loses evidence useful for replay detection and timing. Bounded deque(maxlen=64) drops oldest events silently when full; this bounds memory but is not a durable capture guarantee.

Proposed event envelope: camera identity + connection generation + host capture sequence; preserve original vendor ID, vehicle ID, camera timestamp and host receive monotonic time separately. Store immutable metadata/media together. Missing event evidence must be explicit. Keep frame dropping separate from transaction-event retention.

SmartPark already has visit-scoped session lookup, durable claims and unique constraints in parking_sessions.py and migration 0007_visit_idempotency.py. Preserve these. Test repeated stationary detections, zero/reused vendor IDs, reconnect, offline replay, concurrent arrivals and a later legitimate visit by the same plate. Plate text alone is not an event identity.
