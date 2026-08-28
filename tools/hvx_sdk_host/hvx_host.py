from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import platform
import struct
import sys
from urllib.parse import parse_qs, urlparse

from hvx_sdk import HVXSDK, HVXSDKError, describe_rc

HOST="127.0.0.1"
PORT=8765


def resolve_vendor_dir() -> Path:
    env = os.environ.get("SMARTPARK_HVX_VENDOR_DIR")
    if env:
        return Path(env)
    here = Path(__file__).resolve().parent
    ocx = here.parent.parent / "OcxConfig"
    local = here / "vendor"
    for candidate in (ocx, local):
        if (candidate / "NetSDK.dll").exists():
            return candidate
    return ocx if ocx.exists() else local


VENDOR = resolve_vendor_dir()

sdk=None
startup_error=""
try:
    sdk=HVXSDK(VENDOR)
except Exception as exc:
    startup_error=str(exc)


def reply(handler, status, payload):
    body=json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type","application/json")
    handler.send_header("Content-Length",str(len(body)))
    handler.end_headers(); handler.wfile.write(body)


def reply_jpeg(handler, jpeg: bytes, status=200):
    handler.send_response(status)
    handler.send_header("Content-Type", "image/jpeg")
    handler.send_header("Content-Length", str(len(jpeg)))
    handler.end_headers()
    handler.wfile.write(jpeg)


class Handler(BaseHTTPRequestHandler):
    server_version="SmartParkHVXHost/0.1"
    def log_message(self, fmt, *args):
        sys.stdout.write("[hvx-host] "+fmt%args+"\n")
    def do_GET(self):
        parsed=urlparse(self.path)
        path=parsed.path
        query=parse_qs(parsed.query)
        if path == "/info":
            required = ["NetSDK.dll", "CommModule.dll", "PlaySdk.dll", "Log.dll", "RtspRecvSdk.dll", "DecodeSdk.dll"]
            files = {name: (VENDOR / name).exists() for name in required}
            return reply(self, 200, {
                "available": sdk is not None,
                "startup_error": startup_error,
                "python_bits": struct.calcsize("P") * 8,
                "platform": platform.platform(),
                "vendor_dir": str(VENDOR),
                "dll": "NetSDK.dll",
                "files": files,
                "missing": [name for name, present in files.items() if not present],
                "sdk_control_port_default": 30000,
                "timeout_unit": "seconds",
                "connect_sequence": [
                    "Net_Init",
                    "Net_AddCamera",
                    "Net_RegReportMessEx",
                    "Net_ConnCameraEx then Net_ConnCamera fallback",
                    "Net_QueryConnState",
                    "Net_RegOffLineClient",
                    "Net_RegImageRecvEx2 then Net_RegImageRecvEx",
                    "Net_StartVideo then Net_GetJpgBuffer",
                ],
            })
        if path == "/captures":
            if not sdk: return reply(self,503,{"error":startup_error})
            try:
                return reply(self,200,{"captures": sdk.last_captures()})
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        if path.startswith("/events/"):
            if not sdk: return reply(self,503,{"error":startup_error})
            try:
                handle=int(path.rsplit("/",1)[-1])
                return reply(self,200,{"events": sdk.drain_events(handle)})
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        if path.startswith("/event-jpeg/"):
            if not sdk: return reply(self,503,{"error":startup_error})
            try:
                handle=int(path.rsplit("/",1)[-1])
                image_id=query.get("image_id") or query.get("id")
                jpeg=sdk.event_jpeg_for(handle, int(image_id[0]) if image_id else None)
                if not jpeg:
                    return reply(self,404,{"error":"no car snapshot yet"})
                return reply_jpeg(self, jpeg)
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        if path.startswith("/event-crop/"):
            if not sdk: return reply(self,503,{"error":startup_error})
            try:
                handle=int(path.rsplit("/",1)[-1])
                image_id=query.get("image_id") or query.get("id")
                jpeg=sdk.event_crop_for(handle, int(image_id[0]) if image_id else None)
                if not jpeg:
                    return reply(self,404,{"error":"no plate crop yet"})
                return reply_jpeg(self, jpeg)
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        if path.startswith("/live-jpeg/") or path.startswith("/capture-jpeg/"):
            if not sdk: return reply(self,503,{"error":startup_error})
            try:
                handle=int(path.rsplit("/",1)[-1])
                jpeg=sdk.live_jpeg_for(handle)
                if not jpeg:
                    return reply(self,404,{"error":"no live video frame yet — Net_StartVideo / Net_GetJpgBuffer"})
                return reply_jpeg(self, jpeg)
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        if path.startswith("/state/"):
            if not sdk: return reply(self,503,{"error":startup_error})
            try:
                handle=int(path.rsplit("/",1)[-1]); state=sdk.state(handle)
                payload = {"handle": handle}
                if isinstance(state, dict):
                    payload.update(state)
                else:
                    payload["state"] = state
                return reply(self,200,payload)
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        return reply(self,404,{"error":"not found"})
    def do_POST(self):
        path=urlparse(self.path).path
        length=int(self.headers.get("Content-Length","0") or 0)
        try: data=json.loads(self.rfile.read(length) or b"{}")
        except Exception: return reply(self,400,{"error":"invalid JSON"})
        if not sdk: return reply(self,503,{"error":startup_error})
        if path == "/discover":
            if not sdk: return reply(self,503,{"error":startup_error})
            try:
                wait=float(data.get("wait_seconds",2))
                return reply(self,200,sdk.discover(wait))
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        if path == "/connect":
            try:
                result=sdk.add_and_connect(str(data["ip"]),int(data.get("port",30000)),int(data.get("timeout",3)),str(data.get("username","")),str(data.get("password","")))
                return reply(self,200,result)
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        if path.startswith("/disconnect/"):
            try:
                handle=int(path.rsplit("/",1)[-1]); rc=sdk.disconnect(handle)
                return reply(self,200,{"ok":rc==0,"rc":rc})
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        if path.startswith("/snapshot-trigger/"):
            try:
                handle=int(path.rsplit("/",1)[-1]); rc=sdk.snapshot_trigger(handle)
                return reply(self,200,{
                    "ok": rc==0,
                    "rc": rc,
                    "jpeg_bytes": len(sdk.jpeg_for(handle)),
                    "note": "Net_ImageSnap queued. JPEG arrives on the image callback.",
                })
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        if path == "/gpio/write":
            try:
                handle=int(data["handle"]); index=int(data.get("index",0)); value=int(data.get("value",1))
                rc=sdk.write_gpio(handle, index, value)
                return reply(self,200,{"ok":rc==0,"rc":rc,"rc_name":describe_rc(rc),"handle":handle,"index":index,"value":value})
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        if path == "/gpio/pulse":
            try:
                handle=int(data["handle"]); index=int(data.get("index",0)); pulse_ms=int(data.get("pulse_ms",500))
                return reply(self,200,sdk.gpio_pulse(handle, index, pulse_ms))
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        if path == "/gate-setup":
            try:
                handle=int(data["handle"]); state=int(data.get("state",1)); index=int(data.get("index",0))
                rc=sdk.gate_setup(handle, state, index)
                return reply(self,200,{"ok":rc==0,"rc":rc,"rc_name":describe_rc(rc),"handle":handle,"state":state,"index":index})
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        return reply(self,404,{"error":"not found"})


if __name__ == "__main__":
    print(f"SmartPark HVX SDK Host — http://{HOST}:{PORT}")
    print(f"Python bitness: {struct.calcsize('P')*8}")
    if startup_error: print("SDK unavailable:",startup_error)
    server=ThreadingHTTPServer((HOST,PORT),Handler)
    try: server.serve_forever()
    finally:
        if sdk: sdk.close()
