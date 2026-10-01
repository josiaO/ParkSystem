"""Pure parking tariff quote. Amounts come from configuration, not Rock City constants."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class TariffQuote:
    duration_seconds: int
    due_minor: int
    currency: str
    car_type: str
    breakdown: list[str]
    in_grace: bool


def quote_stay(
    entry_time: datetime,
    exit_time: datetime,
    rules: dict[str, Any],
) -> TariffQuote:
    """Price a stay from tariff JSON. Empty rules are rejected so values stay configured."""
    if not isinstance(rules, dict) or not rules:
        raise ValueError("Tariff rules are required configuration")
    from app.services.fee_engine import calculate_car1_fee

    result = calculate_car1_fee(entry_time, exit_time, rules)
    return TariffQuote(
        duration_seconds=int(result.duration_seconds),
        due_minor=int(result.due),
        currency=str(result.currency),
        car_type=str(result.car_type),
        breakdown=list(result.breakdown or []),
        in_grace="grace" in (result.breakdown or []),
    )
