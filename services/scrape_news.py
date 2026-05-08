from __future__ import annotations

import argparse
import shutil
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_DIR / "data" / "news"
DOCS_DIR = REPO_DIR / "docs" / "data" / "news"
NEWS_FILE = DATA_DIR / "news.json"


def sync_outputs() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    for path in DATA_DIR.glob("*.json"):
        shutil.copy2(path, DOCS_DIR / path.name)
    print(f"Synced news data to dashboard: {DOCS_DIR}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run news scrape/sync.")
    parser.add_argument("--source", choices=["all", "local-file"], default="all", help="Which news source to scrape.")
    parser.add_argument("--hard", action="store_true", help="Remove generated news output before scraping/syncing.")
    parser.add_argument("--limit", type=int, default=0, help="Accepted for wrapper consistency; current news source is not item-limited.")
    parser.add_argument("--max-pages", type=int, default=0, help="Accepted for wrapper consistency; current news source is not paged.")
    args = parser.parse_args()

    if args.hard and NEWS_FILE.exists():
        print(f"Hard news requested, but current news source is the checked-in local JSON: {NEWS_FILE}", flush=True)
    sync_outputs()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
