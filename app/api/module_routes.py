"""Route-level module entitlement, independent from existing RBAC dependencies."""
from __future__ import annotations

from fastapi import Depends, HTTPException
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from app.db import get_db


def modules_for_route(path: str) -> tuple[str, ...]:
    parts = path.strip("/").split("/")
    root = parts[0]
    if root == "p":
        if parts[-1] == "kiosk-pay":
            return ("payments.kiosk",)
        return ("payments.public_web",)
    if root in {"sessions", "sim"}:
        if parts[-1] == "pay":
            return ("parking.sessions", "payments.core", "payments.kiosk")
        return ("parking.sessions",)
    if path == "/reports/payments.csv":
        return ("reports", "payments.core")
    if root == "cameras":
        if "barrier" in parts or "led" in parts:
            return ("camera.management", "access.gates")
        if "alpr" in parts or "plates" in parts or "plate-corrections" in parts or "presence" in parts:
            return ("camera.management", "recognition.alpr")
        if "live" in parts or "live.mjpeg" in parts or "snapshot.jpg" in parts:
            return ("camera.management", "media.streaming")
        return ("camera.management",)
    ownership = {"payments": "payments.core", "gates": "access.gates",
                 "fees": "parking.tariffs", "tariffs": "parking.tariffs",
                 "vehicles": "parking.subscribers", "access-plans": "parking.subscribers",
                 "alpr": "recognition.alpr", "recognition": "recognition.alpr",
                 "captures": "recognition.alpr", "reports": "reports",
                 "media": "media.streaming", "printers": "parking.sessions"}
    if path == "/settings/parking":
        return ("parking.sessions",)
    module = ownership.get(root)
    return (module,) if module else ()


def module_dependency(modules: tuple[str, ...]):
    def check(db: Session = Depends(get_db)):
        from app.services.modules import is_enabled

        for module in modules:
            if not is_enabled(module, db):
                raise HTTPException(status_code=404, detail=f"Module not enabled: {module}")
    return check


class ModuleRoute(APIRoute):
    def __init__(self, path: str, endpoint, **kwargs):
        modules = modules_for_route(path)
        if modules:
            kwargs["dependencies"] = [Depends(module_dependency(modules)), *(kwargs.get("dependencies") or [])]
        super().__init__(path, endpoint, **kwargs)
