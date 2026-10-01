"""QR scanner adapters for exit/kiosk fallback.

Most USB QR scanners act as HID keyboards and need no device library: the UI
collects the completed scan string and submits it to the parking controller.

Serial/COM scanners use pySerial with bounded read timeouts so a missing or
silent scanner never blocks the site service indefinitely.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.domain.receipt_engine import extract_session_token


@dataclass(frozen=True)
class QrScan:
    raw: str
    token: str
    source: str


@runtime_checkable
class QrScannerAdapter(Protocol):
    id: str

    async def read(self) -> QrScan | None: ...


class HidKeyboardQrScanner:
    """Stateless parser for keyboard-wedge scanners.

    The OS/UI receives keystrokes; this adapter validates the completed line.
    """

    id = "hid_keyboard"

    @staticmethod
    def parse(raw: str) -> QrScan | None:
        text = (raw or "").strip()
        token = extract_session_token(text)
        if not token:
            return None
        return QrScan(raw=text, token=token, source=HidKeyboardQrScanner.id)

    async def read(self) -> QrScan | None:
        raise RuntimeError("HID scanners are event-driven; pass completed input to parse().")


class SerialQrScanner:
    id = "serial"

    def __init__(
        self,
        port: str,
        *,
        baudrate: int = 9600,
        timeout_seconds: float = 1.0,
        encoding: str = "utf-8",
    ) -> None:
        self.port = str(port or "").strip()
        self.baudrate = int(baudrate)
        self.timeout_seconds = max(0.05, float(timeout_seconds))
        self.encoding = encoding

    async def read(self) -> QrScan | None:
        if not self.port:
            raise ValueError("serial QR scanner port is required")

        import asyncio

        def _blocking_read() -> bytes:
            try:
                import serial  # type: ignore
            except ImportError as exc:
                raise RuntimeError("pyserial is required for serial QR scanners") from exc
            with serial.Serial(
                self.port,
                self.baudrate,
                timeout=self.timeout_seconds,
                write_timeout=self.timeout_seconds,
            ) as device:
                return device.readline()

        raw = await asyncio.wait_for(
            asyncio.to_thread(_blocking_read),
            timeout=self.timeout_seconds + 0.5,
        )
        if not raw:
            return None
        text = raw.decode(self.encoding, "replace").strip()
        token = extract_session_token(text)
        if not token:
            return None
        return QrScan(raw=text, token=token, source=self.id)
