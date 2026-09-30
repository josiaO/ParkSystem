"""Gemini Developer API provider (``generateContent`` with JSON-schema output).

Sends only the plate crop (and, when explicitly enabled, a downscaled vehicle
image). One request per review, short timeout, shared circuit breaker, no
retries: the caller already treats "unavailable" as "continue without AI".
The model id is configuration because availability changes.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any

from app.config import settings
from app.domain.ai_review import (
    IncidentSummary,
    IncidentSummaryRequest,
    VehicleReview,
    VehicleReviewRequest,
    judge,
)

PLATE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "readable": {"type": "BOOLEAN"},
        "plate_candidate": {"type": "STRING"},
        "vehicle_type": {"type": "STRING"},
        "vehicle_color": {"type": "STRING"},
        "notes": {"type": "STRING"},
    },
    "required": ["readable", "plate_candidate"],
}

_PLATE_PROMPT = (
    "You are reviewing a cropped vehicle licence plate image from a parking camera. "
    "Read the plate characters exactly as printed, left to right, letters and digits only, no spaces. "
    "If the characters cannot be read with certainty set readable=false and plate_candidate=\"\". "
    "Do not guess a country format. Do not report a confidence number. "
    "Existing machine reads for context (may be wrong): {candidates}. "
    "{vehicle_hint}Return only the JSON object."
)
_VEHICLE_HINT = "A second image shows the vehicle; describe vehicle_type (car, suv, pickup, van, truck, bus, motorcycle, other) and vehicle_color in one word each. "
_INCIDENT_PROMPT = (
    "Summarise the following parking/security events for an operator in at most five short sentences. "
    "State facts only; do not recommend opening a gate or changing payments. "
    "Question from the operator (may be empty): {question}\n\nEvents (JSON):\n{events}"
)


class GeminiError(RuntimeError):
    def __init__(self, message: str, *, code: str = "error", retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class GeminiAIReviewProvider:
    provider_id = "gemini"

    def __init__(self, http=None):
        from app.services.circuit import breaker

        self._http = http
        self.breaker = breaker("ai-gemini")
        self.model = str(settings.ai_model or "gemini-2.5-flash-lite").strip()
        self.base_url = str(settings.gemini_base_url or "").rstrip("/")
        self.timeout = float(settings.ai_timeout_seconds or 4.0)

    # -- configuration -----------------------------------------------------------
    @property
    def api_key(self) -> str:
        return str(settings.gemini_api_key or "").strip()

    def configured(self) -> bool:
        return bool(self.api_key) and bool(self.model) and bool(self.base_url)

    def health(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "model": self.model,
            "configured": self.configured(),
            "available": self.configured() and self.breaker.allow(),
            "reason": "" if self.configured() else "gemini_api_key not set",
            "breaker": self.breaker.snapshot(),
            "data_treatment_accepted": bool(settings.ai_data_treatment_accepted),
        }

    # -- transport -----------------------------------------------------------------
    async def _post(self, path: str, body: dict) -> tuple[int, Any]:
        if self._http is not None:
            return await self._http(path, body)
        import httpx

        url = f"{self.base_url}/{path}"
        headers = {"x-goog-api-key": self.api_key, "content-type": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.post(url, headers=headers, json=body)
        try:
            data = res.json()
        except Exception:
            data = {"raw": res.text[:400]}
        return res.status_code, data

    async def _generate(self, parts: list[dict], *, schema: dict | None) -> tuple[Any, float]:
        if not self.configured():
            raise GeminiError("gemini not configured", code="unconfigured")
        if not self.breaker.allow():
            raise GeminiError("gemini circuit open", code="circuit_open", retryable=True)
        generation: dict[str, Any] = {"temperature": 0, "maxOutputTokens": 256}
        if schema is not None:
            generation["responseMimeType"] = "application/json"
            generation["responseSchema"] = schema
        body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": generation}
        started = time.perf_counter()
        try:
            status, data = await self._post(f"models/{self.model}:generateContent", body)
        except Exception as exc:
            self.breaker.failure()
            raise GeminiError(f"gemini unreachable: {type(exc).__name__}", code="unreachable", retryable=True) from exc
        latency = (time.perf_counter() - started) * 1000
        if status == 429:
            self.breaker.failure()
            raise GeminiError("gemini quota exceeded", code="quota", retryable=True)
        if status >= 500:
            self.breaker.failure()
            raise GeminiError(f"gemini server error {status}", code="server", retryable=True)
        if status >= 400:
            self.breaker.success()  # our fault, not the service's; do not trip the breaker
            message = str(((data or {}).get("error") or {}).get("message") or f"http {status}")
            raise GeminiError(f"gemini rejected request: {message[:160]}", code="rejected")
        self.breaker.success()
        text = _first_text(data)
        if text is None:
            raise GeminiError("gemini returned no text part", code="empty")
        return text, latency

    # -- provider API --------------------------------------------------------------
    async def review_vehicle_event(self, request: VehicleReviewRequest) -> VehicleReview:
        candidates = request.candidates()
        review = VehicleReview(readable=False, plate_candidate="", provider=self.provider_id, model=self.model,
                               reason=request.reason, at=time.time())
        if not request.crop_jpeg and not request.vehicle_jpeg:
            review.error = "no image"
            return judge(review, candidates)
        want_vehicle = bool(request.want_vehicle_attributes and request.vehicle_jpeg)
        prompt = _PLATE_PROMPT.format(
            candidates=", ".join(candidates) or "none",
            vehicle_hint=_VEHICLE_HINT if want_vehicle else "",
        )
        parts: list[dict] = [{"text": prompt}]
        if request.crop_jpeg:
            parts.append(_image_part(request.crop_jpeg))
        if want_vehicle:
            parts.append(_image_part(request.vehicle_jpeg))
        try:
            text, latency = await self._generate(parts, schema=PLATE_SCHEMA)
            payload = _parse_json(text)
        except GeminiError as exc:
            review.error = str(exc)
            return judge(review, candidates)
        except ValueError as exc:
            review.error = f"gemini returned invalid JSON: {exc}"
            return judge(review, candidates)
        review.latency_ms = round(latency, 1)
        review.readable = bool(payload.get("readable"))
        review.plate_candidate = str(payload.get("plate_candidate") or "")
        review.vehicle_type = str(payload.get("vehicle_type") or "")[:40]
        review.vehicle_color = str(payload.get("vehicle_color") or "")[:40]
        review.notes = str(payload.get("notes") or "")[:300]
        return judge(review, candidates)

    async def summarize_incident(self, request: IncidentSummaryRequest) -> IncidentSummary:
        summary = IncidentSummary(text="", provider=self.provider_id, model=self.model)
        events = json.dumps(request.events[:50], default=str)[:6000]
        prompt = _INCIDENT_PROMPT.format(question=(request.question or "")[:300], events=events)
        try:
            text, latency = await self._generate([{"text": prompt}], schema=None)
        except GeminiError as exc:
            summary.error = str(exc)
            return summary
        summary.text = str(text).strip()[:2000]
        summary.latency_ms = round(latency, 1)
        return summary


def _image_part(jpeg: bytes) -> dict:
    return {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(jpeg).decode("ascii")}}


def _first_text(data: Any) -> str | None:
    try:
        for cand in data.get("candidates") or []:
            for part in ((cand.get("content") or {}).get("parts") or []):
                if isinstance(part.get("text"), str):
                    return part["text"]
    except AttributeError:
        return None
    return None


def _parse_json(text: str) -> dict:
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("not an object")
    return data
