function commissionEsc(value) {
  return String(value == null ? "" : value).replace(/[&<>"]/g, function (ch) {
    return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[ch];
  });
}

function renderCommissioning(data) {
  const summary = document.getElementById("commission-summary");
  const evidence = document.getElementById("commission-evidence");
  const recs = document.getElementById("commission-recommendations");
  const details = document.getElementById("commission-details");
  if (!summary || !evidence || !recs || !details) return;

  const recognition = data.recognition || {};
  const capture = data.capture || {};
  const quality = capture.capture_quality || {};
  const media = data.media || {};
  const worker = data.worker || {};
  const detect = data.detect_stream || {};
  const fusion = capture.fusion || {};
  const native = capture.native || {};
  const local = capture.local || recognition.latest_local || {};
  function conf(value) {
    const pct = confidencePercent(value);
    return pct == null ? "—" : pct + "%";
  }
  function age(value) {
    return value == null ? "—" : Math.round(Number(value)) + " ms";
  }

  summary.innerHTML =
    '<span class="chip ' + (recognition.native_capable ? 'c-ok' : 'c-mut') + '">' +
      (recognition.native_capable ? 'Native ALPR capable' : 'Software ALPR') + '</span> ' +
    '<span class="chip c-info">' + commissionEsc(recognition.mode || "—") + '</span> ' +
    '<span class="chip ' + ((media.connection_state === "STREAMING" || media.connection_state === "LIVE") ? 'c-ok' : 'c-wrn') + '">' +
      commissionEsc(media.connection_state || "—") + '</span> ' +
    '<span class="chip ' + (worker.owns_continuous_software_reads ? 'c-info' : 'c-mut') + '">' +
      (worker.owns_continuous_software_reads ? 'Continuous DETECT worker' : 'Event-driven software verification') + '</span>';

  const cropUrl = capture.crop_url || ((recognition.latest_local || {}).crop_url || "");
  const snapshotUrl = capture.snapshot_url || "";
  let images = "";
  if (snapshotUrl) images += '<img alt="vehicle evidence" src="' + mediaUrl(snapshotUrl) + '" style="max-width:360px;max-height:200px;object-fit:contain;background:#000;border-radius:8px">';
  if (cropUrl) images += '<img alt="plate crop" src="' + mediaUrl(cropUrl) + '" style="max-width:320px;max-height:120px;object-fit:contain;background:#000;border-radius:8px">';
  if (!images) images = '<span class="muted">No stored event image yet.</span>';

  evidence.innerHTML =
    '<div><span>Latest plate</span><b class="plate">' + commissionEsc(capture.plate || local.plate || native.plate || "—") + '</b></div>' +
    '<div><span>Native reading</span><b>' + commissionEsc(native.plate || capture.native_plate || "—") + ' · ' + conf(native.confidence || fusion.native_confidence) + '</b></div>' +
    '<div><span>Zirp reading</span><b>' + commissionEsc(local.plate || capture.local_plate || "—") + ' · ' + conf(local.confidence || fusion.local_confidence) + '</b></div>' +
    '<div><span>Fusion</span><b>' + commissionEsc(fusion.method || "—") + (fusion.needs_review ? ' · review' : '') + '</b></div>' +
    '<div><span>Plate width</span><b>' + (quality.plate_width_px ? quality.plate_width_px + ' px' : '—') + ' · ' + commissionEsc(quality.quality || "UNKNOWN") + '</b></div>' +
    '<div><span>OCR latency</span><b>' + ((recognition.latest_local && recognition.latest_local.latency_ms != null) ? Math.round(Number(recognition.latest_local.latency_ms)) + ' ms' : '—') + '</b></div>' +
    '<div><span>Live video</span><b>' + (media.live_fps || 0) + ' FPS · frame age ' + age(media.live_frame_age_ms) + '</b></div>' +
    '<div><span>DETECT</span><b>' + (media.ai_processed_fps || 0) + ' FPS · frame age ' + age(media.detect_frame_age_ms) + '</b></div>' +
    '<div><span>DETECT source</span><b>' + commissionEsc(detect.configured_source || "—") + ' → recommended ' + commissionEsc(detect.recommended_source || "—") + '</b></div>' +
    '<div><span>RTSP</span><b>' + commissionEsc(media.transport || "—") + ' · ' + commissionEsc(media.codec || "—") + ' · reconnects ' + (media.reconnects || 0) + '</b></div>' +
    '<div style="grid-column:1/-1"><span>Recognition evidence</span><div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:8px">' + images + '</div></div>';

  recs.innerHTML = (data.recommendations || []).map(function (row) {
    const sev = String(row.severity || "info").toLowerCase();
    const tone = sev === "critical" ? "c-dgr" : (sev === "warning" ? "c-wrn" : (sev === "ok" ? "c-ok" : "c-info"));
    return '<div class="notice"><span class="chip ' + tone + '">' + commissionEsc(row.code || sev) + '</span> ' + commissionEsc(row.message || "") + '</div>';
  }).join("") + (detect.reason ? '<p class="muted" style="margin-top:8px">' + commissionEsc(detect.reason) + '</p>' : "");

  details.textContent = JSON.stringify(data, null, 2);
}

async function loadRecognitionCommissioning(forceList) {
  const select = document.getElementById("commission-camera");
  const error = document.getElementById("commission-error");
  if (!select) return;
  if (error) error.textContent = "";
  try {
    if (forceList || !cameraRowsCache.length) cameraRowsCache = await api("/cameras");
    const previous = select.value;
    select.innerHTML = cameraRowsCache.map(function (camera) {
      return '<option value="' + camera.id + '">' + commissionEsc(camera.name) + ' · ' + commissionEsc(camera.side || camera.lane_direction || "") + '</option>';
    }).join("");
    if (previous && Array.from(select.options).some(function (o) { return o.value === previous; })) select.value = previous;
    if (!select.value && select.options.length) select.value = select.options[0].value;
    if (!select.value) {
      document.getElementById("commission-summary").textContent = "No camera is configured.";
      document.getElementById("commission-evidence").innerHTML = "";
      document.getElementById("commission-recommendations").innerHTML = "";
      document.getElementById("commission-details").textContent = "";
      return;
    }
    renderCommissioning(await api("/cameras/" + select.value + "/commissioning/recognition"));
  } catch (err) {
    if (error) error.textContent = err.message;
  }
}

async function runRecognitionCommissioningRead() {
  const select = document.getElementById("commission-camera");
  const error = document.getElementById("commission-error");
  if (!select || !select.value) return;
  if (error) error.textContent = "";
  try {
    const result = await api("/cameras/" + select.value + "/commissioning/recognition/read", {
      method: "POST",
      body: "{}",
      timeoutMs: 20000,
    });
    const best = result.best || {};
    const text = best.plate || best.plate_normalized || "";
    const pct = confidencePercent(best.confidence);
    toast(
      text ? ("Software read: " + text + " (" + (pct == null ? "—" : pct) + "%)") : ("Software read completed: " + (result.detail || "no plate")),
      text ? "info" : "warn"
    );
    await loadRecognitionCommissioning(false);
  } catch (err) {
    if (error) error.textContent = err.message;
  }
}

async function loadHardware() {
  const el = document.getElementById("hvx-info");
  try { el.textContent = JSON.stringify(await api("/hardware/hvx/info"), null, 2); }
  catch (err) { el.textContent = err.message; }
  await loadRecognitionCommissioning(true);
}
document.getElementById("check-hvx").addEventListener("click", loadHardware);
document.getElementById("check-alpr").addEventListener("click", async () => {
  const el = document.getElementById("hvx-info");
  try { el.textContent = JSON.stringify(await api("/alpr/status"), null, 2); }
  catch (err) { el.textContent = err.message; }
});
document.getElementById("check-media").addEventListener("click", async () => {
  const el = document.getElementById("hvx-info");
  try { el.textContent = JSON.stringify(await api("/media/gateway"), null, 2); }
  catch (err) { el.textContent = err.message; }
});
document.getElementById("check-decode").addEventListener("click", async () => {
  const el = document.getElementById("hvx-info");
  try { el.textContent = JSON.stringify(await api("/hardware/decode"), null, 2); }
  catch (err) { el.textContent = err.message; }
});
document.getElementById("commission-camera").addEventListener("change", function () { loadRecognitionCommissioning(false); });
document.getElementById("commission-refresh").addEventListener("click", function () { loadRecognitionCommissioning(true); });
document.getElementById("commission-read").addEventListener("click", runRecognitionCommissioningRead);

document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    stopLive();
    stopHealth();
  }
});
