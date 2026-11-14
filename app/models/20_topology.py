from __future__ import annotations

class Node(Base):
    """Central registry identity for one physical Edge Node.

    This is intentionally separate from ``User``. A node credential can
    authenticate a runtime, but it is never a human RBAC identity.
    """
    __tablename__ = "nodes"
    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"), index=True)
    name: Mapped[str] = mapped_column(String(160), default="")
    node_type: Mapped[str] = mapped_column(String(40), default="EDGE_NODE")
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", index=True)
    credential_hash: Mapped[str] = mapped_column(String(300), default="")
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[str] = mapped_column(String(80), default="")
    last_seen_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    assignments: Mapped[list["NodeGateAssignment"]] = relationship(back_populates="node", cascade="all, delete-orphan")

class NodeAuthSession(Base):
    """Revocable bearer session issued to a node runtime."""
    __tablename__ = "node_auth_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(AwareDateTime())
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)

class Site(Base):
    __tablename__ = "sites"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), default="Default Site")
    timezone: Mapped[str] = mapped_column(String(80), default="UTC")
    locale: Mapped[str] = mapped_column(String(20), default="en")
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    zones: Mapped[list["Zone"]] = relationship(back_populates="site")

class Zone(Base):
    __tablename__ = "zones"
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    site: Mapped[Site] = relationship(back_populates="zones")
    lanes: Mapped[list["Lane"]] = relationship(back_populates="zone")

class Gate(Base):
    __tablename__ = "gates"
    __table_args__ = (UniqueConstraint("site_id", "name", name="uq_gates_site_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    mode: Mapped[str] = mapped_column(String(30), default=GateMode.COMMISSIONING.value)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    physical_control_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id"), nullable=False, default=DEFAULT_SITE_ID, server_default=str(DEFAULT_SITE_ID), index=True
    )
    zone_id: Mapped[int | None] = mapped_column(ForeignKey("zones.id"), nullable=True)
    cameras: Mapped[list["Camera"]] = relationship(back_populates="gate")
    sessions: Mapped[list["ParkingSession"]] = relationship(back_populates="gate", foreign_keys="ParkingSession.gate_id")
    lanes: Mapped[list["Lane"]] = relationship(back_populates="gate")
    node_assignments: Mapped[list["NodeGateAssignment"]] = relationship(back_populates="gate")

class NodeGateAssignment(Base):
    """Authoritative central ownership of a physical gate by a node."""
    __tablename__ = "node_gate_assignments"
    __table_args__ = (
        UniqueConstraint("node_id", "gate_id", name="uq_node_gate_assignment"),
        # A physical gate may have exactly one live owner.  The central
        # server uses this as the final race-proof boundary; the API also
        # performs a friendly conflict check before this constraint fires.
        Index(
            "uq_node_gate_assignment_active_gate",
            "gate_id",
            unique=True,
            sqlite_where=text("enabled = 1"),
            postgresql_where=text("enabled = true"),
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"), index=True)
    gate_id: Mapped[int] = mapped_column(ForeignKey("gates.id"), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    node: Mapped[Node] = relationship(back_populates="assignments")
    gate: Mapped[Gate] = relationship(back_populates="node_assignments")

class Lane(Base):
    __tablename__ = "lanes"
    id: Mapped[int] = mapped_column(primary_key=True)
    gate_id: Mapped[int | None] = mapped_column(ForeignKey("gates.id"), nullable=True, index=True)
    zone_id: Mapped[int | None] = mapped_column(ForeignKey("zones.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    direction: Mapped[str] = mapped_column(String(20), default="ENTRY")
    bidirectional: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    gate: Mapped[Gate | None] = relationship(back_populates="lanes")
    zone: Mapped[Zone | None] = relationship(back_populates="lanes")

class Camera(Base):
    __tablename__ = "cameras"
    __table_args__ = (UniqueConstraint("site_id", "name", name="uq_cameras_site_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id"), nullable=False, default=DEFAULT_SITE_ID, server_default=str(DEFAULT_SITE_ID), index=True
    )
    name: Mapped[str] = mapped_column(String(120), index=True)
    ip_address: Mapped[str] = mapped_column(String(64), index=True)
    sdk_port: Mapped[int] = mapped_column(Integer, default=30000)
    username: Mapped[str] = mapped_column(String(120), default="admin")
    # Legacy column. With an external SecretStore this holds "" and the real
    # value lives behind ``credentials_ref``; use the ``password_secret``
    # property, never the column directly.
    _password_secret: Mapped[str] = mapped_column("password_secret", String(300), default="")
    credentials_ref: Mapped[str] = mapped_column(String(120), default="", server_default="")
    gate_id: Mapped[int | None] = mapped_column(ForeignKey("gates.id"), nullable=True)
    lane_id: Mapped[int | None] = mapped_column(ForeignKey("lanes.id"), nullable=True)
    lane_direction: Mapped[str] = mapped_column(String(20), default="ENTRY")
    controller_ip: Mapped[str] = mapped_column(String(64), default="")
    display_ip: Mapped[str] = mapped_column(String(64), default="")
    adapter_id: Mapped[str] = mapped_column(String(40), default="hvx")
    connection_mode: Mapped[str] = mapped_column(String(20), default="DIRECT")
    rtsp_url: Mapped[str] = mapped_column(Text, default="")
    stream_profiles: Mapped[dict] = mapped_column(JSON, default=dict)
    ffmpeg_profile: Mapped[str] = mapped_column(String(40), default="LOW_LATENCY_LAN")
    rtsp_transport: Mapped[str] = mapped_column(String(16), default="TCP")
    # HTTPS snapshot certificates are verified unless this camera opts out
    # (self-signed camera web UI). Never a site-wide default.
    allow_insecure_tls: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    media_capabilities: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default=CameraStatus.UNKNOWN.value)
    sdk_handle: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    last_seen_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    recognition_mode: Mapped[str] = mapped_column(String(40), default="")
    vendor: Mapped[str] = mapped_column(String(80), default="")
    model_name: Mapped[str] = mapped_column(String(80), default="")
    serial: Mapped[str] = mapped_column(String(80), default="")
    timezone: Mapped[str] = mapped_column(String(80), default="")
    camera_type: Mapped[str] = mapped_column(String(40), default="")
    # ONVIF capability snapshot from the last discovery: services, capabilities,
    # snapshot URI, plate topics and whether Profile M event pulling is enabled.
    onvif_profile: Mapped[dict] = mapped_column(JSON, default=dict)
    gate: Mapped[Gate | None] = relationship(back_populates="cameras")

    @property
    def password_secret(self) -> str:
        """Raw camera password for adapters. Resolved through the SecretStore when configured."""
        from app.infrastructure.secrets import resolve_secret

        return resolve_secret(self.credentials_ref, fallback=self._password_secret or "")

    @password_secret.setter
    def password_secret(self, value: str | None) -> None:
        from app.infrastructure.secrets import SecretStoreError, store_secret, uses_external_store

        value = value or ""
        if uses_external_store():
            try:
                self.credentials_ref = store_secret(value, kind="camera", ref=self.credentials_ref or None)
                self._password_secret = ""
                return
            except SecretStoreError:
                pass  # fall back to the legacy column rather than losing the credential
        self._password_secret = value

    def has_password(self) -> bool:
        return bool(self._password_secret) or bool(self.credentials_ref)
