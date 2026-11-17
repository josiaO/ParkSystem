# Payment handlers live in app/api/payment_handlers.py (a normal module).
# This part re-exports them into the runtime namespace so the route table in
# app/api/payments.py and ``app.api_main.<name>`` keep resolving, and mounts
# the handlers' own router here to keep route order unchanged.
from app.api import payment_handlers as _payment_handlers
from app.api.payment_handlers import (  # noqa: F401
    list_payments,
    mobile_money_webhook,
    sim_exit_ep,
    public_receipt,
    public_receipt_status,
    public_receipt_short_link,
    public_receipt_pay,
    public_payment_intent,
    public_payment_status,
    payment_provider_webhook,
    payments_health_ep,
    payments_reconcile_ep,
    kiosk_receipt_pay,
    exit_qr_scan,
    session_by_token,
    lookup_session,
    session_near_matches,
    _staff_may_see_photos,
    _session_image,
    public_snapshot,
    public_crop,
    public_receipt_qr,
)

app.include_router(_payment_handlers.router)
