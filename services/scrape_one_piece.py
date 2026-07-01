from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[1]
if str(REPO_DIR) not in sys.path:
    sys.path.append(str(REPO_DIR))

from services.common.scrape_metadata import record_scrape_outputs, run_and_record


DATA_DIR = REPO_DIR / "docs" / "data" / "one_piece"
MISSING_CARDS_FILE = DATA_DIR / "missing_cards.json"
STORE_SOURCES = ["bigbang", "collectiverse", "geekhaven", "knightly", "marvellous", "tanuki"]
STORE_NAMES = {
    "bigbang": "Big Bang Shop",
    "collectiverse": "CollectiVerse",
    "geekhaven": "GeekHaven",
    "knightly": "Knightly Gaming",
    "marvellous": "Marvellous Hobbies",
    "tanuki": "Tanuki Trader",
    "toad": "Toad Trader TCG",
}


def count_store_listings(source: str) -> int:
    store_name = STORE_NAMES.get(source, "")
    if not store_name or not MISSING_CARDS_FILE.exists():
        return 0
    try:
        payload = json.loads(MISSING_CARDS_FILE.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return 0
    listings = payload.get("listings")
    if not isinstance(listings, list):
        return 0
    return sum(1 for row in listings if isinstance(row, dict) and str(row.get("store") or "").strip() == store_name)


def run_store_scrape(source: str) -> None:
    command = [sys.executable, "services/one_piece/find_missing_cards.py", source]
    print(f"Running One Piece scrape: {' '.join(command)}", flush=True)
    start = time.perf_counter()
    try:
        subprocess.run(command, cwd=REPO_DIR, check=True)
    finally:
        duration = time.perf_counter() - start
        record_scrape_outputs(
            [MISSING_CARDS_FILE],
            module="one-piece",
            source=source,
            duration_seconds=duration,
            command=command,
            item_count=count_store_listings(source),
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run One Piece missing-card scrapes.")
    parser.add_argument("--source", choices=["all", "bigbang", "collectiverse", "geekhaven", "knightly", "marvellous", "toad", "tanuki"], default="all", help="Which store source to scrape.")
    parser.add_argument("--hard", action="store_true", help="Remove selected report outputs before scraping.")
    parser.add_argument("--limit", type=int, default=0, help="Accepted for wrapper consistency; store scraping is not item-limited.")
    parser.add_argument("--max-pages", type=int, default=0, help="Accepted for wrapper consistency; store pagination is source-defined.")
    args = parser.parse_args()

    if args.hard:
        patterns = ["*_missing_available.csv", "new_missing_cards.json"] if args.source == "all" else [f"*{args.source}*_missing_available.csv"]
        for pattern in patterns:
            for path in DATA_DIR.glob(pattern):
                print(f"Removing stale One Piece output: {path}", flush=True)
                path.unlink()

    update_command = [sys.executable, "services/one_piece/update_collection.py"]
    if args.hard:
        update_command.append("--hard")
    print(f"Updating One Piece collection: {' '.join(update_command)}", flush=True)
    run_and_record(
        update_command,
        cwd=REPO_DIR,
        outputs=[DATA_DIR / "collection.json"],
        module="one-piece",
        source="collection",
    )

    source_names = STORE_SOURCES if args.source == "all" else [args.source]
    for source in source_names:
        run_store_scrape(source)
    product_command = [sys.executable, "services/one_piece/scrape_products.py", "--pages", "1"]
    if args.hard:
        product_command.append("--hard")
    print(f"Running One Piece products scrape: {' '.join(product_command)}", flush=True)
    run_and_record(
        product_command,
        cwd=REPO_DIR,
        outputs=[DATA_DIR / "products.json"],
        module="one-piece",
        source="products",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
