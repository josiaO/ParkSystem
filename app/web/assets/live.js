function whepFetch(url, options) {
  const target = new URL(url, window.location.href);
  const headers = { ...(options.headers || {}) };
  if (target.origin === window.location.origin && state.token) headers.Authorization = `Bearer ${state.token}`;
  return fetch(target, { ...options, headers });
}

function whepClose(session) {
  if (!session) return;
  session.closed = true;
  if (session.abort) session.abort.abort();
  clearTimeout(session.signalingTimer);
  clearTimeout(session.videoTimer);
  clearTimeout(session.disconnectTimer);
  clearTimeout(session.statsTimer);
  try { session.pc.ontrack = null; session.pc.onconnectionstatechange = null; session.pc.close(); } catch (_) {}
  if (session.location && !session.deletedLocation) {
    session.deletedLocation = true;
    whepFetch(session.location, { method: "DELETE", signal: AbortSignal.timeout(3000) }).catch(() => {});
  }
}

async function whepStart(video, whepUrl, onState, onSession) {
  if (typeof RTCPeerConnection === "undefined") throw new Error("WebRTC unavailable in this browser");
  const pc = new RTCPeerConnection({ iceServers: [] });
  const session = { pc, location: null, closed: false, whepUrl, abort: new AbortController() };
  if (onSession) onSession(session);
  pc.addTransceiver("video", { direction: "recvonly" });
  pc.addTransceiver("audio", { direction: "recvonly" });
  pc.ontrack = (evt) => {
    if (session.closed) return;
    if (evt.track.kind !== "video") return;
    session.videoTrack = evt.track;
    video.srcObject = new MediaStream([evt.track]);
    video.play().catch(() => {});
  };
  video.onloadeddata = () => {
    if (!session.closed && session.videoTrack && video.videoWidth > 0) {
      session.videoReady = true;
      clearTimeout(session.videoTimer);
      onState("video", session);
    }
  };
  pc.onconnectionstatechange = () => {
    if (session.closed || !onState) return;
    clearTimeout(session.disconnectTimer);
    onState(pc.connectionState, session);
    if (pc.connectionState === "disconnected") session.disconnectTimer = setTimeout(() => {
      if (!session.closed) onState("failed", session);
    }, 4000);
  };
  try {
  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);
  await new Promise((resolve) => {
    if (pc.iceGatheringState === "complete") return resolve();
    const timer = setTimeout(resolve, 1500);
    pc.onicegatheringstatechange = () => {
      if (pc.iceGatheringState === "complete") { clearTimeout(timer); resolve(); }
    };
  });
  session.signalingTimer = setTimeout(() => session.abort.abort(), 8000);
  const res = await whepFetch(whepUrl, {
    method: "POST",
    headers: { "Content-Type": "application/sdp" },
    body: pc.localDescription.sdp,
    signal: session.abort.signal,
  });
  if (!res.ok) throw new Error(`WHEP SIGNALING FAILED (${res.status})`);
  session.location = res.headers.get("Location");
  if (session.location && !/^https?:/i.test(session.location)) {
    session.location = new URL(session.location, new URL(whepUrl, window.location.href)).toString();
  }
  await pc.setRemoteDescription({ type: "answer", sdp: await res.text() });
  clearTimeout(session.signalingTimer);
  if (session.closed) { whepClose(session); throw new Error("WHEP session closed"); }
  if (!session.videoReady) session.videoTimer = setTimeout(() => {
    if (!session.closed && !session.videoReady) onState(session.videoTrack ? "no-frames" : "no-video-track", session);
  }, 10000);
  if (typeof pc.getStats === "function") {
    let lastFrames = 0;
    let lastProgress = performance.now();
    const checkFrames = async () => {
      if (session.closed) return;
      try {
        const stats = await pc.getStats();
        if (session.closed) return;
        stats.forEach((report) => {
          if (report.type === "inbound-rtp" && (report.kind === "video" || report.mediaType === "video") && report.framesDecoded > lastFrames) {
            lastFrames = report.framesDecoded;
            lastProgress = performance.now();
          }
        });
        if (performance.now() - lastProgress > 8000) {
          onState("no-frames", session);
          return;
        }
      } catch (_) {}
      if (!session.closed) session.statsTimer = setTimeout(checkFrames, 2000);
    };
    session.statsTimer = setTimeout(checkFrames, 2000);
  }
  return session;
  } catch (error) {
    whepClose(session);
    throw error;
  }
}

function whepStop(slot) {
  const session = whepSessions[slot];
  whepSessions[slot] = null;
  if (!session) return;
  whepClose(session);
}

function whepCodec(session) {
  try {
    const receivers = session.pc.getReceivers().filter((r) => r.track && r.track.kind === "video");
    const codecs = receivers.flatMap((r) => (r.getParameters().codecs || []).map((c) => c.mimeType));
    return codecs[0] ? codecs[0].replace("video/", "") : "";
  } catch (_) { return ""; }
}

function mediaUrl(path) {
  const join = path.includes("?") ? "&" : "?";
  return `${path}${join}access_token=${encodeURIComponent(state.token)}`;
}

let lastDiscover = null;

function camerasPageVisible() {
  const page = document.getElementById("page-cameras");
  return page && !page.classList.contains("hidden");
}

function liveTabVisible() {
  return camerasPageVisible() && cameraSub === "live";
}

function paneEls(slot) {
  const pane = document.querySelector(`.live-pane[data-slot="${slot}"]`);
  if (!pane) return {};
  return {
    pane,
    camera: pane.querySelector('[data-role="camera"]'),
    pick: pane.querySelector('[data-role="pick"]'),
    img: pane.querySelector('[data-role="video"]'),
    webrtc: pane.querySelector('[data-role="webrtc"]'),
    canvas: pane.querySelector('[data-role="overlay"]'),
    status: pane.querySelector('[data-role="status"]'),
    zoom: pane.querySelector('[data-role="zoom"]'),
    zoomLabel: pane.querySelector('[data-role="zoom-label"]'),
    zoneHint: pane.querySelector('[data-role="zone-hint"]'),
    snap: pane.querySelector('[data-role="snap"]'),
    crop: pane.querySelector('[data-role="crop"]'),
    plate: pane.querySelector('[data-role="plate"]'),
    details: pane.querySelector('[data-role="details"]'),
    hold: pane.querySelector('[data-role="hold"]'),
    online: pane.querySelector('[data-role="online"]'),
    confidence: pane.querySelector('[data-role="confidence"]'),
    decision: pane.querySelector('[data-role="decision"]'),
    bizCamera: pane.querySelector('[data-role="biz-camera"]'),
    bizVideo: pane.querySelector('[data-role="biz-video"]'),
    bizRecog: pane.querySelector('[data-role="biz-recog"]'),
    bizLast: pane.querySelector('[data-role="biz-last"]'),
  };
}

function cameraSide(camera) {
  return String((camera && (camera.lane_direction || camera.side)) || "").toUpperCase();
}

function pairLaneCameras(cameras, gateId) {
  let cams = Array.isArray(cameras) ? cameras.slice() : [];
  if (gateId !== "" && gateId != null) {
    cams = cams.filter((c) => String(c.gate_id) === String(gateId));
  }
  const entry = cams.find((c) => cameraSide(c).includes("ENTRY"));
  const exitCam = cams.find((c) => cameraSide(c).includes("EXIT"));
  const leftover = cams.filter((c) => c !== entry && c !== exitCam);
  let left = entry || leftover.shift() || null;
  let right = exitCam || leftover.shift() || null;
  if (!left && !right && cams.length) {
    left = cams[0];
    right = cams[1] || null;
  }
  return [left, right];
}

function formatWhen(iso) {
  if (!iso) return "—";
  const parsed = new Date(String(iso));
  if (Number.isNaN(parsed.getTime())) return String(iso).slice(0, 19).replace("T", " ");
  try {
    return new Intl.DateTimeFormat(undefined, {
      timeZone: state.siteTimezone || "UTC",
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", hour12: false,
    }).format(parsed).replace(",", "");
  } catch (_) {
    return String(iso).slice(0, 19).replace("T", " ");
  }
}

function cameraOptionLabel(camera) {
  return [camera.name, camera.lane_name || camera.gate_name || "", camera.side || camera.lane_direction || "", camera.ip_address || ""]
    .filter(Boolean).join(" · ");
}

function slotStorageKey(slot) { return `smartpark_live_slot_${slot}`; }

function savedSlotId(slot) {
  const raw = sessionStorage.getItem(slotStorageKey(slot));
  return raw ? Number(raw) : null;
}

function saveSlotId(slot, id) {
  if (id == null || id === "") sessionStorage.removeItem(slotStorageKey(slot));
  else sessionStorage.setItem(slotStorageKey(slot), String(id));
}

function cameraFromSelect(slot) {
  const id = paneEls(slot).camera && paneEls(slot).camera.value;
  if (!id) return null;
  return cameraLiveRowsCache.find((c) => String(c.id) === String(id)) || null;
}

let liveLayout = lsGet("smartpark_live_layout") || "2";

function ensureSlot(slot) {
  const bags = [liveCameras, liveWatchIds, liveFrameSeq, liveObjectUrls, liveFetchBusy, liveOverlays, liveLastCars, snapshotTimers];
  bags.forEach((bag) => {
    while (bag.length <= slot) bag.push(bag === liveFrameSeq || bag === liveFetchBusy ? 0 : null);
  });
  if (liveFetchBusy[slot] == null) liveFetchBusy[slot] = false;
  if (liveFrameSeq[slot] == null) liveFrameSeq[slot] = 0;
}

function fillPaneSelects(rows) {
  document.querySelectorAll(".live-pane").forEach((pane) => {
    const slot = Number(pane.dataset.slot);
    const sel = paneEls(slot).camera;
    if (!sel) return;
    const current = sel.value || String(savedSlotId(slot) || "");
    sel.innerHTML = `<option value="">Choose camera…</option>` +
      (rows || []).map((c) => `<option value="${c.id}">${cameraOptionLabel(c)}</option>`).join("");
    if (current && [...sel.options].some((o) => o.value === current)) sel.value = current;
  });
}

function bindExtraPane(pane) {
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
  const openBtn = pane.querySelector('[data-role="open-side"]');
  if (openBtn) openBtn.addEventListener("click", () => openPaneSide(slot, "open"));
  const closeBtn = pane.querySelector('[data-role="close-side"]');
  if (closeBtn) closeBtn.addEventListener("click", () => openPaneSide(slot, "close"));
  pane.addEventListener("pointerdown", () => { markLiveShortcutTarget(slot); });
  const correctBtn = pane.querySelector('[data-role="correct-plate"]');
  if (correctBtn) correctBtn.addEventListener("click", () => correctPanePlate(slot));
}

function syncLivePanes() {
  const grid = document.querySelector(".dual-live");
  if (!grid) return;
  grid.classList.toggle("layout-1", liveLayout === "1");
  grid.classList.toggle("layout-all", liveLayout === "all");
  const pane1 = grid.querySelector('.live-pane[data-slot="1"]');
  if (pane1) pane1.hidden = liveLayout === "1";
  if (liveLayout === "1") stopLiveSlot(1);
  const want = liveLayout === "all" ? Math.max(cameraLiveRowsCache.length, 2) : 2;
  [...grid.querySelectorAll(".live-pane")].forEach((pane) => {
    const slot = Number(pane.dataset.slot);
    if (slot >= 2 && slot >= want) {
      stopLiveSlot(slot);
      pane.remove();
    }
  });
  const template = grid.querySelector('.live-pane[data-slot="0"]');
  for (let slot = 2; slot < want; slot += 1) {
    if (grid.querySelector(`.live-pane[data-slot="${slot}"]`)) continue;
    const clone = template.cloneNode(true);
    clone.dataset.slot = String(slot);
    const label = clone.querySelector("label.live-title");
    if (label && label.firstChild) label.firstChild.textContent = `Camera ${slot + 1} `;
    grid.appendChild(clone);
    ensureSlot(slot);
    bindExtraPane(clone);
  }
  document.querySelectorAll("#live-layout button").forEach((btn) => {
    btn.classList.toggle("on", btn.dataset.layout === liveLayout);
  });
}

function openCameraPicker(slot) {
  markLiveShortcutTarget(slot);
  const sel = paneEls(slot).camera;
  if (!sel) return;
  sel.focus();
  if (typeof sel.showPicker === "function") {
    try { sel.showPicker(); } catch (_) {}
  }
}

async function watchCamera(id) {
  if (!id) return;
  try { await api(`/cameras/${id}/live/watch`, { method: "POST", body: "{}" }); }
  catch (_) {}
}

async function unwatchCamera(id) {
  if (!id) return;
  try { await api(`/cameras/${id}/live/unwatch`, { method: "POST", body: "{}" }); }
  catch (_) {}
}

function stopLiveSlot(slot, release = true) {
  if (snapshotTimers[slot]) { clearInterval(snapshotTimers[slot]); snapshotTimers[slot] = null; }
  liveFetchBusy[slot] = false;
  liveFrameSeq[slot] = 0;
  const prev = liveWatchIds[slot];
  liveWatchIds[slot] = null;
  if (release) unwatchCamera(prev);
  const els = paneEls(slot);
  liveGenerations[slot] = (liveGenerations[slot] || 0) + 1;
  whepStop(slot);
  if (els.webrtc) {
    els.webrtc.style.display = "none";
    try { els.webrtc.pause(); } catch (_) {}
    els.webrtc.srcObject = null;
    els.webrtc.removeAttribute("src");
  }
  if (els.img) {
    els.img.style.display = "block";
    els.img.onload = null;
    els.img.onerror = null;
    els.img.removeAttribute("src");
    delete els.img.dataset.cameraId;
  }
  if (liveObjectUrls[slot]) {
    URL.revokeObjectURL(liveObjectUrls[slot]);
    liveObjectUrls[slot] = null;
  }
  liveOverlays[slot] = null;
  // Never carry the previous vehicle into a newly opened live view. The
  // capture endpoint may still legitimately return the last raw read,
  // but it must not appear as a current plate after tab navigation.
  liveLastCars[slot] = null;
  const resetEls = paneEls(slot);
  if (resetEls.plate) resetEls.plate.textContent = "—";
  if (resetEls.snap) resetEls.snap.innerHTML = `<p class="muted">Waiting for a car</p>`;
  if (resetEls.crop) resetEls.crop.innerHTML = `<p class="muted">—</p>`;
}

function stopLive() {
  if (liveAlprTimer) { clearInterval(liveAlprTimer); liveAlprTimer = null; }
  document.querySelectorAll(".live-pane").forEach((pane) => stopLiveSlot(Number(pane.dataset.slot)));
  liveCameras.forEach((_, slot) => { liveCameras[slot] = null; });
}

const zoneDraft = {};
const zoneZoom = {};

function liveMedia(slot) {
  const els = paneEls(slot);
  if (els.webrtc && els.webrtc.style.display !== "none" && els.webrtc.videoWidth) return els.webrtc;
  return els.img;
}

function mediaBox(slot, canvas) {
  const media = liveMedia(slot);
  const nw = (media && (media.videoWidth || media.naturalWidth)) || canvas.width;
  const nh = (media && (media.videoHeight || media.naturalHeight)) || canvas.height;
  const scale = Math.min(canvas.width / Math.max(nw, 1), canvas.height / Math.max(nh, 1));
  const drawW = nw * scale;
  const drawH = nh * scale;
  return { ox: (canvas.width - drawW) / 2, oy: (canvas.height - drawH) / 2, drawW, drawH };
}

function parseRoi(value) {
  const parts = String(value || "").split(",").map((item) => Number(item.trim()));
  if (parts.length !== 4 || parts.some((n) => !Number.isFinite(n))) return null;
  const [x1, y1, x2, y2] = parts;
  if (!(x1 >= 0 && y1 >= 0 && x2 <= 1 && y2 <= 1 && x2 - x1 >= 0.08 && y2 - y1 >= 0.08)) return null;
  return { x1, y1, x2, y2 };
}

function defaultZone() {
  return { x1: 0.06, y1: 0.18, x2: 0.94, y2: 0.92 };
}

function loadZone(slot, camera) {
  const framing = (camera && camera.framing) || {};
  zoneDraft[slot] = parseRoi(framing.detect_roi) || defaultZone();
  zoneZoom[slot] = Math.min(4, Math.max(1, Number(framing.detect_zoom) || 1));
  const els = paneEls(slot);
  if (els.zoom) els.zoom.value = String(zoneZoom[slot]);
  if (els.zoomLabel) els.zoomLabel.textContent = zoneZoom[slot].toFixed(1) + "×";
  drawLiveOverlay(slot);
}

function drawLiveOverlay(slot) {
  const els = paneEls(slot);
  const canvas = els.canvas;
  if (!canvas) return;
  const frame = canvas.parentElement;
  const rect = (frame || canvas).getBoundingClientRect();
  canvas.width = Math.max(1, Math.round(rect.width));
  canvas.height = Math.max(1, Math.round(rect.height));
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const placed = mediaBox(slot, canvas);
  const box = liveOverlays[slot];
  const media = liveMedia(slot);
  const nw = media && (media.videoWidth || media.naturalWidth);
  if (box && nw) {
    const srcW = box.image_width || nw;
    const srcH = box.image_height || (media.videoHeight || media.naturalHeight);
    const sx = placed.drawW / srcW;
    const sy = placed.drawH / srcH;
    const x = placed.ox + box.x1 * sx;
    const y = placed.oy + box.y1 * sy;
    const w = Math.max(2, (box.x2 - box.x1) * sx);
    const h = Math.max(2, (box.y2 - box.y1) * sy);
    ctx.strokeStyle = "#00dc5a";
    ctx.lineWidth = 2;
    ctx.strokeRect(x, y, w, h);
    if (box.label) {
      ctx.fillStyle = "#00dc5a";
      ctx.font = "14px sans-serif";
      ctx.fillText(box.label, x, Math.max(14, y - 6));
    }
  }
  const zone = zoneDraft[slot];
  if (!zone) return;
  const zx = placed.ox + zone.x1 * placed.drawW;
  const zy = placed.oy + zone.y1 * placed.drawH;
  const zw = (zone.x2 - zone.x1) * placed.drawW;
  const zh = (zone.y2 - zone.y1) * placed.drawH;
  ctx.strokeStyle = "#f5c542";
  ctx.lineWidth = 2;
  ctx.strokeRect(zx, zy, zw, zh);
  const zoom = zoneZoom[slot] || 1;
  if (zoom > 1.05) {
    const innerW = zw / zoom;
    const innerH = zh / zoom;
    ctx.setLineDash([6, 4]);
    ctx.strokeRect(zx + (zw - innerW) / 2, zy + (zh - innerH) / 2, innerW, innerH);
    ctx.setLineDash([]);
  }
}

function pointerToNorm(slot, ev) {
  const canvas = paneEls(slot).canvas;
  const rect = canvas.getBoundingClientRect();
  const placed = mediaBox(slot, canvas);
  const scaleX = canvas.width / Math.max(rect.width, 1);
  const scaleY = canvas.height / Math.max(rect.height, 1);
  const x = ((ev.clientX - rect.left) * scaleX - placed.ox) / placed.drawW;
  const y = ((ev.clientY - rect.top) * scaleY - placed.oy) / placed.drawH;
  return {
    x: Math.min(1, Math.max(0, x)),
    y: Math.min(1, Math.max(0, y)),
  };
}

function bindZoneEditor(pane) {
  const slot = Number(pane.dataset.slot);
  const canvas = pane.querySelector('[data-role="overlay"]');
  const edit = pane.querySelector('[data-role="zone-edit"]');
  const zoom = pane.querySelector('[data-role="zoom"]');
  const save = pane.querySelector('[data-role="zone-save"]');
  const viewZoom = pane.querySelector('[data-role="view-zoom"]');
  if (viewZoom) viewZoom.addEventListener("input", () => {
    const factor = Math.min(4, Math.max(1, Number(viewZoom.value) || 1));
    pane.querySelectorAll('.live-frame > video, .live-frame > img, .live-frame > canvas').forEach((element) => {
      element.style.transform = `scale(${factor})`;
      element.style.transformOrigin = "center center";
    });
    pane.querySelector('[data-role="view-zoom-label"]').textContent = factor.toFixed(1) + "×";
  });
  let drag = null;
  if (edit) edit.addEventListener("click", () => {
    const on = pane.dataset.zoneEdit !== "1";
    pane.dataset.zoneEdit = on ? "1" : "0";
    if (canvas) canvas.classList.toggle("zone-editing", on);
    edit.textContent = on ? "Done drawing" : "Set detection zone";
    const hint = pane.querySelector('[data-role="zone-hint"]');
    if (hint) hint.textContent = on
      ? "Drag on the picture. A tight box where the car stops is better than the whole view."
      : "Drag a box where the car should stop. Detection focus narrows the reading area. View zoom magnifies the picture only. Digital zoom does not add camera detail.";
  });
  if (zoom) zoom.addEventListener("input", () => {
    zoneZoom[slot] = Number(zoom.value) || 1;
    const label = pane.querySelector('[data-role="zoom-label"]');
    if (label) label.textContent = zoneZoom[slot].toFixed(1) + "×";
    drawLiveOverlay(slot);
  });
  if (canvas) {
    canvas.addEventListener("pointerdown", (ev) => {
      if (pane.dataset.zoneEdit !== "1") return;
      ev.preventDefault();
      ev.stopPropagation();
      const start = pointerToNorm(slot, ev);
      drag = start;
      zoneDraft[slot] = { x1: start.x, y1: start.y, x2: start.x, y2: start.y };
      canvas.setPointerCapture(ev.pointerId);
    });
    canvas.addEventListener("pointermove", (ev) => {
      if (!drag || pane.dataset.zoneEdit !== "1") return;
      const point = pointerToNorm(slot, ev);
      zoneDraft[slot] = {
        x1: Math.min(drag.x, point.x),
        y1: Math.min(drag.y, point.y),
        x2: Math.max(drag.x, point.x),
        y2: Math.max(drag.y, point.y),
      };
      drawLiveOverlay(slot);
    });
    const finish = (ev) => {
      if (!drag) return;
      drag = null;
      const zone = zoneDraft[slot];
      if (!zone || zone.x2 - zone.x1 < 0.08 || zone.y2 - zone.y1 < 0.08) {
        zoneDraft[slot] = defaultZone();
        toast("Draw a larger box. It needs to cover the car's plate area.", "warn");
      }
      drawLiveOverlay(slot);
      if (ev) ev.stopPropagation();
    };
    canvas.addEventListener("pointerup", finish);
    canvas.addEventListener("pointercancel", finish);
    canvas.addEventListener("click", (ev) => {
      if (pane.dataset.zoneEdit === "1") ev.stopPropagation();
    });
  }
  if (save) save.addEventListener("click", async () => {
    const cam = liveCameras[slot];
    const zone = zoneDraft[slot];
    if (!cam || !zone) { toast("Choose a camera first.", "warn"); return; }
    const detect_roi = [zone.x1, zone.y1, zone.x2, zone.y2].map((n) => n.toFixed(3)).join(",");
    try {
      const data = await api(`/cameras/${cam.id}/framing`, {
        method: "PUT",
        body: JSON.stringify({ detect_roi, detect_zoom: zoneZoom[slot] || 1 }),
      });
      cam.framing = data.framing;
      const row = cameraRowsCache.find((item) => item.id === cam.id);
      if (row) row.framing = data.framing;
      toast("Detection zone saved. The next stopped car is cropped, then read.");
    } catch (err) {
      toast(err.message, "dgr");
    }
  });
}

function startMjpegLive(slot, id) {
  if (snapshotTimers[slot]) { clearInterval(snapshotTimers[slot]); snapshotTimers[slot] = null; }
  const els = paneEls(slot);
  const prev = liveObjectUrls[slot];
  if (prev) { try { URL.revokeObjectURL(prev); } catch (_) {} liveObjectUrls[slot] = ""; }
  // Continuous MJPEG stream — smoother than 40ms snapshot polling.
  els.img.onload = () => {
    liveRetryCounts[slot] = 0;
    if (els.status) els.status.textContent = "Live";
    drawLiveOverlay(slot);
  };
  els.img.onerror = () => {
    if (els.img.dataset.cameraId !== String(id)) return;
    if (els.status) els.status.textContent = "Reconnecting live stream…";
    if (snapshotTimers[slot]) clearTimeout(snapshotTimers[slot]);
    liveRetryCounts[slot] = (liveRetryCounts[slot] || 0) + 1;
    // Retry the persistent MJPEG stream. Never switch to 120 ms snapshot
    // polling: that restarts/loads decoders and is exactly the backlog path
    // that made live video progressively slow.
    snapshotTimers[slot] = setTimeout(() => {
      snapshotTimers[slot] = null;
      if (els.img.dataset.cameraId === String(id)) startMjpegLive(slot, id);
    }, Math.min(10000, 1000 * (2 ** Math.min(liveRetryCounts[slot] - 1, 4))));
  };
  els.img.src = mediaUrl(`/cameras/${id}/live.mjpeg`) + "&t=" + Date.now();
}

async function reportViewerTransport(cameraId, transport) {
  try {
    await api(`/cameras/${cameraId}/live/viewer-state`, {
      method: "POST",
      body: JSON.stringify({ transport }),
    });
  } catch (_) {}
}

async function startLiveSlot(slot, camera, force = false) {
  const els = paneEls(slot);
  if (els.camera && camera) els.camera.value = String(camera.id);
  if (els.camera && !camera) els.camera.value = "";
  if (!camera) {
    stopLiveSlot(slot);
    liveCameras[slot] = null;
    saveSlotId(slot, null);
    els.status.textContent = "Click this view or the list to choose a camera.";
    els.details.textContent = "Any added camera can go on the left or the right.";
    els.plate.textContent = "—";
    els.snap.innerHTML = `<p class="muted">Waiting for a car</p>`;
    els.crop.innerHTML = `<p class="muted">—</p>`;
    return;
  }
  const id = camera.id;
  liveCameras[slot] = camera;
  loadZone(slot, camera);
  saveSlotId(slot, id);
  if (!force && els.img.dataset.cameraId === String(id) && (snapshotTimers[slot] || whepSessions[slot] || els.img.getAttribute("src"))) {
    refreshPlates(slot);
    return;
  }
  if (els.img.dataset.cameraId !== String(id)) liveLastCars[slot] = null;
  const prev = liveWatchIds[slot];
  stopLiveSlot(slot, false);
  const generation = liveGenerations[slot];
  if (prev && prev !== id) unwatchCamera(prev);
  liveCameras[slot] = camera;
  liveWatchIds[slot] = id;
  els.status.textContent = "Opening live view…";
  els.img.dataset.cameraId = String(id);
  if (prev !== id) watchCamera(id);
  let ep = null;
  try { ep = await api(`/cameras/${id}/live/endpoint`); } catch (_) {}
  if (liveWatchIds[slot] !== id || liveGenerations[slot] !== generation) return; // switched while resolving
  if (ep && ep.provider === "MEDIAMTX" && ep.transport === "WEBRTC" && (ep.whep || ep.webrtc) && els.webrtc) {
    // WebRTC is the only live transport for this pane. Do not also poll
    // snapshot.jpg or MJPEG: that is a second decode path per viewer.
    if (snapshotTimers[slot]) { clearInterval(snapshotTimers[slot]); snapshotTimers[slot] = null; }
    els.img.style.display = "none";
    els.webrtc.style.display = "block";
    const codec = ep.codec ? ` · ${ep.codec}` : "";
    const stateLabel = ep.state && ep.state !== "LIVE" ? ep.state : "CONNECTING";
    els.status.textContent = `${stateLabel} (WebRTC${codec})`;
    try {
      const session = await whepStart(els.webrtc, ep.whep || `${ep.webrtc.replace(/\/$/, "")}/whep`, (connState, activeSession) => {
        if (liveWatchIds[slot] !== id || liveGenerations[slot] !== generation) return;
        if (connState === "video") {
          const seen = whepCodec(activeSession) || ep.codec || "";
          els.status.textContent = `LIVE (WebRTC${seen ? " · " + seen : ""})`;
          reportViewerTransport(id, "WEBRTC");
        } else if (connState === "disconnected") {
          els.status.textContent = "DEGRADED (WebRTC reconnecting)";
        } else if (["failed", "closed", "no-frames", "no-video-track"].includes(connState)) {
          const reason = connState === "no-video-track" ? "MEDIA RECEIVED BUT VIDEO TRACK MISSING" : connState === "no-frames" ? "CODEC UNSUPPORTED OR NO VIDEO FRAMES" : "ICE FAILED";
          els.status.textContent = `${reason} · retrying…`;
          whepClose(activeSession);
          whepStop(slot);
          setTimeout(() => { if (liveWatchIds[slot] === id && liveGenerations[slot] === generation) startLiveSlot(slot, camera, true); }, 3000);
        }
      }, (openingSession) => { whepSessions[slot] = openingSession; });
      if (liveWatchIds[slot] !== id || liveGenerations[slot] !== generation) {
        whepClose(session);
        return;
      }
      whepSessions[slot] = session;
      reportViewerTransport(id, "WEBRTC");
      refreshPlates(slot);
      return;
    } catch (err) {
      if (liveWatchIds[slot] !== id || liveGenerations[slot] !== generation) return;
      // WHEP unavailable: report it and use the MediaMTX-fed MJPEG cache.
      // The failed peer connection is closed first, so still one transport.
      whepStop(slot);
      els.status.textContent = `DEGRADED (WebRTC unavailable: ${err.message}) · DIRECT_MJPEG`;
      reportViewerTransport(id, "MJPEG");
      setTimeout(() => { if (liveWatchIds[slot] === id && liveGenerations[slot] === generation) startLiveSlot(slot, camera, true); }, 5000);
    }
  } else if (ep && ep.reason) {
    els.status.textContent = `DEGRADED · ${ep.reason}`;
  }
  if (els.webrtc) {
    els.webrtc.style.display = "none";
    els.webrtc.srcObject = null;
  }
  els.img.style.display = "block";
  startMjpegLive(slot, id);
  reportViewerTransport(id, "MJPEG");
  refreshPlates(slot);
}

function applyLanePreset() {
  const gateId = document.getElementById("live-lane").value;
  pushRecognitionScope(gateId);
  const pair = pairLaneCameras(cameraLiveRowsCache, gateId);
  [0, 1].forEach((slot) => {
    const cam = pair[slot];
    const sel = paneEls(slot).camera;
    if (sel) sel.value = cam ? String(cam.id) : "";
    saveSlotId(slot, cam ? cam.id : null);
    startLiveSlot(slot, cam, true);
  });
}

function startDualLive(force = false) {
  if (!liveTabVisible()) { stopLive(); return; }
  syncLivePanes();
  fillPaneSelects(cameraLiveRowsCache);
  const slots = [...document.querySelectorAll(".dual-live .live-pane")]
    .map((pane) => Number(pane.dataset.slot))
    .filter((slot) => liveLayout !== "1" || slot === 0);
  if (liveLayout === "all") {
    slots.forEach((slot, index) => {
      const cam = cameraLiveRowsCache[index] || null;
      const sel = paneEls(slot).camera;
      if (sel) sel.value = cam ? String(cam.id) : "";
      startLiveSlot(slot, cam, force);
    });
  } else {
    const anyChosen = slots.some((slot) => cameraFromSelect(slot));
    if (!anyChosen && cameraLiveRowsCache.length) {
      const left = cameraLiveRowsCache[0];
      const right = cameraLiveRowsCache[1] || null;
      if (paneEls(0).camera) paneEls(0).camera.value = left ? String(left.id) : "";
      if (paneEls(1).camera && liveLayout !== "1") paneEls(1).camera.value = right ? String(right.id) : "";
    }
    slots.forEach((slot) => startLiveSlot(slot, cameraFromSelect(slot), force));
  }
  if (!liveAlprTimer) {
    liveAlprTimer = setInterval(() => {
      liveCameras.forEach((cam, slot) => { if (cam) refreshPlates(slot); });
    }, 2000);
  }
}

async function commandCameraBarrier(cameraId, action, errorEl) {
  const error = errorEl || document.getElementById("camera-error");
  const verb = action === "close" ? "close" : "open";
  if (error) error.textContent = "";
  if (!cameraId) {
    const msg = "Select 1# Entry, 1# Exit, 2# Entry, or 2# Exit first.";
    if (error) error.textContent = msg;
    else toast(msg, "warn");
    return;
  }
  const reason = prompt("Reason", `manual ${verb}`);
  if (!reason) return;
  const confirmMsg = verb === "close"
    ? "Close only this camera's barrier (not the other side of the lane)?"
    : "Pulse only this camera's barrier (not the other side of the lane)?";
  if (!confirm(confirmMsg)) return;
  try {
    alert(JSON.stringify(await api(`/cameras/${cameraId}/barrier/open`, {
      method: "POST",
      body: JSON.stringify({ reason, action: verb }),
    })));
  } catch (err) {
    if (error) error.textContent = err.message;
    else toast(err.message, "dgr");
  }
}

async function commandGateBarrier(gateId, side, action) {
  const error = document.getElementById("gate-error");
  const verb = action === "close" ? "close" : "open";
  if (error) error.textContent = "";
  const reason = prompt("Reason", `manual ${verb}`);
  if (!reason) return;
  const label = String(side || "ENTRY").toLowerCase();
  const confirmMsg = verb === "close"
    ? `Close only this lane's ${label} barrier (not the other side)?`
    : `Pulse only this lane's ${label} barrier (not the other side)?`;
  if (!confirm(confirmMsg)) return;
  try {
    alert(JSON.stringify(await api(`/gates/${gateId}/open`, {
      method: "POST",
      body: JSON.stringify({ reason, side: side || "ENTRY", action: verb }),
    })));
  } catch (err) {
    if (error) error.textContent = err.message;
  }
}

async function openPaneSide(slot, action) {
  const cam = liveCameras[slot] || cameraFromSelect(slot);
  const error = document.getElementById("camera-error");
  if (!cam) { error.textContent = "No camera on this view."; return; }
  await commandCameraBarrier(cam.id, action || "open", error);
}

async function correctPanePlate(slot) {
  const cam = liveCameras[slot];
  const shown = liveLastCars[slot] || {};
  const error = document.getElementById("camera-error");
  if (!cam) { error.textContent = "No camera on this view."; return; }
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
}

function fillLiveLanes(rows, gates) {
  const select = document.getElementById("live-lane");
  if (!select) return;
  const current = select.value;
  const seen = new Map();
  (gates || gateRowsCache || []).forEach((g) => {
    if (g.id != null) seen.set(String(g.id), g.name || `Lane ${g.id}`);
  });
  (rows || []).forEach((c) => {
    if (c.gate_id == null) return;
    if (!seen.has(String(c.gate_id))) seen.set(String(c.gate_id), c.lane_name || c.gate_name || `Lane ${c.gate_id}`);
  });
  let html = `<option value="">All cameras</option>`;
  seen.forEach((name, id) => { html += `<option value="${id}">${name}</option>`; });
  select.innerHTML = html;
  if (current && [...select.options].some((o) => o.value === current)) select.value = current;
  else if (!current && seen.size) select.value = [...seen.keys()][0];
  pushRecognitionScope(select.value);
}

function pushRecognitionScope(gateId) {
  const hint = document.getElementById("recognition-scope-hint");
  api("/runtime/recognition-scope").then((body) => {
    if (body.deployment_profile === "DEVELOPMENT" && !body.pinned) return api("/runtime/recognition-scope", {
      method: "POST", body: JSON.stringify({ gate_id: gateId ? Number(gateId) : null }),
    });
    return body;
  }).then((body) => {
    if (hint) hint.textContent = (body && body.detail) || "";
  }).catch((err) => {
    if (hint) hint.textContent = err.message || "";
  });
}

async function assignRecognitionOwner() {
  const hint = document.getElementById("recognition-scope-hint");
  const gateId = document.getElementById("live-lane").value;
  if (!gateId) {
    if (hint) hint.textContent = "Select a gate first.";
    return;
  }
  const button = document.getElementById("assign-recognition-owner");
  if (button) button.disabled = true;
  try {
    const body = await api("/runtime/recognition-owner", {
      method: "PUT",
      body: JSON.stringify({ gate_id: Number(gateId) }),
    });
    if (hint) hint.textContent = body.detail || "This PC is now assigned to the selected gate.";
    toast("Recognition ownership assigned. Loading this gate's cameras.", "info");
    await loadCameras();
    applyLanePreset();
  } catch (err) {
    if (hint) hint.textContent = err.message || "Could not assign this PC.";
    toast(err.message || "Could not assign this PC.", "dgr");
  } finally {
    if (button) button.disabled = false;
  }
}

function showCameraSub(name) {
  cameraSub = name;
  document.querySelectorAll("#cameras-subnav button").forEach((b) => b.classList.toggle("active", b.dataset.sub === name));
  document.getElementById("cameras-sub-live").classList.toggle("hidden", name !== "live");
  document.getElementById("cameras-sub-ips").classList.toggle("hidden", name !== "ips");
  if (name === "live") startDualLive();
  else stopLive();
}

function streamLine(role, row) {
  if (!row || !Object.keys(row).length) return "";
  const bits = [role];
  if (row.codec) bits.push(String(row.codec).toUpperCase());
  if (row.width && row.height) bits.push(`${row.width}x${row.height}`);
  if (row.fps) bits.push(`${row.fps} FPS`);
  if (row.gop) bits.push(`GOP ${row.gop}`);
  if (row.transport) bits.push(row.transport);
  if (row.source) bits.push(`Source: ${row.source}`);
  if (row.ai_fps) bits.push(`AI sampling: ${row.ai_fps} FPS`);
  if (row.protocol) bits.push(row.protocol);
  return bits.join(" · ");
}

function renderStreamProfiles(data) {
  const box = document.getElementById("stream-profiles");
  if (!box) return;
  if (!data) {
    box.innerHTML = `<p class="muted">Select a camera to see MAIN / SUB / DETECT roles, codec, FPS, GOP, transport, and frame age.</p>`;
    return;
  }
  const profiles = data.stream_profiles || {};
  const media = data.media || {};
  const cards = ["MAIN", "SUB", "LIVE", "DETECT", "EVIDENCE"].map((role) => {
    const line = streamLine(role, profiles[role]);
    if (!line) return "";
    return `<div class="stream-card"><strong>${role}</strong>${line.replace(role + " · ", "").replace(role, "") || line}</div>`;
  }).filter(Boolean);
  const age = [];
  if (media.live_frame_age_ms != null) age.push(`Live frame age ${Math.round(media.live_frame_age_ms)} ms`);
  if (media.ai_frame_age_ms != null) age.push(`AI frame age ${Math.round(media.ai_frame_age_ms)} ms`);
  if (media.fps) age.push(`Live ${media.fps} FPS`);
  if (media.ai_fps) age.push(`AI ${media.ai_fps} FPS`);
  if (media.connection_state) age.push(media.connection_state);
  const warnings = (data.warnings || media.warnings || []).map((w) => `<li>${w}</li>`).join("");
  box.innerHTML = `
    <div class="stream-grid">${cards.join("") || "<p class='muted'>No profiles stored yet. Probe RTSP or ONVIF profiles after Connect.</p>"}</div>
    <p class="muted">${age.join(" · ") || "Frame age appears after the media gateway produces frames."}</p>
    ${renderMediaMtxTelemetry(media.mediamtx, data.live_endpoint)}
    ${warnings ? `<ul class="warn-list">${warnings}</ul>` : ""}
  `;
}

function renderMediaMtxTelemetry(tele, liveEndpoint) {
  if (!tele) return "";
  const esc = (v) => String(v == null ? "" : v).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    const transport = (liveEndpoint && (liveEndpoint.live_provider || liveEndpoint.transport)) || "";
    const head = [
    `Media <strong>${esc(tele.state || "OFFLINE")}</strong>`,
    transport ? `Live provider ${esc(transport)}` : "",
    tele.codec ? `Codec ${esc(tele.codec)}` : "",
    tele.control_api_ok ? "Control API OK" : "Control API unreachable",
  ].filter(Boolean).join(" · ");
  const rows = Object.entries(tele.roles || {}).map(([role, row]) => {
    const rtp = row.rtp || {};
    const bits = [
      `<strong>${esc(role)}</strong>`,
      `path ${esc(row.mediamtx_path || "")}${row.shared_upstream ? " (shared upstream)" : ""}${row.on_demand ? " (on demand)" : ""}`,
      row.ready ? "ready" : (row.registered ? "not ready" : "not registered"),
      row.readers != null ? `readers ${row.readers}` : "",
      rtp.packets_lost != null ? `RTP loss ${rtp.packets_lost}` : "",
      rtp.packets_in_error != null ? `RTP errors ${rtp.packets_in_error}` : "",
      rtp.jitter_max != null ? `jitter ${Math.round(Number(rtp.jitter_max) * 100) / 100}` : "",
      row.reconnects != null ? `reconnects ${row.reconnects}` : "",
      row.bytes_received != null ? `in ${Math.round(Number(row.bytes_received) / 1024)} KiB` : "",
    ].filter(Boolean).join(" · ");
    return `<li>${bits}</li>`;
  }).join("");
  const compat = tele.webrtc || {};
  const compatLine = compat.compatible === false
    ? `<li class="warn">${esc(compat.reason)}</li>`
    : (compat.compatible === null && compat.reason && tele.codec ? `<li>${esc(compat.reason)}</li>` : "");
  return `<div class="mediamtx-telemetry"><p class="muted">${head}</p><ul class="muted">${rows}${compatLine}</ul></div>`;
}

async function refreshStreamProfiles(id) {
  try {
    renderStreamProfiles(await api(`/cameras/${id}/streams`));
  } catch (_) {}
}

function renderSlotCar(slot, data) {
  const els = paneEls(slot);
  const emptyLane = Boolean(data && (data.clear_last_car || data.vehicle_present === false));
  if (emptyLane) {
    liveLastCars[slot] = null;
    liveOverlays[slot] = null;
  }
  const last = emptyLane ? {} : ((data && (data.last_car || data.capture)) || {});
  if (!emptyLane && (last.snapshot_url || last.crop_url || last.plate)) liveLastCars[slot] = last;
  const shown = emptyLane ? {} : (liveLastCars[slot] || last);
  const plate = emptyLane ? "" : (shown.plate || shown.plate_raw || (data && data.current_plate) || "");
  const chars = shown.characters || (plate ? plate.split("").join(" ") : "—");
  els.plate.textContent = chars;
  const setEvidence = (container, url, label, empty) => {
    const next = url ? mediaUrl(url) : "";
    if (container.dataset.evidenceUrl === next) return;
    container.dataset.evidenceUrl = next;
    container.replaceChildren();
    if (next) {
      const img = document.createElement("img");
      img.alt = label;
      img.onerror = () => {
        if (container.dataset.evidenceUrl === next) container.dataset.evidenceUrl = "";
      };
      img.src = next;
      container.appendChild(img);
    } else {
      const text = document.createElement("p");
      text.className = "muted";
      text.textContent = empty;
      container.appendChild(text);
    }
  };
  setEvidence(els.snap, shown.snapshot_url, "Vehicle snapshot", "Waiting for a vehicle");
  const cropUrl = emptyLane ? "" : (shown.crop_url || (data && data.plate_crop_url) || "");
  setEvidence(els.crop, cropUrl, "Plate crop used for recognition", "Waiting for a plate crop");
  const cam = liveCameras[slot] || {};
  const pct = confidencePercent(shown.confidence);
  const conf = pct != null ? `${pct}%` : "";
  const source = sourceLabel(shown.source || (data && data.fusion && data.fusion.method) || "");
  const side = shown.lane_direction || cam.side || cam.lane_direction || "";
  const when = formatWhen(shown.created_at);
  const fusion = (data && data.fusion) || shown.fusion || {};
  const held = Boolean(shown.pending_confirmation || shown.needs_review || fusion.needs_review);
  const low = pct != null && pct < 80;
  if (els.confidence) els.confidence.textContent = conf;
  if (els.decision) {
    if (!plate) els.decision.innerHTML = "";
    else if (held || low) els.decision.innerHTML = `<span class="chip c-wrn">Check plate</span>`;
    else els.decision.innerHTML = `<span class="chip c-ok">Plate read</span>`;
  }
  if (els.bizLast) els.bizLast.textContent = plate ? (when || "Just now") : "—";
  if (els.bizRecog) els.bizRecog.textContent = plate ? source : "Waiting";
  if (plate) {
    const bits = [when, side, isTechnician() ? source : ""].filter(Boolean);
    els.details.textContent = bits.join(" · ");
    if (els.hold) els.hold.textContent = held ? "Confirm or correct this plate before the barrier decides." : "";
  } else {
    els.details.textContent = "No vehicle yet. Add a camera on Devices, then wait for a vehicle.";
    if (els.hold) els.hold.textContent = "";
  }
  liveOverlays[slot] = (data && data.overlay) || null;
  drawLiveOverlay(slot);
}

async function refreshPlates(slot) {
  const camera = liveCameras[slot];
  const els = paneEls(slot);
  if (!camera || plateRequests.has(slot)) return;
  plateRequests.add(slot);
  try {
    if (alprInstalled === null) {
      try { alprInstalled = Boolean((await api("/alpr/status", { timeoutMs: 5000 })).installed); }
      catch (_) { alprInstalled = false; }
    }
    const data = await api(`/cameras/${camera.id}/plates`, { timeoutMs: 5000 });
    if (!liveCameras[slot] || liveCameras[slot].id !== camera.id) return;
    const camName = (camera.name || "Camera");
    if (els.bizCamera) els.bizCamera.textContent = camName;
    if (els.online) {
      els.online.textContent = data.live ? "Online" : "No video";
      els.online.className = "chip " + (data.live ? "c-ok" : "c-wrn");
    }
    if (els.bizVideo) els.bizVideo.textContent = data.live ? "Live" : "Waiting";
    if (whepSessions[slot]) {
      // WebRTC pane: the transport state (LIVE / DEGRADED / OFFLINE) is
      // owned by the peer-connection callbacks; do not overwrite it here.
    } else if (data.live) {
      if (isTechnician()) {
        const fps = data.live_fps ? ` · ${data.live_fps} fps` : "";
        const src = data.live_source ? ` · ${data.live_source}` : "";
        const age = data.live_frame_age_ms != null ? ` · ${Math.round(data.live_frame_age_ms)} ms` : "";
        els.status.textContent = (data.url_redacted ? `Live${src}${fps}${age} · ${data.url_redacted}` : `Live${src}${fps}${age}`);
      } else {
        els.status.textContent = "Video is live.";
      }
    } else {
      els.status.textContent = isTechnician()
        ? (data.error || "Waiting for first frame…")
        : "Video unavailable. The camera may still be reading plates. Retry, or ask a technician if this continues.";
    }
    renderSlotCar(slot, data);
  } catch (err) {
    if (els.status && liveCameras[slot] && liveCameras[slot].id === camera.id) els.status.textContent = err.message;
  } finally {
    plateRequests.delete(slot);
  }
}
