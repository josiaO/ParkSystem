function dashboardCards(stats) {
  const kind = deploymentKind();
  const online = stats.sdk_connected ?? 0;
  const cameras = stats.cameras ?? 0;
  if (kind === "lpr") {
    return [
      ["Cameras online", online],
      ["Cameras configured", cameras],
      ["Registered vehicles", stats.registered_plates ?? 0],
    ];
  }
  if (kind === "security") {
    return [
      ["Cameras online", online],
      ["Cameras configured", cameras],
      ["Active notices", (stats.alerts || []).length],
    ];
  }
  if (kind === "access") {
    return [
      ["Registered vehicles", stats.registered_plates ?? 0],
      ["Cameras online", online],
      ["Devices configured", cameras],
    ];
  }
  return [
    ["Vehicles inside", stats.vehicles_inside],
    ["Entries today", stats.entries_today],
    ["Exits today", stats.exits_today],
    ["Revenue today", stats.revenue_today_label || moneyLabel(stats.revenue_today, stats.currency)],
    ["Unpaid sessions", stats.unpaid_active],
    ["Subscribers inside", stats.subscribers_inside],
  ];
}

async function loadDetections() {
  const err = document.getElementById("detection-error");
  const body = document.getElementById("detection-rows");
  if (!body) return;
  if (err) err.textContent = "";
  const q = ((document.getElementById("detect-filter") || {}).value || "").trim().toUpperCase();
  try {
    const rows = await api("/captures?limit=50");
    const filtered = (rows || []).filter((row) => !q || String(row.plate || "").toUpperCase().includes(q));
    body.innerHTML = filtered.map((row) => {
      const pct = confidencePercent(row.confidence);
      const held = row.pending_confirmation || row.needs_review;
      const status = held ? `<span class="chip c-wrn">Check plate</span>` : `<span class="chip c-ok">Read</span>`;
      return `<tr class="click" data-det="${row.id}">
        <td>${formatWhen(row.created_at)}</td>
        <td><span class="plate">${row.plate || "—"}</span></td>
        <td>${row.camera_id ?? "—"}</td>
        <td>${row.lane_direction || "—"}</td>
        <td>${pct == null ? "—" : pct + "%"}</td>
        <td>${sourceLabel(row.source)}</td>
        <td>${status}</td>
      </tr>`;
    }).join("") || `<tr><td colspan="7"><div class="empty-state"><b>No detections yet.</b><p>Detected vehicles will appear here automatically.</p></div></td></tr>`;
    body.querySelectorAll("tr[data-det]").forEach((tr) => {
      tr.addEventListener("click", () => {
        const row = filtered.find((item) => String(item.id) === tr.dataset.det);
        const box = document.getElementById("detection-detail");
        const dest = document.getElementById("detection-detail-body");
        if (!box || !dest || !row) return;
        box.classList.remove("hidden");
        const pct = confidencePercent(row.confidence);
        dest.innerHTML = `
          <div class="kiosk-grid">
            <div>${row.snapshot_url ? `<img alt="Detection" src="${mediaUrl(row.snapshot_url)}" style="width:100%;max-height:240px;object-fit:contain;background:#070B10;border-radius:8px">` : `<p class="muted">No image stored.</p>`}
            ${row.crop_url ? `<img alt="Plate crop" src="${mediaUrl(row.crop_url)}" style="width:100%;max-height:80px;object-fit:contain;background:#070B10;border-radius:8px;margin-top:8px">` : ""}</div>
            <div>
              <p class="plate-chars" style="text-align:left">${row.plate || "—"}</p>
              <p>Confidence <b>${pct == null ? "—" : pct + "%"}</b></p>
              <p>Time <b>${formatWhen(row.created_at)}</b></p>
              <p>Camera <b>${row.camera_id ?? "—"}</b></p>
              <p>Source <b>${sourceLabel(row.source)}</b></p>
            </div>
          </div>`;
      });
    });
  } catch (e) {
    if (err) err.textContent = `Detections could not be loaded. ${e.message}`;
    body.innerHTML = `<tr><td colspan="7"><div class="empty-state"><b>Detections unavailable</b><p>Refresh, or ask a technician if this continues.</p></div></td></tr>`;
  }
}

const developerControlLabels = {
  developer_mode: "Enable Developer mode",
  logging_enabled: "Verbose diagnostic logging",
  printing_enabled: "Printing / receipt device",
  gate_opening_enabled: "Gate opening",
  automatic_gate_opening_enabled: "Automatic gate opening",
  recognition_enabled: "Recognition worker",
  capture_enabled: "Capture and evidence persistence",
  camera_connections_enabled: "Camera connections",
  destructive_tools_enabled: "Destructive test-data tools",
};

function parseDeveloperIds(value) {
  return String(value || "").split(",").map((item) => Number(item.trim())).filter((id) => Number.isInteger(id) && id > 0);
}

async function loadDeveloperPlayground() {
  const card = document.getElementById("developer-playground");
  const controls = document.getElementById("developer-controls");
  const counts = document.getElementById("developer-counts");
  const error = document.getElementById("developer-error");
  if (!card || !controls || !counts || !can("settings.manage")) return;
  card.style.display = "block";
  error.textContent = "";
  try {
    const [cfg, summary] = await Promise.all([api("/developer/settings"), api("/developer/summary")]);
    controls.innerHTML = Object.entries(developerControlLabels).map(([key, label]) => `
      <label class="mod-row" style="cursor:pointer">
        <input type="checkbox" class="bigck developer-control" data-dev-key="${key}" ${cfg[key] ? "checked" : ""}>
        <div><b>${label}</b><div class="muted" style="font-size:11.5px">${key === "gate_opening_enabled" ? "When off, receipt-taking may continue but no barrier actuator is called." : key === "destructive_tools_enabled" ? "Required together with Developer mode before deleting captures or sessions." : ""}</div></div>
      </label>`).join("");
    const labels = { cameras: "Cameras", gates: "Gates", captures: "Captures", sessions: "Sessions", vehicles: "Vehicles", receipts: "Receipts", payments: "Payments", audit_logs: "Audit logs" };
    counts.innerHTML = Object.entries(labels).map(([key, label]) => `<div class="stat"><div class="k">${label}</div><div class="v">${Number((summary.counts || {})[key] || 0)}</div></div>`).join("");
    document.getElementById("developer-save").onclick = async () => {
      error.textContent = "";
      try {
        const payload = {};
        document.querySelectorAll(".developer-control").forEach((el) => { payload[el.dataset.devKey] = el.checked; });
        await api("/developer/settings", { method: "PATCH", body: JSON.stringify(payload) });
        toast("Developer controls saved", "info");
        await loadDeveloperPlayground();
      } catch (e) { error.textContent = e.message; }
    };
    document.getElementById("developer-refresh").onclick = loadDeveloperPlayground;
    document.getElementById("developer-delete-captures").onclick = async () => {
      const ids = parseDeveloperIds(document.getElementById("developer-capture-ids").value);
      if (!ids.length || !confirm(`Delete ${ids.length} capture(s) and their image files?`)) return;
      try { await api("/developer/captures/bulk-delete", { method: "POST", body: JSON.stringify({ ids, confirm: true }) }); document.getElementById("developer-capture-ids").value = ""; await loadDeveloperPlayground(); }
      catch (e) { error.textContent = e.message; }
    };
    document.getElementById("developer-delete-sessions").onclick = async () => {
      const ids = parseDeveloperIds(document.getElementById("developer-session-ids").value);
      if (!ids.length || !confirm(`Delete ${ids.length} session(s) and their test ledger rows?`)) return;
      try { await api("/developer/sessions/bulk-delete", { method: "POST", body: JSON.stringify({ ids, confirm: true }) }); document.getElementById("developer-session-ids").value = ""; await loadDeveloperPlayground(); }
      catch (e) { error.textContent = e.message; }
    };
  } catch (e) {
    card.style.display = "none";
    if (can("settings.manage")) toast(`Developer tools unavailable: ${e.message}`, "warn");
  }
}

async function loadModuleManagement() {
  const card = document.getElementById("module-management");
  const profileSelect = document.getElementById("module-profile");
  const controls = document.getElementById("module-controls");
  const help = document.getElementById("module-profile-help");
  const error = document.getElementById("module-error");
  if (!card || !profileSelect || !controls || !can("settings.manage")) return;
  card.style.display = "block";
  error.textContent = "";
  const escapeHtml = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#39;");
  try {
    const [moduleBody, profileBody] = await Promise.all([api("/modules"), api("/modules/profiles")]);
    const config = moduleBody.config || {};
    const modules = moduleBody.modules || [];
    const profiles = profileBody.profiles || [];
    profileSelect.innerHTML = profiles.map((profile) =>
      `<option value="${escapeHtml(profile.id)}">${escapeHtml(profile.name || profile.id)}</option>`
    ).join("");
    profileSelect.value = config.profile || "CUSTOM";
    const profileDescription = new Map(profiles.map((profile) => [profile.id, profile.description || ""]));
    const render = () => {
      const selectedProfile = profileSelect.value || "CUSTOM";
      const custom = selectedProfile === "CUSTOM";
      help.textContent = profileDescription.get(selectedProfile) || (custom
        ? "Select the modules this site should expose. Required dependencies are added by the server."
        : "");
      controls.innerHTML = modules.map((module) => {
        const inProfile = selectedProfile !== "CUSTOM" && profiles.find((profile) => profile.id === selectedProfile)?.modules?.includes(module.id);
        const required = module.id === "core.identity" || module.id === "core.sites";
        const checked = custom ? (Boolean(module.enabled) || required) : Boolean(inProfile);
        const dependencies = (module.required_dependencies || []).join(", ");
        return `<label class="mod-row" style="cursor:${custom && !required ? "pointer" : "default"}">
          <input type="checkbox" class="bigck module-control" data-module-id="${escapeHtml(module.id)}" ${checked ? "checked" : ""} ${!custom || required ? "disabled" : ""}>
          <div style="flex:1"><b style="font-size:13px">${escapeHtml(module.name || module.id)}</b><div class="muted" style="font-size:11.5px"><span class="mono">${escapeHtml(module.id)}</span>${dependencies ? ` · needs ${escapeHtml(dependencies)}` : ""}</div></div>
        </label>`;
      }).join("");
    };
    profileSelect.onchange = render;
    render();
    document.getElementById("module-refresh").onclick = loadModuleManagement;
    document.getElementById("module-save").onclick = async () => {
      error.textContent = "";
      try {
        const selectedProfile = profileSelect.value || "CUSTOM";
        let result;
        if (selectedProfile === "CUSTOM") {
          const moduleById = new Map(modules.map((module) => [module.id, module]));
          const enabled = new Set([...document.querySelectorAll(".module-control:checked")].map((el) => el.dataset.moduleId));
          let changed = true;
          while (changed) {
            changed = false;
            [...enabled].forEach((moduleId) => {
              (moduleById.get(moduleId)?.required_dependencies || []).forEach((dependency) => {
                if (!enabled.has(dependency)) {
                  enabled.add(dependency);
                  changed = true;
                }
              });
            });
          }
          result = await api("/modules/enabled", { method: "PUT", body: JSON.stringify({ enabled: [...enabled], profile: "CUSTOM" }) });
        } else {
          result = await api("/modules/profile", { method: "PUT", body: JSON.stringify({ profile: selectedProfile }) });
        }
        state.modules = result || state.modules;
        await refreshSessionContext();
        await loadModuleManagement();
        toast("Module configuration saved", "info");
      } catch (e) {
        error.textContent = e.message || "Module configuration could not be saved.";
      }
    };
  } catch (e) {
    card.style.display = "block";
    error.textContent = e.message || "Module configuration unavailable.";
  }
}

async function loadSettingsPage() {
  const box = document.getElementById("settings-summary");
  if (!box) return;
  try {
    const [site, clock] = await Promise.all([api("/settings/site"), api("/settings/clock")]);
    state.siteTimezone = site.timezone || "UTC";
    if (site.currency) state.siteCurrency = site.currency;
    const lang = { en: "English", sw: "Kiswahili", ar: "Arabic", fr: "French", pt: "Portuguese" }[site.language] || site.language || "—";
    box.innerHTML = `<div class="biz-grid">
      <div><span>Site</span><b>${site.name || "—"}</b></div>
      <div><span>Timezone</span><b>${site.timezone || "UTC"}</b></div>
      <div><span>Site clock</span><b>${clock.site_time || "—"}</b></div>
      <div><span>Currency</span><b>${site.currency || "—"}</b></div>
      <div><span>Language</span><b>${lang}</b></div>
    </div>
    <p class="muted" style="margin-top:12px">Change these during setup, or in Testing &amp; Simulation when you have permission.</p>`;
  } catch (e) {
    box.innerHTML = `<div class="empty-state"><b>Settings unavailable</b><p>${e.message}</p></div>`;
  }

  await loadModuleManagement();
  await loadDeveloperPlayground();

  const nodeCard = document.getElementById("node-management");
  const nodeBody = document.getElementById("node-management-body");
  if (!nodeCard || !nodeBody || !can("settings.manage")) return;
  try {
    const [nodes, gates] = await Promise.all([api("/nodes"), api("/gates")]);
    nodeCard.style.display = "block";
    const escapeHtml = (value) => String(value == null ? "" : value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
    const gateList = Array.isArray(gates) ? gates : [];
    const gateName = new Map(gateList.map((gate) => [Number(gate.id), gate.name || `Gate ${gate.id}`]));
    if (!Array.isArray(nodes) || !nodes.length) {
      nodeBody.innerHTML = `<div class="empty-state"><b>No Edge Nodes registered</b><p>Install the node role on the remote PC and complete its setup first.</p></div>`;
      return;
    }
    const options = gateList.map((gate) => `<option value="${Number(gate.id)}">${escapeHtml(gate.name || `Gate ${gate.id}`)}</option>`).join("");
    nodeBody.innerHTML = nodes.map((node) => {
      const assigned = (node.assigned_gate_ids || []).map((id) => gateName.get(Number(id)) || `Gate ${id}`);
      return `<div class="card" style="margin-top:10px;padding:12px;display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap">
        <div><b>${escapeHtml(node.name || node.node_id)}</b><div class="muted">${escapeHtml(node.node_id)} · ${escapeHtml(node.status || "UNKNOWN")} · ${assigned.length ? `Assigned: ${escapeHtml(assigned.join(", "))}` : "Unassigned"}</div></div>
        <div style="display:flex;gap:8px;align-items:center"><select data-node-gate="${escapeHtml(node.node_id)}" ${options ? "" : "disabled"}>${options || "<option>No gates available</option>"}</select><button type="button" data-node-assign="${escapeHtml(node.node_id)}" ${options ? "" : "disabled"}>Assign gate</button></div>
      </div>`;
    }).join("");
    nodeBody.querySelectorAll("[data-node-assign]").forEach((button) => {
      button.addEventListener("click", async () => {
        const nodeId = button.dataset.nodeAssign;
        const select = nodeBody.querySelector(`[data-node-gate="${CSS.escape(nodeId)}"]`);
        const gateId = Number(select && select.value);
        if (!nodeId || !gateId) return;
        button.disabled = true;
        try {
          await api(`/nodes/${encodeURIComponent(nodeId)}/assignments`, {
            method: "PUT",
            body: JSON.stringify({ gate_id: gateId, enabled: true, replace: true }),
          });
          toast("Node gate assignment saved.", "info");
          await loadSettingsPage();
        } catch (error) {
          toast(error.message || "Could not assign the gate.", "warn");
        } finally {
          button.disabled = false;
        }
      });
    });
  } catch (e) {
    if (e && e.status === 403) {
      nodeCard.style.display = "none";
      return;
    }
    nodeCard.style.display = "block";
    nodeBody.innerHTML = `<div class="empty-state"><b>Edge Node assignments unavailable</b><p>${e.message}</p></div>`;
  }
}

async function loadDashboard() {
  const el = document.getElementById("dashboard-summary");
  const cards = document.getElementById("dashboard-cards");
  try {
    const stats = await api("/dashboard");
    const items = dashboardCards(stats);
    const lanesTitle = document.getElementById("dashboard-lanes-title");
    if (lanesTitle) {
      const kind = deploymentKind();
      lanesTitle.textContent = kind === "lpr" || kind === "security" ? "Camera health" : "Lane status";
    }
    cards.className = "statband";
    cards.innerHTML = items.map(([label, value]) =>
      `<div class="stat"><div class="k">${label}</div><div class="v">${value ?? 0}</div></div>`
    ).join("");
    const lanes = document.getElementById("dashboard-lanes");
    if (lanes) {
      const rows = stats.lanes || [];
      lanes.innerHTML = rows.map((lane) => {
        const video = String(lane.live_video || "—");
        const alpr = String(lane.plate_recognition || "—");
        const barrier = String(lane.barrier || "—");
        const chip = (v) => {
          const s = v.toLowerCase();
          if (s.includes("ok") || s.includes("online") || s.includes("ready") || s.includes("open")) return "c-ok";
          if (s.includes("disabled") || s.includes("off") || s === "—") return "c-mut";
          if (s.includes("warn") || s.includes("degraded")) return "c-wrn";
          if (s.includes("down") || s.includes("fail") || s.includes("error")) return "c-dgr";
          return "c-info";
        };
        return `<div class="gate-card"><h3>${lane.label || lane.name || ""}</h3>
          <p>Camera: ${lane.camera || "—"}</p>
          <p>Live Video: <span class="chip ${chip(video)}">${video}</span></p>
          <p>Plate Recognition: <span class="chip ${chip(alpr)}">${alpr}</span></p>
          <p>Barrier: <span class="chip ${chip(barrier)}">${barrier}</span></p>
        </div>`;
      }).join("") || `<div class="card card-b empty-state"><b>No lanes yet</b><p>Add a camera to start live monitoring and plate recognition.</p></div>`;
    }
    if (stats.currency) state.siteCurrency = stats.currency;
    const alerts = (stats.alerts && stats.alerts.length) ? stats.alerts.join(" · ") : "No hardware alerts.";
    el.className = (stats.alerts && stats.alerts.length) ? "notice" : "muted";
    el.textContent = alerts;
    refreshBackupBanner();
  } catch (err) {
    el.textContent = `Unable to load dashboard: ${err.message}`;
  }
}

function stopHealth() {
  if (healthTimer) { clearInterval(healthTimer); healthTimer = null; }
}

function healthTone(value) {
  const s = String(value == null ? "" : value).toLowerCase();
  if (s === "disabled" || s === "off" || s === "n/a" || s.startsWith("n/a ") || s === "—") return "c-mut";
  if (s === "ok" || s === "healthy" || s === "ready" || s === "online" || s === "up") return "c-ok";
  if (s === "warn" || s === "degraded" || s === "warning") return "c-wrn";
  if (s === "down" || s === "critical" || s === "error" || s === "fail") return "c-dgr";
  return "c-info";
}

function stopHdrHealth() {
  if (hdrHealthTimer) { clearInterval(hdrHealthTimer); hdrHealthTimer = null; }
}

async function refreshHdrHealth() {
  if (!state.token || appView.classList.contains("hidden")) return;
  try {
    const live = await api("/health/live");
    const st = String(live.state || live.status || "ok").toLowerCase();
    if (st.includes("critical") || st.includes("down")) setHdrHealth("Critical", "c-dgr");
    else if (st.includes("degrad") || st.includes("warn")) setHdrHealth("Degraded", "c-wrn");
    else setHdrHealth("Operational", "c-ok");
  } catch (_) {
    setHdrHealth("Unreachable", "c-wrn");
  }
}

function startHdrHealth() {
  stopHdrHealth();
  refreshHdrHealth();
  hdrHealthTimer = setInterval(refreshHdrHealth, 8000);
}

function healthSentences(details, live) {
  const status = String(details.status || details.state || (live && live.state) || "ok");
  const lines = [`The site is ${status.replaceAll("_", " ")}.`];
  const hvx = details.hvx_host || {};
  if (hvx.ok) lines.push("The camera host that talks to HVX cameras is running.");
  else if (hvx.required === false || hvx.supported === false) lines.push("This computer does not run the Windows HVX camera host. IP cameras can still be used.");
  else if (details.hvx_host) lines.push("The HVX camera host is not responding. Parking can continue on cameras that do not need it.");
  const modules = (details.modules && details.modules.components) || details.modules || {};
  Object.keys(modules).forEach((key) => {
    if (["components", "profile", "enabled_modules"].includes(key)) return;
    const item = modules[key];
    const state = (item && (item.state || item.status)) || (typeof item === "string" ? item : "");
    if (!state) return;
    const label = key.replaceAll("_", " ");
    const lower = String(state).toLowerCase();
    if (lower.includes("disabled") || lower === "n/a" || lower.includes("neutral")) {
      lines.push(`${label} is turned off. That is normal when you are not using it.`);
    } else if (lower.includes("ok") || lower.includes("ready") || lower.includes("healthy")) {
      lines.push(`${label} is working.`);
    } else {
      lines.push(`${label} needs attention (${state}).`);
    }
  });
  const pay = (details.domains && details.domains.payment) || {};
  if (pay.active_mobile_provider && pay.active_mobile_provider !== "simulated") {
    const prov = (pay.providers || {})[pay.active_mobile_provider] || {};
    if (prov.available) lines.push(`Phone payments go through ${pay.active_mobile_provider} in ${prov.mode || "?"} mode. Money is only marked paid after the provider confirms it.`);
    else lines.push(`Phone payments via ${pay.active_mobile_provider} are not available: ${prov.reason || "not configured"}. Cash and kiosk payments still work.`);
  }
  if (lines.length === 1) lines.push("No extra warnings.");
  return lines;
}

async function refreshBackupBanner() {
  const banner = document.getElementById("backup-banner");
  if (!banner) return;
  try {
    const status = await api("/backup");
    if (status.offline_due || status.cloud_due) {
      const bits = [];
      if (status.offline_due) bits.push(status.offline_message);
      if (status.cloud_due) bits.push(status.cloud_message);
      banner.classList.remove("hidden");
      banner.innerHTML = `${bits.join(" ")} <button type="button" id="backup-banner-open">Open reports</button> <button type="button" class="secondary" id="backup-banner-snooze">Remind me tomorrow</button>`;
      document.getElementById("backup-banner-open").addEventListener("click", () => showPage("reports"));
      document.getElementById("backup-banner-snooze").addEventListener("click", async () => {
        await api("/backup/snooze", { method: "POST", body: "{}" });
        banner.classList.add("hidden");
      });
    } else {
      banner.classList.add("hidden");
      banner.textContent = "";
    }
  } catch (_) {
    banner.classList.add("hidden");
  }
}

async function loadHealth() {
  const cards = document.getElementById("health-cards");
  const pre = document.getElementById("health-details");
  try {
    const live = await api("/health/live");
    let details = live;
    try { details = await api("/health/details"); }
    catch (_) {
      try { details = await api("/health/ready"); } catch (e) { details = { live, error: e.message }; }
    }
    const proc = details.process || live.process || {};
    const modules = details.modules || live.modules || {};
    const hvx = details.hvx_host || {};
    let hvxLabel = "disabled";
    if (hvx.ok) hvxLabel = "ok";
    else if (hvx.required === false || hvx.supported === false) hvxLabel = "n/a (web OS)";
    else if (details.hvx_host) hvxLabel = "down";
    const items = [
      ["State", details.status || details.state || live.state || "—"],
      ["OS", (details.platform && details.platform.os) || "—"],
      ["Version", proc.version || "—"],
      ["Uptime s", proc.uptime_seconds ?? "—"],
      ["Threads", proc.thread_count ?? "—"],
      ["HVX host", hvxLabel],
      ["ALPR mode", details.alpr_mode || "FASTALPR_ONLY"],
    ];
    const pay = (details.domains && details.domains.payment) || {};
    if (pay.active_mobile_provider) {
      const prov = (pay.providers || {})[pay.active_mobile_provider] || {};
      const mode = prov.mode ? ` ${prov.mode}` : "";
      items.push(["Mobile pay", `${pay.active_mobile_provider}${mode}`]);
    }
    const components = (modules && modules.components) || modules || {};
    Object.keys(components).forEach((key) => {
      if (key === "components" || key === "profile" || key === "enabled_modules") return;
      const m = components[key];
      const val = (m && (m.state || m.status)) || (typeof m === "string" ? m : "—");
      items.push([String(key).toUpperCase(), val]);
    });
    cards.className = "statband";
    cards.innerHTML = items.map(([label, value]) =>
      `<div class="stat"><div class="k">${label}</div><div class="v"><span class="chip ${healthTone(value)}">${value}</span></div></div>`
    ).join("");
    const st = String(details.status || details.state || live.state || "ok").toLowerCase();
    if (st.includes("critical") || st.includes("down") || st.includes("not_ready")) setHdrHealth("Critical", "c-dgr");
    else if (st.includes("degrad") || st.includes("warn")) setHdrHealth("Degraded", "c-wrn");
    else setHdrHealth("Operational", "c-ok");
    const plain = document.getElementById("health-plain");
    if (plain) plain.innerHTML = healthSentences(details, live).map((line) => `<p>${line}</p>`).join("");
    pre.textContent = JSON.stringify(details, null, 2);
  } catch (err) {
    pre.textContent = err.message;
    setHdrHealth("Unreachable", "c-wrn");
  }
}

function startHealth() {
  stopHealth();
  loadHealth();
  healthTimer = setInterval(loadHealth, 3000);
}
