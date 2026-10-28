"""Change emails for successful, menu-selected sources only."""
from __future__ import annotations

import json

from services.common.scrape_metadata import load_json
from services.one_piece.notify_new_cards import send_email
from services.scrape_one_piece import STORE_NAMES
from services.common.scrape_options import source_option


def rows_from_payload(payload):
    if isinstance(payload, list):
        result = []
        for row in payload:
            if isinstance(row, str):
                result.append({"title": row})
            elif isinstance(row, dict):
                if any(isinstance(row.get(key), list) for key in ("items", "entries", "videos")):
                    result.extend(rows_from_payload(row))
                else:
                    result.append(row)
        return result
    if not isinstance(payload, dict):
        return []
    for key in ("listings", "items", "new_releases", "coming_soon", "entries", "videos", "rows", "products", "events", "results"):
        if isinstance(payload.get(key), list):
            return rows_from_payload(payload[key])
    if isinstance(payload.get("groups"), list):
        return [row for group in payload["groups"] for row in rows_from_payload(group)]
    if any(key in payload for key in ("currently_watching", "backlog", "history_by_year", "series")):
        rows = []
        def visit(value):
            if isinstance(value, list):
                rows.extend(rows_from_payload(value))
            elif isinstance(value, dict):
                for nested in value.values():
                    visit(nested)
        for key in ("currently_watching", "backlog", "history_by_year", "series"):
            visit(payload.get(key))
        return rows
    return [dict(value, _key=key) for key, value in payload.items() if isinstance(value, dict)]


def read_source_rows(root, config):
    rows = {}
    for output in config.outputs:
        for row in rows_from_payload(load_json(root / output)):
            if config.module == "one-piece" and config.source in STORE_NAMES:
                if row.get("store") != STORE_NAMES[config.source]:
                    continue
            if config.module == "news":
                is_f1 = row.get("id") == "f1-snapshot-current-season"
                if config.source == "f1-snapshot" and not is_f1:
                    continue
                if config.source == "rss" and is_f1:
                    continue
            identity = next((str(row[key]) for key in ("id", "url", "link", "video_id", "card_number", "_key", "title", "name") if row.get(key)), None)
            if identity is None:
                identity = json.dumps(row, sort_keys=True)
            key = f"{output}|{identity}"
            rows[key] = {k: v for k, v in row.items() if k not in {"generated_at", "updated_at", "scraped_at", "last_scraped_at", "fetched_at"}}
    return rows


def change_sections(config, controls, interval, before, after):
    if controls.get("email_enabled", True) is False:
        return []
    if controls.get("interval_email_enabled", {}).get(interval, True) is False:
        return []
    module = controls.get("modules", {}).get(config.module, {})
    source = module.get("sources", {}).get(config.source, {})
    flags = source.get("email", module.get("email", {"added": config.module == "one-piece"}))
    changes = {
        "added": [row for key, row in after.items() if key not in before],
        "updated": [row for key, row in after.items() if key in before and row != before[key]],
        "removed": [row for key, row in before.items() if key not in after],
    }
    sections = []
    for kind, rows in changes.items():
        if not flags.get(kind, False):
            continue
        if config.module == "one-piece" and config.source in STORE_NAMES:
            limit = source_option(controls, config.module, config.source, "max_price", 100)
            try:
                ceiling = float(limit)
            except (ValueError, TypeError):
                ceiling = 100
            def below_limit(row):
                try:
                    return ceiling <= 0 or float(row.get("price", "")) < ceiling
                except (ValueError, TypeError):
                    return False
            rows = [row for row in rows if below_limit(row)]
        if rows:
            lines = [f"{config.label} — {kind}: {len(rows)}"]
            for row in rows:
                lines.append(json.dumps(row, ensure_ascii=False, sort_keys=True))
            sections.append("\n".join(lines))
    return sections


def send_sections(sections, interval):
    if sections:
        send_email(f"Dashboard scrape updates ({interval})", "\n\n".join(sections))
