@app.get("/reports/summary")
def reports_summary(
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_any("dashboard.view", "fees.view", "payments.view")),
):
    from app.services.reports_desk import report_summary
    return report_summary(db, start, end)


@app.get("/reports/export.csv")
def reports_export(
    kind: str = "payments",
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_any("dashboard.view", "fees.view", "payments.view")),
):
    from app.services.reports_desk import report_by_id, report_summary, table_csv
    summary = report_summary(db, start, end)
    try:
        sheet = report_by_id(summary, kind)
    except KeyError:
        raise HTTPException(404, "Unknown report")
    filename = f"smartpark-{sheet['id']}.csv"
    return Response(
        content=table_csv(sheet),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/reports/payments.csv")
def reports_csv(
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_any("dashboard.view", "fees.view", "payments.view")),
):
    from app.services.reports_desk import report_csv, report_summary
    summary = report_summary(db, start, end)
    return Response(
        content=report_csv(summary),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="smartpark-payments.csv"'},
    )


@app.get("/backup")
def backup_status(db: Session = Depends(get_db), _: User = Depends(require_any("dashboard.view", "settings.manage"))):
    from app.services.backup import public_backup_status
    return public_backup_status(db)


@app.patch("/backup")
def backup_update(
    payload: BackupSettingsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require("settings.manage")),
):
    from app.services.backup import public_backup_status, save_backup_settings
    try:
        save_backup_settings(db, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    write_audit(db, user, "backup.update", "site", "backup", "")
    db.commit()
    return public_backup_status(db)


@app.post("/backup/offline")
def backup_mark_offline(db: Session = Depends(get_db), user: User = Depends(require("settings.manage"))):
    from app.services.backup import mark_offline_saved
    status = mark_offline_saved(db)
    write_audit(db, user, "backup.offline", "site", "backup", status.get("last_offline_at") or "")
    db.commit()
    return status


@app.post("/backup/snooze")
def backup_snooze(db: Session = Depends(get_db), _: User = Depends(require_any("dashboard.view", "settings.manage"))):
    from app.services.backup import snooze_offline_reminder
    return snooze_offline_reminder(db)


@app.get("/backup/download")
def backup_download(db: Session = Depends(get_db), user: User = Depends(require("settings.manage"))):
    from app.services.backup import backup_filename, dump_sql, mark_offline_saved
    try:
        body = dump_sql(db)
    except Exception as exc:
        raise HTTPException(409, str(exc)) from exc
    mark_offline_saved(db)
    write_audit(db, user, "backup.download", "site", "backup", backup_filename())
    db.commit()
    return Response(
        content=body,
        media_type="application/sql",
        headers={"Content-Disposition": f'attachment; filename="{backup_filename()}"'},
    )


@app.post("/backup/cloud")
def backup_cloud(db: Session = Depends(get_db), user: User = Depends(require("settings.manage"))):
    from app.services.backup import push_cloud_backup
    try:
        status = push_cloud_backup(db)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc
    write_audit(db, user, "backup.cloud", "site", "backup", "ok")
    db.commit()
    return status


@app.get("/dashboard")
def dashboard_stats(db: Session = Depends(get_db), _: User = Depends(require_any("dashboard.view", "cameras.view"))):
    from app.services.cache import dashboard_cache
    from app.services.runtime import startup_state
    from app.services.simulation import OPEN_STATUSES
    from app.services.site_policy import as_site_local, site_policy, format_money
    from app.services.lane_status import lane_operator_status

    cached = dashboard_cache.get("overview")
    if cached is not None:
        return cached
    policy = site_policy(db)
    lanes = lane_operator_status(db)
    cams = list(db.scalars(select(Camera)).all())
    connected = sum(1 for c in cams if c.status in ("SDK_CONNECTED", "VIDEO_CONNECTED"))
    offline = sum(1 for c in cams if c.enabled and c.status in ("OFFLINE", "SDK_FAILED", "UNKNOWN"))
    inside = db.scalar(
        select(func.count(ParkingSession.id)).where(ParkingSession.status.in_(tuple(OPEN_STATUSES)))
    ) or 0
    registered = db.scalar(select(func.count(RegisteredVehicle.id)).where(RegisteredVehicle.enabled.is_(True))) or 0
    # Compute local midnight, then convert it to UTC for indexed DB queries.
    local_now = as_site_local(datetime.now(timezone.utc), policy)
    start = local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    entries_today = db.scalar(
        select(func.count(ParkingSession.id)).where(ParkingSession.entry_time >= start)
    ) or 0
    exits_today = db.scalar(
        select(func.count(ParkingSession.id)).where(ParkingSession.exit_time >= start)
    ) or 0
    revenue_today = db.scalar(
        select(func.coalesce(func.sum(PaymentTransaction.amount), 0)).where(
            PaymentTransaction.status == "SUCCEEDED",
            PaymentTransaction.confirmed_at >= start,
        )
    ) or 0
    unpaid_active = db.scalar(
        select(func.count(ParkingSession.id)).where(
            ParkingSession.status.in_(("ACTIVE", "OPEN", "WAITING_RECEIPT")),
            ParkingSession.parker_kind == "CASUAL",
        )
    ) or 0
    subscribers_inside = db.scalar(
        select(func.count(ParkingSession.id)).where(
            ParkingSession.status.in_(tuple(OPEN_STATUSES)),
            ParkingSession.parker_kind != "CASUAL",
        )
    ) or 0
    review = db.scalar(
        select(func.count(AccessDecision.id)).where(AccessDecision.outcome.in_(("WAITING_RECEIPT", "DENIED_PAYMENT")))
    ) or 0
    alerts = []
    if offline:
        alerts.append(f"{offline} camera(s) not live")
    if review:
        alerts.append(f"{int(review)} recent hold/unpaid decisions")
    body = {
        "cameras": len(cams),
        "sdk_connected": connected,
        "vehicles_inside": int(inside),
        "registered_plates": int(registered),
        "entries_today": int(entries_today),
        "exits_today": int(exits_today),
        "revenue_today": float(revenue_today),
        "revenue_today_label": format_money(revenue_today, policy),
        "unpaid_active": int(unpaid_active),
        "subscribers_inside": int(subscribers_inside),
        "alerts": alerts,
        "receipt_policies": list(RECEIPT_POLICIES),
        "runtime": {"state": startup_state(), "version": settings.app_version},
        "currency": policy.get("currency"),
        "timezone": policy.get("timezone"),
        "lanes": lanes.get("lanes") or [],
    }
    return dashboard_cache.set("overview", body)


@app.get("/printers/status")
async def printer_status(
    db: Session = Depends(get_db),
    _: User = Depends(require_any("hardware.view", "sessions.view", "fees.view", "simulation.run")),
):
    cfg = parking_settings(db)
    adapter = printer_adapter(cfg.get("printer_adapter"), printer_name=cfg.get("printer_name") or "")
    health = await adapter.health()
    printers = health.get("printers")
    if printers is None:
        printers = list_system_printers()
    return {
        "adapter_id": adapter.id,
        **health,
        "printer_name": cfg.get("printer_name") or health.get("printer_name") or "",
        "printers": printers,
        "policies": list(RECEIPT_POLICIES),
    }


@app.post("/printers/test")
async def printer_test(
    db: Session = Depends(get_db),
    user: User = Depends(require_any("hardware.view", "simulation.run")),
):
    from app.infrastructure.hardware.printers import ReceiptDocument
    from app.services.receipts import _qr_png, public_receipt_url, resolve_public_base_url
    cfg = parking_settings(db)
    token = "TEST"
    public_url = public_receipt_url(token, base_url=resolve_public_base_url(db))
    document = ReceiptDocument(
        site_name=settings.site_name or settings.app_name,
        plate="T000TST",
        entry_time="Test print",
        entry_gate="Simulation",
        public_reference=token,
        public_url=public_url,
        payment_instructions="Zirp thermal printer test ticket. Scan the QR code.",
        body_text="Zirp test receipt\nPlate: T000TST\n",
        qr_payload=public_url,
        qr_png=_qr_png(public_url),
        lines=["Zirp test receipt"],
    )
    adapter = printer_adapter(cfg.get("printer_adapter"), printer_name=cfg.get("printer_name") or "")
    printed = await adapter.print_receipt(document)
    write_audit(db, user, "printer.test", "printer", adapter.id, printed.message)
    db.commit()
    return printed.__dict__


@app.get("/access-plans")
def list_access_plans(db: Session = Depends(get_db), _: User = Depends(require("subscribers.view"))):
    ensure_access_plans(db)
    return [plan_dict(row) for row in db.scalars(
        select(AccessPlan).options(selectinload(AccessPlan.vehicles)).order_by(AccessPlan.id)
    ).all()]


@app.post("/access-plans")
def create_access_plan(payload: AccessPlanCreate, db: Session = Depends(get_db), user: User = Depends(require("subscribers.manage"))):
    row = AccessPlan(
        name=payload.name.strip(), kind=payload.kind.strip().upper(),
        auto_open=payload.auto_open, print_receipt=payload.print_receipt,
        enabled=payload.enabled, notes=payload.notes or "",
    )
    db.add(row)
    commit_or_conflict(db, "A plan with that name already exists")
    db.refresh(row)
    write_audit(db, user, "plan.create", "access_plan", str(row.id), row.name)
    return plan_dict(row)


@app.patch("/access-plans/{plan_id}")
def update_access_plan(plan_id: int, payload: AccessPlanUpdate, db: Session = Depends(get_db), user: User = Depends(require("subscribers.manage"))):
    row = db.get(AccessPlan, plan_id)
    if not row:
        raise HTTPException(404, "Plan not found")
    data = payload.model_dump(exclude_unset=True)
    if "kind" in data and data["kind"]:
        data["kind"] = str(data["kind"]).strip().upper()
    for key, value in data.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    write_audit(db, user, "plan.update", "access_plan", str(row.id), row.name)
    return plan_dict(row)


@app.get("/vehicles")
def list_vehicles(db: Session = Depends(get_db), _: User = Depends(require("subscribers.view"))):
    ensure_access_plans(db)
    return [vehicle_dict(row) for row in db.scalars(
        select(RegisteredVehicle).options(joinedload(RegisteredVehicle.plan)).order_by(RegisteredVehicle.plate)
    ).all()]


@app.post("/vehicles")
def create_vehicle(payload: VehicleCreate, db: Session = Depends(get_db), user: User = Depends(require("subscribers.manage"))):
    ensure_access_plans(db)
    plate = normalize_plate(payload.plate)
    if not plate:
        raise HTTPException(400, "Enter a number plate")
    plan_id = payload.plan_id
    if plan_id is None:
        first = db.scalar(select(AccessPlan).order_by(AccessPlan.id))
        plan_id = first.id if first else None
    if plan_id and db.get(AccessPlan, plan_id) is None:
        raise HTTPException(404, "Access plan not found")
    row = RegisteredVehicle(
        plate=plate, owner_name=payload.owner_name or "", plan_id=plan_id,
        enabled=payload.enabled, valid_from=payload.valid_from, valid_until=payload.valid_until,
        notes=payload.notes or "",
    )
    db.add(row)
    commit_or_conflict(db, "That number plate is already registered")
    db.refresh(row)
    write_audit(db, user, "vehicle.register", "registered_vehicle", str(row.id), plate)
    return vehicle_dict(row)


@app.patch("/vehicles/{vehicle_id}")
def update_vehicle(vehicle_id: int, payload: VehicleUpdate, db: Session = Depends(get_db), user: User = Depends(require("subscribers.manage"))):
    row = db.get(RegisteredVehicle, vehicle_id)
    if not row:
        raise HTTPException(404, "Vehicle not found")
    data = payload.model_dump(exclude_unset=True)
    if "plate" in data:
        data["plate"] = normalize_plate(data["plate"] or "")
        if not data["plate"]:
            raise HTTPException(400, "Enter a number plate")
    if data.get("plan_id") and db.get(AccessPlan, data["plan_id"]) is None:
        raise HTTPException(404, "Access plan not found")
    for key, value in data.items():
        setattr(row, key, value)
    commit_or_conflict(db, "That number plate is already registered")
    db.refresh(row)
    write_audit(db, user, "vehicle.update", "registered_vehicle", str(row.id), row.plate)
    return vehicle_dict(row)


@app.post("/vehicles/bulk")
def create_vehicles_bulk(payload: VehicleBulkCreate, db: Session = Depends(get_db), user: User = Depends(require("subscribers.manage"))):
    """Register many plates at once. One bad row does not skip the others that succeed."""
    from app.core.plate import normalize_plate as norm
    ensure_access_plans(db)
    created = []
    errors = []
    for index, item in enumerate(payload.vehicles):
        plate = norm(item.plate)
        if not plate:
            errors.append({"index": index, "error": "Enter a number plate"})
            continue
        plan_id = item.plan_id
        if plan_id is None:
            first = db.scalar(select(AccessPlan).order_by(AccessPlan.id))
            plan_id = first.id if first else None
        if plan_id and db.get(AccessPlan, plan_id) is None:
            errors.append({"index": index, "plate": plate, "error": "Access plan not found"})
            continue
        row = RegisteredVehicle(
            plate=plate, owner_name=item.owner_name or "", plan_id=plan_id,
            enabled=item.enabled, valid_from=item.valid_from, valid_until=item.valid_until,
            notes=item.notes or "",
        )
        db.add(row)
        try:
            db.commit()
            db.refresh(row)
        except IntegrityError:
            db.rollback()
            errors.append({"index": index, "plate": plate, "error": "That number plate is already registered"})
            continue
        write_audit(db, user, "vehicle.register", "registered_vehicle", str(row.id), plate)
        db.commit()
        created.append(vehicle_dict(row))
    return {"ok": True, "created": created, "errors": errors}


@app.post("/vehicles/bulk-delete")
def delete_vehicles_bulk(payload: VehicleBulkDelete, db: Session = Depends(get_db), user: User = Depends(require("subscribers.manage"))):
    deleted = []
    for vehicle_id in payload.ids:
        row = db.get(RegisteredVehicle, int(vehicle_id))
        if row is None:
            continue
        plate = row.plate
        db.delete(row)
        deleted.append(vehicle_id)
        write_audit(db, user, "vehicle.delete", "registered_vehicle", str(vehicle_id), plate)
    db.commit()
    return {"ok": True, "deleted": deleted}


@app.delete("/vehicles/{vehicle_id}")
def delete_vehicle(vehicle_id: int, db: Session = Depends(get_db), user: User = Depends(require("subscribers.manage"))):
    row = db.get(RegisteredVehicle, vehicle_id)
    if not row:
        raise HTTPException(404, "Vehicle not found")
    plate = row.plate
    db.delete(row)
    db.commit()
    write_audit(db, user, "vehicle.delete", "registered_vehicle", str(vehicle_id), plate)
    return {"ok": True}


@app.get("/vehicles/lookup/{plate}")
def lookup_vehicle(plate: str, db: Session = Depends(get_db), _: User = Depends(require("subscribers.view"))):
    return lookup_entitlement(db, plate).__dict__


@app.get("/roles")
def list_roles(db: Session = Depends(get_db), _: User = Depends(require("users.view"))):
    return [{"id": r.id, "name": r.name, "permissions": sorted(r.permissions()), "system_role": r.system_role}
            for r in db.scalars(select(Role).order_by(Role.id)).all()]


@app.get("/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(require("users.view"))):
    return [user_dict(u) for u in load_users(db)]


@app.get("/users/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db), _: User = Depends(require("users.view"))):
    user = load_user(db, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return user_dict(user)


@app.post("/users")
def add_user(payload: UserCreate, db: Session = Depends(get_db), actor: User = Depends(require("users.manage"))):
    user = create_user(
        db,
        username=payload.username.strip(),
        full_name=payload.full_name.strip(),
        password=payload.password,
        status=payload.status,
        roles=payload.roles,
    )
    write_audit(db, actor, "user.create", "user", str(user.id), f"Created {user.username}")
    return user_dict(user)


@app.patch("/users/{user_id}")
def patch_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db), actor: User = Depends(require("users.manage"))):
    user = load_user(db, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    user = update_user(
        db,
        user,
        full_name=payload.full_name,
        password=payload.password,
        status=payload.status,
        roles=payload.roles,
    )
    write_audit(db, actor, "user.update", "user", str(user.id), f"Updated {user.username}")
    return user_dict(user)


@app.delete("/users/{user_id}")
def remove_user(user_id: int, db: Session = Depends(get_db), actor: User = Depends(require("users.manage"))):
    user = load_user(db, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    username = user.username
    delete_user(db, user, actor.id)
    write_audit(db, actor, "user.delete", "user", str(user_id), f"Deleted {username}")
    return {"ok": True}


@app.get("/audit")
def audits(db: Session = Depends(get_db), _: User = Depends(require("audit.view"))):
    from app.models import AuditLog
    rows=db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(200)).all()
    return [{"id":x.id,"user_id":x.user_id,"action":x.action,"target_type":x.target_type,"target_id":x.target_id,"detail":x.detail,"created_at":x.created_at} for x in rows]


# Subsystem route registration lives beside the subsystem, while this module
# remains the stable ASGI/compatibility entry point.  The explicit handler map
# makes the migration seam auditable and preserves ``app.api_main`` imports.
from app.api.registry import register_subsystem_routers

register_subsystem_routers(app, globals())
