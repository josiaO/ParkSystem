"""Device registry is a projection of Camera/Gate rows — not a second store."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.devices import (
    DEFAULT_CAMERA_ADAPTER,
    DEFAULT_CONNECTION_MODE,
    ConnectionMode,
    DeviceRecord,
    DeviceType,
)
from app.models import Camera, Gate
from app.services.site_cameras import side_label


def camera_adapter_id(camera: Camera) -> str:
    return (getattr(camera, "adapter_id", None) or DEFAULT_CAMERA_ADAPTER).strip().lower() or DEFAULT_CAMERA_ADAPTER


def camera_connection_mode(camera: Camera) -> str:
    value = (getattr(camera, "connection_mode", None) or DEFAULT_CONNECTION_MODE).strip().upper()
    return value if value in {item.value for item in ConnectionMode} else DEFAULT_CONNECTION_MODE


def camera_device(camera: Camera) -> DeviceRecord:
    lane = camera.gate.name if camera.gate else ""
    return DeviceRecord(
        id=f"camera:{camera.id}",
        device_type=DeviceType.CAMERA.value,
        name=camera.name,
        adapter_id=camera_adapter_id(camera),
        vendor="HVX" if camera_adapter_id(camera) == DEFAULT_CAMERA_ADAPTER else camera_adapter_id(camera),
        ip=camera.ip_address,
        port=camera.sdk_port,
        gate_id=camera.gate_id,
        lane_id=f"{lane}:{side_label(camera.lane_direction)}" if lane else side_label(camera.lane_direction),
        enabled=bool(camera.enabled),
        connection_mode=camera_connection_mode(camera),
        capabilities={
            "sdk_login": camera_adapter_id(camera) == DEFAULT_CAMERA_ADAPTER,
            "gpio": camera_adapter_id(camera) == DEFAULT_CAMERA_ADAPTER,
            "native_plates": camera_adapter_id(camera) == DEFAULT_CAMERA_ADAPTER,
        },
        source_table="cameras",
        source_id=camera.id,
    )


def list_devices(db: Session) -> list[DeviceRecord]:
    rows: list[DeviceRecord] = []
    for camera in db.scalars(select(Camera).order_by(Camera.id)).all():
        rows.append(camera_device(camera))
        if (camera.controller_ip or "").strip():
            rows.append(DeviceRecord(
                id=f"controller:{camera.id}",
                device_type=DeviceType.CONTROLLER.value,
                name=f"{camera.name} Board",
                adapter_id="board_tcp",
                ip=camera.controller_ip,
                gate_id=camera.gate_id,
                enabled=bool(camera.enabled),
                connection_mode=DEFAULT_CONNECTION_MODE,
                capabilities={"tcp_io": True},
                source_table="cameras",
                source_id=camera.id,
            ))
        if (camera.display_ip or "").strip():
            rows.append(DeviceRecord(
                id=f"display:{camera.id}",
                device_type=DeviceType.DISPLAY.value,
                name=f"{camera.name} LED",
                adapter_id="led_udp",
                ip=camera.display_ip,
                gate_id=camera.gate_id,
                enabled=bool(camera.enabled),
                connection_mode=DEFAULT_CONNECTION_MODE,
                capabilities={"udp_text": True},
                source_table="cameras",
                source_id=camera.id,
            ))
    for gate in db.scalars(select(Gate).order_by(Gate.id)).all():
        rows.append(DeviceRecord(
            id=f"gate:{gate.id}",
            device_type=DeviceType.BARRIER.value,
            name=gate.name,
            adapter_id="hvx",
            gate_id=gate.id,
            enabled=bool(gate.enabled),
            connection_mode=DEFAULT_CONNECTION_MODE,
            capabilities={"mode": gate.mode, "physical_control_verified": gate.physical_control_verified},
            source_table="gates",
            source_id=gate.id,
        ))
    return rows


def devices_as_dicts(db: Session) -> list[dict]:
    return [
        {
            "id": row.id,
            "device_type": row.device_type,
            "name": row.name,
            "adapter_id": row.adapter_id,
            "vendor": row.vendor,
            "ip": row.ip,
            "port": row.port,
            "gate_id": row.gate_id,
            "lane_id": row.lane_id,
            "enabled": row.enabled,
            "connection_mode": row.connection_mode,
            "capabilities": row.capabilities,
            "source_table": row.source_table,
            "source_id": row.source_id,
        }
        for row in list_devices(db)
    ]
