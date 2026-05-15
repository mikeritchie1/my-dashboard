from __future__ import annotations

import json
from pathlib import Path

import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))
from env import get as env_get


REPO_DIR = Path(__file__).resolve().parents[1]
SECRETS_FILE = REPO_DIR / "secrets.env"
OUTPUT_PATH = REPO_DIR / "docs" / "data" / "runtime_config.json"


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


def main() -> int:
    payload = {
        "reading": {
            "drive_folder_id": setting("READING_DRIVE_FOLDER_ID"),
            "google_drive_client_id": setting("GOOGLE_DRIVE_CLIENT_ID"),
        }
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote runtime config to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
