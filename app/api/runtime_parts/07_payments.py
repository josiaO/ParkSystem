def list_payments(db: Session = Depends(get_db), _: User = Depends(require_any("payments.view", "fees.view", "kiosk.use"))):
    return [transaction_dict(row) for row in list_transactions(db)]


async def mobile_money_webhook(request: Request, db: Session = Depends(get_db)):
    """Deprecated compatibility endpoint; never credits a parking session."""
    from app.infrastructure.payments import payment_provider_for

    raw = await request.body()
    signature = request.headers.get("x-signature") or request.headers.get("x-smartpark-signature") or ""
    try:
        import json
        payload = json.loads(raw.decode("utf-8") or "{}") if raw else {}
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    provider = payment_provider_for("mobile_money")
    verified = await provider.verify_callback({
        **payload,
        "signature": signature or payload.get("signature") or "",
        "raw_body": raw,
        "x_signature": signature,
    })
    if not verified.get("verified"):
        raise HTTPException(400, verified.get("error") or "Unverified webhook")
    # This compatibility endpoint cannot prove a provider transaction because
    # the old adapter has no server-side status API.  Accepting its session_id
    # and amount would let a signed-but-unbound callback credit any visit.
    # Real deployments must use /api/webhooks/{flutterwave|clickpesa}, which
    # binds the callback to a pending intent and queries the provider.
    raise HTTPException(
        status_code=410,
        detail="Legacy mobile-money callbacks are disabled; configure Flutterwave or ClickPesa and use the external payment-intent flow.",
    )


@app.post("/sim/exit")
async def sim_exit_ep(payload: SimExitRequest, db: Session = Depends(get_db), user: User = Depends(require("simulation.run"))):
    _require_development_simulation()
    gate = get_gate_or_404(db, payload.gate_id)
    result = await handle_exit(db, plate=payload.plate, gate=gate, side=payload.side)
    write_audit(db, user, "sim.exit", "gate", str(gate.id), payload.plate)
    db.commit()
    if not result.get("ok") and not result.get("pay_required"):
        raise HTTPException(409, result.get("message") or "Exit failed")
    return result


def public_receipt(token: str, db: Session = Depends(get_db)):
    from app.services.public_pay import public_session_payload, session_by_public_token
    from app.services.public_ingress import privacy_headers

    row = session_by_public_token(db, token)
    if not row:
        raise HTTPException(404, "Receipt not found")
    data = public_session_payload(db, row)
    external_pay = str(data.get("pay_endpoint") or "").startswith("/api/public/")
    remaining = float(data["amount_remaining"])
    paid = float(data["amount_paid"])
    due = float(data["amount_due"])
    currency = data["currency"]
    entry = "—"
    if row.entry_time:
        try:
            # public_session_payload is already projected into site-local
            # time. Use that value so the phone receipt follows Settings.
            entry = datetime.fromisoformat(str(data.get("entry_time"))).strftime("%d %b %Y %H:%M")
        except (TypeError, ValueError):
            entry = row.entry_time.strftime("%d %b %Y %H:%M")
    status_label = "PAID" if data["paid"] else data["status"]
    pay_disabled = "disabled" if not data.get("payable") or not data.get("online_payment_available") else ""
    online_label = "Pay with mobile money" if external_pay else (
        "Simulate mobile payment" if data.get("online_payment_available") else "Pay on phone (mobile unavailable)"
    )
    online_help = "" if data.get("online_payment_available") else (
        "Mobile payment is not configured on this site. Use the kiosk or configure an external mobile-money provider."
    )
    success_display = "" if data.get("payment_stage") == "PAID" else " style=\"display:none\""
    stay = data.get("duration_label") or "—"
    image_note = data.get("image_note") or ""
    snapshot = data.get("snapshot_url") or ""
    crop = data.get("crop_url") or ""
    display_site = escape(str(settings.site_name or settings.app_name or "SmartPark"))
    display_plate = escape(str(row.plate or "—"))
    display_entry = escape(str(entry))
    display_gate = escape(str(data.get("entry_gate") or "—"))
    display_status = escape(str(status_label))
    display_currency = escape(str(currency))
    display_token = escape(str(token))
    logo_url = "/assets/zirp-logo.png"
    photo_block = ""
    if snapshot:
        photo_block = f'<img class="vehicle-photo" src="{escape(str(snapshot), quote=True)}" alt="Vehicle captured at entry">'
    else:
        photo_block = '<div class="vehicle-photo vehicle-photo-empty"><span>Entry photo unavailable</span><small>Use the plate and visit details below.</small></div>'
    crop_block = ""
    if crop:
        crop_block = f'<div class="crop-panel"><span class="eyebrow">Plate crop</span><img class="plate-crop" src="{escape(str(crop), quote=True)}" alt="Plate crop from entry camera"></div>'
    image_note_class = "evidence-note warning" if data.get("image_matches_plate") is False else "evidence-note"
    display_stay = escape(str(stay))
    display_image_note = escape(str(image_note))
    inside_label = "Still inside" if data.get("still_inside") else "Visit complete"
    display_inside_label = escape(inside_label)
    phone_field = (
        '<label class="field-label" for="phone">Mobile number</label>'
        '<input id="phone" type="tel" inputmode="tel" autocomplete="tel" placeholder="Mobile number e.g. 07XX XXX XXX" style="display:block">'
        if external_pay else
        '<input id="phone" type="tel" inputmode="tel" autocomplete="tel" placeholder="Mobile number e.g. 07XX XXX XXX" style="display:none">'
    )
    network_field = ""
    if external_pay and str(data.get("mobile_provider") or "").lower() == "flutterwave":
        network_field = (
            '<label class="field-label" for="network">Mobile network</label>'
            '<select id="network" style="width:100%;box-sizing:border-box;padding:12px;border:1px solid #dfe5ef;'
            'border-radius:8px;margin-top:6px;font-size:16px">'
            '<option value="">Select network</option>'
            '<option value="airtel">Airtel</option>'
            '<option value="tigo">Tigo</option>'
            '<option value="halopesa">Halopesa</option>'
            '<option value="vodacom">Vodacom</option>'
            '</select>'
        )
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Pay — {display_plate}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
      :root{{--navy:#0d1b34;--ink:#172033;--muted:#627189;--line:#dbe3ef;--bg:#f1f5fa;--blue:#1f5eff;--blue-dark:#1547c7;--green:#087a3e;--green-bg:#e9f8ef;--amber:#9a5b00;--amber-bg:#fff5df}}
      *{{box-sizing:border-box}}
      body{{font:15px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;background:var(--bg);color:var(--ink);overflow-x:hidden}}
      .topbar{{background:var(--navy);color:#fff;border-bottom:4px solid #2f74ff}}
      .topbar-inner{{max-width:1120px;margin:0 auto;padding:18px 24px;display:flex;align-items:center;justify-content:space-between;gap:16px}}
      .brand{{display:flex;align-items:center;gap:10px;min-width:0;font-weight:750;letter-spacing:-.02em;font-size:18px}}
      .brand-logo{{width:38px;height:38px;flex:0 0 38px;border-radius:10px;background:#fff;display:grid;place-items:center;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.18)}}
      .brand-logo img{{width:100%;height:100%;object-fit:contain;transform:scale(2.2);display:block}}
      .brand-name{{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
      .secure{{font-size:12px;color:#d7e5ff;display:flex;align-items:center;gap:6px;white-space:nowrap}}
      .secure::before{{content:"";width:8px;height:8px;border-radius:50%;background:#53d88e;box-shadow:0 0 0 4px rgba(83,216,142,.14)}}
      main{{max-width:1120px;margin:0 auto;padding:36px 24px 56px}}
      .eyebrow{{font-size:11px;letter-spacing:.12em;text-transform:uppercase;font-weight:750;color:var(--muted)}}
      .heading{{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;margin-bottom:22px}}
      h1{{font-size:31px;line-height:1.1;letter-spacing:-.04em;margin:7px 0 0;color:var(--navy)}}
      .heading-copy{{max-width:650px}}
      .heading-copy p{{margin:10px 0 0;color:var(--muted)}}
      .site-label{{text-align:right;color:var(--muted);font-size:13px;max-width:220px}}
      .summary{{background:#fff;border:1px solid var(--line);border-radius:14px;padding:15px 18px;margin-bottom:20px;display:flex;align-items:center;gap:16px;flex-wrap:wrap}}
      .summary .plate{{font-size:22px;letter-spacing:.1em;font-weight:800;color:var(--navy)}}
      .summary-divider{{height:24px;width:1px;background:var(--line)}}
      .status{{font-size:11px;text-transform:uppercase;letter-spacing:.08em;font-weight:800;border-radius:99px;padding:5px 10px;background:#edf2f8;color:var(--muted)}}
      .status.paid{{color:var(--green);background:var(--green-bg)}}
      .layout{{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(340px,.9fr);gap:20px;align-items:start}}
      .card{{background:#fff;border:1px solid var(--line);border-radius:14px;box-shadow:0 4px 18px rgba(19,42,78,.04)}}
      .card-head{{padding:19px 22px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:flex-start;gap:14px}}
      .card-head h2{{font-size:17px;margin:0;color:var(--navy);letter-spacing:-.02em}}
      .card-head p{{margin:3px 0 0;color:var(--muted);font-size:13px}}
      .card-body{{padding:22px}}
      .vehicle-media{{display:grid;grid-template-columns:minmax(0,1fr) 150px;gap:12px;margin-bottom:18px}}
      .vehicle-photo{{width:100%;height:clamp(200px,24vw,250px);display:block;object-fit:cover;background:#101b2d;border-radius:10px}}
      .vehicle-photo-empty{{display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;color:#cad5e6;padding:20px;background:linear-gradient(145deg,#15243c,#263a5a)}}
      .vehicle-photo-empty small{{color:#9fb0c8;margin-top:5px}}
      .crop-panel{{border:1px solid var(--line);border-radius:10px;padding:10px;background:#fafcff;display:flex;flex-direction:column;gap:8px;min-width:0}}
      .plate-crop{{width:100%;height:75px;object-fit:contain;background:#fff;border-radius:6px}}
      .platebox{{border:1px solid var(--line);border-radius:10px;padding:14px 16px;display:flex;align-items:center;justify-content:space-between;gap:10px;background:#fbfcff}}
      .platebox .plate{{font-size:25px;letter-spacing:.12em;font-weight:850;color:var(--navy)}}
      .verified{{font-size:12px;font-weight:700;color:var(--green);background:var(--green-bg);border-radius:99px;padding:6px 9px;white-space:nowrap}}
      .verified.warning{{color:var(--amber);background:var(--amber-bg)}}
      .evidence-note{{margin:12px 0 20px;color:var(--muted);font-size:13px}}
      .evidence-note.warning{{color:var(--amber)}}
      .details{{display:grid;grid-template-columns:1fr 1fr;gap:15px 20px;border-top:1px solid var(--line);padding-top:18px}}
      .detail-label{{display:block;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:700;margin-bottom:3px}}
      .detail-value{{font-weight:650;color:var(--ink)}}
      .amount-box{{margin-top:20px;border-radius:11px;background:#f5f8fd;padding:16px;display:flex;align-items:end;justify-content:space-between;gap:12px}}
      .amount-box .due{{font-size:30px;line-height:1.1;font-weight:850;letter-spacing:-.04em;color:var(--navy)}}
      .amount-box .paid{{font-size:12px;color:var(--muted);text-align:right}}
      .notice{{border:1px solid #cfe0ff;background:#f1f6ff;color:#35527e;border-radius:10px;padding:12px 13px;font-size:13px;margin-bottom:18px}}
      .notice b{{color:var(--navy)}}
      .methods{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:18px}}
      .method{{border:1px solid var(--line);border-radius:10px;padding:12px;background:#fff}}
      .method.active{{border-color:#86a9ff;background:#f5f8ff;box-shadow:0 0 0 2px rgba(31,94,255,.09)}}
      .method-title{{font-weight:750;color:var(--navy);font-size:13px}}
      .method-sub{{font-size:12px;color:var(--muted);margin-top:2px}}
      label.field-label{{display:block;font-size:12px;font-weight:700;color:var(--ink);margin:14px 0 6px}}
      input,select{{font:inherit;width:100%;padding:12px 13px;border:1px solid #cfd9e7;border-radius:9px;background:#fff;color:var(--ink)}}
      input:focus,select:focus{{outline:3px solid rgba(31,94,255,.16);border-color:var(--blue)}}
      .btn{{display:block;width:100%;min-height:48px;text-align:center;background:var(--blue);color:#fff;border:0;border-radius:9px;padding:13px 15px;margin-top:17px;font-weight:750;font-size:15px;cursor:pointer;transition:background .15s ease}}
      .btn:hover{{background:var(--blue-dark)}}
      .btn:disabled{{opacity:.5;cursor:not-allowed}}
      .btn.secondary{{background:#eef2f8;color:var(--ink);text-decoration:none}}
      .btn.secondary:hover{{background:#e2e9f3}}
      #online-help,#msg{{min-height:1.4em;margin:10px 0 0;font-size:13px}}
      .muted{{color:var(--muted)}}
      .ok{{color:var(--green);font-weight:700}}
      .success{{background:var(--green-bg);border:1px solid #9bd8b5;border-radius:14px;padding:21px;text-align:center;margin-top:20px}}
      .success h2{{color:var(--green);margin:5px 0 7px;font-size:21px}}
      .success .check{{width:45px;height:45px;margin:auto;border-radius:50%;display:grid;place-items:center;background:#c9f0d8;color:var(--green);font-size:27px;font-weight:800}}
      .success p{{margin:5px 0}}
      .kiosk-card{{margin-top:20px}}
      .kiosk-content{{display:flex;align-items:center;gap:18px}}
      img.qr{{width:142px;height:142px;flex:0 0 142px;background:#fff;padding:8px;border:1px solid var(--line);border-radius:9px}}
      .kiosk-content p{{margin:0 0 9px;color:var(--muted);font-size:13px}}
      code{{background:#eef2f8;padding:2px 6px;border-radius:4px;font-size:12px}}
      .footer-note{{text-align:center;color:var(--muted);font-size:12px;margin:25px auto 0;max-width:620px}}
      @media (max-width:760px){{
        .topbar-inner,main{{padding-left:16px;padding-right:16px}}
        .topbar-inner{{padding-top:13px;padding-bottom:13px}}
        main{{padding-top:24px;padding-bottom:40px}}
        .heading{{display:block}}
        .site-label{{text-align:left;margin-top:12px}}
        h1{{font-size:27px}}
        .layout{{grid-template-columns:1fr}}
        .vehicle-media{{grid-template-columns:1fr}}
        .vehicle-photo{{height:clamp(205px,52vw,280px)}}
        .crop-panel{{display:grid;grid-template-columns:auto minmax(0,1fr);align-items:center;gap:12px}}
        .plate-crop{{height:64px}}
      }}
      @media (max-width:430px){{
        .secure{{font-size:0;gap:0}}
        .secure::before{{width:9px;height:9px}}
        .card-head{{padding:16px}}
        .card-body{{padding:16px}}
        .summary{{padding:13px 15px;gap:7px 10px}}
        .summary-divider{{display:none}}
        .summary .plate{{font-size:20px;flex:1 0 100%}}
        .methods{{grid-template-columns:1fr}}
        .details{{gap:13px 12px}}
        .amount-box{{align-items:flex-start;flex-direction:column}}
        .amount-box .paid{{text-align:left}}
        .kiosk-content{{align-items:stretch;flex-direction:column}}
        img.qr{{width:min(180px,100%);height:auto;align-self:center}}
      }}
    </style></head>
    <body><header class="topbar"><div class="topbar-inner">
      <div class="brand"><span class="brand-logo"><img src="{logo_url}" alt=""></span><span class="brand-name">{display_site}</span></div>
      <span class="secure">Secure payment page</span>
    </div></header>
    <main>
      <div class="heading"><div class="heading-copy"><div class="eyebrow">Parking payment</div><h1>Review your visit</h1><p>Confirm the vehicle and entry details before you complete payment.</p></div><div class="site-label">Receipt link for this visit<br><span class="muted">Keep this page for exit</span></div></div>
      <div class="summary"><span class="plate">{display_plate}</span><span class="summary-divider"></span><span class="muted">Entry gate: {display_gate}</span><span class="status {'paid' if data.get('paid') else ''}" id="status">{display_status}</span></div>
      <div class="layout">
        <section class="card" id="receipt-details"><div class="card-head"><div><h2>Vehicle &amp; visit</h2><p>Entry camera evidence and parking details</p></div><span class="eyebrow">Receipt</span></div>
          <div class="card-body">
            <div class="vehicle-media">{photo_block}{crop_block}</div>
            <div class="platebox"><span class="plate">{display_plate}</span><span class="{'verified warning' if data.get('image_matches_plate') is False else 'verified'}">{'Review plate' if data.get('image_matches_plate') is False else 'Camera verified'}</span></div>
            <p class="{image_note_class}">{display_image_note}</p>
            <div class="details">
              <div><span class="detail-label">Entry time</span><span class="detail-value">{display_entry}</span></div>
              <div><span class="detail-label">Gate</span><span class="detail-value">{display_gate}</span></div>
              <div><span class="detail-label">Time inside</span><span class="detail-value" id="stay">{display_stay}</span></div>
              <div><span class="detail-label">Visit state</span><span class="detail-value" id="inside-state">{display_inside_label}</span></div>
            </div>
            <div class="amount-box"><div><span class="detail-label">Amount due</span><div class="due" id="due">{display_currency} {remaining:,.0f}</div></div><div class="paid">Paid {display_currency} {paid:,.0f}<br>of {display_currency} {due:,.0f}</div></div>
          </div>
        </section>
        <section class="card"><div class="card-head"><div><h2>Complete payment</h2><p>Choose how you want to settle this visit</p></div></div>
          <div class="card-body">
            <div class="notice"><b>Check the details above first.</b><br>If the photo and plate do not match, ask the parking team to review the visit before paying.</div>
            <div class="methods"><div class="method active"><div class="method-title">Mobile money</div><div class="method-sub">Fastest option</div></div><div class="method"><div class="method-title">At the kiosk</div><div class="method-sub">Cash or operator help</div></div></div>
            {phone_field}
            {network_field}
            <button class="btn" id="pay-mobile" {pay_disabled}>{online_label}</button>
            <p id="online-help" class="muted">{online_help}</p><p id="msg" class="muted"></p>
            <a class="btn secondary" href="#kiosk">Use the kiosk instead</a>
          </div>
        </section>
      </div>
      <div class="success" id="success"{success_display}><div class="check">✓</div><h2 id="success-title">Payment successful</h2><p id="success-detail">{display_currency} {paid:,.0f} paid.</p><p class="ok" id="success-next">You may now proceed to the exit gate.</p><a class="btn secondary" href="#receipt-details">View receipt details</a></div>
      <section class="card kiosk-card" id="kiosk"><div class="card-head"><div><h2>Need help or cash payment?</h2><p>The same receipt works at the site kiosk</p></div><span class="eyebrow">Fallback</span></div><div class="card-body kiosk-content"><img class="qr" src="/p/{display_token}/qr.png" alt="Payment QR"><div><p>Scan this QR or type code <code>{display_token}</code> at the kiosk. An operator can confirm cash and update the visit immediately.</p><a class="btn secondary" href="#receipt-details">Back to payment</a></div></div></section>
      <p class="footer-note">Lost paper is OK — your vehicle plate and this secure receipt link identify the visit.</p>
    <script>
      const token = {json.dumps(str(token))};
      const externalPay = {'true' if external_pay else 'false'};
      const payBtn = document.getElementById("pay-mobile");
      const phoneInput = document.getElementById("phone");
      const networkInput = document.getElementById("network");
      const msg = document.getElementById("msg");
      const success = document.getElementById("success");
      const successTitle = document.getElementById("success-title");
      const successDetail = document.getElementById("success-detail");
      const successNext = document.getElementById("success-next");
      const onlineHelp = document.getElementById("online-help");
      let pendingSince = 0;
      const statusUrl = externalPay
        ? "/api/public/payment-status/" + encodeURIComponent(token)
        : "/p/" + encodeURIComponent(token) + "/status";
      async function refresh() {{
        const res = await fetch(statusUrl);
        if (!res.ok) return;
        const data = await res.json();
        const statusEl = document.getElementById("status");
        statusEl.textContent = data.paid ? "PAID" : data.status;
        statusEl.className = "status" + (data.paid ? " paid" : "");
        document.getElementById("due").textContent = data.currency + " " + Math.round(data.amount_remaining).toLocaleString();
        if (data.duration_label) document.getElementById("stay").textContent = data.duration_label;
        if (data.still_inside !== undefined) document.getElementById("inside-state").textContent = data.still_inside ? "Still inside" : "Visit complete";
        const intent = data.intent || null;
        const waiting = externalPay && intent && intent.status === "PENDING" && !data.paid;
        payBtn.disabled = !data.payable || !data.online_payment_available || waiting;
        onlineHelp.textContent = data.online_payment_available
          ? ""
          : "Mobile payment is not configured on this site. Use the kiosk or ask staff to configure mobile money.";
        if (data.payment_stage === "PAID") {{
          success.style.display = "block";
          successTitle.textContent = "Payment successful";
          successDetail.textContent = data.currency + " " + Math.round(data.amount_paid).toLocaleString() + " paid.";
          successNext.textContent = data.can_exit ? "You may now proceed to the exit gate." : "Payment recorded. Follow the exit-lane instructions.";
        }} else if (data.payment_stage === "NO_PAYMENT_REQUIRED") {{
          success.style.display = "block";
          successTitle.textContent = "No payment required";
          successDetail.textContent = "This visit is within the free period.";
          successNext.textContent = data.can_exit ? "You may now proceed to the exit gate." : "Keep this receipt for exit.";
        }} else {{
          success.style.display = "none";
        }}
        if (!data.payable) {{
          msg.textContent = data.pay_blocked_reason || (data.paid ? "Paid. You can leave when the exit camera reads your plate." : "Nothing to pay.");
          msg.className = data.paid ? "ok" : "muted";
        }} else if (waiting) {{
          msg.textContent = "Approve the payment prompt on your phone. This page updates when the provider confirms.";
          msg.className = "muted";
        }} else if (externalPay && intent && ["FAILED", "EXPIRED", "BLOCKED", "MISMATCH"].includes(intent.status) && pendingSince) {{
          msg.textContent = intent.status === "MISMATCH"
            ? "Payment needs staff review at the kiosk."
            : ("Payment was not completed" + (intent.message ? " (" + intent.message + ")" : "") + ". Try again or pay at the kiosk.");
          msg.className = "muted";
          pendingSince = 0;
        }}
      }}
      payBtn.addEventListener("click", async () => {{
        payBtn.disabled = true;
        msg.className = "muted";
        try {{
          let res, data;
          if (externalPay) {{
            const phone = (phoneInput && phoneInput.value || "").trim();
            if (!phone) throw new Error("Enter the mobile number that will pay.");
            msg.textContent = "Sending payment prompt to your phone…";
            const network = (networkInput && networkInput.value || "").trim();
            res = await fetch("/api/public/payment-intents", {{
              method: "POST",
              headers: {{"Content-Type": "application/json"}},
              body: JSON.stringify({{token: token, phone: phone, ...(network ? {{network: network}} : {{}})}}),
            }});
            data = await res.json();
            if (!res.ok) throw new Error(data.detail || data.error || "Payment could not be started");
            if (data.already_paid) {{ msg.textContent = "Already paid."; msg.className = "ok"; }}
            else {{ pendingSince = Date.now(); msg.textContent = "Approve the prompt on your phone. Waiting for confirmation…"; }}
          }} else {{
            msg.textContent = "Confirming payment…";
            res = await fetch("/p/" + encodeURIComponent(token) + "/pay", {{
              method: "POST",
              headers: {{"Content-Type": "application/json"}},
              body: JSON.stringify({{method: "MOBILE_SIMULATED"}}),
            }});
            data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Payment failed");
            msg.textContent = data.already_paid ? "Already paid." : "Payment recorded.";
            msg.className = "ok";
          }}
          await refresh();
        }} catch (err) {{
          msg.textContent = err.message || String(err);
          msg.className = "muted";
          payBtn.disabled = false;
        }}
      }});
      setInterval(refresh, externalPay ? 3000 : 5000);
    </script>
    </main></body></html>"""
    return HTMLResponse(html, headers=privacy_headers())


def public_receipt_status(token: str, db: Session = Depends(get_db)):
    from app.services.public_pay import public_session_payload, session_by_public_token
    from app.services.public_ingress import privacy_headers

    row = session_by_public_token(db, token)
    if not row:
        raise HTTPException(404, "Receipt not found")
    return JSONResponse(public_session_payload(db, row), headers=privacy_headers())


def public_receipt_short_link(token: str, db: Session = Depends(get_db)):
    """Open the canonical receipt QR path in the public Driver page."""
    from app.services.public_pay import session_by_public_token
    from app.services.public_ingress import privacy_headers

    if not session_by_public_token(db, token):
        raise HTTPException(404, "Receipt not found")
    return RedirectResponse(f"/p/{token}", headers=privacy_headers(), status_code=307)


async def public_receipt_pay(token: str, payload: PaymentConfirm = PaymentConfirm(method="MOBILE_SIMULATED"), db: Session = Depends(get_db)):
    """Phone payment from the receipt QR page.

    Uses the simulated provider until a live mobile-money aggregator is wired.
    Kiosk cash must use the authenticated kiosk endpoint instead.
    """
    from app.services.public_pay import pay_public_session, session_by_public_token
    from app.services.public_ingress import privacy_headers

    row = session_by_public_token(db, token)
    if not row:
        raise HTTPException(404, "Receipt not found")
    method = (payload.method or "MOBILE_SIMULATED").strip().upper()
    if method in {"KIOSK_CASH", "CASH", "KIOSK"}:
        raise HTTPException(401, "Kiosk cash requires a signed-in operator. Open Sessions and pay there, or POST /p/{token}/kiosk-pay.")
    from app.services import mobile_payments

    if mobile_payments.active_mobile_provider_id() in mobile_payments.external_provider_ids():
        # A real aggregator is configured: the instant simulated path must not
        # be reachable from a browser. Money only moves via payment intents.
        raise HTTPException(409, "Mobile payments use POST /api/public/payment-intents on this site.")
    try:
        result = await pay_public_session(db, row, method=method, amount=payload.amount)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, str(exc))
    return JSONResponse(result, headers=privacy_headers())


# ---------------------------------------------------------------------------
# Narrow public payment surface (tunnel-exposed). Everything else stays LAN.
# ---------------------------------------------------------------------------


async def public_payment_intent(payload: PublicPaymentIntentRequest, db: Session = Depends(get_db)):
    """Start a mobile-money collection for a receipt token.

    Creates a PENDING PaymentIntent and asks the provider to push a USSD
    prompt. Nothing is marked paid here; verification happens server-side.
    """
    from app.services import mobile_payments
    from app.services.public_pay import session_by_public_token
    from app.services.public_ingress import privacy_headers

    row = session_by_public_token(db, payload.token)
    if not row:
        raise HTTPException(404, "Receipt not found")
    provider_id = (payload.provider or "").strip().lower() or mobile_payments.active_mobile_provider_id()
    if provider_id not in mobile_payments.external_provider_ids():
        raise HTTPException(409, "No external mobile-money provider is active on this site.")
    try:
        result = await mobile_payments.start_mobile_payment(
            db, row, phone=payload.phone, provider_id=provider_id, network=payload.network, amount=payload.amount,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if not result.get("ok"):
        return JSONResponse(status_code=503, content={**result, "token": row.public_token}, headers=privacy_headers())
    return JSONResponse({**result, "token": row.public_token}, headers=privacy_headers())


def public_payment_status(token: str, db: Session = Depends(get_db)):
    """Read-only status for the phone page: session paid state + latest intent."""
    from app.services import mobile_payments
    from app.services.public_pay import public_session_payload, session_by_public_token
    from app.services.public_ingress import privacy_headers

    row = session_by_public_token(db, token)
    if not row:
        raise HTTPException(404, "Receipt not found")
    body = public_session_payload(db, row)
    latest = mobile_payments.latest_intent_for_session(db, row.id)
    body["intent"] = mobile_payments.intent_dict(latest) if latest else None
    body["mobile_provider"] = mobile_payments.active_mobile_provider_id()
    return JSONResponse(body, headers=privacy_headers())


async def payment_provider_webhook(provider_id: str, request: Request, db: Session = Depends(get_db)):
    """Authenticated provider callback. Never opens a barrier; never trusts the body for money."""
    from app.services import mobile_payments

    if provider_id not in mobile_payments.external_provider_ids():
        raise HTTPException(404, "Unknown provider")
    raw = await request.body()
    status, body = await mobile_payments.handle_webhook(
        db, provider_id, raw_body=raw, headers={k.lower(): v for k, v in request.headers.items()},
    )
    return JSONResponse(status_code=status, content=body)


def payments_health_ep(db: Session = Depends(get_db), _: User = Depends(require_any("payments.view", "fees.view", "kiosk.use"))):
    from app.services import mobile_payments
    from app.services.public_ingress import describe as ingress_describe

    return {**mobile_payments.payments_health(db), "public_ingress": ingress_describe()}


async def payments_reconcile_ep(db: Session = Depends(get_db), _: User = Depends(require_any("payments.view", "payments.create"))):
    """Operator-triggered reconciliation (same code path as the background job)."""
    from app.services import mobile_payments

    return await mobile_payments.reconcile_pending(db=db)


async def kiosk_receipt_pay(
    token: str,
    payload: PaymentConfirm = PaymentConfirm(method="KIOSK_CASH"),
    db: Session = Depends(get_db),
    user: User = Depends(require_any("payments.create", "kiosk.use", "simulation.run")),
):
    """Operator confirms cash after scanning the receipt QR at the kiosk."""
    from app.services.public_pay import pay_public_session, session_by_public_token

    row = session_by_public_token(db, token)
    if not row:
        raise HTTPException(404, "Receipt not found")
    try:
        result = await pay_public_session(
            db, row, method=payload.method or "KIOSK_CASH", amount=payload.amount, operator_id=user.id,
            audience="operator",
        )
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    write_audit(db, user, "payments.create", "parking_session", str(row.id), f"kiosk QR {row.plate}")
    return result




@app.post("/exit/qr-scan")
async def exit_qr_scan(
    payload: ExitQrScanRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require("gates.open")),
):
    """Authenticated QR fallback for an exit lane.

    The same entry-receipt QR resolves the existing site session and enters the
    same ExitLaneController used by plate recognition. This route never creates
    a parallel exit/payment path.
    """
    from uuid import uuid4
    from app.application.exit_lane import ExitLaneController
    from app.application.entry_lane import policy_from_parking_settings

    gate = _gate_for_node(db, int(payload.gate_id), action="exit-qr-scan")
    if not gate.enabled:
        raise HTTPException(404, "Exit gate not found or disabled")
    camera = _camera_for_node(db, int(payload.camera_id), action="exit-qr-scan") if payload.camera_id else None
    if camera is not None and camera.gate_id not in {None, gate.id}:
        raise HTTPException(409, "Camera is assigned to a different gate")
    site_id = int(payload.site_id or gate.site_id or DEFAULT_SITE_ID)
    if int(gate.site_id or DEFAULT_SITE_ID) != site_id:
        raise HTTPException(409, "Gate does not belong to the requested site")

    out = await ExitLaneController().submit_qr(
        db,
        raw_scan=payload.raw_scan,
        event_id=f"qr-{uuid4().hex}",
        site_id=site_id,
        gate=gate,
        camera=camera,
        lane_id=payload.lane_id or (camera.lane_id if camera else None),
        policy=policy_from_parking_settings(parking_settings(db)),
        source="operator-qr",
    )
    write_audit(
        db, user, "exit.qr_scan", "parking_session",
        str((out.get("session") or {}).get("id") or ""),
        f"gate={gate.id} result={out.get('reason')}",
    )
    if not out.get("ok") and out.get("reason") in {"invalid_qr", "no_session"}:
        raise HTTPException(404, out.get("message") or "No active session for that QR")
    if not out.get("ok") and out.get("reason") in {"gate_unavailable", "gate_unassigned"}:
        raise HTTPException(503, out.get("message") or "Exit barrier unavailable")
    return out

@app.get("/sessions/by-token/{token}")
def session_by_token(token: str, db: Session = Depends(get_db), _: User = Depends(require_any("sessions.view", "fees.view", "kiosk.use", "payments.create"))):
    from app.services.public_pay import public_session_payload, session_by_public_token

    row = session_by_public_token(db, token)
    if not row:
        raise HTTPException(404, "No session for that receipt code")
    return public_session_payload(db, row, audience="operator")


@app.get("/sessions/lookup")
def lookup_session(q: str = "", db: Session = Depends(get_db), _: User = Depends(require_any("sessions.view", "fees.view", "kiosk.use", "payments.create"))):
    """Find a visit from a scanned QR, a receipt link, or a number plate."""
    from app.services.kiosk_lookup import find_session
    from app.services.public_pay import public_session_payload

    row = find_session(db, q)
    if not row:
        raise HTTPException(404, "No visit matches that QR code or plate")
    return public_session_payload(db, row, audience="operator")


def _session_image(db: Session, token: str, kind: str):
    from app.services.kiosk_lookup import capture_for_session
    from app.services.preview import media_path
    from app.services.public_pay import session_by_public_token
    from app.services.public_ingress import privacy_headers

    row = session_by_public_token(db, token)
    if not row:
        raise HTTPException(404, "Receipt not found")
    # Resolve the exact capture used to build the presentation. Never fall
    # back to the latest plate/camera capture: repeated visits may share both.
    capture = capture_for_session(db, row)
    stored = (capture.snapshot_path if kind == "snapshot" else capture.crop_path) if capture else ""
    if not stored or "/" not in stored.replace("\\", "/"):
        raise HTTPException(404, "No photo for this visit")
    folder, name = str(stored).replace("\\", "/").split("/", 1)
    path = media_path(folder, name)
    if path is None:
        raise HTTPException(404, "No photo for this visit")
    return FileResponse(path, media_type="image/jpeg", headers=privacy_headers())


def public_snapshot(token: str, db: Session = Depends(get_db)):
    return _session_image(db, token, "snapshot")


def public_crop(token: str, db: Session = Depends(get_db)):
    return _session_image(db, token, "crop")


def public_receipt_qr(token: str, db: Session = Depends(get_db)):
    row = db.scalar(select(Receipt).where(Receipt.public_token == token).order_by(Receipt.id.desc()))
    from app.services.public_ingress import privacy_headers
    path = Path(row.qr_path) if row and row.qr_path else None
    if path:
        root = settings.media_dir.joinpath("receipts").resolve()
        candidate = path if path.is_absolute() else settings.media_dir.joinpath(path)
        try:
            safe_path = candidate.resolve()
        except OSError:
            safe_path = None
        if safe_path and safe_path.is_relative_to(root) and safe_path.exists():
            return FileResponse(safe_path, media_type="image/png", headers=privacy_headers())
    from app.domain.receipt_engine import session_qr_payload
    from app.services.receipts import _qr_png, resolve_public_base_url
    png = _qr_png(session_qr_payload(token, base_url=resolve_public_base_url(db)))
    if not png:
        raise HTTPException(404, "QR not available")
    return Response(content=png, media_type="image/png", headers=privacy_headers())
