from __future__ import annotations

import shutil
import sys
from pathlib import Path

from one_piece_missing import (
    run_all,
    run_big_bang,
    run_knightly,
    run_marvellous,
    run_tanuki,
)


RUNNERS = {
    "all": run_all,
    "bigbang": run_big_bang,
    "bigbangshop": run_big_bang,
    "knightly": run_knightly,
    "knightlygaming": run_knightly,
    "marvellous": run_marvellous,
    "marvelloushobbies": run_marvellous,
    "tanuki": run_tanuki,
    "tanukitrader": run_tanuki,
}


REPO_DIR = Path(__file__).resolve().parents[2]
DATA_ONE_PIECE_DIR = REPO_DIR / "data" / "one_piece"
DOCS_ONE_PIECE_DIR = REPO_DIR / "docs" / "data" / "one_piece"


def sync_one_piece_to_docs() -> None:
    if not DATA_ONE_PIECE_DIR.exists():
        return
    DOCS_ONE_PIECE_DIR.mkdir(parents=True, exist_ok=True)
    for source in DATA_ONE_PIECE_DIR.glob("*"):
        if source.is_file():
            shutil.copy2(source, DOCS_ONE_PIECE_DIR / source.name)
    print(f"Synced One Piece data to dashboard: {DOCS_ONE_PIECE_DIR}")


def main() -> int:
    store = sys.argv[1].lower().replace("-", "").replace("_", "") if len(sys.argv) > 1 else "all"
    runner = RUNNERS.get(store)
    if runner is None:
        choices = "all, bigbang, knightly, marvellous, tanuki"
        print(f"Unknown store {sys.argv[1]!r}. Use one of: {choices}", file=sys.stderr)
        return 2

    runner()
    sync_one_piece_to_docs()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
