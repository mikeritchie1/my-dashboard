from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


REPO_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_DIR / "docs" / "data"
METADATA_PATH = DATA_DIR / "scrape_metadata.json"


def load_json(path: Path) -> object:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return None


def count_items(value: object) -> int:
    if isinstance(value, list):
        return len(value)
    if not isinstance(value, dict):
        return 0

    for key in ("items", "new_releases", "coming_soon", "entries", "videos", "rows"):
        nested = value.get(key)
        if isinstance(nested, list):
            return len(nested)

    if isinstance(value.get("groups"), list):
        return sum(len(group.get("items") or []) for group in value["groups"] if isinstance(group, dict))

    total = 0
    for nested in value.values():
        if isinstance(nested, list):
            total += len(nested)
    return total or len(value)


def output_item_count(path: Path) -> int:
    payload = load_json(path)
    return count_items(payload)


def metadata_key(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_DIR).as_posix()
    except ValueError:
        return path.as_posix()


def read_metadata() -> dict:
    payload = load_json(METADATA_PATH)
    if not isinstance(payload, dict):
        return {"version": 1, "outputs": {}, "sources": {}}
    payload.setdefault("version", 1)
    payload.setdefault("outputs", {})
    payload.setdefault("sources", {})
    return payload


def write_metadata(payload: dict) -> None:
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    METADATA_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def record_scrape_outputs(
    outputs: Iterable[Path],
    *,
    module: str,
    source: str,
    duration_seconds: float,
    command: list[str],
    item_count: int | None = None,
    status: str = "ok",
    error: str = "",
) -> None:
    payload = read_metadata()
    now = datetime.now(timezone.utc).isoformat()
    output_map = payload.setdefault("outputs", {})
    source_key = f"{module}/{source}"
    source_outputs = list(outputs)
    source_item_count = item_count
    if source_item_count is None:
        source_item_count = 0
        for output in source_outputs:
            source_item_count += output_item_count(output)
    source_entry = {
        "module": module,
        "source": source,
        "last_scraped_at": now,
        "duration_seconds": round(float(duration_seconds), 3),
        "item_count": source_item_count,
        "outputs": [metadata_key(output) for output in source_outputs],
        "command": command,
        "status": status,
    }
    if error:
        source_entry["error"] = error
    payload.setdefault("sources", {})[source_key] = source_entry
    for output in source_outputs:
        output_entry = {
            "module": module,
            "source": source,
            "last_scraped_at": now,
            "duration_seconds": round(float(duration_seconds), 3),
            "item_count": output_item_count(output),
            "command": command,
            "status": status,
        }
        if error:
            output_entry["error"] = error
        output_map[metadata_key(output)] = output_entry
    payload["updated_at"] = now
    write_metadata(payload)


def run_and_record(
    command: list[str],
    *,
    cwd: Path,
    outputs: Iterable[Path],
    module: str,
    source: str,
    item_count: int | None = None,
) -> None:
    start = time.perf_counter()
    status = "ok"
    error = ""
    try:
        subprocess.run(command, cwd=cwd, check=True)
    except subprocess.CalledProcessError as exc:
        status = "error"
        error = f"Command failed with exit code {exc.returncode}"
        raise
    finally:
        duration = time.perf_counter() - start
        record_scrape_outputs(
            outputs,
            module=module,
            source=source,
            duration_seconds=duration,
            command=command,
            item_count=item_count,
            status=status,
            error=error,
        )
