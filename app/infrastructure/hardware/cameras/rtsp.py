"""Generic IP camera adapter (Dahua, Hikvision, and similar).

Connects over HTTP snapshot or RTSP JPEG. Never reports SDK login or native plates.
FastALPR is the plate engine for these cameras.
"""

from __future__ import annotations

from typing import Any

from app.domain.cameras import CameraLike
from app.services.frame_grab import grab_camera_frame
from app.services.http_snapshot import grab_http_snapshot
from app.services.rtsp_probe import probe, vendor_candidates


def _without_jpeg(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "jpeg"}


class RTSPCameraAdapter:
    id = "rtsp"

    async def capabilities(self, device: CameraLike) -> dict[str, Any]:
        return {
            "adapter_id": self.id,
            "sdk_login": False,
            "native_plates": False,
            "local_alpr": True,
            "live_jpeg": True,
            "rtsp_probe": True,
            "media_capabilities": ["RTSP", "SNAPSHOT", "HTTP_MJPEG", "MAIN_STREAM", "SUB_STREAM"],
            "note": (
                "Generic IP camera: HTTP snapshot or RTSP video. "
                "Not NetSDK login. Plates come from local FastALPR."
            ),
        }

    async def connect(self, device: CameraLike) -> dict[str, Any]:
        ip = device.ip_address
        username = device.username
        password = device.password_secret
        explicit = (device.rtsp_url or "").strip()
        http = await grab_http_snapshot(ip, username, password)
        if http.get("ok"):
            return {
                "connected": True,
                "adapter_id": self.id,
                "handle": None,
                "sdk_login": False,
                "native_plates": False,
                "local_alpr": True,
                "source": "http",
                "url": http.get("url") or "",
                "url_redacted": http.get("url_redacted") or "",
                "jpeg": http.get("jpeg"),
            }
        grabbed = await grab_camera_frame(ip, username, password, explicit)
        if grabbed.get("ok"):
            return {
                "connected": True,
                "adapter_id": self.id,
                "handle": None,
                "sdk_login": False,
                "native_plates": False,
                "local_alpr": True,
                "source": "rtsp",
                "url": grabbed.get("url") or explicit,
                "url_redacted": grabbed.get("url_redacted") or "",
                "jpeg": grabbed.get("jpeg"),
            }
        return {
            "connected": False,
            "adapter_id": self.id,
            "handle": None,
            "sdk_login": False,
            "native_plates": False,
            "local_alpr": True,
            "error": (
                grabbed.get("error") or http.get("error")
                or "No live JPEG. A browser login page is not enough — SmartPark needs a snapshot or RTSP. "
                "Install ffmpeg for RTSP, and check the camera username/password."
            ),
            "http": _without_jpeg(http),
            "rtsp": _without_jpeg(grabbed),
        }

    async def health(self, device: CameraLike) -> dict[str, Any]:
        url = (device.rtsp_url or "").strip()
        if not url:
            http = await grab_http_snapshot(device.ip_address, device.username, device.password_secret)
            return {
                "ok": bool(http.get("ok")),
                "adapter_id": self.id,
                "source": "http",
                **_without_jpeg(http),
            }
        result = await probe(url)
        return {"ok": result.ok, "adapter_id": self.id, **result.__dict__}

    async def snapshot(self, device: CameraLike) -> bytes:
        http = await grab_http_snapshot(device.ip_address, device.username, device.password_secret)
        if http.get("ok") and http.get("jpeg"):
            return http["jpeg"]
        grabbed = await grab_camera_frame(
            device.ip_address, device.username, device.password_secret, device.rtsp_url or "",
        )
        return grabbed.get("jpeg") or b""

    async def live_sources(self, device: CameraLike) -> list[dict[str, Any]]:
        urls = vendor_candidates(device.ip_address, device.username, device.password_secret, device.rtsp_url)
        return [{"kind": "rtsp", "url": url, "adapter_id": self.id} for url in urls]

    async def probe_candidates(self, device: CameraLike) -> list[dict[str, Any]]:
        rows = []
        for url in vendor_candidates(device.ip_address, device.username, device.password_secret, device.rtsp_url):
            result = await probe(url)
            rows.append(result.__dict__)
            if result.ok:
                break
        return rows
