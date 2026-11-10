function localDateTimeValue(date) {
  const p = (n) => String(n).padStart(2, "0");
  try {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: state.siteTimezone || "UTC", year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", hour12: false,
    }).formatToParts(date).reduce((out, part) => { out[part.type] = part.value; return out; }, {});
    return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
  } catch (_) {
    return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}T${p(date.getHours())}:${p(date.getMinutes())}`;
  }
}

function fillTariffForm(editor) {
  if (!editor) return;
  const form = document.getElementById("tariff-form");
  Object.entries(editor).forEach(([key, value]) => {
    if (form.elements[key]) form.elements[key].value = value ?? "";
  });
}

async function loadFees() {
  const error = document.getElementById("fee-error");
  error.textContent = "";
  const entry = document.getElementById("fee-entry");
  const exit = document.getElementById("fee-exit");
  if (!entry.value || !exit.value) {
    const now = new Date();
    const earlier = new Date(now.getTime() - 2 * 60 * 60 * 1000);
    if (!entry.value) entry.value = localDateTimeValue(earlier);
    if (!exit.value) exit.value = localDateTimeValue(now);
  }
  try {
    const site = await api("/settings/site");
    state.siteTimezone = site.timezone || "UTC";
    const tariff = await api("/fees/tariff");
    fillTariffForm(tariff.editor);
    document.getElementById("fee-result").textContent = `${tariff.name} · ${tariff.currency}. Site time: ${state.siteTimezone}. Day rate ${tariff.editor.day_block_fee} per ${tariff.editor.day_block_minutes} min.`;
  } catch (err) {
    error.textContent = err.message;
  }
}
document.getElementById("refresh-tariff").addEventListener("click", loadFees);
document.getElementById("save-tariff").addEventListener("click", async () => {
  const error = document.getElementById("fee-error");
  error.textContent = "";
  const form = document.getElementById("tariff-form");
  const payload = {};
  [...form.elements].forEach((el) => {
    if (!el.name) return;
    payload[el.name] = el.type === "number" ? Number(el.value) : el.value;
  });
  try {
    const saved = await api("/fees/tariff", { method: "PATCH", body: JSON.stringify(payload) });
    fillTariffForm(saved.editor);
    document.getElementById("fee-result").textContent = "Tariff saved.";
  } catch (err) {
    error.textContent = err.message;
  }
});
document.getElementById("quote-fee").addEventListener("click", async () => {
  const error = document.getElementById("fee-error");
  error.textContent = "";
  try {
    const data = await api("/fees/quote", { method: "POST", body: JSON.stringify({
      entry_time: document.getElementById("fee-entry").value.trim(),
      exit_time: document.getElementById("fee-exit").value.trim(),
      car_type: "Car1",
    }) });
    const minutes = Math.round(Number(data.duration_seconds || 0) / 60);
    document.getElementById("fee-result").textContent = `${data.currency || ""} ${Number(data.due || 0).toLocaleString()} for ${minutes} min.`;
  } catch (err) {
    error.textContent = err.message;
  }
});

function reportQuery() {
  const start = document.getElementById("report-start").value;
  const end = document.getElementById("report-end").value;
  const bits = [];
  if (start) bits.push(`start=${encodeURIComponent(start)}`);
  if (end) bits.push(`end=${encodeURIComponent(end)}`);
  return bits.length ? `?${bits.join("&")}` : "";
}

async function loadReports() {
  const error = document.getElementById("report-error");
  const start = document.getElementById("report-start");
  const end = document.getElementById("report-end");
  if (start && !start.value) {
    const today = new Date();
    const p = (n) => String(n).padStart(2, "0");
    const stamp = `${today.getFullYear()}-${p(today.getMonth() + 1)}-${p(today.getDate())}`;
    start.value = stamp;
    end.value = stamp;
  }
  try {
    const status = await api("/backup");
    document.getElementById("backup-status").textContent = `${status.offline_message} ${status.cloud_message}`;
    document.getElementById("backup-days").value = status.reminder_days;
    document.getElementById("backup-url").value = status.cloud_url || "";
    document.getElementById("backup-hours").value = status.cloud_interval_hours;
    document.getElementById("backup-enabled").value = status.cloud_enabled ? "true" : "false";
  } catch (err) {
    if (error) error.textContent = err.message;
  }
}

let lastReportPack = null;

function reportText(value) {
  return String(value ?? "").replace(/[&<>]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[ch]));
}

function reportSheetHtml(sheet) {
  if (!sheet) return "<p>That report is not in this pack.</p>";
  const sections = (sheet.sections || []).map((section) => `
    <h3 style="margin:14px 0 6px">${reportText(section.title)}</h3>
    <table><tbody>${(section.rows || []).map((row) => `<tr><th>${reportText(row.label)}</th><td>${reportText(row.value)}</td></tr>`).join("")}</tbody></table>
  `).join("");
  const columns = sheet.columns || [];
  if (!columns.length) return `<h2>${reportText(sheet.title)}</h2>${sections}`;
  const head = columns.map((column) => `<th>${reportText(column.label)}</th>`).join("");
  const body = (sheet.rows || []).map((row) =>
    `<tr>${columns.map((column) => `<td>${reportText(row[column.key])}</td>`).join("")}</tr>`
  ).join("") || `<tr><td colspan="${columns.length}">Nothing in this period.</td></tr>`;
  return `<h2>${reportText(sheet.title)}</h2>${sections}<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function openReportPrint(html, title) {
  const printer = window.open("", "smartpark-report", "width=800,height=900");
  if (!printer) return;
  printer.document.write(`<!DOCTYPE html><html><head><title>${title}</title><style>body{font:14px/1.4 system-ui,sans-serif;padding:24px}table{border-collapse:collapse;width:100%;margin-bottom:18px}td,th{border-bottom:1px solid #ddd;text-align:left;padding:6px}h2{margin-top:28px}</style></head><body><h1>${title}</h1>${html}</body></html>`);
  printer.document.close();
  printer.focus();
  setTimeout(() => printer.print(), 300);
}

document.getElementById("run-report").addEventListener("click", async () => {
  const error = document.getElementById("report-error");
  error.textContent = "";
  try {
    lastReportPack = await api(`/reports/summary${reportQuery()}`);
    const kind = document.getElementById("report-kind").value;
    const sheet = (lastReportPack.reports || []).find((item) => item.id === kind) || (lastReportPack.reports || [])[0];
    document.getElementById("report-body").innerHTML = reportSheetHtml(sheet);
  } catch (err) {
    error.textContent = err.message;
  }
});
document.getElementById("print-report").addEventListener("click", () => {
  openReportPrint(document.getElementById("report-body").innerHTML, "Zirp report");
});
document.getElementById("print-all-reports").addEventListener("click", () => {
  const sheets = (lastReportPack && lastReportPack.reports) || [];
  if (!sheets.length) {
    document.getElementById("report-error").textContent = "Show a report first, then print all.";
    return;
  }
  openReportPrint(sheets.map(reportSheetHtml).join(""), "Zirp audit pack");
});
document.getElementById("download-report").addEventListener("click", async () => {
  const kind = document.getElementById("report-kind").value || "payments";
  const q = reportQuery();
  const joiner = q ? "&" : "?";
  const res = await fetch(`/reports/export.csv${q}${joiner}kind=${encodeURIComponent(kind)}`, { headers: state.token ? { Authorization: `Bearer ${state.token}` } : {} });
  if (!res.ok) { document.getElementById("report-error").textContent = "Could not download that report."; return; }
  const blob = await res.blob();
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `smartpark-${kind}.csv`;
  link.click();
});
document.getElementById("backup-save").addEventListener("click", async () => {
  const error = document.getElementById("report-error");
  error.textContent = "";
  const payload = {
    reminder_days: Number(document.getElementById("backup-days").value),
    cloud_url: document.getElementById("backup-url").value.trim(),
    cloud_interval_hours: Number(document.getElementById("backup-hours").value),
    cloud_enabled: document.getElementById("backup-enabled").value === "true",
  };
  const token = document.getElementById("backup-token").value;
  if (token) payload.cloud_token = token;
  try {
    const status = await api("/backup", { method: "PATCH", body: JSON.stringify(payload) });
    document.getElementById("backup-status").textContent = `${status.offline_message} ${status.cloud_message}`;
    document.getElementById("backup-token").value = "";
  } catch (err) {
    error.textContent = err.message;
  }
});
document.getElementById("backup-download").addEventListener("click", async () => {
  const error = document.getElementById("report-error");
  error.textContent = "";
  try {
    const res = await fetch("/backup/download", { headers: state.token ? { Authorization: `Bearer ${state.token}` } : {} });
    if (!res.ok) throw new Error("Could not download the backup.");
    const blob = await res.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "smartpark-backup.sql";
    link.click();
    await loadReports();
    refreshBackupBanner();
  } catch (err) {
    error.textContent = err.message;
  }
});
document.getElementById("backup-cloud").addEventListener("click", async () => {
  const error = document.getElementById("report-error");
  error.textContent = "";
  try {
    const status = await api("/backup/cloud", { method: "POST", body: "{}" });
    document.getElementById("backup-status").textContent = status.cloud_message || "Cloud backup finished.";
  } catch (err) {
    error.textContent = err.message;
  }
});
document.getElementById("backup-snooze").addEventListener("click", async () => {
  await api("/backup/snooze", { method: "POST", body: "{}" });
  await loadReports();
  refreshBackupBanner();
});
