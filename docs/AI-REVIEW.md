# Optional AI review (Gemini)

## Purpose

A cloud model can give a *second opinion* on a hard plate crop, describe a
vehicle, or summarise an incident in plain language. It is an enhancement:
disabled by default, never a dependency of live view, recognition, sessions,
payments or gate control, and never allowed to overwrite a verified read.

## What it must NOT do

- open a gate, or feed a value into the gate/access decision
- mark a payment successful or change a tariff
- overwrite `VehicleCapture.plate` automatically
- run per frame, or block the capture/gate path while it waits
- send real customer imagery on the free tier without explicit acceptance

## Contract (`app/domain/ai_review.py`)

```python
class AIReviewProvider(Protocol):
    async def review_vehicle_event(self, request: VehicleReviewRequest) -> VehicleReview
    async def summarize_incident(self, request: IncidentSummaryRequest) -> IncidentSummary
    def health(self) -> dict
```

`VehicleReview` carries `readable`, `plate_candidate`, `vehicle_type`,
`vehicle_color`, `notes`, `latency_ms` and — computed locally by `judge()`, not
by the model — a `verdict`:

| Verdict | Meaning | Effect |
| --- | --- | --- |
| `supporting` | AI read equals an existing native/FastALPR candidate | shown as supporting evidence |
| `conflicting` | AI read differs | capture stays in operator review / temporal consensus |
| `unreadable` | model could not read the crop | nothing changes |
| `unavailable` | disabled, budget, privacy, timeout, breaker, error | normal flow continues |

No confidence number is requested from the model and none is invented.

## Provider: `GeminiAIReviewProvider` (`app/infrastructure/ai/gemini.py`)

`POST {gemini_base_url}/models/{ai_model}:generateContent` with header
`x-goog-api-key`, temperature 0, `responseMimeType=application/json` and a
strict `responseSchema` (`readable`, `plate_candidate`, `vehicle_type`,
`vehicle_color`, `notes`). Parts sent: the prompt, the plate crop JPEG, and —
only when `ai_send_vehicle_image=true` — a vehicle image downscaled to
`ai_vehicle_image_max_px`. One attempt, no retries. HTTP 429/5xx/timeouts trip
the shared `ai-gemini` circuit breaker; 4xx (our request) do not.

Registry: `app/infrastructure/ai.provider_for()`; unknown ids resolve to a
`NullAIReviewProvider` that never calls out.

## Service limits (`app/services/ai_review.py`)

| Limit | Setting | Default |
| --- | --- | --- |
| master switch | `SMARTPARK_AI_ENABLED` (plus `recognition.alpr` module on) | `false` |
| provider / model | `SMARTPARK_AI_PROVIDER`, `SMARTPARK_AI_MODEL` | `gemini`, `gemini-2.5-flash-lite` |
| key | `SMARTPARK_GEMINI_API_KEY` | empty → unavailable |
| timeout | `SMARTPARK_AI_TIMEOUT_SECONDS` | 4 s |
| concurrency | `SMARTPARK_AI_MAX_CONCURRENCY` | 2 |
| daily cap | `SMARTPARK_AI_DAILY_REQUEST_CAP` | 200 |
| per-camera interval | `SMARTPARK_AI_MIN_INTERVAL_SECONDS` | 2 s |
| trigger | `SMARTPARK_AI_LOW_CONFIDENCE_BELOW` | 0.75 |
| vehicle image | `SMARTPARK_AI_SEND_VEHICLE_IMAGE` | `false` |
| privacy | `SMARTPARK_AI_DATA_TREATMENT_ACCEPTED` | `false` |

Triggers (`review_reason`): native/FastALPR disagreement (`needs_review` with
different `native_plate`/`local_plate`), any held capture, or a plate read below
the confidence threshold. Reviews are scheduled from `_persist_capture_event`
**after** the capture row exists, as an `asyncio` task; the gate/session logic
in the same function does not await them. Results land on
`vehicle_captures.ai_review` (Alembic `0003`) and appear in `capture_dict` as
`ai_review`.

Privacy: Google states free-tier content may be used to improve its products.
Captures whose `source` is simulation/synthetic/test are always allowed; real
captures are skipped (`skipped_privacy`) until the deployment sets
`ai_data_treatment_accepted=true` (paid/privacy-configured project or accepted
data treatment).

## API

| Route | Permission | Notes |
| --- | --- | --- |
| `GET /ai/health` | `hardware.view` | enabled flag, provider health, budget, limits, `gate_authority=false` |
| `GET /ai/reviews` | `cameras.view` | last 20 verdicts + counters |
| `POST /ai/review/{capture_id}` | `cameras.connect` | operator second opinion; 409 when disabled, audit `ai.review` |
| `POST /ai/incidents/summary` | `cameras.view` | `{capture_ids|plate, limit, question}` → prose summary from ledger facts |

All `/ai/*` routes belong to the `recognition.alpr` module and disappear (404)
when it is off. `GET /health/details` → `domains.recognition.ai_review`.

## Rollback

`SMARTPARK_AI_ENABLED=false` (default). Nothing else changes: the
`ai_review` column stays and is simply empty for new captures.

## Verification status

Provider behaviour was implemented from the Gemini API reference and exercised
against faked HTTP in `tests/test_ai_review.py`. No request was made to the real
Gemini API in this environment; model availability and quota must be confirmed
by the deployment with its own key.
