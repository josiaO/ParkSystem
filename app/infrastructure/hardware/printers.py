"""Printer adapters. Store a slip always; send ESC/POS to USB or LAN thermal, or file-only."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from app.config import settings


@dataclass
class ReceiptDocument:
    site_name: str
    plate: str
    entry_time: str
    entry_gate: str
    public_reference: str
    public_url: str
    payment_instructions: str
    body_text: str
    qr_payload: str
    qr_png: bytes = b""
    lines: list[str] = field(default_factory=list)


@dataclass
class PrintResult:
    ok: bool
    adapter_id: str
    status: str
    message: str
    simulated: bool = True
    path: str = ""


@runtime_checkable
class PrinterAdapter(Protocol):
    id: str

    async def health(self) -> dict[str, Any]: ...

    async def print_receipt(self, document: ReceiptDocument) -> PrintResult: ...


def store_slip_files(document: ReceiptDocument) -> str:
    folder = settings.media_dir / "receipts"
    folder.mkdir(parents=True, exist_ok=True)
    stem = document.public_reference or document.plate or "receipt"
    path = folder / f"{stem}.txt"
    path.write_text(document.body_text, encoding="utf-8")
    if document.qr_png.startswith(b"\x89PNG"):
        (folder / f"{stem}.png").write_bytes(document.qr_png)
    return str(path)


def escpos_bytes(document: ReceiptDocument) -> bytes:
    """Plain ESC/POS text ticket. QR URL is printed as text so any 58/80mm printer can cut it."""
    init = b"\x1b@"
    center = b"\x1ba\x01"
    left = b"\x1ba\x00"
    wide = b"\x1d!\x11"
    normal = b"\x1d!\x00"
    cut = b"\x1dV\x00"
    lines = [
        init,
        center,
        wide,
        (document.site_name or "SmartPark").encode("utf-8", "replace") + b"\n",
        normal,
        b"PARKING ENTRY\n",
        left,
        f"Plate: {document.plate}\n".encode("utf-8", "replace"),
        f"Entry: {document.entry_time}\n".encode("utf-8", "replace"),
        f"Gate: {document.entry_gate}\n".encode("utf-8", "replace"),
        f"Ref: {document.public_reference}\n\n".encode("utf-8", "replace"),
        (document.payment_instructions or "").encode("utf-8", "replace") + b"\n",
        (document.public_url or "").encode("utf-8", "replace") + b"\n\n",
        cut,
    ]
    return b"".join(lines)


def render_a4_png(document: ReceiptDocument) -> bytes:
    """A4 page at 150 dpi so a normal USB office printer can print it."""
    from PIL import Image, ImageDraw, ImageFont

    width, height = 1240, 1754
    page = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(page)
    try:
        title_font = ImageFont.truetype("arial.ttf", 48)
        body_font = ImageFont.truetype("arial.ttf", 32)
    except Exception:
        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
            body_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32)
        except Exception:
            title_font = ImageFont.load_default()
            body_font = title_font
    y = 80
    draw.text((80, y), document.site_name or "SmartPark", fill=(20, 30, 50), font=title_font)
    y += 70
    draw.text((80, y), "PARKING ENTRY", fill=(31, 94, 255), font=title_font)
    y += 90
    for line in (
        f"Plate: {document.plate}",
        f"Entry: {document.entry_time}",
        f"Gate: {document.entry_gate}",
        f"Reference: {document.public_reference}",
        "",
        document.payment_instructions or "",
        document.public_url or "",
    ):
        draw.text((80, y), line, fill=(23, 32, 51), font=body_font)
        y += 48
    if document.qr_png.startswith(b"\x89PNG"):
        try:
            qr = Image.open(BytesIO(document.qr_png)).convert("RGB")
            qr = qr.resize((360, 360))
            page.paste(qr, (80, min(y + 20, height - 420)))
        except Exception:
            pass
    buf = BytesIO()
    page.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _send_tcp(host: str, port: int, payload: bytes, timeout: float = 3.0) -> None:
    with socket.create_connection((host, int(port)), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(payload)


def _run(cmd: list[str], timeout: float = 12.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _is_usb_port(port: str) -> bool:
    p = (port or "").upper()
    return p.startswith("USB") or "USB" in p or p.startswith("DOT4") or p.startswith("WSD")


def list_system_printers() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if os.name == "nt":
        rows.extend(_windows_printers())
    else:
        rows.extend(_cups_printers())
    seen = set()
    unique = []
    for row in rows:
        name = str(row.get("name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        unique.append(row)
    unique.sort(key=lambda r: (not r.get("is_default"), not r.get("is_usb"), str(r.get("name") or "").lower()))
    return unique


def _windows_printers() -> list[dict[str, Any]]:
    try:
        import win32print  # type: ignore
    except Exception:
        win32print = None
    rows: list[dict[str, Any]] = []
    if win32print is not None:
        try:
            default = ""
            try:
                default = win32print.GetDefaultPrinter() or ""
            except Exception:
                default = ""
            flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            for item in win32print.EnumPrinters(flags):
                name = item[2]
                port = ""
                try:
                    info = win32print.GetPrinter(win32print.OpenPrinter(name), 2)
                    port = str(info.get("pPortName") or "")
                except Exception:
                    port = ""
                rows.append({
                    "name": name,
                    "port": port,
                    "is_usb": _is_usb_port(port) or _is_usb_port(name),
                    "is_default": name == default,
                    "offline": False,
                })
            if rows:
                return rows
        except Exception:
            rows = []
    script = (
        "Get-CimInstance Win32_Printer | "
        "Select-Object Name,PortName,Default,WorkOffline | ConvertTo-Json -Compress"
    )
    try:
        proc = _run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], timeout=8)
        text = (proc.stdout or "").strip()
        if not text:
            return rows
        data = json.loads(text)
        if isinstance(data, dict):
            data = [data]
        for item in data or []:
            name = str(item.get("Name") or "").strip()
            port = str(item.get("PortName") or "")
            if not name:
                continue
            rows.append({
                "name": name,
                "port": port,
                "is_usb": _is_usb_port(port) or _is_usb_port(name),
                "is_default": bool(item.get("Default")),
                "offline": bool(item.get("WorkOffline")),
            })
    except Exception:
        return rows
    return rows


def _cups_printers() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    default = ""
    try:
        dest = _run(["lpstat", "-d"], timeout=4)
        for part in (dest.stdout or "").split(":"):
            default = part.strip()
    except Exception:
        default = ""
    try:
        proc = _run(["lpstat", "-p"], timeout=4)
        for line in (proc.stdout or "").splitlines():
            bits = line.split()
            if len(bits) >= 2 and bits[0] == "printer":
                name = bits[1]
                rows.append({
                    "name": name,
                    "port": "usb" if "usb" in line.lower() else "",
                    "is_usb": "usb" in line.lower(),
                    "is_default": name == default,
                    "offline": "disabled" in line.lower() or "paused" in line.lower(),
                })
    except Exception:
        pass
    return rows


def send_escpos_to_system_printer(printer_name: str, payload: bytes) -> None:
    """Send raw ESC/POS bytes to a USB or shared Windows/CUPS printer."""
    name = (printer_name or "").strip()
    if not name:
        raise ValueError("printer name required")
    if not payload:
        raise ValueError("empty receipt payload")
    if os.name == "nt":
        _windows_raw_print(name, payload)
        return
    _cups_raw_print(name, payload)


def _windows_raw_print(printer_name: str, payload: bytes) -> None:
    try:
        import win32print  # type: ignore
    except Exception:
        win32print = None
    if win32print is not None:
        handle = win32print.OpenPrinter(printer_name)
        try:
            win32print.StartDocPrinter(handle, 1, ("SmartPark Receipt", None, "RAW"))
            try:
                win32print.StartPagePrinter(handle)
                try:
                    win32print.WritePrinter(handle, payload)
                finally:
                    win32print.EndPagePrinter(handle)
            finally:
                win32print.EndDocPrinter(handle)
        finally:
            win32print.ClosePrinter(handle)
        return
    import base64
    import ctypes
    from ctypes import wintypes

    encoded = base64.b64encode(payload).decode("ascii")
    quoted_name = printer_name.replace("'", "''")
    script = (
        f"$name = '{quoted_name}'; $bytes = [Convert]::FromBase64String('{encoded}'); "
        "Add-Type @'\n"
        "using System; using System.Runtime.InteropServices;\n"
        "public class RawPrinter {\n"
        " [DllImport(\"winspool.drv\", CharSet=CharSet.Unicode, SetLastError=true)]\n"
        " public static extern bool OpenPrinter(string p, out IntPtr h, IntPtr d);\n"
        " [DllImport(\"winspool.drv\", SetLastError=true)] public static extern bool ClosePrinter(IntPtr h);\n"
        " [DllImport(\"winspool.drv\", CharSet=CharSet.Unicode, SetLastError=true)]\n"
        " public static extern bool StartDocPrinter(IntPtr h, int lvl, [In] ref DOCINFO di);\n"
        " [DllImport(\"winspool.drv\", SetLastError=true)] public static extern bool EndDocPrinter(IntPtr h);\n"
        " [DllImport(\"winspool.drv\", SetLastError=true)] public static extern bool StartPagePrinter(IntPtr h);\n"
        " [DllImport(\"winspool.drv\", SetLastError=true)] public static extern bool EndPagePrinter(IntPtr h);\n"
        " [DllImport(\"winspool.drv\", SetLastError=true)]\n"
        " public static extern bool WritePrinter(IntPtr h, byte[] b, int n, out int w);\n"
        " [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]\n"
        " public struct DOCINFO { public string DocName; public string OutputFile; public string DataType; }\n"
        "}\n"
        "'@; "
        "$h = [IntPtr]::Zero; if (-not [RawPrinter]::OpenPrinter($name, [ref]$h, [IntPtr]::Zero)) { throw 'OpenPrinter failed' }; "
        "try { "
        "$di = New-Object RawPrinter+DOCINFO; $di.DocName='SmartPark Receipt'; $di.DataType='RAW'; "
        "if (-not [RawPrinter]::StartDocPrinter($h, 1, [ref]$di)) { throw 'StartDocPrinter failed' }; "
        "try { "
        "if (-not [RawPrinter]::StartPagePrinter($h)) { throw 'StartPagePrinter failed' }; "
        "try { $written = 0; if (-not [RawPrinter]::WritePrinter($h, $bytes, $bytes.Length, [ref]$written)) { throw 'WritePrinter failed' } } "
        "finally { [void][RawPrinter]::EndPagePrinter($h) } "
        "} finally { [void][RawPrinter]::EndDocPrinter($h) } "
        "} finally { [void][RawPrinter]::ClosePrinter($h) }"
    )
    proc = _run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], timeout=20)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "Windows raw print failed").strip()[:300])


def _cups_raw_print(printer_name: str, payload: bytes) -> None:
    cmd = ["lp", "-d", printer_name, "-o", "raw"]
    proc = subprocess.run(cmd, input=payload, capture_output=True, timeout=15, check=False)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "lp raw failed").decode("utf-8", "replace").strip()[:300])


def send_to_system_printer(path: str, printer_name: str) -> None:
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(path)
    name = (printer_name or "").strip()
    if os.name == "nt":
        _windows_print(target, name)
        return
    cmd = ["lp"]
    if name:
        cmd.extend(["-d", name])
    cmd.extend(["-o", "media=A4", "-o", "fit-to-page", str(target)])
    proc = _run(cmd, timeout=15)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "lp failed").strip()[:300])


def _windows_print(path: Path, printer_name: str) -> None:
    name = (printer_name or "").strip()
    if name:
        quoted_file = str(path).replace("'", "''")
        quoted_name = name.replace("'", "''")
        script = (
            f"$p = '{quoted_file}'; $n = '{quoted_name}'; "
            "try { Start-Process -FilePath $p -Verb PrintTo -ArgumentList $n -WindowStyle Hidden -Wait } "
            "catch { Get-Content -Raw $p | Out-Printer -Name $n }"
        )
        proc = _run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], timeout=20)
        if proc.returncode == 0:
            return
        paint = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "mspaint.exe"
        if paint.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}:
            painted = _run([str(paint), "/pt", str(path), name], timeout=20)
            if painted.returncode == 0:
                return
        raise RuntimeError((proc.stderr or proc.stdout or "Windows print failed").strip()[:300])
    os.startfile(str(path), "print")  # type: ignore[attr-defined]


class SimulatedPrinterAdapter:
    """Stores the slip as a .txt/.png ready for any printer. Used when no paper printer is set."""

    id = "simulated"

    async def health(self) -> dict[str, Any]:
        printers = list_system_printers()
        return {
            "ok": True,
            "adapter_id": self.id,
            "configured": True,
            "printers": printers,
            "note": "Receipts are stored as text files. Choose a thermal receipt printer in Settings to print tickets.",
        }

    async def print_receipt(self, document: ReceiptDocument) -> PrintResult:
        path = store_slip_files(document)
        return PrintResult(
            ok=True,
            adapter_id=self.id,
            status="READY",
            message=f"Receipt ready for printing ({path})",
            simulated=True,
            path=path,
        )


class EscPosPrinterAdapter:
    id = "escpos"

    async def health(self) -> dict[str, Any]:
        host = (settings.printer_escpos_host or "").strip()
        return {
            "ok": bool(host),
            "adapter_id": self.id,
            "configured": bool(host),
            "host": host,
            "port": settings.printer_escpos_port,
            "printers": list_system_printers(),
            "note": "Set SMARTPARK_PRINTER_ESCPOS_HOST and SMARTPARK_PRINTER_ADAPTER=escpos for a LAN printer.",
        }

    async def print_receipt(self, document: ReceiptDocument) -> PrintResult:
        path = store_slip_files(document)
        host = (settings.printer_escpos_host or "").strip()
        if not host:
            return PrintResult(
                ok=True,
                adapter_id=self.id,
                status="READY",
                message=f"Receipt stored at {path}. Set SMARTPARK_PRINTER_ESCPOS_HOST to send to paper.",
                simulated=True,
                path=path,
            )
        try:
            payload = escpos_bytes(document)
            await asyncio.wait_for(
                asyncio.to_thread(_send_tcp, host, settings.printer_escpos_port, payload, 3.0),
                timeout=3.5,
            )
            return PrintResult(
                ok=True,
                adapter_id=self.id,
                status="PRINTED",
                message=f"Sent to {host}:{settings.printer_escpos_port}",
                simulated=False,
                path=path,
            )
        except Exception as exc:
            return PrintResult(
                ok=True,
                adapter_id=self.id,
                status="READY",
                message=f"Receipt stored at {path}; printer send failed: {exc}",
                simulated=True,
                path=path,
            )


class SystemPrinterAdapter:
    """USB or shared thermal receipt printer selected in Settings (ESC/POS raw)."""

    id = "system"

    def __init__(self, printer_name: str = ""):
        self.printer_name = (printer_name or settings.printer_name or "").strip()

    async def health(self) -> dict[str, Any]:
        printers = list_system_printers()
        names = {row["name"] for row in printers}
        chosen = self.printer_name
        return {
            "ok": bool(chosen) and (not names or chosen in names),
            "adapter_id": self.id,
            "configured": bool(chosen),
            "printer_name": chosen,
            "printers": printers,
            "note": "Plug in a USB thermal receipt printer (58 mm or 80 mm), pick it in Settings, then entry prints and the gate opens.",
        }

    async def print_receipt(self, document: ReceiptDocument) -> PrintResult:
        path = store_slip_files(document)
        name = self.printer_name
        if not name:
            return PrintResult(
                ok=True,
                adapter_id=self.id,
                status="READY",
                message=f"Receipt stored at {path}. Select a thermal printer in Settings.",
                simulated=True,
                path=path,
            )
        payload = escpos_bytes(document)
        try:
            await asyncio.wait_for(
                asyncio.to_thread(send_escpos_to_system_printer, name, payload),
                timeout=12.0,
            )
            return PrintResult(
                ok=True,
                adapter_id=self.id,
                status="PRINTED",
                message=f"Printed on {name}",
                simulated=False,
                path=path,
            )
        except Exception as exc:
            return PrintResult(
                ok=True,
                adapter_id=self.id,
                status="READY",
                message=f"Receipt stored at {path}; printer send failed: {exc}",
                simulated=True,
                path=path,
            )


ADAPTERS: dict[str, PrinterAdapter] = {
    "simulated": SimulatedPrinterAdapter(),
    "escpos": EscPosPrinterAdapter(),
}


def printer_adapter(adapter_id: str | None = None, printer_name: str | None = None) -> PrinterAdapter:
    key = (adapter_id or settings.printer_adapter or "simulated").strip().lower()
    if key in {"system", "usb", "a4", "thermal"}:
        return SystemPrinterAdapter(printer_name or settings.printer_name)
    return ADAPTERS.get(key) or ADAPTERS["simulated"]
