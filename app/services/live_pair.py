"""Pick the two cameras shown on Live Gates for a lane."""

from __future__ import annotations


def camera_side(camera: dict | None) -> str:
    if not camera:
        return ""
    return str(camera.get("lane_direction") or camera.get("side") or "").upper()


def pair_lane_cameras(cameras, gate_id=None):
    """Return (entry, exit) for a gate, or the first two cameras when unscoped."""
    cams = list(cameras or [])
    if gate_id is not None and gate_id != "":
        cams = [c for c in cams if str(c.get("gate_id") or "") == str(gate_id)]
    entry = next((c for c in cams if "ENTRY" in camera_side(c)), None)
    exit_cam = next((c for c in cams if "EXIT" in camera_side(c)), None)
    leftover = [c for c in cams if c is not entry and c is not exit_cam]
    left = entry or (leftover.pop(0) if leftover else None)
    right = exit_cam or (leftover.pop(0) if leftover else None)
    if left is None and right is None and cams:
        left = cams[0]
        right = cams[1] if len(cams) > 1 else None
    return left, right


def lane_options(cameras):
    """Combo items: All cameras, then each gate that has cameras."""
    seen: list[tuple] = []
    keys = set()
    for camera in cameras or []:
        gate_id = camera.get("gate_id")
        if gate_id is None or gate_id in keys:
            continue
        keys.add(gate_id)
        name = camera.get("lane_name") or camera.get("gate_name") or f"Lane {gate_id}"
        seen.append((gate_id, str(name)))
    return [(None, "All cameras"), *seen]


def camera_label(camera: dict | None) -> str:
    if not camera:
        return "Choose camera…"
    bits = [
        camera.get("name") or f"Camera {camera.get('id')}",
        camera.get("lane_name") or camera.get("gate_name") or "",
        camera.get("side") or camera.get("lane_direction") or "",
        camera.get("ip_address") or "",
    ]
    return " · ".join(str(bit) for bit in bits if bit)


def camera_by_id(cameras, camera_id):
    if camera_id is None or camera_id == "":
        return None
    wanted = str(camera_id)
    return next((c for c in (cameras or []) if str(c.get("id")) == wanted), None)


def slot_cameras(cameras, left_id=None, right_id=None):
    """Independent left/right picks. Empty slots stay empty until the operator chooses."""
    left = camera_by_id(cameras, left_id)
    right = camera_by_id(cameras, right_id)
    return left, right
