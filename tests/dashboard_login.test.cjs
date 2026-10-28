const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

(async () => {
  const worker = (await import("../cloudflare-state-worker/src/index.js")).default;
  const env = { DASHBOARD_PASSWORD: "test-password", DASH_STATE: { get: async () => '{"existing":true}' } };
  const call = (route, options = {}) => worker.fetch(new Request(`https://dashboard.example${route}`, options), env);
  let response = await call("/auth/session");
  assert.equal(response.status, 401);
  response = await call("/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password: "wrong" }) });
  assert.equal(response.status, 401);
  response = await call("/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password: "test-password" }) });
  assert.equal(response.status, 200);
  const { token } = await response.json();
  response = await call("/auth/session", { headers: { Authorization: `Bearer ${token}` } });
  assert.equal((await response.json()).authenticated, true);
  response = await call("/auth/session", { headers: { Authorization: `Bearer ${token}tampered` } });
  assert.equal(response.status, 401);
  response = await call("/state");
  assert.deepEqual(await response.json(), { existing: true }, "Existing state access remains compatible");
  response = await call("/auth/login", { method: "OPTIONS" });
  assert.match(response.headers.get("Access-Control-Allow-Headers"), /Authorization/);

  const source = fs.readFileSync(path.join(__dirname, "../docs/app.js"), "utf8");
  const start = source.indexOf("async function bootstrapDashboard()");
  const end = source.indexOf("\nvoid bootstrapDashboard();", start);
  const boot = source.slice(start, end);
  const calls = [];
  const context = { window: { dashboardAccess: { ready: Promise.resolve(false), isOwner: () => false } } };
  const functions = [...boot.matchAll(/\b((?:load|set|sync|render|setup|start|seed)\w+)\(/g)].map(match => match[1]);
  for (const name of functions) context[name] = () => { calls.push(name); };
  vm.createContext(context);
  vm.runInContext(boot, context);
  await context.bootstrapDashboard();
  assert.ok(calls.includes("loadWeather"));
  assert.ok(calls.includes("loadSpecials"));
  assert.ok(calls.includes("loadReleases"));
  assert.ok(calls.includes("loadQuicketEvents"));
  assert.ok(!calls.includes("loadRemoteDashboardState"), "Guest visits do not read or overwrite owner state");
  assert.ok(!calls.includes("loadWatchlist"));
  assert.ok(!calls.includes("loadOnePieceCards"));
  assert.ok(!calls.includes("setupDashboardSectionEditor"));
  context.window.dashboardAccess.isOwner = () => true;
  context.state = {};
  context.localStorage = { getItem: () => "0" };
  context.DAILY_GOALS_TS_KEY = "daily-goals-ts";
  context.dailyGoalsTodayKey = () => "2026-10-28";
  calls.length = 0;
  await context.bootstrapDashboard();
  assert.ok(calls.includes("loadRemoteDashboardState"));
  assert.ok(calls.includes("loadWatchlist"));
  assert.ok(calls.includes("loadOnePieceCards"));
  assert.ok(calls.includes("setupDashboardSectionEditor"));

  const accessSource = fs.readFileSync(path.join(__dirname, "../docs/access.js"), "utf8");
  async function loginBrowser(saved, responses) {
    const nodes = new Map();
    for (const id of ["owner-login-toggle", "owner-login-dialog", "owner-login-form", "owner-password", "owner-login-error", "owner-login-submit", "owner-login-cancel"]) {
      nodes.set(`#${id}`, { listeners: {}, value: "", addEventListener(name, handler) { this.listeners[name] = handler; }, showModal() {}, close() {}, focus() {} });
    }
    const storage = new Map(saved ? [["my-dashboard:owner-session:v1", saved]] : []);
    const requests = [];
    let reloads = 0;
    const browser = {
      URL, window: {}, location: { hostname: "localhost", href: "http://localhost:8081/docs/", reload: () => { reloads++; } },
      document: { documentElement: { dataset: { owner: "false" } }, querySelector: id => nodes.get(id) },
      sessionStorage: { getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) },
      fetch: async (url, options) => { requests.push({ url, options }); return responses.shift(); },
    };
    vm.createContext(browser);
    vm.runInContext(accessSource, browser);
    await browser.window.dashboardAccess.ready;
    return { browser, nodes, storage, requests, reloads: () => reloads };
  }
  const publicBrowser = await loginBrowser("fake-session", [{ ok: false, json: async () => ({ authenticated: false }) }]);
  assert.equal(publicBrowser.browser.window.dashboardAccess.isOwner(), false);
  assert.equal(publicBrowser.storage.size, 0, "A stored flag/token cannot unlock the page without server verification");
  const ownerBrowser = await loginBrowser(token, [{ ok: true, json: async () => ({ authenticated: true }) }]);
  assert.equal(ownerBrowser.browser.document.documentElement.dataset.owner, "true");
  assert.equal(ownerBrowser.nodes.get("#owner-login-toggle").textContent, "Logout");
  ownerBrowser.nodes.get("#owner-login-toggle").listeners.click();
  assert.equal(ownerBrowser.storage.size, 0);
  assert.equal(ownerBrowser.reloads(), 1);
  const freshBrowser = await loginBrowser("", [{ ok: false, json: async () => ({ error: "Incorrect password." }) }]);
  freshBrowser.nodes.get("#owner-password").value = "wrong";
  await freshBrowser.nodes.get("#owner-login-form").listeners.submit({ preventDefault() {} });
  assert.equal(freshBrowser.nodes.get("#owner-login-error").textContent, "Incorrect password.");
  assert.equal(freshBrowser.reloads(), 0);

  const html = fs.readFileSync(path.join(__dirname, "../docs/index.html"), "utf8");
  assert.match(html, /<html[^>]*data-owner="false"/);
  assert.equal((html.match(/data-public-module/g) || []).length, 2);
  for (const id of ["scrape-control-toggle", "newsletter-preview-toggle", "layout-edit-toggle", "theme-toggle"]) {
    assert.match(html, new RegExp(`<button[^>]*id="${id}"[^>]*data-owner-only`));
  }
  console.log("Dashboard login and public view checks passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
