from __future__ import annotations

def parking_settings(db: Session) -> dict:
    cached = db.info.get("smartpark.parking_settings") if hasattr(db, "info") else None
    if isinstance(cached, dict):
        return dict(cached)
    row = db.get(SiteSetting, "parking")
    merged = dict(DEFAULT_PARKING_SETTINGS)
    if row and isinstance(row.value, dict):
        merged.update(row.value)
    # Physical lanes must wait for the passage sensor and require a usable
    # receipt before opening.  The development profile intentionally retains
    # the simulator defaults so fixture tests and commissioning remain usable.
    if str(getattr(app_settings, "deployment_profile", "DEVELOPMENT") or "DEVELOPMENT").upper() != "DEVELOPMENT":
        merged["receipt_required_before_open"] = True
        merged["receipt_policy"] = "REQUIRE_TAKEN_BEFORE_OPEN"
        merged["passage_sensing"] = "WAIT_FOR_PASSAGE"
    policy = resolve_receipt_policy(merged)
    merged["receipt_policy"] = policy
    merged["receipt_required_before_open"] = policy_requires_taken(policy)
    if hasattr(db, "info"):
        db.info["smartpark.parking_settings"] = dict(merged)
    return merged

def save_parking_settings(db: Session, payload: dict) -> dict:
    current = parking_settings(db)
    keys = set(DEFAULT_PARKING_SETTINGS) | {"receipt_policy"}
    for key in keys:
        if key in payload and payload[key] is not None:
            current[key] = payload[key]
    if "receipt_policy" in payload and payload["receipt_policy"]:
        current["receipt_policy"] = str(payload["receipt_policy"]).strip().upper()
        current["receipt_required_before_open"] = policy_requires_taken(current["receipt_policy"])
    elif "receipt_required_before_open" in payload:
        current["receipt_policy"] = (
            "REQUIRE_TAKEN_BEFORE_OPEN" if payload["receipt_required_before_open"] else "PRINT_AND_OPEN"
        )
    row = db.get(SiteSetting, "parking")
    if row is None:
        row = SiteSetting(key="parking", value=current)
        db.add(row)
    else:
        row.value = current
    if current.get("printer_name") and str(current.get("printer_adapter") or "simulated") == "simulated":
        current["printer_adapter"] = "system"
        row.value = current
    if not current.get("printer_name") and str(current.get("printer_adapter") or "") in {"system", "usb", "a4", "thermal"}:
        current["printer_adapter"] = "simulated"
        row.value = current
    db.commit()
    if hasattr(db, "info"):
        db.info.pop("smartpark.parking_settings", None)
    return parking_settings(db)
