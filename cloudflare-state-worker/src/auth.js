const encoder = new TextEncoder();
const lifetime = 90 * 24 * 60 * 60;
const attempts = new Map();

function encode(bytes) {
  return btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function decode(value) {
  return Uint8Array.from(atob(value.replace(/-/g, "+").replace(/_/g, "/")), c => c.charCodeAt(0));
}

async function signingKey(password) {
  return crypto.subtle.importKey("raw", encoder.encode(password), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
}

export async function issueSession(password) {
  const payload = encode(encoder.encode(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + lifetime, nonce: crypto.randomUUID() })));
  const signature = await crypto.subtle.sign("HMAC", await signingKey(password), encoder.encode(payload));
  return `${payload}.${encode(signature)}`;
}

export async function validSession(token, password) {
  if (!password || typeof token !== "string" || token.length > 2048) return false;
  try {
    const parts = token.split(".");
    if (parts.length !== 2) return false;
    const [payload, signature] = parts;
    if (!await crypto.subtle.verify("HMAC", await signingKey(password), decode(signature), encoder.encode(payload))) return false;
    const data = JSON.parse(new TextDecoder().decode(decode(payload)));
    const now = Date.now() / 1000;
    return typeof data.exp === "number" && data.exp > now && data.exp <= now + lifetime;
  } catch { return false; }
}

export async function authResponse(request, env, respond) {
  const path = new URL(request.url).pathname;
  if (path === "/auth/session" && request.method === "GET") {
    const token = (request.headers.get("Authorization") || "").replace(/^Bearer /, "");
    const authenticated = await validSession(token, env.DASHBOARD_PASSWORD);
    return respond(authenticated
      ? { authenticated: true, token: await issueSession(env.DASHBOARD_PASSWORD) }
      : { authenticated: false }, authenticated ? 200 : 401);
  }
  if (path !== "/auth/login" || request.method !== "POST") return respond({ error: "Not found" }, 404);
  if (!env.DASHBOARD_PASSWORD) return respond({ error: "Owner login has not been configured on the server." }, 503);
  const now = Date.now();
  for (const [key, value] of attempts) if (value.until < now) attempts.delete(key);
  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  const entry = attempts.get(ip) || { until: now + 60000, count: 0 };
  if (entry.count >= 5 || attempts.size > 5000) return respond({ error: "Too many attempts. Try again in a minute." }, 429);
  entry.count++;
  attempts.set(ip, entry);
  // Best-effort per-isolate throttling; this login only controls interface visibility.
  if (!(request.headers.get("Content-Type") || "").startsWith("application/json")) return respond({ error: "JSON required" }, 415);
  const text = await request.text();
  if (text.length > 2048) return respond({ error: "Invalid request" }, 400);
  let candidate;
  try { candidate = JSON.parse(text)?.password; } catch { return respond({ error: "Invalid JSON" }, 400); }
  if (typeof candidate !== "string" || candidate.length > 256) return respond({ error: "Incorrect password." }, 401);
  const expected = new Uint8Array(await crypto.subtle.digest("SHA-256", encoder.encode(env.DASHBOARD_PASSWORD)));
  const actual = new Uint8Array(await crypto.subtle.digest("SHA-256", encoder.encode(candidate)));
  let difference = 0;
  for (let i = 0; i < expected.length; i++) difference |= expected[i] ^ actual[i];
  if (difference) return respond({ error: "Incorrect password." }, 401);
  return respond({ token: await issueSession(env.DASHBOARD_PASSWORD) });
}
