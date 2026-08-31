"""Payment provider seam. Ledger records are the authority, not the HTTP response."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.infrastructure.payments.ledger import (  # noqa: F401
    apply_session_payment_state,
    list_transactions,
    paid_total,
    record_succeeded_payment,
    transaction_dict,
)


@runtime_checkable
class PaymentProvider(Protocol):
    id: str

    async def create_intent(self, request: dict[str, Any]) -> dict[str, Any]: ...

    async def initiate_collection(self, intent: dict[str, Any]) -> dict[str, Any]: ...

    async def verify_callback(self, request: dict[str, Any]) -> dict[str, Any]: ...

    async def query_status(self, provider_ref: str) -> dict[str, Any]: ...


class SimulatedPaymentProvider:
    id = "simulated"

    async def create_intent(self, request: dict[str, Any]) -> dict[str, Any]:
        return {"status": "CREATED", "provider_id": self.id, **request}

    async def initiate_collection(self, intent: dict[str, Any]) -> dict[str, Any]:
        return {"status": "PENDING", "provider_id": self.id, **intent}

    async def verify_callback(self, request: dict[str, Any]) -> dict[str, Any]:
        return {"status": "SUCCEEDED", "provider_id": self.id, "verified": True, **request}

    async def query_status(self, provider_ref: str) -> dict[str, Any]:
        return {"status": "PENDING", "provider_id": self.id, "provider_ref": provider_ref}


class ManualKioskPaymentProvider:
    id = "kiosk_manual"

    async def create_intent(self, request: dict[str, Any]) -> dict[str, Any]:
        return {"status": "PENDING", "provider_id": self.id, "method": "KIOSK_CASH", **request}

    async def initiate_collection(self, intent: dict[str, Any]) -> dict[str, Any]:
        return {"status": "PENDING", "provider_id": self.id, "method": "KIOSK_CASH", **intent}

    async def verify_callback(self, request: dict[str, Any]) -> dict[str, Any]:
        return {"status": "SUCCEEDED", "provider_id": self.id, "verified": True, **request}

    async def query_status(self, provider_ref: str) -> dict[str, Any]:
        return {"status": "SUCCEEDED", "provider_id": self.id, "provider_ref": provider_ref}


PROVIDERS: dict[str, PaymentProvider] = {
    "simulated": SimulatedPaymentProvider(),
    "kiosk_manual": ManualKioskPaymentProvider(),
}


def payment_provider_for(provider_id: str) -> PaymentProvider:
    return PROVIDERS.get(provider_id) or PROVIDERS["kiosk_manual"]


def list_payment_providers() -> list[str]:
    return sorted(PROVIDERS.keys())
