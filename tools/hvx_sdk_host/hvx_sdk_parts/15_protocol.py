from __future__ import annotations

def stream_type_from_function_list(blob: bytes | bytearray | memoryview) -> int:
    """Return the PlaySdk stream type selected by OcxConfig's bit tests."""
    raw = bytes(blob or b"")
    if len(raw) <= FUNCTION_LIST_FLAGS_OFFSET or raw[0] == 0:
        return 0
    flags = struct.unpack_from("<I", raw, FUNCTION_LIST_FLAGS_OFFSET)[0]
    for stream_type, bit in STREAM_TYPE_FLAGS:
        if flags & bit:
            return stream_type
    return 0

def function_list_flags(blob: bytes | bytearray | memoryview) -> int:
    raw = bytes(blob or b"")
    if len(raw) < FUNCTION_LIST_FLAGS_OFFSET + 4 or raw[:1] == b"\x00":
        return 0
    return int(struct.unpack_from("<I", raw, FUNCTION_LIST_FLAGS_OFFSET)[0])

def describe_rc(rc: int) -> str:
    return RETURN_CODES.get(int(rc), f"unknown_{rc}")

def describe_state(state: int) -> str:
    return CONN_STATES.get(int(state), f"unknown_{state}")

def is_connected_state(state: int) -> bool:
    """Accept both public QY state encodings used by shipped NetSDK builds."""
    try:
        return int(state) in CONN_STATE_CONNECTED_VALUES
    except (TypeError, ValueError):
        return False

def plate_box_usable(box) -> bool:
    try:
        return int(box[2]) > int(box[0]) and int(box[3]) > int(box[1])
    except (TypeError, ValueError, IndexError):
        return False

def parse_image_user_info(blob: bytes) -> dict:
    """Read the callback prefix the OcxConfig NetSDK fills.

    DCCSendPictureByCallBackEx copies 0x44 bytes into the Ex/Ex2 argument.
    FUN_1000a470 writes the plate at +8 and the four usLpBox ushorts at
    +0x18, +0x1a, +0x1c and +0x1e. OcxConfig's image callback reads the same
    words. Score is the byte at +0x40.
    """
    if not blob or len(blob) < 0x20:
        return {}
    width, height = struct.unpack_from("<HH", blob, 0)
    box = [int(value) for value in struct.unpack_from("<HHHH", blob, 0x18)]
    return {
        "plate_raw": bytes(blob[8:24]),
        "plate_box": box,
        "image_width": int(width),
        "image_height": int(height),
        "score": int(blob[0x40]) if len(blob) > 0x40 else None,
        "have_vehicle": bool(blob[0x25]) if len(blob) > 0x25 else False,
        "snap_type": int(blob[0x24]) if len(blob) > 0x24 else None,
        "camera_timestamp": bytes(blob[0x26:0x38]).split(b"\x00", 1)[0].decode("ascii", "ignore"),
        "vehicle_id": int.from_bytes(blob[0x3C:0x40], "little") if len(blob) >= 0x40 else 0,
        "snapshot_index": int(blob[0x43]) if len(blob) > 0x43 else 0,
    }

def jpeg_pixel_size(blob: bytes) -> tuple[int, int]:
    if not blob or blob[:2] != b"\xff\xd8":
        return 0, 0
    index = 2
    limit = len(blob)
    while index + 8 < limit:
        if blob[index] != 0xFF:
            index += 1
            continue
        marker = blob[index + 1]
        if marker in (0xD8, 0xD9):
            index += 2
            continue
        if index + 4 > limit:
            break
        length = int.from_bytes(blob[index + 2:index + 4], "big")
        if marker in (0xC0, 0xC1, 0xC2, 0xC3) and index + 8 < limit:
            height = int.from_bytes(blob[index + 5:index + 7], "big")
            width = int.from_bytes(blob[index + 7:index + 9], "big")
            if width > 0 and height > 0:
                return width, height
        if length < 2:
            break
        index += 2 + length
    return 0, 0

def retain_plate_box(previous: dict | None, row: dict, *, now: float | None = None) -> dict:
    """Do not let a later empty callback erase a box for the same picture."""
    if plate_box_usable(row.get("plate_box")):
        return row
    prev = previous or {}
    if not plate_box_usable(prev.get("plate_box")):
        return row
    moment = time.time() if now is None else float(now)
    try:
        age = moment - float(prev.get("captured_at_epoch") or 0)
    except (TypeError, ValueError):
        return row
    if age < 0 or age > 3.0:
        return row
    same_image = int(row.get("image_id") or 0) != 0 and int(row.get("image_id") or 0) == int(prev.get("image_id") or 0)
    same_plate = bool(row.get("plate")) and row.get("plate") == prev.get("plate")
    if not same_image and not same_plate:
        return row
    kept = dict(row)
    kept["plate_box"] = list(prev["plate_box"])
    if not int(kept.get("image_width") or 0):
        kept["image_width"] = int(prev.get("image_width") or 0)
        kept["image_height"] = int(prev.get("image_height") or 0)
    kept["have_vehicle"] = True
    return kept

def _decode_plate(raw: bytes) -> str:
    text = raw.split(b"\x00", 1)[0].strip()
    if not text:
        return ""
    for encoding in ("gb2312", "gbk", "utf-8", "latin-1"):
        try:
            plate = text.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
        if plate:
            return plate
    return ""
