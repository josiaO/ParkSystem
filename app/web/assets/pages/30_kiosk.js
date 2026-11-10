let kioskVisit = null;
function showKioskVisit(data) {
  kioskVisit = data;
  selectedSessionId = Number(data.session_id);
  const card = document.getElementById("kiosk-card");
  card.classList.remove("hidden");
  document.getElementById("kiosk-plate").textContent = data.plate || "—";
  const inside = data.still_inside ? "still inside" : "visit ended";
  document.getElementById("kiosk-stay").textContent = `Time on site: ${data.duration_label || "—"} (${inside}). Entered ${formatWhen(data.entry_time)}.`;
  const remain = Math.round(Number(data.amount_remaining || 0));
  document.getElementById("kiosk-due").textContent = data.payable
    ? `${data.currency || "TZS"} ${remain.toLocaleString()} to pay`
    : "Nothing to pay";
  document.getElementById("kiosk-note").textContent = data.image_note || "";
  const photo = document.getElementById("kiosk-photo");
  const crop = document.getElementById("kiosk-crop");
  const missing = document.getElementById("kiosk-photo-missing");
  if (data.snapshot_url) {
    photo.hidden = false;
    photo.src = data.snapshot_url;
    missing.hidden = true;
  } else {
    photo.hidden = true;
    photo.removeAttribute("src");
    missing.hidden = false;
  }
  if (data.crop_url) {
    crop.hidden = false;
    crop.src = data.crop_url;
  } else {
    crop.hidden = true;
    crop.removeAttribute("src");
  }
  document.getElementById("kiosk-correct").value = data.image_matches_plate === false ? "" : (data.plate || "");
  const allow = Boolean(data.payable) && (can("payments.create") || can("kiosk.use"));
  document.getElementById("kiosk-pay").disabled = !allow;
  document.getElementById("kiosk-mobile").disabled = !data.payable;
  document.getElementById("pay-session").disabled = !allow;
}

async function lookupReceipt() {
  const err = document.getElementById("session-error");
  err.textContent = "";
  const token = (document.getElementById("receipt-token").value || "").trim();
  if (!token) {
    err.textContent = "Scan the receipt QR or type a plate.";
    return;
  }
  try {
    const data = await api(`/sessions/lookup?q=${encodeURIComponent(token)}`);
    await loadSessions();
    const row = document.querySelector(`#session-rows tr[data-id="${data.session_id}"]`);
    if (row) {
      document.querySelectorAll("#session-rows tr").forEach((r) => r.classList.remove("selected"));
      row.classList.add("selected");
      row.scrollIntoView({ block: "nearest" });
    }
    showKioskVisit(data);
    err.textContent = "";
  } catch (e) {
    err.textContent = e.message;
  }
}

document.getElementById("lookup-receipt").addEventListener("click", lookupReceipt);
document.getElementById("receipt-token").addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); lookupReceipt(); }
});
async function recordKioskPayment() {
  const err = document.getElementById("session-error");
  err.textContent = "";
  if (kioskVisit && !kioskVisit.payable) {
    err.textContent = kioskVisit.pay_blocked_reason || "This vehicle does not have a fee to pay.";
    return;
  }
  const token = (kioskVisit && kioskVisit.token) || "";
  if (!selectedSessionId && !token) {
    err.textContent = "Scan a receipt QR or select a visit first.";
    return;
  }
  try {
    if (token) {
      const data = await api(`/p/${encodeURIComponent(token)}/kiosk-pay`, {
        method: "POST",
        body: JSON.stringify({ method: "KIOSK_CASH" }),
      });
      if (data.already_paid) err.textContent = "Already settled. Nothing new to collect.";
      showKioskVisit(data.session_id ? data : (data.session || data));
    } else {
      await api(`/sessions/${selectedSessionId}/pay`, { method: "POST", body: JSON.stringify({ method: "KIOSK_CASH" }) });
    }
    await loadSessions();
    await loadPayments();
    if (token) {
      const fresh = await api(`/sessions/lookup?q=${encodeURIComponent(token)}`);
      showKioskVisit(fresh);
    }
  } catch (e) {
    err.textContent = e.message;
  }
}
document.getElementById("pay-session").addEventListener("click", recordKioskPayment);
document.getElementById("kiosk-pay").addEventListener("click", recordKioskPayment);
document.getElementById("kiosk-mobile").addEventListener("click", async () => {
  const err = document.getElementById("session-error");
  err.textContent = "";
  if (!kioskVisit || !kioskVisit.payable || !kioskVisit.token) {
    err.textContent = (kioskVisit && kioskVisit.pay_blocked_reason) || "Scan a receipt before paying by mobile.";
    return;
  }
  try {
    const data = await api(`/p/${encodeURIComponent(kioskVisit.token)}/pay`, {
      method: "POST",
      body: JSON.stringify({ method: "MOBILE_SIMULATED" }),
    });
    showKioskVisit(data);
    await loadSessions();
    await loadPayments();
  } catch (e) {
    err.textContent = e.message;
  }
});
document.getElementById("kiosk-save-plate").addEventListener("click", async () => {
  const err = document.getElementById("session-error");
  err.textContent = "";
  if (!selectedSessionId) { err.textContent = "Find a visit first."; return; }
  const plate = document.getElementById("kiosk-correct").value.trim();
  if (!plate) { err.textContent = "Type the plate you can see on the car."; return; }
  try {
    await api(`/sessions/${selectedSessionId}/correct-plate`, {
      method: "POST",
      body: JSON.stringify({ plate, confirm: true }),
    });
    const token = (kioskVisit && kioskVisit.token) || plate;
    const fresh = await api(`/sessions/lookup?q=${encodeURIComponent(token)}`);
    showKioskVisit(fresh);
    await loadSessions();
  } catch (e) {
    err.textContent = e.message;
  }
});
document.getElementById("scan-receipt-camera").addEventListener("click", async () => {
  const err = document.getElementById("session-error");
  err.textContent = "";
  if (!("BarcodeDetector" in window) || !navigator.mediaDevices) {
    err.textContent = "This browser cannot scan with a webcam. Use a USB scanner in the box above.";
    return;
  }
  const video = document.getElementById("qr-camera");
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
    video.hidden = false;
    video.srcObject = stream;
    await video.play();
    const detector = new BarcodeDetector({ formats: ["qr_code"] });
    const timer = setInterval(async () => {
      try {
        const codes = await detector.detect(video);
        if (!codes || !codes[0]) return;
        clearInterval(timer);
        stream.getTracks().forEach((track) => track.stop());
        video.hidden = true;
        document.getElementById("receipt-token").value = codes[0].rawValue || "";
        lookupReceipt();
      } catch (_) {}
    }, 500);
  } catch (e) {
    err.textContent = "Camera permission was blocked. Use a USB scanner instead.";
  }
});
document.getElementById("vehicle-cancel").addEventListener("click", () => document.getElementById("vehicle-dialog").close());
document.getElementById("vehicle-from-today").addEventListener("click", () => {
  const now = new Date();
  const p = (n) => String(n).padStart(2, "0");
  document.querySelector("#vehicle-form [name=valid_from]").value = `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}`;
});
document.getElementById("vehicle-until-today").addEventListener("click", () => {
  const now = new Date();
  const p = (n) => String(n).padStart(2, "0");
  document.querySelector("#vehicle-form [name=valid_until]").value = `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}`;
});
document.getElementById("save-vehicle-bulk").addEventListener("click", async () => {
  const error = document.getElementById("vehicle-error");
  error.textContent = "";
  const lines = document.getElementById("vehicle-bulk").value.split(/\n/).map((line) => line.trim()).filter(Boolean);
  if (!lines.length) { error.textContent = "Add one plate per line."; return; }
  const vehicles = lines.map((line) => {
    const [plate, owner, from, until] = line.split(",").map((part) => (part || "").trim());
    return {
      plate,
      owner_name: owner || "",
      valid_from: from ? `${from}T00:00:00Z` : null,
      valid_until: until ? `${until}T23:59:59Z` : null,
    };
  });
  try {
    const result = await api("/vehicles/bulk", { method: "POST", body: JSON.stringify({ vehicles }) });
    const failed = (result.errors || []).map((item) => item.error).join("; ");
    error.textContent = failed ? `Saved ${result.created.length}. ${failed}` : `Registered ${result.created.length} plates.`;
    document.getElementById("vehicle-bulk").value = "";
    loadVehicles();
  } catch (err) {
    error.textContent = err.message;
  }
});
document.getElementById("delete-vehicles").addEventListener("click", async () => {
  const ids = [...document.querySelectorAll("[data-vehicle-check]:checked")].map((el) => Number(el.dataset.vehicleCheck));
  const error = document.getElementById("vehicle-error");
  if (!ids.length) { error.textContent = "Select at least one plate."; return; }
  if (!confirm(`Remove ${ids.length} registered plate(s)?`)) return;
  try {
    await api("/vehicles/bulk-delete", { method: "POST", body: JSON.stringify({ ids }) });
    loadVehicles();
  } catch (err) {
    error.textContent = err.message;
  }
});
document.getElementById("vehicle-rows").addEventListener("click", async (e) => {
  const editId = e.target.getAttribute && e.target.getAttribute("data-edit-vehicle");
  const delId = e.target.getAttribute && e.target.getAttribute("data-del-vehicle");
  if (editId) {
    const rows = await api("/vehicles");
    openVehicleDialog(rows.find((v) => String(v.id) === String(editId)));
  }
  if (delId && confirm("Remove this registered plate?")) {
    await api(`/vehicles/${delId}`, { method: "DELETE" });
    loadVehicles();
  }
});
document.getElementById("vehicle-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const error = document.getElementById("vehicle-dialog-error");
  error.textContent = "";
  const payload = {
    plate: form.elements.plate.value,
    owner_name: form.elements.owner_name.value,
    plan_id: Number(form.elements.plan_id.value) || null,
    enabled: form.elements.enabled.value === "true",
    notes: form.elements.notes.value,
    valid_from: form.elements.valid_from.value ? `${form.elements.valid_from.value}T00:00:00Z` : null,
    valid_until: form.elements.valid_until.value ? `${form.elements.valid_until.value}T23:59:59Z` : null,
  };
  try {
    if (form.elements.id.value) await api(`/vehicles/${form.elements.id.value}`, { method: "PATCH", body: JSON.stringify(payload) });
    else await api("/vehicles", { method: "POST", body: JSON.stringify(payload) });
    document.getElementById("vehicle-dialog").close();
    loadVehicles();
  } catch (err) {
    error.textContent = err.message;
  }
});
document.getElementById("camera-cancel").addEventListener("click", () => document.getElementById("camera-dialog").close());
document.getElementById("camera-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const error = document.getElementById("camera-dialog-error");
  const payload = {
    name: form.elements.name.value.trim(),
    ip_address: form.elements.ip_address.value.trim(),
    sdk_port: Number(form.elements.sdk_port.value),
    username: form.elements.username.value,
    lane_direction: form.elements.lane_direction.value,
    controller_ip: form.elements.controller_ip.value.trim(),
    display_ip: form.elements.display_ip.value.trim(),
    rtsp_url: form.elements.rtsp_url.value.trim(),
    adapter_id: form.elements.adapter_id.value || "hvx",
    ffmpeg_profile: form.elements.ffmpeg_profile ? form.elements.ffmpeg_profile.value : "LOW_LATENCY_LAN",
    rtsp_transport: form.elements.rtsp_transport ? form.elements.rtsp_transport.value : "TCP",
    recognition_mode: form.elements.recognition_mode ? form.elements.recognition_mode.value : "",
    gate_id: form.elements.gate_id.value ? Number(form.elements.gate_id.value) : null,
  };
  if (form.elements.password.value) payload.password = form.elements.password.value;
  const id = form.elements.id.value;
  try {
    if (id) await api(`/cameras/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
    else await api("/cameras", { method: "POST", body: JSON.stringify({ ...payload, password: form.elements.password.value }) });
    document.getElementById("camera-dialog").close();
    loadCameras();
  } catch (err) {
    error.textContent = err.message;
  }
});

async function cameraAction(path) {
  const error = document.getElementById("camera-error");
  const result = document.getElementById("camera-result");
  error.textContent = "";
  if (!selectedCameraId) { error.textContent = "Select a camera first."; return; }
  try {
    const data = await api(`/cameras/${selectedCameraId}${path}`, { method: "POST" });
    result.classList.remove("hidden");
    result.textContent = JSON.stringify(data, null, 2);
    if (data.plates || data.annotated_url || data.native || data.fusion || data.alpr || data.last_car) {
      liveCameras.forEach((cam, slot) => {
        if (cam && String(cam.id) === String(selectedCameraId)) renderSlotCar(slot, data);
      });
    }
    loadCameras();
    if (path.includes("sdk/connect") || path.includes("sdk/disconnect")) {
      if (liveTabVisible()) startDualLive(true);
    }
  } catch (err) {
    error.textContent = err.message;
  }
}
document.getElementById("sdk-connect").addEventListener("click", () => cameraAction("/sdk/connect"));
document.getElementById("sdk-disconnect").addEventListener("click", () => {
  if (!confirm("Disconnect this camera? Live video for it stops until someone connects it again.")) return;
  cameraAction("/sdk/disconnect");
});
document.getElementById("open-this-side").addEventListener("click", () => {
  commandCameraBarrier(selectedCameraId, "open");
});
document.getElementById("close-this-side").addEventListener("click", () => {
  commandCameraBarrier(selectedCameraId, "close");
});
document.getElementById("rtsp-probe").addEventListener("click", () => cameraAction("/rtsp/probe"));
document.getElementById("onvif-discover").addEventListener("click", () => cameraAction("/onvif/discover"));
document.getElementById("fastalpr").addEventListener("click", () => cameraAction("/alpr/recognize"));
document.getElementById("capture-snapshot").addEventListener("click", async () => {
  const error = document.getElementById("camera-error");
  error.textContent = "";
  if (!selectedCameraId) { error.textContent = "Select a camera first."; return; }
  try {
    const data = await api(`/cameras/${selectedCameraId}/snapshot/capture`, { method: "POST", body: "{}" });
    document.getElementById("camera-result").classList.remove("hidden");
    document.getElementById("camera-result").textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    error.textContent = err.message;
  }
});
document.getElementById("discover-cameras").addEventListener("click", async () => {
  const error = document.getElementById("camera-error");
  const result = document.getElementById("camera-result");
  const table = document.getElementById("discover-table");
  const rows = document.getElementById("discover-rows");
  error.textContent = "";
  result.classList.remove("hidden");
  result.textContent = "Scanning the LAN for HVX (port 30000) and web/RTSP cameras…";
  table.classList.add("hidden");
  rows.innerHTML = "";
  try {
    const data = await api("/cameras/discover?scan_lan=true", { timeoutMs: 45000 });
    lastDiscover = data;
    const cameras = data.cameras || [];
    cameras.forEach((c) => {
      const tr = document.createElement("tr");
      const kind = c.kind || c.adapter_id || "hvx";
      const plates = c.plate_engine === "fastalpr" ? "FastALPR" : "native";
      tr.innerHTML = `<td>${c.ip_address}</td><td>${kind}</td><td>${c.adapter_id || "hvx"}</td><td>${c.reachable ? "yes" : "no"}</td><td>${plates}</td><td class="muted">${c.already_added ? "already added · " : ""}${c.note || ""}</td>`;
      rows.appendChild(tr);
    });
    table.classList.toggle("hidden", cameras.length === 0);
    const ipcams = cameras.filter((c) => (c.adapter_id || "hvx") !== "hvx" && c.reachable);
    result.textContent = (
      `${cameras.length} device(s). ${ipcams.length} web/RTSP camera(s) ready for username/password.\n` +
      (data.note || "")
    );
    if (data.hvx && data.hvx.error) result.textContent += "\nHVX: " + data.hvx.error;
  } catch (err) {
    error.textContent = err.message;
  }
});
document.getElementById("add-ip-cameras").addEventListener("click", async () => {
  const error = document.getElementById("camera-error");
  const result = document.getElementById("camera-result");
  error.textContent = "";
  const cameras = ((lastDiscover && lastDiscover.cameras) || []).filter(
    (c) => (c.adapter_id || "hvx") !== "hvx" && c.reachable
  );
  if (!cameras.length) {
    error.textContent = "Click Discover first. Add IP cameras is for Dahua/Hikvision/web cameras, not HVX.";
    return;
  }
  result.classList.remove("hidden");
  result.textContent = `Adding and connecting ${cameras.length} IP camera(s)…`;
  try {
    const data = await api("/cameras/import-discovered", {
      method: "POST",
      timeoutMs: 60000,
      body: JSON.stringify({
        username: document.getElementById("ipcam-user").value.trim() || "admin",
        password: document.getElementById("ipcam-pass").value,
        connect: true,
        cameras: cameras.map((c) => ({
          ip_address: c.ip_address,
          adapter_id: c.adapter_id || "rtsp",
          name: c.name,
          lane_direction: c.lane_direction || "ENTRY",
        })),
      }),
    });
    const connected = (data.connected || []).filter((row) => row.status === "VIDEO_CONNECTED");
    result.textContent = `Added ${data.created.length}. Connected ${connected.length} for live video + FastALPR.\nHVX cameras are unchanged — use Connect all for NetSDK login.`;
    await loadCameras();
    if (liveTabVisible()) startDualLive(true);
  } catch (err) {
    error.textContent = err.message;
  }
});
document.getElementById("connect-all").addEventListener("click", async () => {
  const error = document.getElementById("camera-error");
  const result = document.getElementById("camera-result");
  error.textContent = "";
  result.classList.remove("hidden");
  result.textContent = "Connecting cameras one at a time. Unreachable cameras are skipped…";
  try {
    const cameras = await api("/cameras");
    const lines = [];
    let connected = 0;
    let attempted = 0;
    let skipped = 0;
    for (const cam of cameras) {
      if (cam.enabled === false) continue;
      attempted += 1;
      result.textContent = `Connecting ${cam.name} (${attempted}/${cameras.length})…`;
      try {
        const item = await api(`/cameras/${cam.id}/sdk/connect`, { method: "POST", body: "{}", timeoutMs: 25000 });
        if (item.status === "SDK_CONNECTED") connected += 1;
        if (item.sdk_result && item.sdk_result.skipped) skipped += 1;
        const err = item.last_error || (item.sdk_result && item.sdk_result.error);
        if (err) lines.push(`${item.name || cam.name}: ${err}`);
      } catch (e) {
        skipped += 1;
        lines.push(`${cam.name}: ${e.message}`);
      }
    }
    result.textContent = [`Connected ${connected} / ${attempted}`, skipped ? `Skipped ${skipped} unreachable or slow camera(s).` : "", ...lines].filter(Boolean).join("\n");
    loadCameras();
  } catch (err) {
    error.textContent = err.message;
  }
});
