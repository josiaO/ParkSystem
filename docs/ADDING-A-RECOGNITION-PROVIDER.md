# Adding a recognition provider

Implement `RecognitionProvider.process(event_or_frame) -> normalized vehicle event`.

Register in `app/infrastructure/recognition/PROVIDERS`.

Normalized fields: `event_id`, `camera_id`, `plate_text`, `normalized_plate`, `confidence`, `source`, timestamps in UTC.

Parking consumes only that event (via fusion → `handle_plate_event`). Do not change Live Gates UI or GPIO when adding OCR.

Existing providers: `hvx_native`, `fastalpr`.
