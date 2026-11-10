"""HTTP boundary for payments and public receipt pages.

Payment provider orchestration remains in ``services/mobile_payments.py`` and
the provider adapters remain in ``infrastructure/payments``.  This module is
only the transport boundary: it defines which payment routes are exposed and
keeps that surface separate from camera, recognition, and gate routes.

Handlers are injected by :mod:`app.api.runtime` during the compatibility phase.
That lets the route registrations move first without changing the callable
symbols used by the desktop client and the existing test suite.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter

from .module_routes import ModuleRoute


def register(handlers: Mapping[str, Any]) -> APIRouter:
    """Register the operator, public, kiosk, and provider callback routes."""

    router = APIRouter(route_class=ModuleRoute)
    routes = (
        ("/payments", "GET", "list_payments", {}),
        ("/payments/mobile-money/webhook", "POST", "mobile_money_webhook", {}),
        ("/payments/health", "GET", "payments_health_ep", {}),
        ("/payments/reconcile", "POST", "payments_reconcile_ep", {}),
        ("/p/{token}", "GET", "public_receipt", {"include_in_schema": False}),
        ("/p/{token}/status", "GET", "public_receipt_status", {}),
        ("/s/{token}", "GET", "public_receipt_short_link", {"include_in_schema": False}),
        ("/p/{token}/pay", "POST", "public_receipt_pay", {}),
        ("/p/{token}/kiosk-pay", "POST", "kiosk_receipt_pay", {}),
        ("/p/{token}/snapshot.jpg", "GET", "public_snapshot", {"include_in_schema": False}),
        ("/p/{token}/crop.jpg", "GET", "public_crop", {"include_in_schema": False}),
        ("/p/{token}/qr.png", "GET", "public_receipt_qr", {"include_in_schema": False}),
        ("/api/public/payment-intents", "POST", "public_payment_intent", {}),
        ("/api/public/payment-status/{token}", "GET", "public_payment_status", {}),
        ("/api/webhooks/{provider_id}", "POST", "payment_provider_webhook", {}),
    )
    for path, method, name, options in routes:
        router.add_api_route(path, handlers[name], methods=[method], **options)
    return router
