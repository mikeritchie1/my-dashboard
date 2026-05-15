# Google Drive Reader Setup

## 1. Prepare Drive folders

1. Create a folder in Google Drive named `My Readings`.
2. Inside it, create subfolders like `Vol 1`, `Vol 2`, etc.
3. Put page images in each volume folder (`001.jpg`, `002.jpg`, ...). Keep file names zero-padded so order is correct.

## 2. Get your My Readings folder id

Open the `My Readings` folder in browser.  
Copy the folder id from URL:

`https://drive.google.com/drive/folders/<FOLDER_ID>`

## 3. Create Google OAuth client id

1. Go to Google Cloud Console.
2. Create/select a project.
3. Enable `Google Drive API`.
4. Configure OAuth consent screen.
5. Create `OAuth client ID` for `Web application`.
6. Add authorized JavaScript origins for your dashboard:
- local dev origin (example `http://127.0.0.1:5500` or your local server origin)
- deployed dashboard origin

## 4. Add secrets (same pattern as your sheet link)

Add these to `secrets.env`:

```env
GOOGLE_DRIVE_CLIENT_ID=YOUR_CLIENT_ID.apps.googleusercontent.com
READING_DRIVE_FOLDER_ID=YOUR_MY_READINGS_FOLDER_ID
```

Then run your local update command so it generates `docs/data/runtime_config.json`:

```powershell
python run_local_dashboard_update.py youtube
```

## 5. Use the My Reading module

1. Open dashboard.
2. Click `Connect Google Drive` and approve access.
3. Select a volume and read.

The reader keeps only a small page window cached:
- previous page
- current page
- next 3 pages

Progress is synced to your Cloudflare state backend (`folder/volume/page`).
