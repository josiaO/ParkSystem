"""HTTP boundary for vehicle recognition.

This module owns the recognition/ALPR/AI route catalog.  The handler
implementations are injected by :mod:`app.api.runtime` so existing
desktop clients and tests can continue importing the legacy symbols while
the remaining route implementations are moved out of that compatibility
module.

Keeping the route catalog here gives recognition a stable API boundary:
recognition endpoints can be tested, documented, and replaced without
editing the payment or parking route registries.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter

from .module_routes import ModuleRoute


def register(handlers: Mapping[str, Any]) -> APIRouter:
    """Register recognition routes against the supplied handler boundary.

    ``handlers`` is deliberately explicit instead of importing the runtime
    here.  That prevents a circular import and makes the extraction seam
    visible: each function below is a route dependency, not a hidden global.
    """

    router = APIRouter(route_class=ModuleRoute)
    routes = (
        ("/alpr/status", "GET", "get_alpr_status", {"include_in_schema": True}),
        (
            "/cameras/{camera_id}/commissioning/recognition",
            "GET",
            "camera_recognition_commissioning",
            {},
        ),
        (
            "/cameras/{camera_id}/commissioning/recognition/read",
            "POST",
            "camera_recognition_commissioning_read",
            {},
        ),
        ("/recognition/engine", "GET", "get_plate_engine", {}),
        ("/recognition/corrections", "POST", "post_plate_correction", {}),
        ("/recognition/model-pack", "POST", "post_model_pack", {}),
        ("/alpr/fuse", "POST", "fuse_plates", {}),
        ("/alpr/recognize", "POST", "alpr_recognize_upload", {}),
        ("/cameras/{camera_id}/alpr/recognize", "POST", "camera_alpr", {}),
        ("/ai/health", "GET", "ai_health", {}),
        ("/ai/reviews", "GET", "ai_recent_reviews", {}),
        ("/ai/review/{capture_id}", "POST", "ai_review_capture", {}),
        ("/ai/incidents/summary", "POST", "ai_incident_summary", {}),
    )
    for path, method, name, options in routes:
        router.add_api_route(path, handlers[name], methods=[method], **options)
    return router
