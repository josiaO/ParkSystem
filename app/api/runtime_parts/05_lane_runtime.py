def _side_payload(camera: Camera | None, last: dict | None) -> dict | None:
    if camera is None:
        return None
    snap = (last or {}).get("snapshot_url")
    return {
        "camera": camera_dict(camera),
        "snapshot_url": snap,
        "last": last,
    }


async def _lane_view_dict(db: Session, gate: Gate, latest_by_camera: dict[int, VehicleCapture] | None = None) -> dict:
    by_side: dict[str, Camera] = {}
    extras: list[Camera] = []
    for camera in gate.cameras or []:
        side = (camera.lane_direction or "").upper()
        if side in {"ENTRY", "EXIT"} and side not in by_side:
            by_side[side] = camera
        else:
            extras.append(camera)

    def last_for(camera: Camera | None) -> dict | None:
        if camera is None:
            return None
        latest = (latest_by_camera or {}).get(int(camera.id)) if latest_by_camera is not None else latest_for_camera(db, camera.id)
        return capture_dict(latest) if latest else None

    entry_last = last_for(by_side.get("ENTRY"))
    exit_last = last_for(by_side.get("EXIT"))
    sides = []
    if "ENTRY" in by_side:
        sides.append({"side": "ENTRY", **_side_payload(by_side["ENTRY"], entry_last)})
    if "EXIT" in by_side:
        sides.append({"side": "EXIT", **_side_payload(by_side["EXIT"], exit_last)})
    for camera in extras:
        last = last_for(camera)
        sides.append({"side": (camera.lane_direction or "OTHER").upper(), **_side_payload(camera, last)})
    recent = [capture_dict(row) for row in list_captures(db, gate_id=gate.id, limit=16)]
    return {
        "gate": gate_dict(gate),
        "sides": sides,
        "entry": _side_payload(by_side.get("ENTRY"), entry_last),
        "exit": _side_payload(by_side.get("EXIT"), exit_last),
        "recent": recent,
    }
