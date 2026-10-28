/* This login controls dashboard visibility; published data remains public. */
(() => {
  const key = "my-dashboard:owner-session:v1";
  const local = ["localhost", "127.0.0.1", "[::1]"].includes(location.hostname);
  const base = local ? new URL("/api/auth/", location.href)
    : new URL("/auth/", window.DASHBOARD_STATE_API || location.href);
  let token = "";
  let owner = false;
  try { token = sessionStorage.getItem(key) || ""; } catch { /* Storage may be disabled. */ }
  const button = document.querySelector("#owner-login-toggle");
  const dialog = document.querySelector("#owner-login-dialog");
  const form = document.querySelector("#owner-login-form");
  const password = document.querySelector("#owner-password");
  const error = document.querySelector("#owner-login-error");
  const submit = document.querySelector("#owner-login-submit");

  function applyOwner(value) {
    owner = value;
    document.documentElement.dataset.owner = String(value);
    button.textContent = value ? "Logout" : "Login";
  }

  async function call(endpoint, options = {}) {
    return fetch(new URL(endpoint, base), { cache: "no-store", ...options });
  }

  const ready = (async () => {
    if (!token) return false;
    try {
      const response = await call("session", { headers: { Authorization: `Bearer ${token}` } });
      const result = await response.json();
      applyOwner(response.ok && result.authenticated === true);
    } catch { applyOwner(false); }
    if (!owner) {
      token = "";
      try { sessionStorage.removeItem(key); } catch { /* Ignore storage failures. */ }
    }
    return owner;
  })();

  button.addEventListener("click", () => {
    if (owner) {
      try { sessionStorage.removeItem(key); } catch { /* Ignore storage failures. */ }
      location.reload();
      return;
    }
    error.textContent = "";
    password.value = "";
    dialog.showModal();
    password.focus();
  });
  document.querySelector("#owner-login-cancel").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => { password.value = ""; });
  form.addEventListener("submit", async event => {
    event.preventDefault();
    submit.disabled = true;
    error.textContent = "";
    try {
      const response = await call("login", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: password.value }),
      });
      const result = await response.json().catch(() => ({ error: local
        ? "Restart the local dashboard server to enable login."
        : "The online login service is unavailable. Please try again later." }));
      if (!response.ok || !result.token) throw new Error(result.error || "Login failed.");
      token = result.token;
      try { sessionStorage.setItem(key, token); } catch {
        throw new Error("Allow session storage in this browser to log in.");
      }
      password.value = "";
      location.reload();
    } catch (failure) {
      error.textContent = failure instanceof TypeError
        ? "Cannot reach the login server. Check your connection or restart the local server."
        : failure.message || "Login failed.";
    } finally { submit.disabled = false; }
  });
  window.dashboardAccess = { ready, isOwner: () => owner };
})();
