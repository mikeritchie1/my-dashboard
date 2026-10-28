# Cloudflare State Sync Setup

## Public view and owner login

Logged-out visitors see Cape Town weather, Events and Specials, and Release Radar.
Weather days continue to filter the map. The four owner toolbar buttons and other
modules appear after clicking **Login** and entering the owner password. The login
button is hidden while logged in. Login lasts for up to 12 hours in the current browser
tab; refreshing keeps the session, while closing the tab ends it.

This is a visibility switch, not private hosting. Published files and the existing
state API remain public, as requested. The password is checked on the server;
it is never included in the page, JavaScript, or tracked configuration.

Create a random password in ignored `secrets.env` (preserves an existing password):

```powershell
python services/setup_dashboard_login.py
```

Look for `DASHBOARD_PASSWORD` in that local file. The normal local server uses it
without additional startup commands; restart an already running server after the
login code is installed. To configure the same password online and deploy the Worker:

```powershell
python services/setup_dashboard_login.py --deploy
```

This requires Wrangler/Cloudflare login. It uploads only `DASHBOARD_PASSWORD`, never
your SMTP or other secrets. Alternatively set `DASHBOARD_PASSWORD` as a secret on
the Cloudflare Worker and deploy its code. After changing the password, deploy
again to update the online password; existing sessions become invalid.

Public visits do not load or save owner dashboard preferences, goals, or private
module content. Owner login restores the usual layout and state sync. Personal
calendar annotations on the weather cards are shown only in the owner view.

This enables your static dashboard to save/load UI state (theme, module order, open panels, One Piece tab/current chapter) across devices.

## 1. What this does

- `docs/app.js` reads/writes state to a Cloudflare Worker endpoint.
- Worker stores the JSON in Cloudflare KV (`DASH_STATE` binding).
- Dashboard still uses localStorage as fallback when API is not set/reachable.

## 2. Create the Worker + KV (Cloudflare website + CLI)

1. In Cloudflare dashboard, create a KV namespace (for example `my-dashboard-state`).
2. Copy both namespace IDs:
- Production Namespace ID
- Preview Namespace ID
3. In this repo, open [wrangler.toml](/c:/Users/mjrit/OneDrive/Desktop/my-dashboard/cloudflare-state-worker/wrangler.toml) and replace:
- `REPLACE_WITH_KV_NAMESPACE_ID`
- `REPLACE_WITH_KV_PREVIEW_NAMESPACE_ID`

## 3. Deploy the Worker

Run:

```powershell
cd cloudflare-state-worker
npx wrangler deploy
```

After deploy, copy the Worker URL (for example `https://my-dashboard-state.<your-subdomain>.workers.dev`).

## 4. Point the dashboard to your Worker

Open [index.html](/c:/Users/mjrit/OneDrive/Desktop/my-dashboard/docs/index.html) and update:

```html
<script>
  window.DASHBOARD_STATE_API = "https://YOUR-WORKER.workers.dev/state";
</script>
```

Use your real Worker URL with `/state` at the end.

## 5. Publish your static site

Deploy your `docs/` folder as usual (GitHub Pages/Cloudflare Pages/etc.).

## 6. Verify it works

1. Open dashboard on device A.
2. Change theme, reorder modules, set a current One Piece chapter.
3. Open dashboard on device B (or private window).
4. Confirm the same state appears.

If state does not sync, check browser devtools network for `GET/POST /state` calls and Worker logs in Cloudflare.
