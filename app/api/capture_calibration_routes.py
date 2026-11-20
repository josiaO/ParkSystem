"""HTTP boundary for per-camera capture calibration (see app/services/capture_calibration.py)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Camera, User
from app.security import require


def _camera(db: Session, camera_id: int) -> Camera:
    camera = db.get(Camera, int(camera_id))
    if camera is None:
        raise HTTPException(404, "Camera not found")
    return camera


def _owning_edge_node(db: Session, camera: Camera) -> str:
    """Name of the Edge Node running this camera, when it is not this computer.

    The live picture, plate boxes and test-mode reads of a camera exist only in
    the process that runs it. On the Site Server a camera handed to an Edge
    Node therefore shows no picture here; the desktop says where to go instead.
    """
    try:
        from sqlalchemy import select

        from app.models import Node, NodeGateAssignment
        from app.services.node_scope import camera_owned_by_edge_node, is_processing_node

        if is_processing_node() or not camera_owned_by_edge_node(camera, db=db):
            return ""
        name = db.scalar(
            select(Node.name).join(NodeGateAssignment, NodeGateAssignment.node_id == Node.id)
            .where(NodeGateAssignment.gate_id == camera.gate_id, NodeGateAssignment.enabled == True)  # noqa: E712
            .order_by(Node.last_seen_at.desc())
        )
        return str(name or "an Edge Node")
    except Exception:
        return ""


def register() -> APIRouter:
    router = APIRouter()

    @router.get("/cameras/{camera_id}/calibration")
    def get_calibration(camera_id: int, db: Session = Depends(get_db), _: User = Depends(require("cameras.view"))):
        from app.services import capture_calibration as calibration

        camera = _camera(db, camera_id)
        return {
            "owned_by_node": _owning_edge_node(db, camera),
            "calibration": calibration.load(db, camera),
            "defaults": dict(calibration.DEFAULTS),
            "limits": {k: list(v) for k, v in calibration.LIMITS.items()},
            "test_mode": calibration.test_mode_status(db, camera.id),
            "warning": calibration.lane_warning(camera.id),
        }

    @router.put("/cameras/{camera_id}/calibration")
    def put_calibration(
        camera_id: int,
        payload: dict[str, Any] = Body(default_factory=dict),
        db: Session = Depends(get_db),
        user: User = Depends(require("cameras.manage")),
    ):
        from app.services import capture_calibration as calibration
        from app.services.audit import write_audit

        camera = _camera(db, camera_id)
        try:
            saved = calibration.save(db, camera, payload or {}, user=user.username)
        except calibration.ConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        calibration.gate_for(camera.id).reset()
        write_audit(db, user, "camera.calibration", "camera", str(camera.id),
                    f"version={saved['version']} enabled={saved['enabled']} zone_points={len(saved['zone'])} "
                    f"min_plate={saved['min_plate_width_px']}x{saved['min_plate_height_px']}")
        db.commit()
        return {"calibration": saved, "test_mode": calibration.test_mode_status(db, camera.id)}

    @router.delete("/cameras/{camera_id}/calibration")
    def delete_calibration(camera_id: int, db: Session = Depends(get_db), user: User = Depends(require("cameras.manage"))):
        """Back to uncalibrated (whole picture, no size or quality gate)."""
        from app.services import capture_calibration as calibration
        from app.services.audit import write_audit

        camera = _camera(db, camera_id)
        calibration.remove(db, camera.id)
        calibration.gate_for(camera.id).reset()
        write_audit(db, user, "camera.calibration", "camera", str(camera.id), "reset to uncalibrated")
        db.commit()
        return {"calibration": calibration.load(db, camera)}

    @router.put("/cameras/{camera_id}/calibration/test-mode")
    def put_test_mode(
        camera_id: int,
        payload: dict[str, Any] = Body(default_factory=dict),
        db: Session = Depends(get_db),
        user: User = Depends(require("cameras.manage")),
    ):
        """Calibration test: reads are shown, never stored. No session, no barrier. Expires on its own."""
        from app.services import capture_calibration as calibration
        from app.services.audit import write_audit

        camera = _camera(db, camera_id)
        enabled = bool((payload or {}).get("enabled"))
        minutes = float((payload or {}).get("minutes") or 30)
        status = calibration.set_test_mode(db, camera.id, enabled=enabled, minutes=minutes)
        calibration.gate_for(camera.id).reset()
        write_audit(db, user, "camera.calibration.test_mode", "camera", str(camera.id),
                    f"enabled={status['enabled']} until={status['until']}")
        db.commit()
        return status

    @router.get("/cameras/{camera_id}/calibration/live")
    def get_live(camera_id: int, db: Session = Depends(get_db), _: User = Depends(require("cameras.view"))):
        """Latest detector boxes, plate sizes, eligibility, chosen frame and read."""
        from app.services import capture_calibration as calibration

        camera = _camera(db, camera_id)
        state = calibration.live_state(camera.id)
        if not state:
            state = _worker_state(camera.id)
        return {
            "camera_id": camera.id,
            "test_mode": calibration.test_mode_status(db, camera.id),
            "state": state,
            "vehicle_boxes": None,
            "vehicle_boxes_note": "The installed detector finds plates, not whole vehicles; vehicle boxes are not available.",
            "has_snapshot": bool(calibration.selected_snapshot(camera.id)),
        }

    @router.get("/cameras/{camera_id}/calibration/rejected.jpg")
    def get_rejected(camera_id: int, part: str = "snapshot", db: Session = Depends(get_db),
                     _: User = Depends(require("cameras.view"))):
        """The last read this camera's calibration refused (whole picture or plate crop)."""
        from app.services import capture_calibration as calibration

        camera = _camera(db, camera_id)
        jpeg = calibration.rejected_image(camera.id, "crop" if part == "crop" else "snapshot")
        if jpeg[:2] != b"\xff\xd8":
            raise HTTPException(404, "No refused read for this camera")
        return Response(jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @router.get("/cameras/{camera_id}/calibration/snapshot.jpg")
    def get_snapshot(camera_id: int, db: Session = Depends(get_db), _: User = Depends(require("cameras.view"))):
        from app.services import capture_calibration as calibration

        camera = _camera(db, camera_id)
        jpeg = calibration.selected_snapshot(camera.id)
        if jpeg[:2] != b"\xff\xd8":
            raise HTTPException(404, "No frame has been selected for this camera yet")
        return Response(jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    return router


def _worker_state(camera_id: int) -> dict:
    """Generic (non-SDK) cameras are read in the Recognition Worker process."""
    try:
        from app.recognition_worker import worker_health

        for row in (worker_health() or {}).get("cameras") or []:
            if int(row.get("camera_id") or row.get("id") or 0) == int(camera_id):
                return dict(row.get("calibration") or {})
    except Exception:
        pass
    return {}
