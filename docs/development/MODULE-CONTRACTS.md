# Module Event Contracts

Defined in `app/domain/events.py`. Published via `app/services/events.py` (durable JSONL outbox).

| Event | When |
|-------|------|
| `VehicleDetected` | Vehicle present, plate optional |
| `PlateRecognized` | Normalized plate from any provider |
| `WatchlistMatched` | Security list hit |
| `ParkingSessionStarted` | Entry session opened |
| `ParkingFeeCalculated` | Tariff applied |
| `PaymentConfirmed` | Ledger transaction succeeded |
| `ExitAuthorized` | Exit allowed |
| `GateCommandRequested` | Barrier command issued |
| `GateOpened` | Barrier confirmed open |

## PlateRecognized (normalized)

```json
{
  "event_id": "uuid",
  "site_id": 1,
  "camera_id": 2,
  "lane_id": null,
  "occurred_at": "2026-08-31T12:00:00+00:00",
  "plate_text_raw": "ABC-123",
  "plate_text_normalized": "ABC123",
  "country_code": null,
  "region_code": null,
  "confidence": 0.93,
  "vehicle_detected": true,
  "recognition_provider": "FASTALPR"
}
```

Modules must not modify each other's ORM rows directly — consume events or call service facades.
