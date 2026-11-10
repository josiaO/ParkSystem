const state = {
  token: sessionStorage.getItem("smartpark_token") || "",
  user: "", userId: null, permissions: [], roles: [], navigation: [], modules: {},
  recommendedAdapter: "hvx",
  platform: null,
  siteTimezone: "UTC",
};
let selectedCameraId = null;
let selectedGateId = null;
let selectedUserId = null;
let focusedLiveSlot = null;
let selectedGateSide = null;

function isMacUi() {
  return /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || "");
}
function shortcutText(combo) {
  const raw = String(combo || "");
  return isMacUi() ? raw.replace(/^Ctrl\+/i, "⌘") : raw;
}
function shortcutKbd(combo) {
  const kbd = document.createElement("kbd");
  kbd.textContent = shortcutText(combo);
  return kbd;
}
function setActionCaption(el, caption, combo) {
  if (!el) return;
  el.textContent = caption;
  if (combo) el.appendChild(shortcutKbd(combo));
}
function localizeShortcutKeys() {
  document.querySelectorAll("kbd").forEach((kbd) => {
    kbd.textContent = shortcutText(kbd.textContent);
  });
}

const loginView = document.getElementById("login-view");
const appView = document.getElementById("app-view");
let pages = ["dashboard", "health", "detections", "sessions", "vehicles", "payments", "fees", "cameras", "gates", "users", "hardware", "sim", "onboarding", "watchlists", "alerts", "incidents", "settings"];
let hdrHealthTimer = null;

function lsGet(k) { try { return localStorage.getItem(k); } catch (_) { return null; } }
function lsSet(k, v) { try { localStorage.setItem(k, v); } catch (_) {} }

function applyTheme(theme) {
  const t = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = t;
  lsSet("smartpark_theme", t);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", t === "dark" ? "#0D1117" : "#F2F4F6");
}
function cycleTheme() {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
}
applyTheme(lsGet("smartpark_theme") || "light");
localizeShortcutKeys();

function toast(msg, tone) {
  const root = document.getElementById("toast-root");
  if (!root || !msg) return;
  const el = document.createElement("div");
  el.className = "toast" + (tone === "warn" || tone === "dgr" || tone === "info" ? " " + tone : "");
  el.textContent = msg;
  root.appendChild(el);
  setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity .3s"; }, 3200);
  setTimeout(() => el.remove(), 3600);
}

function setHdrHealth(label, tone) {
  const chip = document.getElementById("hdr-health");
  const lab = document.getElementById("hdr-health-label");
  if (!chip || !lab) return;
  lab.textContent = label || "—";
  chip.className = "healthchip " + (tone || "c-mut");
}

let liveAlprTimer = null;
let alprInstalled = null;
let healthTimer = null;
let simSessionId = null;
let cameraSub = "live";
let cameraRowsCache = [];
let gateRowsCache = [];
let cameraLiveRowsCache = [];
const liveCameras = [null, null];
const liveWatchIds = [null, null];
const liveFrameSeq = [0, 0];
const liveObjectUrls = [null, null];
const liveFetchBusy = [false, false];
const liveOverlays = [null, null];
const liveLastCars = [null, null];
const snapshotTimers = [null, null];
// One WHEP session per pane. Closed before any other transport starts.
const whepSessions = [null, null];
const liveGenerations = [0, 0];
const plateRequests = new Set();
const liveRetryCounts = {};
