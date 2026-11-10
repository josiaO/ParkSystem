const themeLogin = document.getElementById("theme-toggle");
const themeApp = document.getElementById("theme-toggle-app");
if (themeLogin) themeLogin.addEventListener("click", cycleTheme);
if (themeApp) themeApp.addEventListener("click", cycleTheme);
function enterKiosk() {
  document.body.classList.add("kiosk-mode");
  const card = document.getElementById("kiosk-card");
  if (card) card.classList.remove("hidden");
  showPage("sessions");
  const input = document.getElementById("receipt-token");
  if (input) input.focus();
}
function exitKiosk() {
  document.body.classList.remove("kiosk-mode");
}
const openKioskBtn = document.getElementById("open-kiosk");
if (openKioskBtn) openKioskBtn.addEventListener("click", enterKiosk);
const exitKioskBtn = document.getElementById("kiosk-exit");
if (exitKioskBtn) exitKioskBtn.addEventListener("click", exitKiosk);
function currentPageName() {
  const on = document.querySelector("nav button[data-page].active");
  return (on && on.dataset.page) || "";
}
function isTypingTarget(el) {
  if (!el) return false;
  const tag = (el.tagName || "").toUpperCase();
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  return Boolean(el.isContentEditable);
}
function clickToolbar(id) {
  const el = document.getElementById(id);
  if (!el || el.disabled || el.style.display === "none" || el.hidden) return false;
  el.click();
  return true;
}
function showShortcutHelp() {
  const dlg = document.getElementById("shortcuts-dialog");
  if (dlg && typeof dlg.showModal === "function") dlg.showModal();
}
function shortcutAdd() {
  const page = currentPageName();
  if (page === "cameras" && clickToolbar("add-camera")) return;
  if (page === "gates" && clickToolbar("add-gate")) return;
  if (page === "users" && clickToolbar("add-user")) return;
  if (page === "vehicles" && clickToolbar("add-vehicle")) return;
  toast("Open Cameras, Gates, Vehicles, or Users to add.", "info");
}
function shortcutEdit() {
  const page = currentPageName();
  const map = { cameras: "#camera-rows", gates: "#gate-rows", users: "#user-rows" };
  if (map[page]) {
    const btn = document.querySelector(`${map[page]} tr.selected [data-role="edit"]`);
    if (btn) { btn.click(); return; }
    toast("Select a row to edit.", "warn");
    return;
  }
  if (page === "vehicles") {
    const checked = document.querySelector("[data-vehicle-check]:checked");
    const row = checked && checked.closest("tr");
    const btn = row && row.querySelector("[data-edit-vehicle]");
    if (btn) { btn.click(); return; }
    toast("Select a vehicle to edit.", "warn");
  }
}
function shortcutDelete() {
  const page = currentPageName();
  if (page === "vehicles") {
    clickToolbar("delete-vehicles");
    return;
  }
  const map = { cameras: "#camera-rows", gates: "#gate-rows", users: "#user-rows" };
  if (map[page]) {
    const btn = document.querySelector(`${map[page]} tr.selected [data-role="delete"]`);
    if (btn) { btn.click(); return; }
    toast("Select a row to delete.", "warn");
  }
}
function shortcutRefresh() {
  const page = currentPageName();
  if (page === "cameras") {
    if (liveTabVisible() && clickToolbar("refresh-live")) return;
    clickToolbar("refresh-cameras");
    return;
  }
  const ids = {
    gates: "refresh-gates", vehicles: "refresh-vehicles", users: "refresh-users",
    detections: "refresh-detections", sessions: "refresh-sessions", payments: "refresh-payments",
    fees: "refresh-tariff",
  };
  if (ids[page] && clickToolbar(ids[page])) return;
  if (page === "dashboard") loadDashboard();
  if (page === "health") loadHealth();
}
function liveCameraForSlot(slot) {
  if (slot == null || slot < 0 || Number.isNaN(slot)) return null;
  return liveCameras[slot] || cameraFromSelect(slot) || null;
}
function liveSlotFromFocus() {
  const el = document.activeElement;
  const pane = el && el.closest && el.closest(".live-pane");
  return pane ? Number(pane.dataset.slot) : null;
}
function liveCameraSlotForShortcut() {
  const highlighted = document.querySelector(".live-pane.shortcut-target");
  const slots = [
    liveSlotFromFocus(),
    focusedLiveSlot,
    highlighted ? Number(highlighted.dataset.slot) : null,
  ];
  for (const slot of slots) {
    if (liveCameraForSlot(slot)) return slot;
  }
  return -1;
}
function markLiveShortcutTarget(slot) {
  focusedLiveSlot = slot;
  document.querySelectorAll(".live-pane").forEach((pane) => {
    pane.classList.toggle("shortcut-target", Number(pane.dataset.slot) === slot);
  });
  const hint = document.getElementById("live-shortcut-hint");
  const cam = liveCameraForSlot(slot);
  if (hint) {
    hint.textContent = cam
      ? `F8 / F9 pulse ${cam.name || "this camera"} only — not the other side.`
      : "That view has no camera yet. Choose a camera, then F8 / F9 pulse only this side.";
  }
}
function updateGateShortcutHint() {
  const el = document.getElementById("gate-shortcut-hint");
  if (!el) return;
  const tr = document.querySelector("#gate-rows tr.selected");
  const lane = tr && tr.children[1] ? tr.children[1].textContent.trim() : "";
  const side = selectedGateSide === "EXIT" ? "exit" : selectedGateSide === "ENTRY" ? "entry" : "";
  if (!tr) el.textContent = "Select a lane, then 1 = entry, 2 = exit. F8 / F9 pulse that side only.";
  else if (!side) el.textContent = `${lane}: press 1 for entry or 2 for exit, then F8 / F9.`;
  else el.textContent = `${lane} ${side} is armed. F8 opens it, F9 closes it.`;
}
function shortcutArmDigit(n) {
  const page = currentPageName();
  if (page === "cameras" && liveTabVisible()) {
    const panes = [...document.querySelectorAll(".live-pane")].filter((p) => !p.hidden && p.offsetParent !== null);
    const pane = panes[n - 1];
    if (!pane) { toast(`No camera ${n} on this layout.`, "warn"); return true; }
    markLiveShortcutTarget(Number(pane.dataset.slot));
    const cam = liveCameraForSlot(Number(pane.dataset.slot));
    toast(cam ? `F8 / F9 will pulse ${cam.name || "this camera"} only.` : "That view has no camera yet.", "info");
    return true;
  }
  if (page === "gates") {
    if (n !== 1 && n !== 2) return false;
    selectedGateSide = n === 1 ? "ENTRY" : "EXIT";
    updateGateShortcutHint();
    toast(n === 1 ? "Entry armed. F8 / F9 pulse entry only." : "Exit armed. F8 / F9 pulse exit only.", "info");
    return true;
  }
  return false;
}
function shortcutBarrier(action) {
  const page = currentPageName();
  if (page === "cameras" && liveTabVisible()) {
    const slot = liveCameraSlotForShortcut();
    if (slot < 0) {
      toast("Click a live camera first, or press 1 / 2. F8 and F9 pulse that side only — never both.", "warn");
      return;
    }
    openPaneSide(slot, action);
    return;
  }
  if (page === "cameras") {
    if (!selectedCameraId) {
      toast("Select a camera row first. F8 / F9 pulse that camera only.", "warn");
      return;
    }
    commandCameraBarrier(selectedCameraId, action);
    return;
  }
  if (page === "gates") {
    const tr = document.querySelector("#gate-rows tr.selected");
    if (!tr || !tr.dataset.gateId) { toast("Select a gate row first.", "warn"); return; }
    const sides = (tr.dataset.sides || "").split(",").filter(Boolean);
    let side = selectedGateSide && sides.includes(selectedGateSide) ? selectedGateSide : null;
    if (!side && sides.length === 1) side = sides[0];
    if (!side) {
      toast("This lane has two sides. Press 1 for entry or 2 for exit, then F8 / F9.", "warn");
      return;
    }
    commandGateBarrier(Number(tr.dataset.gateId), side, action);
    return;
  }
  toast("Open Live Gates or Gates, then select one side.", "warn");
}
const openShortcutsBtn = document.getElementById("open-shortcuts");
if (openShortcutsBtn) openShortcutsBtn.addEventListener("click", showShortcutHelp);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !document.querySelector("dialog[open]") && document.body.classList.contains("kiosk-mode")) {
    exitKiosk();
    return;
  }
  if (appView.classList.contains("hidden") || document.body.classList.contains("kiosk-mode")) return;
  if (document.querySelector("dialog[open]")) return;
  const barrierKey = e.key === "F8" || e.key === "F9";
  const inLivePane = e.target && e.target.closest && e.target.closest(".live-pane");
  if (isTypingTarget(e.target) && !barrierKey && e.key !== "F1" && !(inLivePane && /^[1-9]$/.test(e.key))) return;
  if (inLivePane && (e.type === "keydown") && (e.target.tagName === "SELECT" || e.target.closest(".live-pane"))) {
    const slot = Number(e.target.closest(".live-pane").dataset.slot);
    if (!Number.isNaN(slot)) markLiveShortcutTarget(slot);
  }
  const mod = e.ctrlKey || e.metaKey;
  if (e.key === "F1" || (mod && (e.key === "/" || e.key === "?"))) {
    e.preventDefault();
    showShortcutHelp();
    return;
  }
  if (e.key === "F5" || (mod && e.key.toLowerCase() === "r" && !e.shiftKey && !e.altKey)) {
    e.preventDefault();
    shortcutRefresh();
    return;
  }
  if (mod && e.key.toLowerCase() === "n" && !e.shiftKey && !e.altKey) {
    e.preventDefault();
    shortcutAdd();
    return;
  }
  if (mod && e.key.toLowerCase() === "e" && !e.shiftKey && !e.altKey) {
    e.preventDefault();
    shortcutEdit();
    return;
  }
  if (e.key === "Delete" || (mod && e.key === "Backspace")) {
    e.preventDefault();
    shortcutDelete();
    return;
  }
  if (!mod && !e.altKey && /^[1-9]$/.test(e.key)) {
    if (shortcutArmDigit(Number(e.key))) e.preventDefault();
    return;
  }
  if (e.key === "F8") {
    e.preventDefault();
    shortcutBarrier("open");
    return;
  }
  if (e.key === "F9") {
    e.preventDefault();
    shortcutBarrier("close");
  }
});
const refreshDetections = document.getElementById("refresh-detections");
if (refreshDetections) refreshDetections.addEventListener("click", loadDetections);
const detectFilter = document.getElementById("detect-filter");
if (detectFilter) detectFilter.addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); loadDetections(); }
});

const sideToggle = document.getElementById("sidebar-toggle");
if (sideToggle) {
  sideToggle.addEventListener("click", () => {
    document.getElementById("sidebar").classList.toggle("collapsed");
  });
}
const hdrHealthBtn = document.getElementById("hdr-health");
if (hdrHealthBtn) {
  hdrHealthBtn.style.cursor = "pointer";
  hdrHealthBtn.addEventListener("click", () => {
    if (!appView.classList.contains("hidden") && isTechnician()) showPage("health");
  });
}

document.getElementById("onboard-back").addEventListener("click", async () => {
  const prev = Math.max(1, onboardState.step - 1);
  onboardState.step = prev;
  updateOnboardStepsUi(prev);
  renderOnboardBody();
});
document.getElementById("onboard-next").addEventListener("click", async () => {
  const next = Math.min(8, onboardState.step + 1);
  await submitOnboardStep(next);
});
document.getElementById("onboard-skip").addEventListener("click", async () => {
  const next = Math.min(8, onboardState.step + 1);
  await submitOnboardStep(next, { skip: true });
});
document.getElementById("onboard-activate").addEventListener("click", async () => {
  await submitOnboardStep(8, { activate: true });
});
