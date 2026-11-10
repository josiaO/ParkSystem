function can(permission) {
  return state.permissions.includes("*") || state.permissions.includes(permission);
}

function isTechnician() {
  return can("hardware.view");
}

function syncRoleClass() {
  document.body.classList.toggle("role-tech", isTechnician());
}

const FRIENDLY_NAV = {
  "Plate Engine": "Detections",
  "Simulation": "Testing & Simulation",
  "Tariffs": "Tariffs & Schedules",
  "Users": "Users & Roles",
};

function friendlyNavLabel(label) {
  return FRIENDLY_NAV[label] || label;
}

function setNavLabel(btn, label) {
  const text = friendlyNavLabel(label);
  const slot = btn.querySelector(".sl-label");
  if (slot) slot.textContent = text;
  else btn.textContent = text;
  btn.title = text;
}

function deploymentKind() {
  const profile = String((state.modules && state.modules.profile) || "");
  const enabled = new Set((state.modules && state.modules.enabled) || []);
  if (profile === "LPR_ONLY") return "lpr";
  if (profile === "SECURITY") return "security";
  if (profile === "ACCESS_CONTROL") return "access";
  if (profile === "PARKING_LITE" || profile === "PARKING_PRO" || profile === "ENTERPRISE") return "parking";
  if (enabled.has("parking.sessions") || enabled.has("payments.core")) return "parking";
  if (enabled.has("security.watchlists") || enabled.has("security.alerts")) return "security";
  if (enabled.has("access.gates")) return "access";
  if (enabled.has("recognition.alpr")) return "lpr";
  return "parking";
}

function confidencePercent(value) {
  if (value == null || value === "") return null;
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  return Math.round(n <= 1 ? n * 100 : n);
}

function sourceLabel(source) {
  const s = String(source || "").toLowerCase();
  if (!s || s === "—") return "—";
  if (s.includes("operator")) return "Operator";
  if (s.includes("hybrid") || s.includes("fusion")) return "Camera + Zirp";
  if (s.includes("fast") || s.includes("local") || s.includes("smartpark")) return "Zirp AI";
  if (s.includes("native") || s.includes("camera") || s.includes("sdk")) return "Camera";
  return isTechnician() ? String(source) : "Recognition";
}

function moneyLabel(amount, currency) {
  const cur = String(currency || state.siteCurrency || "").trim();
  const n = Number(amount || 0);
  const formatted = n.toLocaleString(undefined, {
    minimumFractionDigits: Number.isInteger(n) ? 0 : 2,
    maximumFractionDigits: 2,
  });
  return cur ? `${cur} ${formatted}` : formatted;
}

function methodLabel(method) {
  const m = String(method || "").toLowerCase();
  if (!m) return "—";
  if (m.includes("cash")) return "Cash";
  if (m.includes("card")) return "Card";
  if (m.includes("mobile") || m.includes("m-pesa") || m.includes("mpesa") || m.includes("wallet")) return "Mobile Money";
  return isTechnician() ? String(method) : "Other";
}

function paymentChip(status) {
  const s = String(status || "").toUpperCase();
  if (s === "PAID" || s === "SUCCEEDED" || s === "SUCCESS") return `<span class="chip c-ok">${s === "SUCCEEDED" || s === "SUCCESS" ? "PAID" : s}</span>`;
  if (s === "PENDING" || s === "CREATED") return `<span class="chip c-wrn">${s}</span>`;
  if (s === "UNPAID" || s === "FAILED" || s === "EXPIRED") return `<span class="chip c-dgr">${s}</span>`;
  if (s.includes("REFUND")) return `<span class="chip c-info">${s}</span>`;
  return `<span class="chip c-mut">${s || "—"}</span>`;
}

function cameraHealth(status) {
  const s = String(status || "").toLowerCase();
  if (s.includes("online") || s.includes("connected") || s === "ok") return ["Online", "c-ok"];
  if (s.includes("discover")) return ["Discovered", "c-info"];
  if (!s) return ["Unknown", "c-mut"];
  if (s.includes("error") || s.includes("fail") || s.includes("offline")) return ["Offline", "c-dgr"];
  return [status, "c-wrn"];
}

function detailMessage(detail, fallback) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg || JSON.stringify(item)).join("; ");
  return fallback;
}

async function loadSim() {
  const error = document.getElementById("sim-error");
  error.textContent = "";
  try {
    const lanes = await api("/lanes");
    const select = document.getElementById("sim-gate");
    const current = select.value;
    select.innerHTML = lanes.map((g) => `<option value="${g.id}">${g.name}</option>`).join("");
    if (current && [...select.options].some((o) => o.value === current)) select.value = current;
    const box = document.getElementById("sim-parking");
    if (can("simulation.run")) {
      box.classList.remove("hidden");
      const cfg = await api("/settings/parking");
      document.getElementById("park-receipt").checked = Boolean(cfg.receipt_required_before_open);
      document.getElementById("park-policy").value = cfg.receipt_policy || "PRINT_AND_OPEN";
      document.getElementById("park-pay").checked = Boolean(cfg.exit_requires_payment);
      document.getElementById("park-prompt").value = cfg.pay_prompt || "";
      const select = document.getElementById("park-printer");
      const printers = await api("/printers/status");
      const chosen = cfg.printer_name || printers.printer_name || "";
      const options = [`<option value="">File only (no paper)</option>`];
      (printers.printers || []).forEach((row) => {
        const bits = [];
        if (row.is_usb) bits.push("USB");
        if (row.is_default) bits.push("default");
        const label = bits.length ? `${row.name} (${bits.join(", ")})` : row.name;
        options.push(`<option value="${row.name}">${label}</option>`);
      });
      if (chosen && !(printers.printers || []).some((row) => row.name === chosen)) {
        options.push(`<option value="${chosen}">${chosen}</option>`);
      }
      select.innerHTML = options.join("");
      const site = await api("/settings/site");
      state.siteTimezone = site.timezone || "UTC";
      document.getElementById("site-timezone").value = state.siteTimezone;
      document.getElementById("site-currency").value = site.currency || "";
      document.getElementById("site-language").value = site.language || "en";
      document.getElementById("site-plate-validation").value = site.plate_validation || "NONE";
      document.getElementById("site-public-url").value = site.public_base_url || "";
      select.value = chosen;
    } else {
      box.classList.add("hidden");
    }
  } catch (err) {
    error.textContent = err.message;
  }
}

async function simAction(kind) {
  const error = document.getElementById("sim-error");
  const out = document.getElementById("sim-receipt");
  error.textContent = "";
  const gateId = Number(document.getElementById("sim-gate").value);
  try {
    let data;
    if (kind === "entry" || kind === "exit") {
      const input = document.getElementById("sim-file");
      const file = input.files && input.files[0];
      if (!file) throw new Error("Choose a JPEG photo of the car first");
      const form = new FormData();
      form.append("gate_id", String(gateId));
      form.append("side", kind === "exit" ? "EXIT" : "ENTRY");
      form.append("file", file, file.name || "car.jpg");
      data = await apiUpload("/sim/capture", form);
      simSessionId = (data.session && data.session.id) || simSessionId;
    } else if (kind === "taken") {
      if (!simSessionId) throw new Error("Upload an ENTRY photo first");
      data = await api(`/sim/sessions/${simSessionId}/receipt-taken`, { method: "POST", body: "{}" });
    } else if (kind === "pay") {
      if (!simSessionId) throw new Error("Upload an ENTRY photo first");
      data = await api(`/sim/sessions/${simSessionId}/pay`, { method: "POST", body: "{}" });
    }
    const parts = [];
    if (data.receipt) parts.push(data.receipt);
    if (data.say) parts.push(data.say);
    if (data.message) parts.push(data.message);
    const best = data.alpr && data.alpr.best;
    if (best && best.plate) parts.push(`FastALPR: ${best.plate}`);
    parts.push(JSON.stringify(data, null, 2));
    out.textContent = parts.join("\n\n");
    const preview = document.getElementById("sim-preview");
    const shown = (best && best.crop_url)
      || (data.session && data.session.crop_url)
      || (data.capture && data.capture.crop_url)
      || (data.alpr && data.alpr.annotated_url)
      || (data.session && data.session.snapshot_url);
    if (shown) { preview.src = mediaUrl(shown); preview.style.display = "block"; }
  } catch (err) {
    error.textContent = err.message;
  }
}

async function simPlate(side) {
  const error = document.getElementById("sim-error");
  const out = document.getElementById("sim-receipt");
  error.textContent = "";
  const plate = document.getElementById("sim-plate").value.trim();
  const gateId = Number(document.getElementById("sim-gate").value);
  if (!plate) { error.textContent = "Enter a number plate."; return; }
  try {
    const path = side === "EXIT" ? "/sim/exit" : "/sim/entry";
    const data = await api(path, { method: "POST", body: JSON.stringify({ plate, gate_id: gateId, side }) });
    simSessionId = (data.session && data.session.id) || simSessionId;
    const parts = [];
    if (data.receipt) parts.push(data.receipt);
    if (data.message) parts.push(data.message);
    parts.push(JSON.stringify(data, null, 2));
    out.textContent = parts.join("\n\n");
  } catch (err) {
    error.textContent = err.message;
  }
}

async function loadVehicles() {
  const error = document.getElementById("vehicle-error");
  error.textContent = "";
  try {
    const rows = await api("/vehicles");
    document.getElementById("vehicle-rows").innerHTML = rows.map((v) => `
      <tr>
        <td><input type="checkbox" data-vehicle-check="${v.id}" aria-label="Select ${v.plate}"></td>
        <td><strong>${v.plate}</strong></td>
        <td>${v.owner_name || "—"}</td>
        <td>${v.plan_name || v.plan_kind || "—"}</td>
        <td>${v.auto_open ? "Yes" : "No"}</td>
        <td>${v.enabled ? "Yes" : "No"}</td>
        <td>${(v.valid_from || "—").toString().slice(0, 10)}</td>
        <td>${(v.valid_until || "—").toString().slice(0, 10)}</td>
        <td class="row-actions">
          ${can("subscribers.manage") ? `<button type="button" data-edit-vehicle="${v.id}">Edit <kbd>${shortcutText("Ctrl+E")}</kbd></button>
          <button class="danger" type="button" data-del-vehicle="${v.id}">Delete <kbd>Del</kbd></button>` : ""}
        </td>
      </tr>`).join("") || `<tr><td colspan="9"><div class="empty-state"><b>No registered vehicles yet.</b><p>Add a vehicle so known plates can be allowed through.</p></div></td></tr>`;
  } catch (err) {
    error.textContent = err.message;
  }
}

async function openVehicleDialog(vehicle) {
  const form = document.getElementById("vehicle-form");
  form.reset();
  document.getElementById("vehicle-dialog-error").textContent = "";
  document.getElementById("vehicle-dialog-title").textContent = vehicle ? "Edit vehicle" : "Register plate";
  const plans = await api("/access-plans");
  form.elements.plan_id.innerHTML = plans.map((p) =>
    `<option value="${p.id}" ${vehicle && vehicle.plan_id === p.id ? "selected" : ""}>${p.name}</option>`
  ).join("");
  if (vehicle) {
    form.elements.id.value = vehicle.id;
    form.elements.plate.value = vehicle.plate;
    form.elements.owner_name.value = vehicle.owner_name || "";
    form.elements.enabled.value = vehicle.enabled ? "true" : "false";
    form.elements.notes.value = vehicle.notes || "";
    form.elements.valid_from.value = (vehicle.valid_from || "").slice(0, 10);
    form.elements.valid_until.value = (vehicle.valid_until || "").slice(0, 10);
  } else {
    form.elements.valid_from.value = "";
    form.elements.valid_until.value = "";
  }
  document.getElementById("vehicle-dialog").showModal();
}

async function apiUpload(path, form) {
  const headers = {};
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const res = await fetch(path, { method: "POST", headers, body: form });
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = { detail: text }; }
  if (!res.ok) {
    const err = new Error(detailMessage(data && data.detail, res.statusText));
    err.status = res.status;
    throw err;
  }
  return data;
}

function showPage(name) {
  if (!pages.includes(name)) name = "dashboard";
  document.querySelectorAll("nav button[data-page]").forEach((b) => {
    const on = b.dataset.page === name;
    b.classList.toggle("active", on);
    b.classList.toggle("on", on);
  });
  pages.forEach((page) => {
    const el = document.getElementById(`page-${page}`);
    if (el) el.classList.toggle("hidden", page !== name);
  });
  const navItem = (state.navigation || []).find((n) => n.page === name || (name === "detections" && n.id === "plates"));
  document.getElementById("page-title").textContent = friendlyNavLabel((navItem && navItem.label) || {
    dashboard: "Dashboard", health: "System Health", cameras: "Live Gates", gates: "Gates",
    detections: "Detections", sessions: "Parking Sessions", vehicles: "Vehicles", payments: "Payments",
    fees: "Tariffs & Schedules", reports: "Reports", users: "Users & Roles", hardware: "Hardware Lab",
    sim: "Testing & Simulation", onboarding: "Setup Wizard", watchlists: "Watchlists",
    alerts: "Alerts", incidents: "Incidents", settings: "Settings",
  }[name] || name);
  const sub = document.getElementById("page-subtitle");
  if (sub) {
    const kind = deploymentKind();
    sub.textContent = {
      dashboard: kind === "lpr" ? "Detections, cameras, and recognition health"
        : kind === "security" ? "Alerts, cameras, and recognition health"
        : kind === "access" ? "Access events, vehicles, and devices"
        : "Vehicles on site, lanes, and payments",
      health: "Healthy, degraded, offline, or disabled. Disabled is neutral.",
      cameras: kind === "lpr" || kind === "security" ? "Monitor cameras and the latest plate read." : "Monitor active lanes and respond to access issues.",
      gates: "Barrier control for each entry or exit.",
      detections: "Search recent plate reads.",
      sessions: "Plate, duration, amount, and payment.",
      vehicles: "Registered vehicles and access plans.",
      payments: "Method, amount, and payment status.",
      fees: "Tariffs and schedules for this site.",
      reports: "Visits, revenue, and backups.",
      users: "Accounts and roles.",
      hardware: "Technician diagnostics for cameras, video, recognition, and gates.",
      sim: "Practice entry and exit without live cameras.",
      onboarding: "Choose what this site is for, then confirm it is ready.",
      watchlists: "Blocked, protected, and staff vehicles.",
      alerts: "Vehicles that need attention.",
      incidents: "Follow-up from alerts.",
      settings: "Site name, time, currency, and language.",
    }[name] || "";
  }
  if (name === "dashboard") loadDashboard();
  if (name === "detections") loadDetections();
  if (name === "settings") loadSettingsPage();
  if (name === "health") startHealth();
  else stopHealth();
  if (name === "cameras") { loadCameras(); showCameraSub(cameraSub || "live"); }
  else stopLive();
  if (name === "gates") loadGates();
  if (name === "sessions") loadSessions();
  if (name === "vehicles") loadVehicles();
  if (name === "payments") loadPayments();
  if (name === "fees") loadFees();
  if (name === "reports") loadReports();
  if (name === "users") loadUsers();
  if (name === "hardware") loadHardware();
  if (name === "sim") loadSim();
  if (name === "onboarding") loadOnboarding();
}

async function api(path, options = {}) {
  const { timeoutMs, ...rest } = options;
  const headers = { ...(rest.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  if (rest.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  const ctrl = timeoutMs ? new AbortController() : null;
  const timer = timeoutMs ? setTimeout(() => ctrl.abort(), timeoutMs) : null;
  try {
    const res = await fetch(path, { ...rest, headers, signal: ctrl ? ctrl.signal : rest.signal });
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = { detail: text }; }
    if (!res.ok) {
      const err = new Error(detailMessage(data && data.detail, res.statusText));
      err.status = res.status;
      throw err;
    }
    return data;
  } catch (err) {
    if (err && err.name === "AbortError") {
      const timeout = new Error("Camera took too long to respond and was skipped.");
      timeout.status = 504;
      throw timeout;
    }
    throw err;
  } finally {
    if (timer) clearTimeout(timer);
  }
}

function applyModuleNavigation() {
  const nav = state.navigation || [];
  const byId = Object.fromEntries(nav.map((n) => [n.id, n]));
  const hasModuleNav = nav.length > 0;

  document.querySelectorAll("nav button[data-nav-id]").forEach((btn) => {
    const navId = btn.dataset.navId;
    const item = byId[navId];
    let visible = false;
    if (hasModuleNav) {
      // Settings is the recovery surface for module configuration. Keep
      // it reachable for an authorized administrator even if a custom
      // profile accidentally omitted the core.sites navigation item.
      visible = navId === "settings" && can("settings.view") ? true : Boolean(item);
      if (item) setNavLabel(btn, item.label);
    } else {
      // Permission-only fallback when /auth/me has no navigation yet.
      const permMap = {
        dashboard: "dashboard.view",
        cameras: "cameras.view",
        health: "hardware.view",
        plates: "cameras.view",
        sessions: "sessions.view",
        vehicles: "subscribers.view",
        watchlists: null,
        alerts: null,
        incidents: null,
        payments: "payments.view",
        fees: "fees.view",
        reports: "dashboard.view",
        onboarding: "settings.manage",
        gates: "gates.view",
        users: "users.view",
        settings: "settings.view",
        hardware: "hardware.view",
        sim: "simulation.run",
      };
      const perm = permMap[navId];
      if (navId === "dashboard") visible = true;
      else if (navId === "sessions") visible = can("sessions.view") || can("fees.view") || can("kiosk.use");
      else if (navId === "payments") visible = can("payments.view") || can("fees.view") || can("kiosk.use");
      else if (navId === "health" || navId === "hardware") visible = can("hardware.view");
      else if (navId === "watchlists" || navId === "alerts" || navId === "incidents" || navId === "onboarding") visible = false;
      else if (navId === "plates") visible = can("cameras.view") && !can("sessions.view");
      else visible = Boolean(perm && can(perm));
    }
    btn.style.display = visible ? "" : "none";
  });

  pages = [...document.querySelectorAll("nav button[data-nav-id]")]
    .filter((b) => b.style.display !== "none")
    .map((b) => b.dataset.page);
  if (!pages.includes("dashboard")) pages.unshift("dashboard");
  ["onboarding", "watchlists", "alerts", "incidents", "detections", "settings"].forEach((page) => {
    if (!pages.includes(page)) pages.push(page);
  });

  document.querySelectorAll("nav .group").forEach((group) => {
    let next = group.nextElementSibling;
    let anyVisible = false;
    while (next && !next.classList.contains("group")) {
      if (next.matches("button[data-nav-id]") && next.style.display !== "none") anyVisible = true;
      next = next.nextElementSibling;
    }
    group.style.display = anyVisible ? "" : "none";
  });
  syncRoleClass();
  setManageVisibility();
}

let onboardState = { step: 1, status: null, draft: {} };

function updateOnboardStepsUi(step) {
  const n = Number(step) || 1;
  const steps = (onboardState.status && onboardState.status.steps) || [
    {id:1,label:"Purpose"},{id:2,label:"Site"},{id:3,label:"Hardware"},{id:4,label:"Recognition"},
    {id:5,label:"Features"},{id:6,label:"Users"},{id:7,label:"Readiness"},{id:8,label:"Activate"}
  ];
  const stepNames = { Topology: "Site", Modules: "Features", Health: "Readiness" };
  const root = document.getElementById("onboard-steps-ui");
  if (!root) return;
  root.innerHTML = steps.map((s, i) => {
    const cls = s.id === n ? "on" : (s.id < n ? "done" : "");
    const dot = s.id < n ? "✓" : String(s.id);
    const bar = i < steps.length - 1 ? '<span class="bar"></span>' : "";
    return `<div class="ob-step ${cls}" data-ob-step="${s.id}"><span class="dot">${dot}</span>${stepNames[s.label] || s.label}</div>${bar}`;
  }).join("");
  document.getElementById("onboard-step-num").textContent = String(n);
  const back = document.getElementById("onboard-back");
  const next = document.getElementById("onboard-next");
  const act = document.getElementById("onboard-activate");
  const skip = document.getElementById("onboard-skip");
  if (back) back.style.visibility = n <= 1 ? "hidden" : "visible";
  if (next) next.classList.toggle("hidden", n >= 8);
  if (act) act.classList.toggle("hidden", n < 8);
  if (skip) skip.classList.toggle("hidden", n === 1 || n === 8);
}

function syncOnboardChoices() {
  const sel = document.getElementById("onboard-use-case");
  if (!sel) return;
  document.querySelectorAll("#onboard-choices .choice").forEach((btn) => {
    btn.classList.toggle("on", btn.dataset.useCase === sel.value);
  });
}

function renderOnboardBody() {
  const body = document.getElementById("onboard-body");
  if (!body) return;
  const st = onboardState.status || {};
  const step = onboardState.step;
  const draft = onboardState.draft;
  const counts = st.counts || {};
  const profile = st.profile || "—";
  document.getElementById("onboard-profile").textContent = profile;

  if (step === 1) {
    const cases = st.use_cases || [];
    body.innerHTML = `<h1 style="font-size:22px;font-weight:700;letter-spacing:-.02em">Welcome to Zirp</h1>
      <p class="muted" style="margin:6px 0 22px">What do you want to use this site for? You can change modules later without reinstalling.</p>
      <div class="ob-grid" id="onboard-choices">${cases.map((c) => `
        <button type="button" class="choice ${c.id==='CUSTOM'?'span2':''} ${(draft.use_case||st.use_case||'PARKING')===c.id?'on':''}" data-use-case="${c.id}">
          <span class="cic">${c.id.slice(0,2)}</span>
          <div><b>${c.label}</b><p>${c.description||''}</p></div>
        </button>`).join("")}</div>
      <p class="muted">Profile: <b id="ob-profile-live">${profile}</b></p>`;
    document.querySelectorAll("#onboard-choices .choice").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.getElementById("onboard-use-case").value = btn.dataset.useCase;
        draft.use_case = btn.dataset.useCase;
        syncOnboardChoices();
      });
    });
    const sel = document.getElementById("onboard-use-case");
    if (draft.use_case || st.use_case) sel.value = draft.use_case || st.use_case;
    syncOnboardChoices();
    return;
  }

  if (step === 2) {
    const preset = draft.topo_preset || "1in1out";
    const site = Object.assign({}, (st.topology && st.topology.site) || {}, draft.site || {});
    const lang = site.language || "en";
    const cur = site.currency || "USD";
    const plate = site.plate_validation || "NONE";
    body.innerHTML = `<h1 style="font-size:22px;font-weight:700">Site</h1>
      <p class="muted" style="margin:6px 0 18px">Name the site and how dates, money, and plates should be shown. You can add more lanes later.</p>
      <div class="ob-grid">
        <button type="button" class="choice ${preset==='1in1out'?'on':''}" data-preset="1in1out"><span class="cic">1↔</span><div><b>1 entry / 1 exit</b><p>A typical small parking site.</p></div></button>
        <button type="button" class="choice ${preset==='bidirectional'?'on':''}" data-preset="bidirectional"><span class="cic">⇄</span><div><b>One bidirectional lane</b><p>A single shared lane.</p></div></button>
        <button type="button" class="choice ${preset==='keep'?'on':''}" data-preset="keep"><span class="cic">+</span><div><b>Multiple lanes</b><p>${counts.gates||0} gates already on this site. Keep them.</p></div></button>
        <button type="button" class="choice ${preset==='lpr_only'?'on':''}" data-preset="lpr_only"><span class="cic">0</span><div><b>No gates</b><p>Cameras only. No barriers.</p></div></button>
      </div>
      <div class="card card-b" style="margin-top:14px;display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <div class="field" style="grid-column:1/-1"><label for="ob-site-name">Site name</label><input class="inp" id="ob-site-name" value="${site.name || "Site"}"></div>
        <div class="field"><label for="ob-site-tz">Timezone</label><input class="inp" id="ob-site-tz" value="${site.timezone || "UTC"}" placeholder="Continent/City"></div>
        <div class="field"><label for="ob-site-cur">Currency</label><select class="inp" id="ob-site-cur">
          <option value="USD">US Dollar (USD)</option>
          <option value="EUR">Euro (EUR)</option>
          <option value="GBP">British Pound (GBP)</option>
          <option value="KES">Kenyan Shilling (KES)</option>
          <option value="TZS">Tanzanian Shilling (TZS)</option>
          <option value="UGX">Ugandan Shilling (UGX)</option>
          <option value="ZAR">South African Rand (ZAR)</option>
          <option value="AED">UAE Dirham (AED)</option>
        </select></div>
        <div class="field"><label for="ob-site-lang">Language</label><select class="inp" id="ob-site-lang">
          <option value="en">English</option>
          <option value="sw">Kiswahili</option>
          <option value="ar">Arabic</option>
          <option value="fr">French</option>
          <option value="pt">Portuguese</option>
        </select></div>
        <div class="field" style="grid-column:1/-1"><label for="ob-site-plate">Plate format check</label><select class="inp" id="ob-site-plate">
          <option value="NONE">Accept any format</option>
          <option value="TZ">Tanzania</option>
          <option value="KE">Kenya</option>
          <option value="ZA">South Africa</option>
          <option value="AE">United Arab Emirates</option>
        </select></div>
      </div>
      <p class="muted">Timezone example: Europe/London, Africa/Nairobi, Asia/Dubai. The product does not assume one country.</p>`;
    const curSel = document.getElementById("ob-site-cur");
    const langSel = document.getElementById("ob-site-lang");
    const plateSel = document.getElementById("ob-site-plate");
    if (cur && ![...curSel.options].some((o) => o.value === cur)) curSel.insertAdjacentHTML("beforeend", `<option value="${cur}">${cur}</option>`);
    if (lang && ![...langSel.options].some((o) => o.value === lang)) langSel.insertAdjacentHTML("beforeend", `<option value="${lang}">${lang}</option>`);
    curSel.value = cur;
    langSel.value = lang;
    plateSel.value = plate;
    document.querySelectorAll("[data-preset]").forEach((btn) => {
      btn.addEventListener("click", () => {
        draft.topo_preset = btn.dataset.preset;
        document.querySelectorAll("[data-preset]").forEach((b) => b.classList.toggle("on", b === btn));
      });
    });
    return;
  }

  if (step === 3) {
    body.innerHTML = `<h1 style="font-size:22px;font-weight:700">Hardware</h1>
      <p class="muted" style="margin:6px 0 18px">Add cameras now, or skip and add them later under Devices. Vendor and stream details stay under Advanced.</p>
      <div class="statband">
        <div class="stat"><div class="k">Cameras</div><div class="v">${counts.cameras||0}</div></div>
        <div class="stat"><div class="k">Gates</div><div class="v">${counts.gates||0}</div></div>
        <div class="stat"><div class="k">Lanes</div><div class="v">${counts.lanes||0}</div></div>
      </div>
      <div class="toolbar" style="margin-top:14px">
        <button type="button" id="ob-discover">Discover cameras on LAN</button>
        <button type="button" class="secondary" id="ob-goto-ips">Open Devices</button>
      </div>
      <pre id="ob-hw-result" class="muted" style="margin-top:12px">No discovery run yet.</pre>
      <p class="muted" style="margin-top:10px">Printers and kiosks can be configured after activation in Simulation / Hardware Lab.</p>`;
    document.getElementById("ob-discover").addEventListener("click", async () => {
      const out = document.getElementById("ob-hw-result");
      out.textContent = "Scanning…";
      try {
        const data = await api("/cameras/discover?scan_lan=true");
        const cams = data.cameras || data || [];
        out.textContent = Array.isArray(cams)
          ? `${cams.length} camera(s) found. Open Devices to add and connect them.`
          : JSON.stringify(data, null, 2);
        draft.hardware = { discovered: Array.isArray(cams) ? cams.length : 0 };
      } catch (e) { out.textContent = e.message; }
    });
    document.getElementById("ob-goto-ips").addEventListener("click", () => {
      showPage("cameras");
      if (typeof showCameraSub === "function") showCameraSub("ips");
    });
    return;
  }

  if (step === 4) {
    const mode = draft.recognition_mode || st.recognition_default || "FASTALPR_ONLY";
    const modes = st.recognition_modes || [];
    body.innerHTML = `<h1 style="font-size:22px;font-weight:700">Recognition per camera</h1>
      <p class="muted" style="margin:6px 0 18px">Default mode for this site. Applied to existing cameras; new cameras inherit it.</p>
      <div class="ob-grid">${modes.map((m) => `
        <button type="button" class="choice ${mode===m.id?'on':''}" data-rec="${m.id}">
          <span class="cic">${m.id==='VIDEO_ONLY'?'VID':m.id.slice(0,2)}</span>
          <div><b>${m.label}</b><p>${m.description||''}</p></div>
        </button>`).join("")}</div>`;
    document.querySelectorAll("[data-rec]").forEach((btn) => {
      btn.addEventListener("click", () => {
        draft.recognition_mode = btn.dataset.rec;
        document.querySelectorAll("[data-rec]").forEach((b) => b.classList.toggle("on", b === btn));
      });
    });
    return;
  }

  if (step === 5) {
    const choices = st.optional_module_choices || [];
    body.innerHTML = `<h1 style="font-size:22px;font-weight:700">Optional modules</h1>
      <p class="muted" style="margin:6px 0 18px">Disabled modules disappear from navigation — nothing is deleted. Core recognition stays available.</p>
      <div class="mod-list" id="ob-mod-list">${choices.map((m) => `
        <label class="mod-row" style="cursor:pointer">
          <input type="checkbox" class="bigck ob-mod" data-mid="${m.id}" ${m.enabled?'checked':''}>
          <div style="flex:1"><b style="font-size:13px">${m.label}</b><div class="muted" style="font-size:11.5px">${m.description}${isTechnician() ? ` · <span class="mono">${m.id}</span>` : ""}</div></div>
        </label>`).join("")}</div>`;
    return;
  }

  if (step === 6) {
    body.innerHTML = `<h1 style="font-size:22px;font-weight:700">Users &amp; roles</h1>
      <p class="muted" style="margin:6px 0 18px">${counts.users||0} account(s) on this site. Create an operator now, or skip and manage users later.</p>
      <div class="card card-b" style="display:grid;grid-template-columns:1fr 1fr;gap:12px;max-width:640px">
        <div class="field"><label>Username</label><input class="inp" id="ob-user-name" placeholder="operator"></div>
        <div class="field"><label>Full name</label><input class="inp" id="ob-user-full" placeholder="Site Operator"></div>
        <div class="field"><label>Password</label><input class="inp" type="password" id="ob-user-pass" placeholder="••••••••"></div>
        <div class="field"><label>Role</label><select class="inp" id="ob-user-role"><option>Operator</option><option>Admin</option><option>Cashier</option><option>Technician</option></select></div>
      </div>
      <p class="muted" style="margin-top:12px">Leave blank to skip creating a user on this step.</p>`;
    return;
  }

  if (step === 7) {
    const comps = (st.health && st.health.components) || {};
    const rows = Object.keys(comps).map((k) => {
      const c = comps[k] || {};
      const state = c.state || "—";
      const tone = !c.enabled || String(state).toLowerCase()==="disabled" ? "c-mut"
        : String(state).toLowerCase().includes("degrad") ? "c-wrn"
        : String(state).toLowerCase().includes("online") || String(state).toLowerCase()==="healthy" || String(state).toLowerCase()==="ready" ? "c-ok"
        : "c-info";
      return `<div class="stat"><div class="k">${k}</div><div class="v"><span class="chip ${tone}">${state}</span></div></div>`;
    }).join("") || `<div class="stat"><div class="k">CORE</div><div class="v"><span class="chip c-ok">Healthy</span></div></div>`;
    body.innerHTML = `<h1 style="font-size:22px;font-weight:700">Health &amp; capability</h1>
      <p class="muted" style="margin:6px 0 18px">Disabled is neutral — not an error. One failed camera must not stop the whole site.</p>
      <div class="statband">${rows}</div>
      <div class="toolbar" style="margin-top:14px"><button type="button" class="secondary" id="ob-refresh-health">Refresh health</button></div>`;
    document.getElementById("ob-refresh-health").addEventListener("click", async () => {
      try {
        onboardState.status = await api("/onboarding/status");
        renderOnboardBody();
        updateOnboardStepsUi(onboardState.step);
      } catch (e) { document.getElementById("onboard-error").textContent = e.message; }
    });
    draft.health_ok = true;
    return;
  }

  // step 8
  const enabled = st.enabled_modules || [];
  body.innerHTML = `<div style="text-align:center;padding:20px 0">
    <div style="width:58px;height:58px;border-radius:50%;background:color-mix(in srgb,var(--accent) 14%,transparent);color:var(--accent);display:inline-flex;align-items:center;justify-content:center;margin-bottom:16px;font-weight:700">✓</div>
    <h1 style="font-size:22px;font-weight:700">Ready to activate</h1>
    <p class="muted" style="margin:8px 0 18px">Profile <b>${profile}</b> · ${enabled.length} modules enabled</p>
    <div class="chips" style="justify-content:center;display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px">${enabled.map((m)=>`<span class="chip c-acc">${m}</span>`).join("")}</div>
    <p class="muted">Activation opens the operator workspace. You can run Setup Wizard again while you still have permission.</p>
  </div>`;
}

async function loadOnboarding() {
  const err = document.getElementById("onboard-error");
  if (err) err.textContent = "";
  try {
    const status = await api("/onboarding/status");
    onboardState.status = status;
    onboardState.step = Math.max(1, Math.min(Number(status.step) || 1, 8));
    if (status.use_case) {
      document.getElementById("onboard-use-case").value = status.use_case;
      onboardState.draft.use_case = status.use_case;
    }
    if (status.recognition_default) onboardState.draft.recognition_mode = status.recognition_default;
    updateOnboardStepsUi(onboardState.step);
    renderOnboardBody();
  } catch (e) {
    if (err) err.textContent = e.message;
  }
}

function collectOnboardPayload(nextStep, { activate = false, skip = false } = {}) {
  const step = onboardState.step;
  const draft = onboardState.draft;
  const payload = {
    step: nextStep,
    use_case: document.getElementById("onboard-use-case").value || draft.use_case || "PARKING",
    activate: Boolean(activate),
    skip: Boolean(skip),
  };
  if (step === 2 && !skip) {
    const preset = draft.topo_preset || "1in1out";
    payload.site = {
      name: (document.getElementById("ob-site-name") || {}).value,
      timezone: (document.getElementById("ob-site-tz") || {}).value,
      currency: (document.getElementById("ob-site-cur") || {}).value,
      language: (document.getElementById("ob-site-lang") || {}).value,
      locale: (document.getElementById("ob-site-lang") || {}).value,
      plate_validation: (document.getElementById("ob-site-plate") || {}).value,
    };
    if (preset !== "keep") payload.topology = { preset };
  }
  if (step === 3 && !skip) {
    payload.hardware = draft.hardware || { reviewed: true };
  }
  if (step === 4 && !skip) {
    payload.recognition_mode = draft.recognition_mode || "HYBRID";
  }
  if (step === 5 && !skip) {
    payload.optional_modules = [...document.querySelectorAll(".ob-mod:checked")].map((el) => el.dataset.mid);
  }
  if (step === 6 && !skip) {
    const username = ((document.getElementById("ob-user-name") || {}).value || "").trim();
    const password = (document.getElementById("ob-user-pass") || {}).value || "";
    if (username && password) {
      payload.user = {
        username,
        password,
        full_name: ((document.getElementById("ob-user-full") || {}).value || username).trim(),
        role: (document.getElementById("ob-user-role") || {}).value || "Operator",
      };
    }
  }
  if (step === 7) payload.health_ok = true;
  return payload;
}

async function submitOnboardStep(nextStep, opts = {}) {
  const err = document.getElementById("onboard-error");
  if (err) err.textContent = "";
  try {
    const payload = collectOnboardPayload(nextStep, opts);
    await api("/onboarding/step", { method: "POST", body: JSON.stringify(payload) });
    await refreshSessionContext();
    if (opts.activate) {
      toast("Deployment activated", "info");
      showPage("dashboard");
      return;
    }
    onboardState.step = nextStep;
    await loadOnboarding();
    onboardState.step = nextStep;
    updateOnboardStepsUi(nextStep);
    renderOnboardBody();
  } catch (e) {
    if (err) err.textContent = e.message;
    toast(e.message || "Onboarding step failed", "dgr");
  }
}

function setManageVisibility() {
  document.getElementById("add-camera").style.display = can("cameras.manage") ? "" : "none";
  document.getElementById("discover-cameras").style.display = can("cameras.manage") ? "" : "none";
  document.getElementById("add-ip-cameras").style.display = can("cameras.manage") ? "" : "none";
  const onboardBtn = document.getElementById("onboard-camera");
  if (onboardBtn) onboardBtn.style.display = can("cameras.manage") ? "" : "none";
  const assignOwner = document.getElementById("assign-recognition-owner");
  if (assignOwner) assignOwner.style.display = can("settings.manage") ? "" : "none";
  document.getElementById("add-gate").style.display = can("gates.manage") ? "" : "none";
  document.getElementById("add-user").style.display = can("users.manage") ? "" : "none";
  const paySession = document.getElementById("pay-session");
  if (paySession) paySession.style.display = (can("payments.create") || can("kiosk.use")) ? "" : "none";
  const openKiosk = document.getElementById("open-kiosk");
  if (openKiosk) openKiosk.style.display = (can("kiosk.use") || can("payments.create") || can("sessions.view")) ? "" : "none";
  const saveTariff = document.getElementById("save-tariff");
  if (saveTariff) saveTariff.style.display = (can("fees.manage") || can("settings.manage")) ? "" : "none";
  const manageVehicles = can("subscribers.manage");
  ["add-vehicle", "save-vehicle-bulk", "delete-vehicles"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.style.display = manageVehicles ? "" : "none";
  });
  const manageBackup = can("settings.manage");
  ["backup-save", "backup-download", "backup-cloud"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.style.display = manageBackup ? "" : "none";
  });
}

async function refreshSessionContext() {
  const me = await api("/auth/me");
  try {
    const site = await api("/settings/site");
    state.siteTimezone = site.timezone || "UTC";
    if (site.currency) state.siteCurrency = site.currency;
  } catch (_) {}
  state.permissions = me.permissions || [];
  state.navigation = me.navigation || [];
  state.modules = me.modules || {};
  state.roles = me.roles || [];
  applyModuleNavigation();
  return me;
}

function setSignedIn(data) {
  state.token = data.token || data.access_token || state.token;
  state.user = data.username || "";
  state.userId = data.id || null;
  state.permissions = data.permissions || [];
  state.navigation = data.navigation || [];
  state.modules = data.modules || {};
  state.roles = data.roles || state.roles || [];
  sessionStorage.setItem("smartpark_token", state.token);
  const nameEl = document.getElementById("whoami-name");
  const who = document.getElementById("whoami");
  const av = document.getElementById("user-avatar");
  if (nameEl) nameEl.textContent = state.user || "Operator";
  if (who) {
    const role = Array.isArray(state.roles) && state.roles.length ? state.roles[0] : "Signed in";
    who.textContent = typeof role === "string" ? role : (role.name || role.id || "Signed in");
  }
  if (av) av.textContent = (state.user || "SP").slice(0, 2).toUpperCase();
  loginView.classList.add("hidden");
  appView.classList.remove("hidden");
  applyModuleNavigation();
  syncRoleClass();
  startHdrHealth();
  const onboardingDone = state.modules.onboarding_completed !== false;
  showPage(onboardingDone ? "dashboard" : "onboarding");
}

function setSignedOut() {
  state.token = ""; state.user = ""; state.userId = null; state.permissions = [];
  state.navigation = []; state.modules = {}; state.siteTimezone = "UTC";
  sessionStorage.removeItem("smartpark_token");
  document.body.classList.remove("role-tech");
  document.body.classList.remove("kiosk-mode");
  stopHdrHealth();
  setHdrHealth("Offline", "c-mut");
  appView.classList.add("hidden");
  loginView.classList.remove("hidden");
}

document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const error = document.getElementById("login-error");
  const btn = document.getElementById("login-btn");
  error.textContent = "";
  btn.disabled = true;
  try {
    const data = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: document.getElementById("username").value.trim(),
        password: document.getElementById("password").value,
      }),
    });
    state.token = data.token;
    const me = await refreshSessionContext();
    setSignedIn({ ...data, ...me });
  } catch (err) {
    const hint = (document.getElementById("login-hint") || {}).textContent || "";
    const msg = err.message || "Sign in failed";
    error.textContent = hint && /invalid|password|401/i.test(msg) ? `${msg}. ${hint}` : msg;
    toast(msg, "dgr");
  } finally {
    btn.disabled = false;
  }
});

document.getElementById("logout-btn").addEventListener("click", async () => {
  try { await api("/auth/logout", { method: "POST" }); } catch (_) {}
  stopLive();
  stopHealth();
  stopHdrHealth();
  setSignedOut();
});
document.querySelectorAll("nav button[data-page]").forEach((btn) => {
  btn.addEventListener("click", () => showPage(btn.dataset.page));
});
