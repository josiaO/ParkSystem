let selectedSessionId = null;
async function loadSessions() {
  const err = document.getElementById("session-error");
  err.textContent = "";
  try {
    const rows = await api("/sessions");
    document.getElementById("session-rows").innerHTML = rows.map((s) => {
      const due = Number(s.amount_due || 0);
      const paid = Number(s.amount_paid || 0);
      const pay = due <= 0 && paid <= 0 ? (s.status || "OPEN") : (paid >= due && due > 0 ? "PAID" : (paid > 0 ? "PENDING" : "UNPAID"));
      return `<tr data-id="${s.id}"><td><span class="plate">${s.plate || ""}</span></td><td>${s.parker_kind || "Casual"}</td><td>${paymentChip(pay)}</td><td>${s.receipt_status || "—"}</td><td><code>${s.public_token || "—"}</code></td><td>${formatWhen(s.entry_time)}</td><td>${moneyLabel(s.amount_due, s.currency)}</td><td>${moneyLabel(s.amount_paid, s.currency)}</td></tr>`;
    }).join("") || `<tr><td colspan="8"><div class="empty-state"><b>No sessions yet.</b><p>Parking visits appear here after a vehicle is detected at an entry.</p></div></td></tr>`;
    document.querySelectorAll("#session-rows tr[data-id]").forEach((tr) => {
      tr.addEventListener("click", () => {
        document.querySelectorAll("#session-rows tr").forEach((row) => row.classList.remove("selected"));
        tr.classList.add("selected");
        selectedSessionId = Number(tr.dataset.id);
      });
    });
  } catch (e) {
    err.textContent = e.message;
  }
}

async function loadPayments() {
  const err = document.getElementById("payment-error");
  err.textContent = "";
  try {
    const rows = await api("/payments");
    document.getElementById("payment-rows").innerHTML = rows.map((p) =>
      `<tr><td>${formatWhen(p.confirmed_at || p.created_at)}</td><td>${p.session_id || "—"}</td><td>${methodLabel(p.method)}</td><td>${moneyLabel(p.amount, p.currency)}</td><td>${paymentChip(p.status)}</td><td class="tech-col">${p.provider_id || "—"}</td></tr>`
    ).join("") || `<tr><td colspan="6"><div class="empty-state"><b>No payments yet.</b><p>Succeeded, pending, and failed payments will appear here.</p></div></td></tr>`;
  } catch (e) {
    err.textContent = e.message;
  }
}

async function fillGateOptions(selected) {
  const select = document.querySelector("#camera-form [name=gate_id]");
  const gates = can("gates.view") ? await api("/gates") : [];
  select.innerHTML = `<option value="">No gate — monitoring only</option>` + gates.map((g) =>
    `<option value="${g.id}" ${String(selected || "") === String(g.id) ? "selected" : ""}>${g.name}</option>`
  ).join("");
}

async function openCameraDialog(camera) {
  const form = document.getElementById("camera-form");
  form.reset();
  document.getElementById("camera-dialog-error").textContent = "";
  document.getElementById("camera-dialog-title").textContent = camera ? "Edit Camera" : "Add Camera";
    form.elements.password.placeholder = camera ? "Leave blank to keep current password" : "Camera default: admin";
    if (!camera) form.elements.password.value = "admin";
  await fillGateOptions(camera && camera.gate_id);
  if (camera) {
    form.elements.id.value = camera.id;
    form.elements.name.value = camera.name;
    form.elements.ip_address.value = camera.ip_address;
    form.elements.sdk_port.value = camera.sdk_port;
    form.elements.username.value = camera.username;
    form.elements.lane_direction.value = camera.lane_direction;
    form.elements.rtsp_url.value = camera.rtsp_url || "";
    form.elements.controller_ip.value = camera.controller_ip || "";
    form.elements.display_ip.value = camera.display_ip || "";
    form.elements.adapter_id.value = camera.adapter_id || "hvx";
    if (form.elements.ffmpeg_profile) form.elements.ffmpeg_profile.value = camera.ffmpeg_profile || "LOW_LATENCY_LAN";
    if (form.elements.rtsp_transport) form.elements.rtsp_transport.value = camera.rtsp_transport || "TCP";
    if (form.elements.recognition_mode) form.elements.recognition_mode.value = camera.recognition_mode || "";
  } else {
    form.elements.id.value = "";
    form.elements.sdk_port.value = "30000";
    form.elements.username.value = "admin";
    form.elements.adapter_id.value = state.recommendedAdapter || "hvx";
    form.elements.controller_ip.value = "";
    form.elements.display_ip.value = "";
  }
  const adapterHint = document.getElementById("camera-adapter-hint");
  if (adapterHint && state.platform && !state.platform.hvx_host_supported) {
    adapterHint.textContent = "This computer cannot run the vendor camera host. Use Advanced only if a technician is connecting a generic camera.";
  } else if (adapterHint) {
    adapterHint.textContent = "Advanced holds vendor, stream, and controller details. Leave them closed unless a technician is commissioning the camera.";
  }
  document.getElementById("camera-dialog").showModal();
}

async function loadCameras() {
  const error = document.getElementById("camera-error");
  error.textContent = "";
  try {
    const [rows, gates] = await Promise.all([api("/cameras"), api("/gates")]);
    gateRowsCache = gates || [];
    const body = document.getElementById("camera-rows");
    body.innerHTML = "";
    rows.forEach((c) => {
      const tr = document.createElement("tr");
      tr.dataset.id = c.id;
      if (String(selectedCameraId) === String(c.id)) tr.classList.add("selected");
      const [healthLabel, healthTone] = cameraHealth(c.status);
      const err = (c.last_error || "").slice(0, 80);
      tr.innerHTML = `<td class="tech-col">${c.id}</td><td>${c.name}</td><td>${c.lane_name || c.gate_name || "—"}</td><td>${c.side || c.lane_direction || "—"}</td><td class="tech-col">${c.ip_address}</td><td class="tech-col">${c.controller_ip || "—"}</td><td class="tech-col">${c.display_ip || "—"}</td><td><span class="chip ${healthTone}">${healthLabel}</span></td><td class="tech-col">${c.sdk_handle == null ? "—" : "handle=" + c.sdk_handle}</td><td class="muted tech-col">${err || "—"}</td><td class="row-actions"></td>`;
      tr.addEventListener("click", (ev) => {
        if (ev.target.closest("button")) return;
        selectedCameraId = c.id;
        loadCameras();
      });
      const actions = tr.querySelector(".row-actions");
      if (can("cameras.manage")) {
        const edit = document.createElement("button");
        edit.className = "secondary";
        edit.dataset.role = "edit";
        setActionCaption(edit, "Edit", "Ctrl+E");
        edit.addEventListener("click", () => openCameraDialog(c));
        const del = document.createElement("button");
        del.className = "danger";
        del.dataset.role = "delete";
        setActionCaption(del, "Delete", "Del");
        del.addEventListener("click", async () => {
          if (!confirm(`Delete camera ${c.name}?`)) return;
          try { await api(`/cameras/${c.id}`, { method: "DELETE" }); loadCameras(); }
          catch (err) { error.textContent = err.message; }
        });
        actions.append(edit, del);
      }
      body.appendChild(tr);
    });
    if (!rows.length) {
      body.innerHTML = `<tr><td colspan="11"><div class="empty-state"><b>No cameras configured.</b><p>Add a camera to start live monitoring and plate recognition.</p></div></td></tr>`;
    }
    cameraRowsCache = rows;
    cameraLiveRowsCache = rows.filter((camera) => camera.stream_allowed !== false);
    // Keep the gate selector populated from the management registry even
    // when this PC has no owner yet.  That is how an administrator chooses
    // a gate before pressing "Assign this PC"; only the camera pickers
    // below are restricted to the local stream scope.
    fillLiveLanes(rows, gateRowsCache);
    fillPaneSelects(cameraLiveRowsCache);
    if (selectedCameraId) refreshStreamProfiles(selectedCameraId);
    if (liveTabVisible()) startDualLive();
  } catch (err) {
    error.textContent = err.message;
  }
}

document.getElementById("refresh-cameras").addEventListener("click", loadCameras);
document.getElementById("assign-recognition-owner").addEventListener("click", assignRecognitionOwner);
document.getElementById("refresh-live").addEventListener("click", () => startDualLive(true));
document.getElementById("apply-lane").addEventListener("click", applyLanePreset);
document.getElementById("live-lane").addEventListener("change", applyLanePreset);
document.getElementById("live-layout").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-layout]");
  if (!btn) return;
  liveLayout = btn.dataset.layout;
  lsSet("smartpark_live_layout", liveLayout);
  startDualLive(true);
});
document.querySelectorAll(".live-pane").forEach((pane) => {
  const slot = Number(pane.dataset.slot);
  const sel = pane.querySelector('[data-role="camera"]');
  const pick = pane.querySelector('[data-role="pick"]');
  if (sel) sel.addEventListener("change", () => {
    startLiveSlot(slot, cameraFromSelect(slot), true);
    markLiveShortcutTarget(slot);
  });
  if (pick) pick.addEventListener("click", () => {
    if (pane.dataset.zoneEdit === "1") return;
    openCameraPicker(slot);
  });
  bindZoneEditor(pane);
  pane.addEventListener("pointerdown", () => { markLiveShortcutTarget(slot); });
});
document.getElementById("cameras-subnav").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-sub]");
  if (!btn) return;
  showCameraSub(btn.dataset.sub);
});
document.querySelectorAll(".live-pane [data-role='open-side']").forEach((btn) => {
  btn.addEventListener("click", () => {
    const pane = btn.closest(".live-pane");
    openPaneSide(Number(pane.dataset.slot), "open");
  });
});
document.querySelectorAll(".live-pane [data-role='close-side']").forEach((btn) => {
  btn.addEventListener("click", () => {
    const pane = btn.closest(".live-pane");
    openPaneSide(Number(pane.dataset.slot), "close");
  });
});
document.querySelectorAll(".live-pane [data-role='correct-plate']").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const pane = btn.closest(".live-pane");
    const slot = Number(pane.dataset.slot);
    const cam = liveCameras[slot];
    const shown = liveLastCars[slot] || {};
    const error = document.getElementById("camera-error");
    if (!cam) { error.textContent = "No camera on this side."; return; }
    const current = shown.plate || "";
    const next = prompt("Correct plate (leave as-is to confirm)", current);
    if (next == null) return;
    error.textContent = "";
    try {
      const data = await api(`/cameras/${cam.id}/plate-corrections`, {
        method: "POST",
        body: JSON.stringify({ plate: String(next).trim() || current, capture_id: shown.id || null, confirm: true }),
      });
      liveLastCars[slot] = data.capture || shown;
      renderSlotCar(slot, { last_car: liveLastCars[slot], fusion: (data.capture || {}).fusion });
      alert(data.message || "Plate confirmed");
    } catch (err) {
      error.textContent = err.message;
    }
  });
});
document.getElementById("sim-entry").addEventListener("click", () => simAction("entry"));
document.getElementById("sim-taken").addEventListener("click", () => simAction("taken"));
document.getElementById("sim-pay").addEventListener("click", () => simAction("pay"));
document.getElementById("sim-exit").addEventListener("click", () => simAction("exit"));
document.getElementById("sim-plate-entry").addEventListener("click", () => simPlate("ENTRY"));
document.getElementById("sim-plate-exit").addEventListener("click", () => simPlate("EXIT"));
document.getElementById("site-save").addEventListener("click", async () => {
  const error = document.getElementById("sim-error");
  error.textContent = "";
  try {
    const saved = await api("/settings/site", {
      method: "PATCH",
      body: JSON.stringify({
        timezone: document.getElementById("site-timezone").value.trim() || "UTC",
        currency: document.getElementById("site-currency").value.trim().toUpperCase(),
        language: document.getElementById("site-language").value,
        plate_validation: document.getElementById("site-plate-validation").value,
        public_base_url: document.getElementById("site-public-url").value.trim().replace(/\/+$/, ""),
      }),
    });
    state.siteTimezone = saved.timezone || "UTC";
    error.textContent = `Site locale saved: ${saved.timezone} / ${saved.currency}`;
  } catch (err) {
    error.textContent = err.message;
  }
});
document.getElementById("park-save").addEventListener("click", async () => {
  const error = document.getElementById("sim-error");
  error.textContent = "";
  try {
    await api("/settings/parking", {
      method: "PATCH",
      body: JSON.stringify({
        receipt_policy: document.getElementById("park-policy").value,
        receipt_required_before_open: document.getElementById("park-receipt").checked,
        exit_requires_payment: document.getElementById("park-pay").checked,
        pay_prompt: document.getElementById("park-prompt").value.trim(),
        printer_adapter: document.getElementById("park-printer").value ? "system" : "simulated",
        printer_name: document.getElementById("park-printer").value || "",
      }),
    });
    error.textContent = "Parking rules saved. Entry prints, then the gate opens.";
  } catch (err) {
    error.textContent = err.message;
  }
});
document.getElementById("park-test").addEventListener("click", async () => {
  const error = document.getElementById("sim-error");
  error.textContent = "";
  try {
    await api("/settings/parking", {
      method: "PATCH",
      body: JSON.stringify({
        receipt_policy: document.getElementById("park-policy").value,
        receipt_required_before_open: document.getElementById("park-receipt").checked,
        exit_requires_payment: document.getElementById("park-pay").checked,
        pay_prompt: document.getElementById("park-prompt").value.trim(),
        printer_adapter: document.getElementById("park-printer").value ? "system" : "simulated",
        printer_name: document.getElementById("park-printer").value || "",
      }),
    });
    const result = await api("/printers/test", { method: "POST", body: "{}" });
    error.textContent = result.message || "Test page sent.";
  } catch (err) {
    error.textContent = err.message;
  }
});
document.getElementById("sim-file").addEventListener("change", () => {
  const file = document.getElementById("sim-file").files && document.getElementById("sim-file").files[0];
  const preview = document.getElementById("sim-preview");
  if (!file) { preview.style.display = "none"; preview.removeAttribute("src"); return; }
  preview.src = URL.createObjectURL(file);
  preview.style.display = "block";
});
document.getElementById("add-camera").addEventListener("click", () => openCameraDialog(null));
document.getElementById("onboard-camera").addEventListener("click", () => {
  document.getElementById("onboard-error").textContent = "";
  document.getElementById("onboard-result").classList.add("hidden");
  document.getElementById("onboard-dialog").showModal();
});
document.getElementById("onboard-close").addEventListener("click", () => document.getElementById("onboard-dialog").close());
document.getElementById("onboard-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const error = document.getElementById("onboard-error");
  const result = document.getElementById("onboard-result");
  error.textContent = "";
  try {
    const data = await api("/cameras/onboard/probe", {
      method: "POST",
      body: JSON.stringify({
        ip_address: form.elements.ip_address.value.trim(),
        username: form.elements.username.value,
        password: form.elements.password.value,
        sdk_port: form.elements.sdk_port.value ? Number(form.elements.sdk_port.value) : null,
        rtsp_url: form.elements.rtsp_url.value.trim(),
      }),
      timeoutMs: 20000,
    });
    result.classList.remove("hidden");
    result.textContent = JSON.stringify(data, null, 2);
    if (data.recommended_adapter) {
      const camForm = document.getElementById("camera-form");
      await openCameraDialog(null);
      camForm.elements.ip_address.value = form.elements.ip_address.value.trim();
      camForm.elements.username.value = form.elements.username.value;
      camForm.elements.password.value = form.elements.password.value;
      camForm.elements.adapter_id.value = data.recommended_adapter;
      if (form.elements.sdk_port.value) camForm.elements.sdk_port.value = form.elements.sdk_port.value;
      if (form.elements.rtsp_url.value) camForm.elements.rtsp_url.value = form.elements.rtsp_url.value;
      if (data.recognition_mode && camForm.elements.recognition_mode) camForm.elements.recognition_mode.value = data.recognition_mode;
    }
  } catch (err) {
    error.textContent = err.message;
  }
});
document.getElementById("onboard-test").addEventListener("click", async () => {
  const form = document.getElementById("onboard-form");
  const error = document.getElementById("onboard-error");
  const result = document.getElementById("onboard-result");
  error.textContent = "";
  try {
    const data = await api("/cameras/onboard/test", {
      method: "POST",
      body: JSON.stringify({
        ip_address: form.elements.ip_address.value.trim(),
        username: form.elements.username.value,
        password: form.elements.password.value,
        adapter_id: "rtsp",
        sdk_port: form.elements.sdk_port.value ? Number(form.elements.sdk_port.value) : 30000,
        rtsp_url: form.elements.rtsp_url.value.trim(),
        duration_seconds: 3,
      }),
      timeoutMs: 20000,
    });
    result.classList.remove("hidden");
    result.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    error.textContent = err.message;
  }
});
document.getElementById("add-vehicle").addEventListener("click", () => openVehicleDialog(null));
document.getElementById("refresh-vehicles").addEventListener("click", loadVehicles);
document.getElementById("refresh-sessions").addEventListener("click", loadSessions);
document.getElementById("refresh-payments").addEventListener("click", loadPayments);
document.getElementById("print-session-receipt").addEventListener("click", async () => {
  const err = document.getElementById("session-error");
  const out = document.getElementById("session-receipt");
  err.textContent = "";
  if (!selectedSessionId) {
    err.textContent = "Select a session first.";
    return;
  }
  try {
    const issued = await api(`/sessions/${selectedSessionId}/receipt`, { method: "POST", body: "{}" });
    const body = (issued && issued.receipt) || "";
    const qrUrl = issued && (issued.qr_url || (issued.public_token ? `/p/${issued.public_token}/qr.png` : ""));
    const safe = (body || "").replace(/[&<>]/g, (ch) => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[ch]));
    const qrSrc = qrUrl
      ? (qrUrl.startsWith("http") ? qrUrl : `${location.origin}${qrUrl}`)
      : "";
    const qrBlock = qrSrc
      ? `<p style="margin:16px 0;text-align:center"><img src="${qrSrc}" alt="Payment QR" style="width:200px;height:200px;border:1px solid #ccc;padding:8px;background:#fff"></p><p class="muted">Scan this QR at the kiosk if the camera cannot read the plate.</p>`
      : "";
    out.classList.remove("hidden");
    out.innerHTML = `<pre style="margin:0;white-space:pre-wrap;word-break:break-word">${safe || "Receipt stored."}</pre>${qrBlock}`;
    const printer = window.open("", "smartpark-receipt", "width=480,height=720");
    if (printer) {
      printer.document.write(`<!DOCTYPE html><html><head><title>Parking receipt</title><style>body{font:14px/1.4 ui-monospace,monospace;padding:16px;max-width:420px}pre{white-space:pre-wrap;word-break:break-word}</style></head><body><pre>${safe}</pre>${qrBlock}</body></html>`);
      printer.document.close();
      printer.focus();
      setTimeout(() => printer.print(), 400);
    }
  } catch (e) {
    err.textContent = e.message;
  }
});
