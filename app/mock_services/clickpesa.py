"""Mock ClickPesa: the real USSD-push API shape, a phone simulator and faults.

Run:  python -m app.mock_services.clickpesa [--host 0.0.0.0] [--port 9100]

Point Zirp at it (or run ``python -m app.cli env preset mock-payments``):

    SMARTPARK_PAYMENTS_MOBILE_PROVIDER=clickpesa
    SMARTPARK_CLICKPESA_BASE_URL=http://127.0.0.1:9100/third-parties
    SMARTPARK_CLICKPESA_CLIENT_ID / _API_KEY / _CHECKSUM_KEY  (any test values)

The mock reads the same ``SMARTPARK_CLICKPESA_*`` settings as the Site
Service, so credentials and the webhook checksum key always match. Because
the base URL is a private host, the provider runs in MOCK mode: no live flag
is needed and no real money can move.

Pages:
  /phone   the driver's handset: approve, decline or ignore each USSD push
  /admin   fault switches (late, dropped, duplicated or forged webhooks,
           underpayment, provider outage) and a payment log
"""

from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import settings
from app.infrastructure.payments.clickpesa import payload_checksum

BASE = "/third-parties"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Faults:
    """Switches that rehearse what a real provider does on a bad day."""

    webhook_delay_seconds: float = 0.0
    drop_webhook: bool = False          # reconciliation must settle it via the status query
    duplicate_webhook: bool = False     # the ledger must credit once
    underpay_by: int = 0                # collectedAmount = amount - underpay_by (mismatch)
    bad_checksum: bool = False          # Zirp must reject the webhook
    provider_down: bool = False         # every API call returns 503
    auto_approve_seconds: float = 0.0   # >0: approve pushes automatically (load tests)


@dataclass
class Payment:
    id: str
    orderReference: str
    paymentReference: str
    phoneNumber: str
    amount: str
    currency: str
    status: str = "PROCESSING"
    collectedAmount: str = "0"
    collectedCurrency: str = "TZS"
    channel: str = "M-PESA"
    createdAt: str = field(default_factory=_now)
    updatedAt: str = field(default_factory=_now)
    webhooks: list[dict] = field(default_factory=list)

    def public(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("webhooks", None)
        data["clientId"] = settings.clickpesa_client_id
        return data


class MockClickPesa:
    def __init__(self, *, webhook_url: str, client_id: str, api_key: str, checksum_key: str,
                 webhook_poster=None, sync_webhooks: bool = False):
        """``webhook_poster(payload) -> str`` and ``sync_webhooks`` exist for tests."""
        self.webhook_url = webhook_url
        self.webhook_poster = webhook_poster
        self.sync_webhooks = sync_webhooks
        self.client_id = client_id
        self.api_key = api_key
        self.checksum_key = checksum_key
        self.tokens: set[str] = set()
        self.payments: dict[str, Payment] = {}
        self.faults = Faults()

    # -- auth -------------------------------------------------------------
    def check_token(self, authorization: str | None) -> None:
        if self.faults.provider_down:
            raise HTTPException(503, "Service temporarily unavailable (mock outage)")
        if not authorization or authorization not in self.tokens:
            raise HTTPException(401, "Unauthorized: invalid or expired token")

    def check_body(self, body: dict) -> None:
        for key in ("amount", "currency", "orderReference", "phoneNumber"):
            if not str(body.get(key) or "").strip():
                raise HTTPException(400, f"{key} is required")
        if self.checksum_key:
            expected = payload_checksum(self.checksum_key, body)
            if str(body.get("checksum") or "").lower() != expected:
                raise HTTPException(400, "Invalid checksum")

    # -- webhooks ---------------------------------------------------------
    def webhook_payload(self, payment: Payment, event: str) -> dict:
        data = payment.public()
        payload: dict[str, Any] = {"event": event, "data": data}
        payload["checksum"] = payload_checksum(self.checksum_key or "missing", payload)
        if self.faults.bad_checksum:
            payload["checksum"] = "0" * 64
        return payload

    async def send_webhook(self, payment: Payment, event: str) -> None:
        if self.faults.drop_webhook:
            payment.webhooks.append({"at": _now(), "event": event, "result": "dropped (fault)"})
            return
        if self.faults.webhook_delay_seconds > 0:
            await asyncio.sleep(self.faults.webhook_delay_seconds)
        copies = 2 if self.faults.duplicate_webhook else 1
        payload = self.webhook_payload(payment, event)
        if self.webhook_poster is not None:
            for _ in range(copies):
                result = await self.webhook_poster(payload)
                payment.webhooks.append({"at": _now(), "event": event, "result": result})
            return
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            for _ in range(copies):
                try:
                    res = await client.post(self.webhook_url, json=payload)
                    result = f"HTTP {res.status_code} {res.text[:160]}"
                except Exception as exc:  # the Site Service may be down: reconciliation covers it
                    result = f"error: {type(exc).__name__}: {exc}"[:200]
                payment.webhooks.append({"at": _now(), "event": event, "result": result})

    # -- phone actions ----------------------------------------------------
    async def resolve(self, ref: str, action: str) -> Payment:
        payment = self.payments.get(ref)
        if payment is None:
            raise HTTPException(404, "Payment not found")
        if action == "approve":
            if payment.status != "PROCESSING":
                raise HTTPException(409, f"Payment is {payment.status}")
            collected = max(Decimal(0), Decimal(payment.amount) - Decimal(int(self.faults.underpay_by or 0)))
            payment.status, payment.collectedAmount = "SUCCESS", format(collected.normalize(), "f")
            event = "PAYMENT RECEIVED"
        elif action == "decline":
            if payment.status != "PROCESSING":
                raise HTTPException(409, f"Payment is {payment.status}")
            payment.status = "FAILED"
            event = "PAYMENT FAILED"
        elif action == "reverse":
            if payment.status not in {"SUCCESS", "SETTLED"}:
                raise HTTPException(409, "Only a successful payment can be reversed")
            payment.status = "REVERSED"
            event = "PAYMENT REVERSED"
        else:
            raise HTTPException(400, "Unknown action")
        payment.updatedAt = _now()
        if self.sync_webhooks:
            await self.send_webhook(payment, event)
        else:
            asyncio.get_running_loop().create_task(self.send_webhook(payment, event))
        return payment


def create_app(mock: MockClickPesa | None = None) -> FastAPI:
    mock = mock or MockClickPesa(
        webhook_url=default_webhook_url(),
        client_id=(settings.clickpesa_client_id or "").strip(),
        api_key=(settings.clickpesa_api_key or "").strip(),
        checksum_key=(settings.clickpesa_checksum_key or "").strip(),
    )
    app = FastAPI(title="Mock ClickPesa (no real money)", docs_url="/docs")
    app.state.mock = mock

    @app.post(f"{BASE}/generate-token")
    def generate_token(client_id: str | None = Header(default=None, alias="client-id"),
                       api_key: str | None = Header(default=None, alias="api-key")):
        if mock.faults.provider_down:
            raise HTTPException(503, "Service temporarily unavailable (mock outage)")
        if client_id != mock.client_id or api_key != mock.api_key or not mock.client_id:
            raise HTTPException(401, "Invalid client-id or api-key")
        token = f"Bearer mock-{secrets.token_urlsafe(24)}"
        mock.tokens.add(token)
        return {"success": True, "token": token}

    @app.post(f"{BASE}/payments/preview-ussd-push-request")
    async def preview(request: Request, authorization: str | None = Header(default=None)):
        mock.check_token(authorization)
        body = await request.json()
        mock.check_body(body)
        return {"activeMethods": [{"name": "M-PESA", "status": "AVAILABLE", "fee": 0},
                                  {"name": "TIGO-PESA", "status": "AVAILABLE", "fee": 0},
                                  {"name": "AIRTEL-MONEY", "status": "AVAILABLE", "fee": 0}],
                "sender": {"accountNumber": body.get("phoneNumber"), "accountName": "Mock Driver"}}

    @app.post(f"{BASE}/payments/initiate-ussd-push-request")
    async def initiate(request: Request, authorization: str | None = Header(default=None)):
        mock.check_token(authorization)
        body = await request.json()
        mock.check_body(body)
        ref = str(body["orderReference"])
        if ref in mock.payments:
            raise HTTPException(409, "orderReference already used")
        payment = Payment(
            id=f"MOCK{uuid.uuid4().hex[:12].upper()}",
            orderReference=ref,
            paymentReference=f"PR{secrets.token_hex(5).upper()}",
            phoneNumber=str(body["phoneNumber"]),
            amount=str(body["amount"]),
            currency=str(body.get("currency") or "TZS").upper(),
            collectedCurrency=str(body.get("currency") or "TZS").upper(),
        )
        mock.payments[ref] = payment
        if mock.faults.auto_approve_seconds > 0:
            async def _auto():
                await asyncio.sleep(mock.faults.auto_approve_seconds)
                if payment.status == "PROCESSING":
                    await mock.resolve(ref, "approve")
            asyncio.get_running_loop().create_task(_auto())
        return payment.public()

    @app.get(f"{BASE}/payments/{{order_reference}}")
    def status(order_reference: str, authorization: str | None = Header(default=None)):
        mock.check_token(authorization)
        payment = mock.payments.get(order_reference)
        if payment is None:
            return JSONResponse(status_code=404, content={"message": "Payment not found"})
        return [payment.public()]

    # -- phone simulator --------------------------------------------------
    @app.get("/api/payments")
    def list_payments():
        rows = sorted(mock.payments.values(), key=lambda p: p.createdAt, reverse=True)
        return [{**p.public(), "webhooks": p.webhooks[-4:]} for p in rows[:100]]

    @app.post("/api/payments/{ref}/{action}")
    async def act(ref: str, action: str):
        return (await mock.resolve(ref, action)).public()

    @app.get("/api/faults")
    def get_faults():
        return asdict(mock.faults)

    @app.post("/api/faults")
    async def set_faults(request: Request):
        body = await request.json()
        for key, value in (body or {}).items():
            if hasattr(mock.faults, key):
                current = getattr(mock.faults, key)
                setattr(mock.faults, key, type(current)(value))
        return asdict(mock.faults)

    @app.get("/", response_class=HTMLResponse)
    @app.get("/phone", response_class=HTMLResponse)
    def phone():
        return HTMLResponse(PHONE_HTML)

    @app.get("/admin", response_class=HTMLResponse)
    def admin():
        return HTMLResponse(ADMIN_HTML)

    @app.get("/health")
    def health():
        return {"ok": True, "mock": True, "webhook_url": mock.webhook_url,
                "credentials_configured": bool(mock.client_id and mock.api_key),
                "checksum_configured": bool(mock.checksum_key), "payments": len(mock.payments),
                "faults": asdict(mock.faults)}

    return app


def default_webhook_url() -> str:
    explicit = os.environ.get("SMARTPARK_MOCK_CLICKPESA_WEBHOOK_URL", "").strip()
    if explicit:
        return explicit
    port = int(getattr(settings, "api_port", 8760) or 8760)
    return f"http://127.0.0.1:{port}/api/webhooks/clickpesa"


_STYLE = """
:root{--bg:#0b1020;--card:#151c33;--ink:#e8ecf8;--muted:#9aa5c4;--ok:#22c55e;--bad:#ef4444;--warn:#f59e0b;--line:#26304f}
*{box-sizing:border-box}body{margin:0;font:16px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--ink)}
main{max-width:520px;margin:0 auto;padding:18px}h1{font-size:20px;margin:6px 0 2px}.sub{color:var(--muted);font-size:13px;margin-bottom:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px;margin:10px 0}
.row{display:flex;justify-content:space-between;gap:8px;align-items:center}.amt{font-size:26px;font-weight:700}
.pill{font-size:12px;padding:3px 9px;border-radius:99px;background:#26304f;color:var(--muted)}
.pill.SUCCESS{background:#14532d;color:#bbf7d0}.pill.FAILED,.pill.REVERSED{background:#7f1d1d;color:#fecaca}.pill.PROCESSING{background:#78350f;color:#fde68a}
button{border:0;border-radius:12px;padding:12px 14px;font-weight:600;font-size:15px;cursor:pointer;flex:1}
.ok{background:var(--ok);color:#052e16}.bad{background:var(--bad);color:#fff}.ghost{background:#26304f;color:var(--ink)}
.muted{color:var(--muted);font-size:13px}.banner{background:#1e3a8a;color:#dbeafe;border-radius:12px;padding:8px 12px;font-size:13px}
label{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--line)}input{width:90px;padding:6px;border-radius:8px;border:1px solid var(--line);background:#0b1020;color:var(--ink)}
a{color:#93c5fd}
"""

PHONE_HTML = """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Mock phone · ClickPesa</title><style>""" + _STYLE + """</style></head><body><main>
<div class=banner>MOCK ClickPesa: no real money. This page stands in for the driver's phone.</div>
<h1>USSD prompts</h1><div class=sub>Approve or decline each push. <a href="/admin">Fault switches</a></div>
<div id=list><p class=muted>Waiting for payment prompts…</p></div></main>
<script>
const fmt=n=>Number(n).toLocaleString();
async function act(ref,a){await fetch('/api/payments/'+encodeURIComponent(ref)+'/'+a,{method:'POST'});load()}
async function load(){const r=await fetch('/api/payments');const rows=await r.json();const el=document.getElementById('list');
if(!rows.length){el.innerHTML='<p class=muted>No prompts yet. Start a mobile payment from a receipt.</p>';return}
el.innerHTML=rows.map(p=>`<div class=card><div class=row><div><div class=muted>+${p.phoneNumber} · ${p.channel}</div>
<div class=amt>${p.currency} ${fmt(p.amount)}</div><div class=muted>Ref ${p.orderReference}</div></div><span class="pill ${p.status}">${p.status}</span></div>
${p.status==='PROCESSING'?`<p class=muted>Enter PIN to pay ${p.currency} ${fmt(p.amount)} to ZIRP PARKING?</p><div class=row>
<button class=ok onclick="act('${p.orderReference}','approve')">Approve (PIN)</button><button class=bad onclick="act('${p.orderReference}','decline')">Decline</button></div>`:''}
${p.status==='SUCCESS'?`<div class=row><span class=muted>Collected ${p.collectedCurrency} ${fmt(p.collectedAmount)}</span><button class=ghost style="flex:0" onclick="act('${p.orderReference}','reverse')">Reverse</button></div>`:''}
${(p.webhooks||[]).map(w=>`<div class=muted>↳ ${w.event}: ${w.result}</div>`).join('')}</div>`).join('')}
load();setInterval(load,1500);
</script></body></html>"""

ADMIN_HTML = """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Mock ClickPesa · faults</title><style>""" + _STYLE + """</style></head><body><main>
<div class=banner>MOCK ClickPesa fault switches. They rehearse what a real provider does on a bad day.</div>
<h1>Faults</h1><div class=sub><a href="/phone">Phone</a> · <a href="/health">Health</a> · <a href="/docs">API</a></div>
<div class=card id=f></div></main>
<script>
const help={webhook_delay_seconds:'Delay webhooks (s)',drop_webhook:'Drop webhooks (reconciliation must settle)',duplicate_webhook:'Send every webhook twice',
underpay_by:'Collect less than asked (TZS)',bad_checksum:'Forge webhook checksum',provider_down:'Provider outage (HTTP 503)',auto_approve_seconds:'Auto-approve after (s, 0 = off)'};
async function save(k,v){await fetch('/api/faults',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({[k]:v})});load()}
async function load(){const f=await (await fetch('/api/faults')).json();document.getElementById('f').innerHTML=Object.entries(f).map(([k,v])=>
typeof v==='boolean'?`<label>${help[k]||k}<input type=checkbox ${v?'checked':''} onchange="save('${k}',this.checked)" style="width:auto"></label>`
:`<label>${help[k]||k}<input type=number value="${v}" onchange="save('${k}',Number(this.value))"></label>`).join('')}
load();
</script></body></html>"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mock ClickPesa for Zirp (no real money).")
    parser.add_argument("--host", default=os.environ.get("SMARTPARK_MOCK_CLICKPESA_HOST", "127.0.0.1"),
                        help="0.0.0.0 to reach the phone page from a real phone on the LAN")
    parser.add_argument("--port", type=int, default=int(os.environ.get("SMARTPARK_MOCK_CLICKPESA_PORT", "9100")))
    parser.add_argument("--webhook-url", default=None, help="Zirp webhook URL (default: local Site Service)")
    args = parser.parse_args(argv)
    if args.webhook_url:
        os.environ["SMARTPARK_MOCK_CLICKPESA_WEBHOOK_URL"] = args.webhook_url
    app = create_app()
    mock = app.state.mock
    if not (mock.client_id and mock.api_key and mock.checksum_key):
        print("SMARTPARK_CLICKPESA_CLIENT_ID / _API_KEY / _CHECKSUM_KEY are not set.\n"
              "Run:  python -m app.cli env preset mock-payments")
        return 2
    print(f"Mock ClickPesa on http://{args.host}:{args.port}  (phone: /phone, faults: /admin)")
    print(f"Webhooks go to {mock.webhook_url}")
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
