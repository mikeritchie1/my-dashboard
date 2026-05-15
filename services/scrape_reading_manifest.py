from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from env import get as env_get


REPO_DIR = Path(__file__).resolve().parents[1]
OUTPUT_PATH = REPO_DIR / "docs" / "data" / "reading_manifest.json"
SECRETS_FILE = REPO_DIR / "secrets.env"
DRIVE_API_BASE = "https://www.googleapis.com/drive/v3/files"


def local_secret(name: str) -> str:
    if not SECRETS_FILE.exists():
        return ""
    for raw_line in SECRETS_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == name:
            return value.strip().strip('"').strip("'")
    return ""


def setting(name: str) -> str:
    return (env_get(name, "") or local_secret(name)).strip()


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "my-dashboard/reading-scraper"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def list_files(query: str, api_key: str) -> list[dict]:
    items: list[dict] = []
    page_token = ""
    while True:
        params = {
            "q": query,
            "fields": "nextPageToken,files(id,name,mimeType)",
            "orderBy": "name_natural",
            "pageSize": "1000",
            "key": api_key,
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        if page_token:
            params["pageToken"] = page_token
        url = f"{DRIVE_API_BASE}?{urllib.parse.urlencode(params)}"
        payload = fetch_json(url)
        files = payload.get("files", [])
        if isinstance(files, list):
            items.extend([row for row in files if isinstance(row, dict)])
        page_token = str(payload.get("nextPageToken", "")).strip()
        if not page_token:
            break
    return items


def first_image_in_folder(folder_id: str, api_key: str) -> str:
    query = f"'{folder_id}' in parents and trashed=false and mimeType contains 'image/'"
    images = list_files(query, api_key)
    if not images:
        return ""
    first_id = str(images[0].get("id", "")).strip()
    return image_url(first_id) if first_id else ""


def parse_folder_id(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    if "/folders/" in value:
        tail = value.split("/folders/", 1)[1]
        return tail.split("?", 1)[0].split("/", 1)[0].strip()
    if "id=" in value:
        return value.split("id=", 1)[1].split("&", 1)[0].strip()
    return value


def image_url(file_id: str) -> str:
    return f"https://drive.google.com/thumbnail?id={file_id}&sz=w2000"


def main() -> int:
    api_key = setting("GOOGLE_DRIVE_API_KEY") or setting("GOOGLE_API_KEY")
    root_folder_id = parse_folder_id(setting("READING_DRIVE_FOLDER_ID"))

    if not api_key:
        raise RuntimeError("Missing GOOGLE_DRIVE_API_KEY (or GOOGLE_API_KEY) in secrets.env/environment")
    if not root_folder_id:
        raise RuntimeError("Missing READING_DRIVE_FOLDER_ID in secrets.env/environment")

    folder_mime = "application/vnd.google-apps.folder"
    series_query = f"'{root_folder_id}' in parents and trashed=false and mimeType='{folder_mime}'"
    series_folders = list_files(series_query, api_key)

    series_payload = []
    for series in series_folders:
        series_id = str(series.get("id", "")).strip()
        series_name = str(series.get("name", "")).strip()
        if not series_id:
            continue
        series_cover_url = first_image_in_folder(series_id, api_key)

        volume_query = f"'{series_id}' in parents and trashed=false and mimeType='{folder_mime}'"
        volumes = list_files(volume_query, api_key)
        volume_payload = []
        for volume in volumes:
            volume_id = str(volume.get("id", "")).strip()
            volume_name = str(volume.get("name", "")).strip()
            if not volume_id:
                continue

            pages_query = f"'{volume_id}' in parents and trashed=false and mimeType contains 'image/'"
            pages = list_files(pages_query, api_key)
            pages_payload = []
            for page in pages:
                page_id = str(page.get("id", "")).strip()
                page_name = str(page.get("name", "")).strip()
                if not page_id:
                    continue
                pages_payload.append(
                    {
                        "id": page_id,
                        "name": page_name,
                        "image_url": image_url(page_id),
                    }
                )

            cover_image_url = pages_payload[0]["image_url"] if pages_payload else ""
            volume_payload.append(
                {
                    "id": volume_id,
                    "name": volume_name,
                    "cover_image_url": cover_image_url,
                    "pages": pages_payload,
                }
            )

        series_payload.append(
            {
                "id": series_id,
                "name": series_name,
                "cover_image_url": series_cover_url,
                "volumes": volume_payload,
            }
        )

    payload = {"series": series_payload}
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote reading manifest to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
