from __future__ import annotations

import json
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parents[2]
EVENTS_DIR = REPO_DIR / "docs" / "data" / "events"
PLACES_PATH = EVENTS_DIR / "places.json"
LOCATIONS_PATH = EVENTS_DIR / "locations.json"


def _load_json(path: Path) -> object:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _read_locations() -> dict[str, dict[str, float]]:
    payload = _load_json(LOCATIONS_PATH)
    if not isinstance(payload, dict):
        return {}
    out: dict[str, dict[str, float]] = {}
    for key, value in payload.items():
        if not isinstance(value, dict):
            continue
        try:
            lat = float(value.get("lat"))
            lng = float(value.get("lng"))
        except (TypeError, ValueError):
            continue
        out[str(key)] = {"lat": lat, "lng": lng}
    return out


def _read_places_locations() -> dict[str, dict[str, float]]:
    payload = _load_json(PLACES_PATH)
    if not isinstance(payload, dict):
        return {}
    out: dict[str, dict[str, float]] = {}
    for place_name, place in payload.items():
        if not isinstance(place, dict):
            continue
        name = str(place.get("name") or place_name).strip()
        if not name:
            continue
        try:
            lat = float(place.get("lat"))
            lng = float(place.get("lng"))
        except (TypeError, ValueError):
            continue
        out[name] = {"lat": lat, "lng": lng}
    return out


def sync_events_data_to_docs() -> None:
    EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    merged = _read_locations()
    for name, coords in _read_places_locations().items():
        merged[name] = coords
    LOCATIONS_PATH.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
