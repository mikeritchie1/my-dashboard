"""Durable summary window shared by every interval workflow and the preview."""
from datetime import datetime, timezone
import json

from services.common.scrape_metadata import load_json
from services.one_piece.notify_new_cards import send_email


def load_summary(path):
    return load_json(path) or {"window_started_at": datetime.now(timezone.utc).isoformat(), "sources": {}}


def save_summary(path, summary):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def collect(summary, config, before, after):
    entry = summary["sources"].setdefault(f"{config.module}/{config.source}", {
        "label": config.label, "runs": 0, "item_count": 0,
        "added": {}, "removed": {}, "updated": {},
    })
    entry["runs"] += 1
    entry["item_count"] = len(after)
    for kind, keys, rows in (
        ("added", after.keys() - before.keys(), after),
        ("removed", before.keys() - after.keys(), before),
        ("updated", {key for key in after.keys() & before.keys() if after[key] != before[key]}, after),
    ):
        for key in keys:
            row = rows[key]
            entry[kind][key] = str(row.get("title") or row.get("name") or row.get("card_number") or row.get("url") or key)


def summary_body(summary):
    lines = [f"Dashboard scrape summary since {summary['window_started_at']}", ""]
    for entry in summary["sources"].values():
        lines.append(f"{entry['label']}: {entry['runs']} runs; {entry['item_count']} items at latest scrape")
        for kind in ("added", "removed", "updated"):
            lines.append(f"{kind.capitalize()}: {len(entry[kind])}")
            lines.extend(f"- {title}" for title in entry[kind].values())
        lines.append("")
    return "\n".join(lines)


def send_if_due(path, summary, controls, interval, *, clear_after_send=True):
    if controls.get("_controls_unavailable") or controls.get("email_enabled", True) is False:
        return False
    if controls.get("summary_interval", "daily") != interval or not summary["sources"]:
        return False
    # Do not clear the window unless SMTP confirms delivery.
    send_email(f"Dashboard scrape summary ({interval})", summary_body(summary))
    if not clear_after_send:
        return True
    now = datetime.now(timezone.utc).isoformat()
    save_summary(path, {"window_started_at": now, "last_sent_at": now, "sources": {}})
    return True
