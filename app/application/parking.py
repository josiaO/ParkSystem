"""Parking use-cases. Delegates to the working simulation/session services."""

from app.services.simulation import (  # noqa: F401
    handle_exit,
    handle_plate_event,
    mark_paid,
    parking_settings,
    session_dict,
    take_receipt,
)
