"""Kiosk/presenter receipt printers. Capabilities are declared, never assumed.

The simulated adapter has a taken sensor for development. USB/LAN thermal
adapters wrap the working ESC/POS path and do **not** claim PRESENTER or
TAKEN_SENSOR when the hardware cannot report those states.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.domain.receipt_engine import (
    CAP_CUTTER,
    CAP_PAPER_STATUS,
    CAP_PRESENTER,
    CAP_TAKEN_SENSOR,
    PrintOutcome,
    PrinterStatus,
)
from app.infrastructure.hardware.printers import (
    ReceiptDocument,
    printer_adapter,
    store_slip_files,
)


class SimulatedKioskPrinter:
    """Development printer: print → presented, taken only when simulate_taken()."""

    id = "simulated_kiosk"
    capabilities = frozenset({CAP_PAPER_STATUS, CAP_PRESENTER, CAP_TAKEN_SENSOR, CAP_CUTTER})

    def __init__(self) -> None:
        self.online = True
        self.paper_ok = True
        self._presented = False
        self._taken = False
        self.last_job_id = ""
        self.last_document: ReceiptDocument | None = None

    async def print_entry_receipt(self, document: ReceiptDocument, *, job_id: str) -> PrintOutcome:
        status = await self.get_status()
        if not status.online:
            return PrintOutcome(ok=False, status="OFFLINE", error="printer offline", simulated=True, adapter_id=self.id)
        if not status.paper_ok:
            return PrintOutcome(ok=False, status="OUT_OF_PAPER", error="out of paper", simulated=True, adapter_id=self.id)
        path = store_slip_files(document)
        self.last_job_id = job_id
        self.last_document = document
        self._presented = True
        self._taken = False
        return PrintOutcome(ok=True, status="PRESENTED", path=path, simulated=True, adapter_id=self.id)

    async def get_status(self) -> PrinterStatus:
        error = ""
        if not self.online:
            error = "printer offline"
        elif not self.paper_ok:
            error = "out of paper"
        return PrinterStatus(
            online=self.online,
            paper_ok=self.paper_ok,
            presented=self._presented,
            taken=self._taken,
            error=error,
            capabilities=self.capabilities,
        )

    async def wait_until_presented(self, *, timeout_seconds: float = 8.0) -> bool:
        if self._presented:
            return True
        await asyncio.sleep(0)
        raise TimeoutError("receipt was not presented")

    async def wait_until_taken(self, *, timeout_seconds: float = 30.0) -> bool:
        if self._taken:
            return True
        await asyncio.sleep(0)
        raise TimeoutError("receipt never taken")

    async def cancel_or_recover(self) -> None:
        self._presented = False
        self._taken = False

    def simulate_taken(self) -> None:
        if self._presented:
            self._taken = True


class HardwareReceiptPrinter:
    """USB/LAN thermal wrap. Does not invent a taken sensor."""

    # Generic Windows/LAN ESC/POS paths can submit print jobs and cut, but
    # they do not prove paper-present or receipt-taken state. Hardware with
    # those sensors must provide a dedicated adapter instead of advertising
    # capabilities it cannot query.
    capabilities = frozenset({CAP_CUTTER})

    def __init__(self, adapter_id: str | None = None, printer_name: str | None = None) -> None:
        self._inner = printer_adapter(adapter_id, printer_name=printer_name)
        self.id = getattr(self._inner, "id", adapter_id or "system")
        self.last_job_id = ""

    async def print_entry_receipt(self, document: ReceiptDocument, *, job_id: str) -> PrintOutcome:
        self.last_job_id = job_id
        printed = await self._inner.print_receipt(document)
        health = await self._inner.health()
        if not health.get("ok") and not printed.simulated:
            return PrintOutcome(ok=False, status="OFFLINE", error=str(health.get("note") or "printer offline"), path=printed.path, simulated=printed.simulated, adapter_id=self.id)
        if not printed.ok:
            return PrintOutcome(ok=False, status="FAILED", error=printed.message, path=printed.path, simulated=printed.simulated, adapter_id=self.id)
        return PrintOutcome(ok=True, status="PRESENTED", path=printed.path, simulated=printed.simulated, adapter_id=self.id)

    async def get_status(self) -> PrinterStatus:
        health = await self._inner.health()
        printers = health.get("printers") or []
        offline = any(row.get("offline") for row in printers if isinstance(row, dict))
        online = bool(health.get("ok", True)) and not offline
        return PrinterStatus(
            online=online,
            # Unknown, not measured. Keep the compatibility field true while the
            # capability set truthfully omits PAPER_STATUS.
            paper_ok=True,
            presented=False,
            taken=False,
            error="" if online else str(health.get("note") or "offline"),
            capabilities=self.capabilities,
        )

    async def wait_until_presented(self, *, timeout_seconds: float = 8.0) -> bool:
        return True

    async def wait_until_taken(self, *, timeout_seconds: float = 30.0) -> bool:
        raise TimeoutError("this printer has no taken sensor")

    async def cancel_or_recover(self) -> None:
        return None


def receipt_printer_for(adapter_id: str | None = None, printer_name: str | None = None) -> Any:
    key = (adapter_id or "simulated_kiosk").strip().lower()
    if key in {"simulated", "simulated_kiosk", "kiosk", ""}:
        return SimulatedKioskPrinter()
    return HardwareReceiptPrinter(adapter_id=key, printer_name=printer_name)
