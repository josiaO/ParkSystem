"""AI review providers. ``provider_for`` is the only selection seam."""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.domain.ai_review import (
    AIReviewProvider,
    IncidentSummary,
    IncidentSummaryRequest,
    VehicleReview,
    VehicleReviewRequest,
)


class NullAIReviewProvider:
    """Used when AI is disabled or the provider id is unknown. Never calls out."""

    provider_id = "none"

    def __init__(self, reason: str = "disabled"):
        self.reason = reason

    async def review_vehicle_event(self, request: VehicleReviewRequest) -> VehicleReview:
        return VehicleReview(readable=False, plate_candidate="", provider=self.provider_id, reason=request.reason,
                             error=self.reason, verdict="unavailable")

    async def summarize_incident(self, request: IncidentSummaryRequest) -> IncidentSummary:
        return IncidentSummary(text="", provider=self.provider_id, error=self.reason)

    def health(self) -> dict[str, Any]:
        return {"provider_id": self.provider_id, "available": False, "reason": self.reason}


def provider_ids() -> tuple[str, ...]:
    return ("gemini",)


def provider_for(provider_id: str | None = None) -> AIReviewProvider:
    pid = str(provider_id or settings.ai_provider or "").strip().lower()
    if pid == "gemini":
        from app.infrastructure.ai.gemini import GeminiAIReviewProvider

        return GeminiAIReviewProvider()
    return NullAIReviewProvider(reason=f"unknown provider {pid!r}" if pid else "no provider configured")
