from __future__ import annotations

class VehicleCapture(Base):
    """One car event from a QY image callback: full snapshot + plate crop + characters."""
    __tablename__ = "vehicle_captures"
    __table_args__ = (
        Index("uq_vehicle_captures_camera_event", "camera_id", "event_id", unique=True,
              sqlite_where=text("event_id != '' AND camera_id IS NOT NULL"),
              postgresql_where=text("event_id != '' AND camera_id IS NOT NULL")),
        Index("uq_vehicle_captures_camera_visit", "camera_id", "visit_id", unique=True,
              sqlite_where=text("visit_id != '' AND camera_id IS NOT NULL"),
              postgresql_where=text("visit_id != '' AND camera_id IS NOT NULL")),
        Index("uq_vehicle_captures_camera_image_identity", "camera_id", "image_id", unique=True,
              sqlite_where=text("image_id > 0 AND camera_id IS NOT NULL"),
              postgresql_where=text("image_id > 0 AND camera_id IS NOT NULL")),
        Index("ix_vehicle_captures_camera_image", "camera_id", "image_id"),
        Index("ix_vehicle_captures_camera_latest", "camera_id", "id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.id"), nullable=True, index=True)
    gate_id: Mapped[int | None] = mapped_column(ForeignKey("gates.id"), nullable=True, index=True)
    lane_direction: Mapped[str] = mapped_column(String(20), default="ENTRY")
    plate: Mapped[str] = mapped_column(String(32), default="", index=True)
    plate_raw: Mapped[str] = mapped_column(String(32), default="")
    confidence: Mapped[float] = mapped_column(Numeric(6, 3), default=0)
    image_id: Mapped[int] = mapped_column(Integer, default=0, index=True)
    snapshot_path: Mapped[str] = mapped_column(String(260), default="")
    crop_path: Mapped[str] = mapped_column(String(260), default="")
    bbox: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    plate_country: Mapped[str] = mapped_column(String(8), default="")
    plate_region: Mapped[str] = mapped_column(String(40), default="")
    plate_type: Mapped[str] = mapped_column(String(40), default="")
    source: Mapped[str] = mapped_column(String(40), default="")
    event_id: Mapped[str] = mapped_column(String(64), default="")
    visit_id: Mapped[str] = mapped_column(String(64), default="", server_default="", index=True)
    # Optional cloud AI second opinion (supporting/conflicting/unreadable). Never the plate authority.
    ai_review: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)

class AccessPlan(Base):
    """Season / VIP / staff policy. Registered plates use a plan, not RFID cards."""
    __tablename__ = "access_plans"
    __table_args__ = (UniqueConstraint("site_id", "name", name="uq_access_plans_site_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id"), nullable=False, default=DEFAULT_SITE_ID, server_default=str(DEFAULT_SITE_ID), index=True
    )
    name: Mapped[str] = mapped_column(String(80), index=True)
    kind: Mapped[str] = mapped_column(String(40), default="MONTHLY", index=True)
    auto_open: Mapped[bool] = mapped_column(Boolean, default=True)
    print_receipt: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    vehicles: Mapped[list["RegisteredVehicle"]] = relationship(back_populates="plan")

class RegisteredVehicle(Base):
    """Plate that may auto-open because it is on an access plan."""
    __tablename__ = "registered_vehicles"
    __table_args__ = (UniqueConstraint("site_id", "plate", name="uq_registered_vehicles_site_plate"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id"), nullable=False, default=DEFAULT_SITE_ID, server_default=str(DEFAULT_SITE_ID), index=True
    )
    plate: Mapped[str] = mapped_column(String(32), index=True)
    owner_name: Mapped[str] = mapped_column(String(160), default="")
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("access_plans.id"), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    valid_from: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)
    plan: Mapped[AccessPlan | None] = relationship(back_populates="vehicles")

class AccessDecision(Base):
    """Authorization outcome for one plate event. Does not pulse hardware."""
    __tablename__ = "access_decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("parking_sessions.id"), nullable=True, index=True)
    plate: Mapped[str] = mapped_column(String(32), default="", index=True)
    gate_id: Mapped[int | None] = mapped_column(ForeignKey("gates.id"), nullable=True, index=True)
    lane_direction: Mapped[str] = mapped_column(String(20), default="ENTRY")
    outcome: Mapped[str] = mapped_column(String(40), index=True)
    reason: Mapped[str] = mapped_column(String(200), default="")
    parker_kind: Mapped[str] = mapped_column(String(40), default="CASUAL")
    automatic: Mapped[bool] = mapped_column(Boolean, default=True)
    barrier_opened: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)

class GateCommandRecord(Base):
    """Durable record of a boom command. Written after GPIO/Board/LED I/O returns."""
    __tablename__ = "gate_commands"
    __table_args__ = (UniqueConstraint("command_uuid", name="uq_gate_command_uuid"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    command_uuid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    gate_id: Mapped[int | None] = mapped_column(ForeignKey("gates.id"), nullable=True, index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("parking_sessions.id"), nullable=True, index=True)
    reason: Mapped[str] = mapped_column(String(200), default="")
    automatic: Mapped[bool] = mapped_column(Boolean, default=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)
