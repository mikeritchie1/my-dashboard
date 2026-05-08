from __future__ import annotations

import shutil
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_DIR / "data" / "events"
DOCS_DIR = REPO_DIR / "docs" / "data" / "events"


def sync_events_data_to_docs() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    for path in DATA_DIR.glob("*.json"):
        shutil.copy2(path, DOCS_DIR / path.name)
    print(f"Synced event data to dashboard: {DOCS_DIR}", flush=True)
