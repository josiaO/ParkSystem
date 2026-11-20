"""Security hardening: public surfaces, receipts, sign-in throttling."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import PropertyMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import Base


@pytest.fixture()
def bootstrap_db(tmp_path):
    from app.api_main import ensure_roles
    from app.services import bootstrap

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with patch.object(Settings, "data_dir", new_callable=PropertyMock, return_value=tmp_path), \
         patch.object(bootstrap.settings, "bootstrap_password", ""):
        with Session() as db:
            ensure_roles(db)
        yield Session
    engine.dispose()


# 1.1 /auth/setup ---------------------------------------------------------

def test_setup_discloses_bootstrap_password_once_to_loopback(bootstrap_db):
    from app.services import bootstrap

    with bootstrap_db() as db:
        first = bootstrap.setup_status(db, local_request=True)
        assert first["password"] == bootstrap.effective_bootstrap_password()
        second = bootstrap.setup_status(db, local_request=True)
        assert second["password"] == ""
        assert str(bootstrap.bootstrap_password_path()) in second["hint"]


def test_setup_never_returns_usernames(bootstrap_db):
    from app.services import bootstrap

    with bootstrap_db() as db:
        for local in (True, False):
            assert "usernames" not in bootstrap.setup_status(db, local_request=local)


def test_setup_never_discloses_password_to_lan(bootstrap_db):
    from app.services import bootstrap

    with bootstrap_db() as db:
        remote = bootstrap.setup_status(db, local_request=False)
        assert remote["password"] == ""
        # A LAN request must not consume the one-time local disclosure.
        assert bootstrap.setup_status(db, local_request=True)["password"]


def test_setup_default_is_not_local(bootstrap_db):
    from app.services import bootstrap

    with bootstrap_db() as db:
        assert bootstrap.setup_status(db)["password"] == ""


def test_setup_does_not_disclose_after_first_run_window(bootstrap_db):
    from app.models import User
    from app.services import bootstrap

    with bootstrap_db() as db:
        bootstrap.ensure_bootstrap_admin(db)
        admin = db.scalar(select(User).where(User.username == bootstrap.settings.bootstrap_username))
        admin.created_at = admin.created_at - bootstrap.FIRST_RUN_WINDOW - timedelta(minutes=1)
        db.commit()
        assert bootstrap.setup_status(db, local_request=True)["password"] == ""


@pytest.mark.parametrize(
    ("client_host", "headers", "expected"),
    [
        ("127.0.0.1", {}, True),
        ("::1", {}, True),
        ("::ffff:127.0.0.1", {}, True),
        ("127.0.0.1", {"x-forwarded-for": "10.0.0.5"}, False),
        ("127.0.0.1", {"forwarded": "for=10.0.0.5"}, False),
        ("10.0.0.5", {}, False),
        ("testclient", {}, False),
        ("", {}, False),
    ],
)
def test_loopback_detection(client_host, headers, expected):
    from types import SimpleNamespace

    from app.api_main import _is_loopback_request

    request = SimpleNamespace(client=SimpleNamespace(host=client_host), headers=headers)
    assert _is_loopback_request(request) is expected


# 1.2 Default password strings ----------------------------------------------

@pytest.mark.parametrize("module_name", ["tools.field_acceptance_test", "tools.camera_lab"])
def test_tools_never_guess_default_passwords(module_name, tmp_path, monkeypatch):
    import importlib

    module = importlib.import_module(module_name)
    for name in ("SMARTPARK_PASSWORD", "SMARTPARK_BOOTSTRAP_PASSWORD", "PROGRAMDATA"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(module.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(module.sys.stdin, "isatty", lambda: False, raising=False)
    assert module.password_candidates("") == []
    monkeypatch.setenv("SMARTPARK_PASSWORD", "from-env-123")
    assert module.password_candidates("") == ["from-env-123"]


@pytest.mark.parametrize("module_name", ["tools.field_acceptance_test", "tools.camera_lab"])
def test_tools_prompt_when_interactive_and_nothing_configured(module_name, tmp_path, monkeypatch):
    import importlib

    module = importlib.import_module(module_name)
    for name in ("SMARTPARK_PASSWORD", "SMARTPARK_BOOTSTRAP_PASSWORD", "PROGRAMDATA"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(module.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(module.sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "typed-pass-123")
    assert module.password_candidates("") == ["typed-pass-123"]


def test_no_default_password_literals_in_scripts_or_tools():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    offenders = []
    for folder in ("tools", "scripts", "packaging"):
        for path in (root / folder).rglob("*"):
            if path.suffix in {".py", ".ps1", ".sh", ".bat", ".cmd"} and "SmartPark1!" in path.read_text(encoding="utf-8", errors="ignore"):
                offenders.append(str(path.relative_to(root)))
    assert offenders == []


# 1.3 Login throttling -----------------------------------------------------

class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _throttle():
    from app.services.login_throttle import LoginThrottle

    clock = _Clock()
    return LoginThrottle(clock=clock), clock


def test_throttle_allows_free_attempts_then_backs_off_and_locks():
    throttle, clock = _throttle()
    for _ in range(throttle.user_free_failures):
        assert throttle.check("10.0.0.5", "admin") == 0
        throttle.record_failure("10.0.0.5", "admin")
    wait = throttle.check("10.0.0.5", "admin")
    assert 0 < wait <= throttle.max_lockout_seconds
    throttle.record_failure("10.0.0.5", "admin")  # attempts while blocked are not even checked
    clock.now += wait + 0.01
    assert throttle.check("10.0.0.5", "admin") == 0
    throttle.record_failure("10.0.0.5", "admin")
    longer = throttle.check("10.0.0.5", "admin")
    assert longer > wait  # exponential backoff
    for _ in range(20):
        clock.now += throttle.check("10.0.0.5", "admin") + 0.01
        throttle.record_failure("10.0.0.5", "admin")
    assert throttle.check("10.0.0.5", "admin") <= throttle.max_lockout_seconds


def test_throttle_is_per_username_and_per_ip():
    throttle, _clock = _throttle()
    for _ in range(throttle.user_free_failures):
        throttle.record_failure("10.0.0.5", "admin")
    assert throttle.check("10.0.0.6", "admin") > 0       # same account, other PC
    assert throttle.check("10.0.0.5", "operator1") == 0  # same PC, other account
    throttle2, _ = _throttle()
    for i in range(throttle2.ip_free_failures):
        throttle2.record_failure("10.0.0.9", f"user{i}")  # spraying many accounts
    assert throttle2.check("10.0.0.9", "someone-else") > 0


def test_throttle_success_clears_account_and_failures_expire():
    throttle, clock = _throttle()
    for _ in range(throttle.user_free_failures - 1):
        throttle.record_failure("10.0.0.5", "Admin")
    throttle.record_success("10.0.0.5", "admin")  # usernames are case-insensitive
    throttle.record_failure("10.0.0.5", "admin")
    assert throttle.check("10.0.0.5", "admin") == 0
    for _ in range(throttle.user_free_failures):
        throttle.record_failure("10.0.0.7", "kiosk")
    clock.now += throttle.window_seconds + throttle.max_lockout_seconds + 1
    assert throttle.check("10.0.0.7", "kiosk") == 0


def _login_client(tmp_path):
    from app.api_main import app, ensure_roles
    from app.db import get_db
    from app.models import Role, User, UserRole
    from app.security import hash_password

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as db:
        ensure_roles(db)
        user = User(username="operator1", full_name="Op", password_hash=hash_password("right-password-1"))
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_id=db.scalar(select(Role).where(Role.name == "Operator")).id))
        db.commit()

    def override():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override
    return TestClient(app, client=("10.0.0.50", 40000)), engine


@pytest.mark.parametrize("endpoint", ["/auth/login", "/auth/token"])
def test_login_endpoints_are_throttled(endpoint, tmp_path):
    from app.api_main import app
    from app.services import login_throttle

    login_throttle.reset()
    client, engine = _login_client(tmp_path)

    def attempt(password):
        if endpoint == "/auth/login":
            return client.post(endpoint, json={"username": "operator1", "password": password})
        return client.post(endpoint, data={"username": "operator1", "password": password})

    try:
        for _ in range(login_throttle.throttle().user_free_failures):
            assert attempt("wrong").status_code == 401
        blocked = attempt("right-password-1")  # even the right password waits
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) >= 1
    finally:
        login_throttle.reset()
        client.close()
        app.dependency_overrides.clear()
        engine.dispose()


# 1.4 Public payment surface ------------------------------------------------

def _prompt_guard():
    from app.services.payment_prompt_guard import PaymentPromptGuard

    clock = _Clock()
    return PaymentPromptGuard(clock=clock), clock


def test_phone_cooldown_between_prompts_and_hourly_cap():
    from app.services.payment_prompt_guard import PaymentPromptCooldown

    guard, clock = _prompt_guard()
    guard.claim("0712 345 678", session_id=1)
    with pytest.raises(PaymentPromptCooldown) as exc:
        guard.claim("+255712345678", session_id=2)  # same number, other format/session
    assert 0 < exc.value.retry_after <= guard.phone_interval_seconds
    for session_id in range(3, 3 + guard.phone_max_per_hour - 1):
        clock.now += guard.phone_interval_seconds + 1
        guard.claim("0712345678", session_id=session_id)
    clock.now += guard.phone_interval_seconds + 1
    with pytest.raises(PaymentPromptCooldown):
        guard.claim("0712345678", session_id=99)
    clock.now += 3600
    guard.claim("0712345678", session_id=100)


def test_one_receipt_cannot_cycle_through_phone_numbers():
    from app.services.payment_prompt_guard import PaymentPromptCooldown

    guard, clock = _prompt_guard()
    for i in range(guard.session_max_per_hour):
        guard.claim(f"07123456{i:02d}", session_id=7)
        clock.now += 1
    with pytest.raises(PaymentPromptCooldown):
        guard.claim("0719999999", session_id=7)


def test_prompt_guard_never_keeps_raw_phone_numbers():
    guard, _clock = _prompt_guard()
    guard.claim("0712345678", session_id=1)
    assert "712345678" not in repr(guard._phones)


def test_invalid_phone_is_rejected_before_any_prompt():
    guard, _clock = _prompt_guard()
    with pytest.raises(ValueError):
        guard.claim("not-a-number", session_id=1)


def test_public_payment_routes_are_rate_limited_on_the_lan_too():
    from app.services.public_ingress import PublicIngressGuard, reset_rate_limiter

    reset_rate_limiter()
    calls = []

    async def inner(scope, receive, send):
        calls.append(scope["path"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    guard = PublicIngressGuard(inner)
    statuses = []

    async def run():
        for _ in range(12):
            scope = {"type": "http", "path": "/api/public/payment-intents", "method": "POST",
                     "headers": [(b"host", b"192.168.1.10:8760")], "client": ("192.168.1.77", 5000)}
            sent = []

            async def send(message):
                sent.append(message)

            await guard(scope, None, send)
            statuses.append(sent[0]["status"])

    import asyncio

    with patch("app.services.public_ingress.settings.public_ingress_hosts", "pay.example.com"):
        asyncio.run(run())
    reset_rate_limiter()
    assert statuses[:10] == [200] * 10
    assert statuses[10:] == [429, 429]


def test_public_client_ip_is_not_taken_from_a_client_supplied_forwarded_header():
    from app.services.public_ingress import client_key

    tunnel = {"host": "pay.example.com", "x-forwarded-for": "1.2.3.4, 203.0.113.9"}
    assert client_key(tunnel, ("127.0.0.1", 1), public=True) == "203.0.113.9"
    assert client_key({**tunnel, "cf-connecting-ip": "198.51.100.7"}, ("127.0.0.1", 1), public=True) == "198.51.100.7"
    # On the LAN the TCP peer is the client; forwarded headers are ignored.
    assert client_key({"x-forwarded-for": "1.2.3.4"}, ("192.168.1.77", 1), public=False) == "192.168.1.77"


# 1.5 Tokens in query strings -------------------------------------------------

@pytest.fixture()
def api_client(tmp_path):
    from app.api_main import app, ensure_roles
    from app.db import get_db
    from app.models import Role, User, UserRole
    from app.security import hash_password

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as db:
        ensure_roles(db)
        user = User(username="viewer", full_name="V", password_hash=hash_password("viewer-pass-1"))
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_id=db.scalar(select(Role).where(Role.name == "Admin")).id))
        db.commit()

    def override():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override
    with patch("app.security.short_session", Session), \
         patch.object(Settings, "data_dir", new_callable=PropertyMock, return_value=tmp_path):
        client = TestClient(app)
        token = client.post("/auth/login", json={"username": "viewer", "password": "viewer-pass-1"}).json()["token"]
        yield client, token, Session
        client.close()
    app.dependency_overrides.clear()
    engine.dispose()


def test_session_token_in_query_is_refused_on_ordinary_routes(api_client):
    client, token, _ = api_client
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert client.get(f"/auth/me?access_token={token}").status_code == 401
    assert client.get(f"/users?access_token={token}").status_code == 401


def test_media_routes_still_accept_query_tokens(api_client):
    client, token, _ = api_client
    # 404 = authenticated (the file does not exist); 401 = refused.
    assert client.get("/media/snapshots/missing.jpg").status_code == 401
    assert client.get(f"/media/snapshots/missing.jpg?access_token={token}").status_code == 404


def test_short_lived_media_token(api_client):
    client, token, _ = api_client
    issued = client.post("/auth/media-token", headers={"Authorization": f"Bearer {token}"})
    assert issued.status_code == 200, issued.text
    media = issued.json()["media_token"]
    assert 0 < issued.json()["expires_in"] <= 15 * 60
    assert media != token and token not in media
    assert client.get(f"/media/snapshots/missing.jpg?media_token={media}").status_code == 404
    # A media token is not a session token anywhere else.
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {media}"}).status_code == 401
    assert client.get(f"/auth/me?media_token={media}").status_code == 401
    assert client.post("/auth/media-token").status_code == 401


def test_media_token_expires_is_bound_to_session_and_tamper_proof(api_client):
    from app import security

    client, token, _ = api_client
    media = client.post("/auth/media-token", headers={"Authorization": f"Bearer {token}"}).json()["media_token"]
    head, sig = media.rsplit(".", 1)
    forged = head + "." + ("A" if sig[0] != "A" else "B") + sig[1:]
    assert client.get(f"/media/snapshots/missing.jpg?media_token={forged}").status_code == 401
    with patch.object(security.time, "time", return_value=security.time.time() + security.MEDIA_TOKEN_TTL_SECONDS + 5):
        assert client.get(f"/media/snapshots/missing.jpg?media_token={media}").status_code == 401
    client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert client.get(f"/media/snapshots/missing.jpg?media_token={media}").status_code == 401


# 1.6 Secrets backend ---------------------------------------------------------

def test_plaintext_secrets_backend_warns_loudly(caplog):
    from app.infrastructure import secrets as secret_mod

    secret_mod._warned_plaintext = False
    with patch.object(secret_mod.settings, "secrets_backend", "db"), patch("platform.system", return_value="Linux"), \
         caplog.at_level("WARNING", logger="smartpark"):
        secret_mod.configured_backend()
        secret_mod.configured_backend()
    warnings = [r for r in caplog.records if "plaintext" in r.getMessage().lower()]
    assert len(warnings) == 1  # loud, but once per process


def test_secrets_health_reports_plaintext_backend():
    from app.infrastructure import secrets as secret_mod

    with patch.object(secret_mod.settings, "secrets_backend", "db"), patch("platform.system", return_value="Linux"):
        secret_mod.set_secret_store(None)
        try:
            info = secret_mod.describe()
        finally:
            secret_mod.set_secret_store(None)
    assert info["plaintext"] is True
    assert info["warning"]


# 1.7 Camera HTTPS verification ----------------------------------------------

def _capture_clients(monkeypatch, module, *, open_ports):
    created = []

    class _Client:
        def __init__(self, **kwargs):
            created.append(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, auth=None):
            raise RuntimeError("offline")

    async def tcp_open(ip, port, timeout=0.0):
        return port in open_ports

    monkeypatch.setattr(module.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(module, "tcp_open", tcp_open)
    return created


@pytest.mark.parametrize(("opt_in", "expected_verify"), [(False, True), (True, False)])
def test_camera_https_verification_is_on_unless_the_camera_opts_out(monkeypatch, opt_in, expected_verify):
    import asyncio

    from app.services import http_snapshot

    created = _capture_clients(monkeypatch, http_snapshot, open_ports={443})
    asyncio.run(http_snapshot.grab_http_snapshot("10.0.0.9", "admin", "pw", allow_insecure_tls=opt_in))
    # Exactly one TLS client is made (port 443); plain-HTTP clients carry no verify flag.
    assert [c["verify"] for c in created if "verify" in c] == [expected_verify]
    assert all(c.get("follow_redirects") is False for c in created)


def test_camera_https_opt_in_is_looked_up_per_camera_when_not_passed(monkeypatch):
    import asyncio

    from app.services import http_snapshot

    created = _capture_clients(monkeypatch, http_snapshot, open_ports={443})
    monkeypatch.setattr(http_snapshot, "camera_allows_insecure_tls", lambda ip: ip == "10.0.0.7")
    asyncio.run(http_snapshot.grab_http_snapshot("10.0.0.7", "admin", "pw"))
    asyncio.run(http_snapshot.grab_http_snapshot("10.0.0.8", "admin", "pw"))
    assert [c["verify"] for c in created if "verify" in c] == [False, True]


def test_camera_tls_opt_in_is_a_saved_camera_setting(api_client):
    client, token, Session = api_client
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post("/cameras", headers=headers, json={
        "name": "Exit B", "ip_address": "10.0.0.7", "adapter_id": "rtsp", "password": "cam-pass-123",
    })
    assert created.status_code == 200, created.text
    assert created.json()["allow_insecure_tls"] is False
    updated = client.patch(f"/cameras/{created.json()['id']}", headers=headers, json={"allow_insecure_tls": True})
    assert updated.status_code == 200, updated.text
    assert updated.json()["allow_insecure_tls"] is True
    from app.services import http_snapshot

    with patch("app.services.http_snapshot.short_session", Session):
        assert http_snapshot.camera_allows_insecure_tls("10.0.0.7") is True
        assert http_snapshot.camera_allows_insecure_tls("10.0.0.99") is False


# 1.8 Public receipt page ------------------------------------------------------

def test_receipt_tokens_are_256_bit():
    import base64

    from app.domain.receipt_engine import new_public_token

    token = new_public_token()
    assert len(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))) * 8 >= 256


@pytest.fixture()
def receipt_with_photo(api_client, tmp_path):
    from io import BytesIO

    from PIL import Image

    from app.models import Camera, ParkingSession, VehicleCapture

    client, token, Session = api_client
    media = tmp_path / "media"
    (media / "snapshots").mkdir(parents=True)
    (media / "crops").mkdir(parents=True)
    picture = Image.new("RGB", (64, 48))
    for x in range(64):
        for y in range(48):
            picture.putpixel((x, y), (255, 255, 255) if (x // 4 + y // 4) % 2 else (0, 0, 0))
    buffer = BytesIO()
    picture.save(buffer, "JPEG", quality=95)
    original = buffer.getvalue()
    (media / "snapshots" / "entry.jpg").write_bytes(original)
    (media / "crops" / "entry.jpg").write_bytes(original)
    with Session() as db:
        from app.services.modules import apply_profile

        apply_profile(db, "PARKING_PRO")  # enables the public receipt pages
        camera = Camera(name="Entry A", ip_address="10.0.0.21", adapter_id="rtsp", lane_direction="ENTRY")
        db.add(camera)
        db.flush()
        session = ParkingSession(plate="T123ABC", public_token="tok-" + "x" * 40, status="ACTIVE",
                                 camera_id=camera.id, entry_event_id="evt-1", visit_id="visit-1")
        db.add(session)
        db.flush()
        db.add(VehicleCapture(plate="T123ABC", camera_id=camera.id, snapshot_path="snapshots/entry.jpg",
                              crop_path="crops/entry.jpg", event_id="evt-1", visit_id="visit-1",
                              lane_direction="ENTRY"))
        db.commit()
        public = session.public_token
    with patch.object(Settings, "media_dir", new_callable=PropertyMock, return_value=media):
        yield client, token, public, original


def _receipt_status(client, public):
    response = client.get(f"/p/{public}/status")
    assert response.status_code == 200, response.text
    return response.json()


def test_public_receipt_hides_the_entry_photo_by_default(receipt_with_photo):
    client, token, public, _original = receipt_with_photo
    body = _receipt_status(client, public)
    assert body["snapshot_url"] is None and body["crop_url"] is None
    assert body["plate"] == "T123ABC"
    assert client.get(f"/p/{public}/snapshot.jpg").status_code == 404
    assert client.get(f"/p/{public}/crop.jpg").status_code == 404
    assert "/snapshot.jpg" not in client.get(f"/p/{public}").text


def test_operators_still_see_the_photo_when_public_photos_are_off(receipt_with_photo):
    client, token, public, original = receipt_with_photo
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get(f"/p/{public}/snapshot.jpg", headers=headers).content == original
    media = client.post("/auth/media-token", headers=headers).json()["media_token"]
    assert client.get(f"/p/{public}/crop.jpg?media_token={media}").content == original


def test_public_receipt_can_show_a_blurred_photo(receipt_with_photo):
    client, _token, public, original = receipt_with_photo
    with patch("app.services.receipt_privacy.settings.public_receipt_photo", "blurred"):
        body = _receipt_status(client, public)
        assert body["snapshot_url"] and body["crop_url"] is None
        blurred = client.get(f"/p/{public}/snapshot.jpg")
        assert blurred.status_code == 200 and blurred.content[:2] == b"\xff\xd8"
        assert blurred.content != original
        assert client.get(f"/p/{public}/crop.jpg").status_code == 404
    from io import BytesIO

    from PIL import Image, ImageStat

    sharp = ImageStat.Stat(Image.open(BytesIO(original)).convert("L")).stddev[0]
    soft = ImageStat.Stat(Image.open(BytesIO(blurred.content)).convert("L")).stddev[0]
    assert soft < sharp / 2  # the checkerboard detail is gone


def test_public_receipt_full_photo_is_an_explicit_opt_in(receipt_with_photo):
    client, _token, public, original = receipt_with_photo
    with patch("app.services.receipt_privacy.settings.public_receipt_photo", "full"):
        assert _receipt_status(client, public)["snapshot_url"]
        assert client.get(f"/p/{public}/snapshot.jpg").content == original


# Phase 2.3 Kiosk device credential ------------------------------------------

def _admin_headers(client, token):
    return {"Authorization": f"Bearer {token}"}


def test_kiosk_device_credential_signs_in_as_a_kiosk_operator(api_client):
    client, token, _Session = api_client
    created = client.post("/kiosk-devices", headers=_admin_headers(client, token), json={"name": "Exit B kiosk"})
    assert created.status_code == 200, created.text
    device = created.json()
    assert device["device_id"].startswith("kiosk-") and len(device["credential"]) >= 40
    listed = client.get("/kiosk-devices", headers=_admin_headers(client, token)).json()
    assert [row["device_id"] for row in listed] == [device["device_id"]]
    assert "credential" not in listed[0] and "credential_hash" not in listed[0]

    signed = client.post("/kiosk/auth", json={"device_id": device["device_id"], "credential": device["credential"]})
    assert signed.status_code == 200, signed.text
    kiosk_headers = {"Authorization": f"Bearer {signed.json()['token']}"}
    assert "kiosk.use" in signed.json()["permissions"]
    assert "users.manage" not in signed.json()["permissions"]
    assert client.get("/auth/me", headers=kiosk_headers).status_code == 200
    assert client.get("/users", headers=kiosk_headers).status_code == 403


def test_kiosk_device_sees_only_the_visit_it_looks_up(api_client):
    """Spec 8B: payment history by permission. A kiosk may be driver-facing."""
    from datetime import datetime, timedelta, timezone

    from app.models import ParkingSession

    client, token, Session = api_client
    with Session() as db:
        for plate, tok in (("T111AAA", "tok-mine"), ("T222BBB", "tok-other")):
            db.add(ParkingSession(plate=plate, status="CLOSED", currency="TZS", amount_due=1000, amount_paid=0,
                                  public_token=tok, entry_time=datetime.now(timezone.utc) - timedelta(hours=1)))
        db.commit()
    device = client.post("/kiosk-devices", headers=_admin_headers(client, token), json={"name": "Pay station"}).json()
    signed = client.post("/kiosk/auth", json={"device_id": device["device_id"], "credential": device["credential"]})
    kiosk = {"Authorization": f"Bearer {signed.json()['token']}"}
    assert set(signed.json()["permissions"]) == {"kiosk.use", "payments.create"}

    # No browsing other drivers' visits, payments or the day's revenue.
    for path in ("/sessions", "/payments", "/dashboard"):
        assert client.get(path, headers=kiosk).status_code == 403, path
    # The visit on the receipt in front of the kiosk is still found and payable.
    found = client.get("/sessions/lookup?q=tok-mine", headers=kiosk)
    assert found.status_code == 200, found.text
    assert found.json()["plate"] == "T111AAA"
    paid = client.post("/p/tok-mine/kiosk-pay", headers=kiosk, json={"method": "KIOSK_CASH"})
    assert paid.status_code == 200, paid.text
    nav = client.get("/modules/navigation", headers=kiosk).json()["navigation"]
    pages = {row["page"] for row in nav}
    assert "payments" not in pages and "dashboard" not in pages

    # Staff keep their history views.
    admin = _admin_headers(client, token)
    assert client.get("/sessions", headers=admin).status_code == 200
    assert client.get("/payments", headers=admin).status_code == 200


def test_kiosk_service_account_cannot_sign_in_with_a_password(api_client):
    client, token, Session = api_client
    device = client.post("/kiosk-devices", headers=_admin_headers(client, token), json={"name": "K"}).json()
    from app.models import KioskDevice, User

    with Session() as db:
        row = db.scalar(select(KioskDevice).where(KioskDevice.device_id == device["device_id"]))
        username = db.get(User, row.user_id).username
    assert client.post("/auth/login", json={"username": username, "password": device["credential"]}).status_code == 401


def test_revoking_a_kiosk_device_ends_its_sessions_at_once(api_client):
    client, token, _Session = api_client
    device = client.post("/kiosk-devices", headers=_admin_headers(client, token), json={"name": "K"}).json()
    session_token = client.post("/kiosk/auth", json=device).json()["token"]
    kiosk_headers = {"Authorization": f"Bearer {session_token}"}
    revoked = client.post(f"/kiosk-devices/{device['id']}/revoke", headers=_admin_headers(client, token))
    assert revoked.status_code == 200, revoked.text
    assert client.get("/auth/me", headers=kiosk_headers).status_code in (401, 403)
    assert client.post("/kiosk/auth", json=device).status_code == 401


def test_kiosk_auth_rejects_wrong_credentials_and_is_throttled(api_client):
    client, token, _Session = api_client
    device = client.post("/kiosk-devices", headers=_admin_headers(client, token), json={"name": "K"}).json()
    codes = [client.post("/kiosk/auth", json={"device_id": device["device_id"], "credential": "wrong"}).status_code
             for _ in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429


def test_kiosk_sessions_outlast_a_shift():
    from app.services.kiosk_devices import KIOSK_SESSION_HOURS

    assert KIOSK_SESSION_HOURS >= 24


# Phase 2.5 near matches (API) -------------------------------------------------

def test_near_matches_route_lists_close_open_visits(api_client):
    from app.models import ParkingSession

    client, token, Session = api_client
    with Session() as db:
        db.add(ParkingSession(plate="T123ABC", public_token="tok-near-1", status="ACTIVE"))
        db.add(ParkingSession(plate="T123ABD", public_token="tok-near-2", status="CLOSED"))
        db.commit()
    res = client.get("/sessions/near-matches?plate=T123A8C", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200, res.text
    assert [row["plate"] for row in res.json()] == ["T123ABC"]  # closed visits are not offered
    assert client.get("/sessions/near-matches?plate=T123A8C").status_code == 401
