(async function boot() {
  try {
    const setup = await fetch("/auth/setup").then((r) => r.json());
    if (setup.username) document.getElementById("username").value = setup.username;
    if (setup.password) document.getElementById("password").value = setup.password;
    else document.getElementById("password").value = "";
    if (setup.hint) document.getElementById("login-hint").textContent = setup.hint;
    if (setup.platform) {
      state.platform = setup.platform;
      state.recommendedAdapter = setup.recommended_camera_adapter || setup.platform.recommended_camera_adapter || "hvx";
      const plat = document.getElementById("login-platform");
      if (plat) {
        plat.textContent = setup.platform.hvx_host_supported
          ? `${setup.platform.os} · desktop or browser`
          : `${setup.platform.os} · browser UI (desktop/HVX host are Windows-only)`;
      }
    }
  } catch (_) {}
  if (!state.token) return;
  try {
    const me = await refreshSessionContext();
    setSignedIn({ token: state.token, ...me });
  } catch (_) {
    setSignedOut();
  }
})();
