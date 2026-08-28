from __future__ import annotations

import httpx

BASE="http://127.0.0.1:8760"


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except Exception:
        body = None
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, list):
        detail = "; ".join(str(item.get("msg") or item) for item in detail)
    if isinstance(detail, str) and detail.strip():
        return detail.strip()
    text = (response.text or "").strip()
    if text:
        return text[:400]
    return f"HTTP {response.status_code}"


class ApiError(RuntimeError):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code


def _check(response: httpx.Response) -> httpx.Response:
    if response.is_success:
        return response
    raise ApiError(response.status_code, _detail(response)) from None


class ApiClient:
    def __init__(self):
        self.token=""
        self.permissions:set[str]=set()
        self.username=""

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def login(self, username, password):
        r=_check(httpx.post(f"{BASE}/auth/login", json={"username":username,"password":password}, timeout=5))
        data=r.json()
        self.token=data["token"]; self.username=data["username"]; self.permissions=set(data["permissions"])
        return data

    def get(self, path, timeout=8):
        r=_check(httpx.get(BASE+path, headers=self._headers(), timeout=timeout)); return r.json()

    def get_bytes(self, path, timeout=8):
        r=_check(httpx.get(BASE+path, headers=self._headers(), timeout=timeout)); return r.content

    def post(self, path, payload=None, timeout=15):
        r=_check(httpx.post(BASE+path, json=payload or {}, headers=self._headers(), timeout=timeout)); return r.json()

    def post_file(self, path, files, data=None, timeout=30):
        r=_check(httpx.post(BASE+path, files=files, data=data or {}, headers=self._headers(), timeout=timeout))
        return r.json()

    def seed_site(self):
        """Add the four site cameras. Works even if the API is an older build without /cameras/seed-site."""
        try:
            return self.post("/cameras/seed-site")
        except ApiError as exc:
            if exc.status_code not in (404, 405):
                raise
        from app.services.site_cameras import KNOWN_SITE_CAMERAS, site_camera_defaults
        defaults = site_camera_defaults()
        created, skipped = [], []
        for row in KNOWN_SITE_CAMERAS:
            payload = {
                "name": row["name"],
                "ip_address": row["ip_address"],
                "sdk_port": defaults["sdk_port"],
                "username": defaults["username"],
                "password": defaults["password"],
                "lane_direction": row["lane_direction"],
                "controller_ip": row.get("controller_ip") or "",
                "display_ip": row.get("display_ip") or "",
            }
            try:
                created.append(self.post("/cameras", payload))
            except ApiError as err:
                if err.status_code == 409:
                    skipped.append({"ip_address": row["ip_address"], "reason": "already added"})
                else:
                    raise
        return {"created": created, "skipped": skipped, "cameras": self.get("/cameras")}

    def connect_all(self):
        """Connect cameras one by one so a slow/dead camera cannot abort the rest."""
        cameras = self.get("/cameras")
        results = []
        connected = 0
        skipped = 0
        for cam in cameras:
            if cam.get("enabled") is False:
                continue
            try:
                item = self.post(f"/cameras/{cam['id']}/sdk/connect", timeout=25)
            except Exception as exc:
                item = {
                    "id": cam.get("id"),
                    "name": cam.get("name"),
                    "status": "SDK_FAILED",
                    "last_error": str(exc),
                    "sdk_result": {"connected": False, "error": str(exc)},
                }
            results.append(item)
            if item.get("status") == "SDK_CONNECTED":
                connected += 1
            if (item.get("sdk_result") or {}).get("skipped"):
                skipped += 1
        return {
            "connected": connected,
            "attempted": len(results),
            "skipped": skipped,
            "results": results,
            "note": "Unreachable cameras are skipped after a short TCP probe.",
        }

    def patch(self, path, payload=None):
        r=_check(httpx.patch(BASE+path, json=payload or {}, headers=self._headers(), timeout=8)); return r.json()

    def delete(self, path):
        r=_check(httpx.delete(BASE+path, headers=self._headers(), timeout=8)); return r.json()

    def can(self, permission):
        return "*" in self.permissions or permission in self.permissions

api=ApiClient()
