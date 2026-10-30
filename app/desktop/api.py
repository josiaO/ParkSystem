from __future__ import annotations

import httpx
from app.deployment import central_server_base_url, local_node_runtime_url

BASE = central_server_base_url()
LOCAL_BASE = local_node_runtime_url()


def configure_base_url(value: str | None = None) -> str:
    """Refresh the central API endpoint after setup or a connection change."""
    global BASE
    BASE = str(value or central_server_base_url()).rstrip("/")
    configure_local_runtime_url()
    return BASE


def configure_local_runtime_url(value: str | None = None) -> str:
    """Refresh the local operational-plane endpoint after setup."""
    global LOCAL_BASE
    LOCAL_BASE = str(value if value is not None else local_node_runtime_url()).rstrip("/")
    return LOCAL_BASE


def stream_http_error(response: httpx.Response) -> str:
    """Describe an HTTP error from a streaming response without using .text.

    httpx raises ResponseNotRead if a ``client.stream()`` body is accessed via
    ``response.text`` before ``read()``. Desktop live.mjpeg used that path on
    409 and painted the exception onto the camera pane.
    """
    code = int(getattr(response, "status_code", 0) or 0)
    try:
        data = response.read()
    except Exception:
        return f"HTTP {code}"
    text = data.decode("utf-8", "replace").strip() if data else ""
    if not text:
        return f"HTTP {code}"
    if text.startswith("{"):
        try:
            import json
            body = json.loads(text)
            detail = body.get("detail") if isinstance(body, dict) else None
            if isinstance(detail, str) and detail.strip():
                return f"HTTP {code}: {detail.strip()[:240]}"
        except Exception:
            pass
    return f"HTTP {code}: {text[:240]}"


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
    try:
        text = (response.text or "").strip()
    except Exception:
        return f"HTTP {response.status_code}"
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
    """Central control-plane client.

    ``ApiClient`` remains the compatibility facade used by the desktop.  The
    local runtime is exposed explicitly through ``local_*`` methods so an
    Edge Node cannot accidentally send a hardware request to the Site Server
    or a central request to its local service.
    """
    def __init__(self, *, base_url: str | None = None, token_owner: "ApiClient | None" = None):
        self.token=""
        self.permissions:set[str]=set()
        self.username=""
        self.navigation:list[dict]=[]
        self.modules:dict={}
        self._base_override = str(base_url).rstrip("/") if base_url else None
        self._token_owner = token_owner

    @property
    def base_url(self) -> str:
        return self._base_override or BASE

    @property
    def local_base_url(self) -> str:
        return LOCAL_BASE

    @property
    def local_runtime_available(self) -> bool:
        return bool(self.local_base_url)

    def configure(self, value: str | None = None) -> str:
        if self._base_override is not None:
            self._base_override = str(value or self._base_override).rstrip("/")
            return self._base_override
        return configure_base_url(value)

    def local_client(self) -> "LocalNodeClient":
        """Return a client for local gate/runtime resources.

        It shares the central session token because a human session is still
        a human session; resource ownership is enforced by the API boundary.
        """
        client = LocalNodeClient(base_url=self.local_base_url, token_owner=self)
        client.token = self.token
        client.username = self.username
        client.permissions = set(self.permissions)
        client.navigation = list(self.navigation)
        client.modules = dict(self.modules)
        return client

    def runtime_client(self) -> "ApiClient":
        """Return the API plane that owns this computer's physical hardware.

        Edge Nodes use the central API for human/site control, but camera
        connect, disconnect, gate I/O, and local media must be sent to the
        Node's own Site Service.  On a Site Server both planes are the same;
        on an Operator Client there is no local runtime, so the central
        client remains the only available plane.
        """
        if self.local_runtime_available and self.local_base_url.rstrip("/") != self.base_url.rstrip("/"):
            return self.local_client()
        return self

    def _local(self) -> "ApiClient":
        if not self.local_runtime_available:
            raise ApiError(503, "This installation has no local node runtime")
        return self.local_client()

    def local_get(self, path, timeout=8):
        return self._local().get(path, timeout=timeout)

    def local_get_bytes(self, path, timeout=8):
        return self._local().get_bytes(path, timeout=timeout)

    def local_post(self, path, payload=None, timeout=15):
        return self._local().post(path, payload, timeout=timeout)

    def local_put(self, path, payload=None, timeout=15):
        return self._local().put(path, payload, timeout=timeout)

    def local_patch(self, path, payload=None):
        return self._local().patch(path, payload)

    def local_delete(self, path):
        return self._local().delete(path)

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def nav_page(self, page: str) -> bool:
        if self.navigation:
            return any(row.get("page") == page for row in self.navigation)
        # Fallback when API has no module navigation yet.
        perm_for = {
            "dashboard": "dashboard.view",
            "health": "hardware.view",
            "cameras": "cameras.view",
            "plates": "cameras.view",
            "sessions": "sessions.view",
            "vehicles": "subscribers.view",
            "payments": "payments.view",
            "fees": "fees.view",
            "reports": "dashboard.view",
            "gates": "gates.view",
            "users": "users.view",
            "hardware": "hardware.view",
            "sim": "simulation.run",
            "settings": "settings.view",
            "onboarding": "settings.manage",
        }
        perm = perm_for.get(page)
        if page == "dashboard":
            return True
        if page == "sessions":
            return self.can("sessions.view") or self.can("fees.view") or self.can("kiosk.use")
        if page == "payments":
            return self.can("payments.view") or self.can("fees.view") or self.can("kiosk.use")
        if page == "health":
            return self.can("hardware.view")
        return bool(perm and self.can(perm))

    def nav_label(self, page: str, default: str) -> str:
        friendly = {
            "Plate Engine": "Detections",
            "Simulation": "Testing & Simulation",
            "Tariffs": "Tariffs & Schedules",
            "Users": "Users & Roles",
        }
        label = default
        for row in self.navigation:
            if row.get("page") == page:
                label = str(row.get("label") or default)
                break
        return friendly.get(label, label)

    def login(self, username, password):
        r=_check(httpx.post(f"{self.base_url}/auth/login", json={"username":username,"password":password}, timeout=5))
        data=r.json()
        self.token=data["token"]; self.username=data["username"]; self.permissions=set(data["permissions"])
        self.navigation=list(data.get("navigation") or [])
        self.modules=dict(data.get("modules") or {})
        try:
            me=self.get("/auth/me")
            self.permissions=set(me.get("permissions") or data["permissions"])
            if me.get("navigation"):
                self.navigation=list(me.get("navigation") or [])
            if me.get("modules"):
                self.modules=dict(me.get("modules") or {})
            return me
        except Exception:
            return data

    def get(self, path, timeout=8):
        r=_check(httpx.get(self.base_url+path, headers=self._headers(), timeout=timeout)); return r.json()

    def get_bytes(self, path, timeout=8):
        r=_check(httpx.get(self.base_url+path, headers=self._headers(), timeout=timeout)); return r.content

    def post(self, path, payload=None, timeout=15):
        r=_check(httpx.post(self.base_url+path, json=payload or {}, headers=self._headers(), timeout=timeout)); return r.json()

    def put(self, path, payload=None, timeout=15):
        r=_check(httpx.put(self.base_url+path, json=payload or {}, headers=self._headers(), timeout=timeout)); return r.json()

    def post_file(self, path, files, data=None, timeout=30):
        r=_check(httpx.post(self.base_url+path, files=files, data=data or {}, headers=self._headers(), timeout=timeout))
        return r.json()

    def seed_site(self):
        """Explicit example import after administrator confirmation; no fallback creation."""
        return self.post("/cameras/seed-site", {"confirm_test_data": True})

    def connect_all(self):
        """Connect cameras one by one so a slow/dead camera cannot abort the rest."""
        runtime = self.runtime_client()
        cameras = runtime.get("/cameras")
        results = []
        connected = 0
        skipped = 0
        for cam in cameras:
            if cam.get("enabled") is False:
                continue
            try:
                item = runtime.post(f"/cameras/{cam['id']}/sdk/connect", timeout=25)
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
        r=_check(httpx.patch(self.base_url+path, json=payload or {}, headers=self._headers(), timeout=8)); return r.json()

    def delete(self, path):
        r=_check(httpx.delete(self.base_url+path, headers=self._headers(), timeout=8)); return r.json()

    def can(self, permission):
        return "*" in self.permissions or permission in self.permissions

class CentralApiClient(ApiClient):
    """Named central control-plane client for new desktop code."""


class LocalNodeClient(ApiClient):
    """Named local operational-plane client for Edge Node hardware."""


api = CentralApiClient()

# Explicit names for new callers. ``api`` remains the central client for
# backwards-compatible desktop pages.
central_api = api
local_node_api = api.local_client() if LOCAL_BASE else None
