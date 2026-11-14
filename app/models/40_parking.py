from __future__ import annotations

class ParkingSession(Base):
    __tablename__ = "parking_sessions"
    __table_args__ = (
        Index(
            "uq_parking_sessions_site_entry_event",
            "site_id",
            "entry_event_id",
            unique=True,
            sqlite_where=text("entry_event_id != ''"),
            postgresql_where=text("entry_event_id != ''"),
        ),
        Index(
            "uq_parking_sessions_one_open_plate",
            "site_id",
            "plate",
            unique=True,
            sqlite_where=text("status IN ('WAITING_RECEIPT','ACTIVE','PAID','OPEN')"),
            postgresql_where=text("status IN ('WAITING_RECEIPT','ACTIVE','PAID','OPEN')"),
        ),
        Index(
            "uq_parking_sessions_public_token",
            "public_token",
            unique=True,
            sqlite_where=text("public_token != ''"),
            postgresql_where=text("public_token != ''"),
        ),
        Index(
            "uq_parking_sessions_human_reference",
            "human_reference",
            unique=True,
            sqlite_where=text("human_reference != ''"),
            postgresql_where=text("human_reference != ''"),
        ),
        Index(
            "uq_parking_sessions_site_camera_visit",
            "site_id",
            "camera_id",
            "visit_id",
            unique=True,
            sqlite_where=text("visit_id != '' AND camera_id IS NOT NULL"),
            postgresql_where=text("visit_id != '' AND camera_id IS NOT NULL"),
        ),
        # Exit callbacks are retried by cameras and by the durable outbox. The
        # lifecycle code is already idempotent, but the database should also
        # reject two sessions claiming the same physical exit event.
        Index(
            "uq_parking_sessions_site_exit_event",
            "site_id",
            "exit_event_id",
            unique=True,
            sqlite_where=text("exit_event_id != ''"),
            postgresql_where=text("exit_event_id != ''"),
        ),
        Index("ix_parking_sessions_site_status_plate", "site_id", "status", "plate"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id"), nullable=False, default=DEFAULT_SITE_ID, server_default=str(DEFAULT_SITE_ID), index=True
    )
    plate: Mapped[str] = mapped_column(String(32), index=True)
    plate_raw: Mapped[str] = mapped_column(String(32), default="", server_default="")
    plate_status: Mapped[str] = mapped_column(String(20), default="", server_default="")
    # gate_id stays as the legacy/entry relationship for backwards compatibility.
    # New code preserves both ends of a visit explicitly.
    gate_id: Mapped[int | None] = mapped_column(ForeignKey("gates.id"), nullable=True)
    entry_gate_id: Mapped[int | None] = mapped_column(ForeignKey("gates.id"), nullable=True, index=True)
    exit_gate_id: Mapped[int | None] = mapped_column(ForeignKey("gates.id"), nullable=True, index=True)
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.id"), nullable=True)
    entry_lane_id: Mapped[int | None] = mapped_column(ForeignKey("lanes.id"), nullable=True)
    exit_lane_id: Mapped[int | None] = mapped_column(ForeignKey("lanes.id"), nullable=True)
    exit_camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.id"), nullable=True)
    lane_direction: Mapped[str] = mapped_column(String(20), default="ENTRY")
    car_type: Mapped[str] = mapped_column(String(40), default="Car1")
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)
    lifecycle: Mapped[str] = mapped_column(String(40), default="", server_default="")
    entry_time: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)
    exit_time: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="TZS")
    amount_due: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    amount_paid: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    breakdown: Mapped[list] = mapped_column(JSON, default=list)
    tariff_rules: Mapped[dict] = mapped_column(JSON, default=dict)
    public_token: Mapped[str] = mapped_column(String(64), default="", index=True)
    human_reference: Mapped[str] = mapped_column(String(16), default="", server_default="")
    receipt_status: Mapped[str] = mapped_column(String(20), default="")
    receipt_printed_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    receipt_taken_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    print_job_id: Mapped[str] = mapped_column(String(64), default="", server_default="")
    print_job_status: Mapped[str] = mapped_column(String(20), default="", server_default="")
    print_retry_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    printer_error: Mapped[str] = mapped_column(String(240), default="", server_default="")
    payment_status: Mapped[str] = mapped_column(String(20), default="", server_default="")
    paid_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    payment_exit_grace_until: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    entry_event_id: Mapped[str] = mapped_column(String(64), default="", server_default="")
    visit_id: Mapped[str] = mapped_column(String(64), default="", server_default="")
    exit_event_id: Mapped[str] = mapped_column(String(64), default="", server_default="")
    entry_image_ref: Mapped[str] = mapped_column(String(260), default="", server_default="")
    open_command_uuid: Mapped[str] = mapped_column(String(64), default="", server_default="")
    exit_open_command_uuid: Mapped[str] = mapped_column(String(64), default="", server_default="")
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    parker_kind: Mapped[str] = mapped_column(String(40), default="CASUAL", index=True)
    access_plan_id: Mapped[int | None] = mapped_column(ForeignKey("access_plans.id"), nullable=True)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("registered_vehicles.id"), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    gate: Mapped[Gate | None] = relationship(back_populates="sessions", foreign_keys=[gate_id])

class ParkingEntryClaim(Base):
    """Transactional idempotency for one physical camera visit.

    Two concurrent entry submissions for the same ``visit_id`` both attempt
    this insert; only one row can exist. The loser reuses ``session_id``.
    """

    __tablename__ = "parking_entry_claims"
    __table_args__ = (
        UniqueConstraint("site_id", "camera_id", "visit_id", name="uq_parking_entry_claims_visit"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(Integer, nullable=False, default=DEFAULT_SITE_ID, server_default=str(DEFAULT_SITE_ID), index=True)
    camera_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    visit_id: Mapped[str] = mapped_column(String(64), nullable=False)
    plate: Mapped[str] = mapped_column(String(32), default="", server_default="")
    event_id: Mapped[str] = mapped_column(String(64), default="", server_default="")
    session_id: Mapped[int | None] = mapped_column(ForeignKey("parking_sessions.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)

class SiteSetting(Base):
    __tablename__ = "site_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON, nullable=True)
