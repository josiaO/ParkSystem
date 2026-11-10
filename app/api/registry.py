"""Compose the HTTP subsystem routers without owning application logic."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI

from . import payments, recognition


def register_subsystem_routers(app: FastAPI, handlers: Mapping[str, Any]) -> None:
    """Attach extracted subsystem route catalogs to the ASGI application."""

    app.include_router(recognition.register(handlers))
    app.include_router(payments.register(handlers))
