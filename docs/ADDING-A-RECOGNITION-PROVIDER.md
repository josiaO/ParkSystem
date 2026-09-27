# Adding a recognition provider

The plate reader is a `PlateEngine` in `app/infrastructure/recognition/engines/`. FastALPR is the engine that ships (`id=fastalpr`). To change libraries, implement `describe` and `recognize_bytes`, call `register_engine`, and set `SMARTPARK_ALPR_ENGINE`. To retrain FastALPR, apply a model pack. Full steps: [PLATE-ENGINE.md](PLATE-ENGINE.md).

`RecognitionProvider.process` still wraps an engine result into a normalized vehicle event. Register that wrapper in `app/infrastructure/recognition/PROVIDERS` only if parking must see a new event source.

Normalized fields: `event_id`, `camera_id`, `plate_text`, `normalized_plate`, `confidence`, `source`, timestamps in UTC.

Parking consumes only that event (via fusion → `handle_plate_event`). Do not change GPIO when adding OCR.

Existing providers: `hvx_native`, `fastalpr`. Existing engine: `fastalpr`.
