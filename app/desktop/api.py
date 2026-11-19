from __future__ import annotations

import httpx
from app.deployment import central_server_base_url, desktop_base_url, local_node_runtime_url

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


def configure_desktop_base_url() -> str:
    """Point the desktop session at the correct local/central API plane."""
    return configure_base_url(desktop_base_url())


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
    """The Site Server answered and refused (``status_code`` >= 400).

    ``detail`` is the server's own reason; ``str(error)`` is the plain
    sentence an operator sees.
    """

    def __init__(self, status_code: int, detail: str):
        self.status_code = int(status_code or 0)
        self.detail = str(detail or "")
        super().__init__(refusal_message(self.status_code, self.detail))


class SiteServerUnreachable(ApiError):
    """No answer from the Site Server: network, server stopped, or too slow."""

    def __init__(self, base_url: str, reason: str = "", *, timed_out: bool = False):
        self.base_url = str(base_url or "")
        self.reason = str(reason or "")
        self.timed_out = bool(timed_out)
        self.status_code = 0
        self.detail = self.reason
        RuntimeError.__init__(self, unreachable_message(self.base_url, timed_out=self.timed_out))


def _host_of(base_url: str) -> str:
    try:
        return httpx.URL(base_url).host or base_url
    except Exception:
        return base_url


def unreachable_message(base_url: str, *, timed_out: bool = False) -> str:
    host = _host_of(base_url)
    where = f" at {host}" if host else ""
    if timed_out:
        return (f"The Site Server{where} did not answer in time. It may be busy or the network is slow; "
                "nothing was changed by this click unless it shows up after a refresh. Try again.")
    return (f"Can't reach the Site Server{where}. Check this computer's network cable or Wi-Fi "
            "and that the Site Server PC is switched on, then try again.")


def refusal_message(status_code: int, detail: str) -> str:
    """Plain words for 'the server answered no'."""
    detail = str(detail or "").strip()
    code = int(status_code or 0)
    if code == 401:
        return "Your sign-in has ended. Sign in again." + (f" ({detail})" if detail and "token" not in detail.lower() else "")
    if code == 403:
        return f"Not allowed for this account: {detail}" if detail else "Not allowed for this account."
    if code == 404:
        return detail or "Not found on the Site Server."
    if code in {400, 409, 422}:
        return f"The Site Server refused: {detail}" if detail else "The Site Server refused this request."
    if code == 429:
        return "Too many requests right now. Wait a moment and try again."
    if code >= 500:
        return (f"The Site Server had a problem and did not finish: {detail}" if detail
                else "The Site Server had a problem and did not finish. Try again; if it repeats, check the server log.")
    return detail or f"The Site Server answered HTTP {code}."


def friendly_error(exc: BaseException) -> str:
    """One sentence for any desktop failure: unreachable vs refused vs local."""
    if isinstance(exc, ApiError):
        return str(exc)
    if isinstance(exc, httpx.TimeoutException):
        return unreachable_message("", timed_out=True)
    if isinstance(exc, httpx.TransportError):
        return unreachable_message("")
    text = str(exc) or type(exc).__name__
    return text


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
        # Set when this desktop is an enrolled kiosk: (device_id, credential).
        self._device: tuple[str, str] | None = None

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
            return self.can("dashboard.view") or self.can("cameras.view")
        if page == "sessions":
            return self.can("sessions.view") or self.can("fees.view") or self.can("kiosk.use")
        if page == "payments":
            # A kiosk takes payment for one visit; it does not read history.
            return self.can("payments.view") or self.can("fees.view")
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

    def _login_post(self, path: str, payload: dict) -> httpx.Response:
        try:
            response = httpx.post(f"{self.base_url}{path}", json=payload, timeout=20, trust_env=False)
        except httpx.TimeoutException as exc:
            raise SiteServerUnreachable(self.base_url, str(exc), timed_out=True) from exc
        except httpx.TransportError as exc:
            raise SiteServerUnreachable(self.base_url, str(exc)) from exc
        if response.status_code == 401:
            # At sign-in a 401 is a wrong name/password, not an ended session.
            error = ApiError(401, _detail(response))
            error.args = (_detail(response) or "Wrong user name or password.",)
            raise error
        return _check(response)

    def login(self, username, password):
        # Argon2 verification and the first database connection can be slower
        # on a Windows field PC. Five seconds made a healthy node look like a
        # network failure during startup. Keep this bounded and do not retry
        # the POST, because retrying could create duplicate auth sessions.
        r=self._login_post("/auth/login", {"username":username,"password":password})
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

    def login_device(self, device_id: str, credential: str):
        """Sign an enrolled kiosk in with its device credential (no person's password)."""
        r=self._login_post("/kiosk/auth", {"device_id": device_id, "credential": credential})
        data=r.json()
        self.token=data["token"]; self.username=data["username"]; self.permissions=set(data["permissions"])
        self.navigation=list(data.get("navigation") or [])
        self.modules=dict(data.get("modules") or {})
        self._device=(str(device_id), str(credential))
        return data

    def _device_owner(self) -> "ApiClient":
        return self._token_owner or self

    def _reauthenticate_device(self) -> bool:
        """Kiosk sessions expire; a kiosk signs in again by itself mid-shift."""
        owner = self._device_owner()
        device = owner._device
        if not device:
            return False
        try:
            owner.login_device(*device)
        except Exception:
            return False
        self.token = owner.token
        return True

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            return getattr(httpx, method)(self.base_url+path, headers=self._headers(), trust_env=False, **kwargs)
        except httpx.TimeoutException as exc:
            raise SiteServerUnreachable(self.base_url, str(exc), timed_out=True) from exc
        except httpx.TransportError as exc:
            raise SiteServerUnreachable(self.base_url, str(exc)) from exc

    def _send(self, method: str, path: str, **kwargs) -> httpx.Response:
        response = self._request(method, path, **kwargs)
        # A 401 is returned before the server acts, so one retry is safe.
        if response.status_code == 401 and self._device_owner()._device and self._reauthenticate_device():
            response = self._request(method, path, **kwargs)
        return _check(response)

    def get(self, path, timeout=8):
        return self._send("get", path, timeout=timeout).json()

    def get_bytes(self, path, timeout=8):
        return self._send("get", path, timeout=timeout).content

    def post(self, path, payload=None, timeout=15):
        return self._send("post", path, json=payload or {}, timeout=timeout).json()

    def put(self, path, payload=None, timeout=15):
        return self._send("put", path, json=payload or {}, timeout=timeout).json()

    def post_file(self, path, files, data=None, timeout=30):
        return self._send("post", path, files=files, data=data or {}, timeout=timeout).json()

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
        return self._send("patch", path, json=payload or {}, timeout=8).json()

    def delete(self, path):
        return self._send("delete", path, timeout=8).json()

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
