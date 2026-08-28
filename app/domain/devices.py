"""Device identity used by the registry. Camera/Gate rows remain the store."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DeviceType(str, Enum):
    CAMERA = "CAMERA"
    BARRIER = "BARRIER"
    DISPLAY = "DISPLAY"
    CONTROLLER = "CONTROLLER"
    PRINTER = "PRINTER"
    KIOSK = "KIOSK"
    SENSOR = "SENSOR"
    EDGE_AGENT = "EDGE_AGENT"


class ConnectionMode(str, Enum):
    DIRECT = "DIRECT"
    EDGE_AGENT = "EDGE_AGENT"


DEFAULT_CAMERA_ADAPTER = "hvx"
DEFAULT_CONNECTION_MODE = ConnectionMode.DIRECT.value


@dataclass(frozen=True)
class DeviceRecord:
    id: str
    device_type: str
    name: str
    adapter_id: str
    vendor: str = ""
    ip: str = ""
    port: int | None = None
    gate_id: int | None = None
    lane_id: str = ""
    enabled: bool = True
    connection_mode: str = DEFAULT_CONNECTION_MODE
    capabilities: dict[str, Any] = field(default_factory=dict)
    source_table: str = ""
    source_id: int | None = None
