function openGateDialog(gate) {
  const form = document.getElementById("gate-form");
  form.reset();
  document.getElementById("gate-dialog-error").textContent = "";
  document.getElementById("gate-dialog-title").textContent = gate ? "Edit Gate" : "Add Gate";
  if (gate) {
    form.elements.id.value = gate.id;
    form.elements.name.value = gate.name;
    form.elements.mode.value = gate.mode;
    form.elements.enabled.value = String(gate.enabled);
  } else {
    form.elements.id.value = "";
    form.elements.mode.value = "COMMISSIONING";
    form.elements.enabled.value = "true";
  }
  document.getElementById("gate-dialog").showModal();
}

async function loadGates() {
  const error = document.getElementById("gate-error");
  error.textContent = "";
  try {
    const rows = await api("/gates");
    const body = document.getElementById("gate-rows");
    body.innerHTML = "";
    rows.forEach((g) => {
      const tr = document.createElement("tr");
      const cams = g.cameras || [];
      const summary = cams.map((row) =>
        `${row.side || row.lane_direction}: cam ${row.ip_address} / ctrl ${row.controller_ip || "—"} / disp ${row.display_ip || "—"}`
      ).join("; ") || "—";
      tr.innerHTML = `<td>${g.id}</td><td>${g.name}</td><td>${g.mode}</td><td>${g.enabled ? "Yes" : "No"}</td><td>${g.physical_control_verified ? "Yes" : "No"}</td><td>${summary}</td><td class="row-actions"></td>`;
      const actions = tr.querySelector(".row-actions");
      const sides = [];
      const seen = new Set();
      cams.forEach((row) => {
        const side = (row.lane_direction || row.side || "").toUpperCase();
        if ((side === "ENTRY" || side === "EXIT") && !seen.has(side)) {
          seen.add(side);
          sides.push(side);
        }
      });
      tr.dataset.gateId = String(g.id);
      tr.dataset.sides = sides.join(",");
      if (String(selectedGateId) === String(g.id)) tr.classList.add("selected");
      tr.addEventListener("click", (ev) => {
        if (ev.target.closest("button")) return;
        selectedGateId = g.id;
        selectedGateSide = null;
        loadGates();
      });
      sides.forEach((side) => {
        const btn = document.createElement("button");
        btn.className = "secondary";
        setActionCaption(btn, side === "ENTRY" ? "Open entry" : "Open exit");
        btn.addEventListener("click", () => {
          selectedGateId = g.id;
          selectedGateSide = side;
          updateGateShortcutHint();
          commandGateBarrier(g.id, side, "open");
        });
        actions.appendChild(btn);
        const closeBtn = document.createElement("button");
        closeBtn.className = "secondary";
        setActionCaption(closeBtn, side === "ENTRY" ? "Close entry" : "Close exit");
        closeBtn.addEventListener("click", () => {
          selectedGateId = g.id;
          selectedGateSide = side;
          updateGateShortcutHint();
          commandGateBarrier(g.id, side, "close");
        });
        actions.appendChild(closeBtn);
      });
      if (can("gates.manage")) {
        const edit = document.createElement("button");
        edit.className = "secondary";
        edit.dataset.role = "edit";
        setActionCaption(edit, "Edit", "Ctrl+E");
        edit.addEventListener("click", () => openGateDialog(g));
        const del = document.createElement("button");
        del.className = "danger";
        del.dataset.role = "delete";
        setActionCaption(del, "Delete", "Del");
        del.addEventListener("click", async () => {
          if (!confirm(`Delete gate ${g.name}? Linked cameras will be unassigned.`)) return;
          try { await api(`/gates/${g.id}`, { method: "DELETE" }); loadGates(); }
          catch (err) { error.textContent = err.message; }
        });
        actions.append(edit, del);
      }
      body.appendChild(tr);
    });
    updateGateShortcutHint();
  } catch (err) {
    error.textContent = err.message;
  }
}
document.getElementById("refresh-gates").addEventListener("click", loadGates);
document.getElementById("led-text").addEventListener("click", async () => {
  const error = document.getElementById("gate-error");
  error.textContent = "";
  try {
    const rows = await api("/gates");
    const gate = rows[0];
    const cams = (gate && gate.cameras) || [];
    if (!cams.length) { error.textContent = "Select a lane with cameras first."; return; }
    const text = prompt("LED message", "WELCOME");
    if (!text) return;
    alert(JSON.stringify(await api(`/cameras/${cams[0].id}/led`, { method: "POST", body: JSON.stringify({ text }) })));
  } catch (err) {
    error.textContent = err.message;
  }
});
document.getElementById("add-gate").addEventListener("click", () => openGateDialog(null));
document.getElementById("gate-cancel").addEventListener("click", () => document.getElementById("gate-dialog").close());
document.getElementById("gate-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const error = document.getElementById("gate-dialog-error");
  const payload = {
    name: form.elements.name.value.trim(),
    mode: form.elements.mode.value,
    enabled: form.elements.enabled.value === "true",
  };
  try {
    if (form.elements.id.value) await api(`/gates/${form.elements.id.value}`, { method: "PATCH", body: JSON.stringify(payload) });
    else await api("/gates", { method: "POST", body: JSON.stringify(payload) });
    document.getElementById("gate-dialog").close();
    loadGates();
  } catch (err) {
    error.textContent = err.message;
  }
});

async function loadRoleOptions(selected) {
  if (!state.roles.length && can("users.view")) state.roles = await api("/roles");
  const box = document.getElementById("user-roles");
  box.innerHTML = state.roles.map((role) => {
    const checked = (selected || []).includes(role.name) ? "checked" : "";
    return `<label><input type="checkbox" name="roles" value="${role.name}" ${checked}> ${role.name}</label>`;
  }).join("");
}

async function openUserDialog(user) {
  const form = document.getElementById("user-form");
  form.reset();
  document.getElementById("user-dialog-error").textContent = "";
  document.getElementById("user-dialog-title").textContent = user ? "Edit User" : "Add User";
  form.elements.username.readOnly = Boolean(user);
  form.elements.password.required = !user;
  form.elements.password.placeholder = user ? "Leave blank to keep current password" : "At least 10 characters";
  await loadRoleOptions(user ? user.roles : ["Operator"]);
  if (user) {
    form.elements.id.value = user.id;
    form.elements.username.value = user.username;
    form.elements.full_name.value = user.full_name || "";
    form.elements.status.value = user.status;
  } else {
    form.elements.id.value = "";
    form.elements.status.value = "ACTIVE";
  }
  document.getElementById("user-dialog").showModal();
}

async function loadUsers() {
  const error = document.getElementById("user-error");
  error.textContent = "";
  try {
    const rows = await api("/users");
    const body = document.getElementById("user-rows");
    body.innerHTML = "";
    rows.forEach((u) => {
      const tr = document.createElement("tr");
      tr.dataset.userId = String(u.id);
      if (String(selectedUserId) === String(u.id)) tr.classList.add("selected");
      tr.innerHTML = `<td>${u.id}</td><td>${u.username}</td><td>${u.full_name || "—"}</td><td>${u.status}</td><td>${u.roles.join(", ")}</td><td class="row-actions"></td>`;
      tr.addEventListener("click", (ev) => {
        if (ev.target.closest("button")) return;
        selectedUserId = u.id;
        loadUsers();
      });
      const actions = tr.querySelector(".row-actions");
      if (can("users.manage")) {
        const edit = document.createElement("button");
        edit.className = "secondary";
        edit.dataset.role = "edit";
        setActionCaption(edit, "Edit", "Ctrl+E");
        edit.addEventListener("click", () => openUserDialog(u));
        const del = document.createElement("button");
        del.className = "danger";
        del.dataset.role = "delete";
        setActionCaption(del, "Delete", "Del");
        del.addEventListener("click", async () => {
          if (!confirm(`Delete user ${u.username}?`)) return;
          try { await api(`/users/${u.id}`, { method: "DELETE" }); loadUsers(); }
          catch (err) { error.textContent = err.message; }
        });
        actions.append(edit, del);
      }
      body.appendChild(tr);
    });
  } catch (err) {
    error.textContent = err.message;
  }
}
document.getElementById("refresh-users").addEventListener("click", loadUsers);
document.getElementById("add-user").addEventListener("click", () => openUserDialog(null));
document.getElementById("user-cancel").addEventListener("click", () => document.getElementById("user-dialog").close());
document.getElementById("user-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const error = document.getElementById("user-dialog-error");
  const roles = [...form.querySelectorAll("input[name=roles]:checked")].map((el) => el.value);
  const payload = {
    full_name: form.elements.full_name.value.trim(),
    status: form.elements.status.value,
    roles,
  };
  if (form.elements.password.value) payload.password = form.elements.password.value;
  try {
    if (form.elements.id.value) {
      await api(`/users/${form.elements.id.value}`, { method: "PATCH", body: JSON.stringify(payload) });
    } else {
      await api("/users", { method: "POST", body: JSON.stringify({
        username: form.elements.username.value.trim(),
        password: form.elements.password.value,
        ...payload,
      }) });
    }
    document.getElementById("user-dialog").close();
    loadUsers();
  } catch (err) {
    error.textContent = err.message;
  }
});
