from __future__ import annotations

import argparse
import json
import os
import re
import smtplib
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any


REPO_DIR = Path(__file__).resolve().parents[1]
if str(REPO_DIR) not in sys.path:
    sys.path.append(str(REPO_DIR))

from services.common.scrape_metadata import output_item_count, record_scrape_outputs

DOCS_DIR = REPO_DIR / "docs"
INDEX_FILE = DOCS_DIR / "index.html"
SCRAPE_CONTROLS_KEY = "scrape-controls"
INTERVALS = {"ten-minute", "hourly", "daily", "weekly"}


@dataclass(frozen=True)
class SourceConfig:
    module: str
    source: str
    label: str
    default_schedule: str
    command: list[str]
    outputs: list[str]


MODULE_DEFAULTS = {
    "one-piece": "hourly",
    "release-radar": "daily",
    "events": "daily",
    "news": "daily",
    "media": "daily",
    "youtube": "daily",
}

SCRIPT_OPTION_FLAGS = {
    "services/scrape_one_piece.py": {"--hard", "--limit", "--max-pages"},
    "services/scrape_release_radar.py": {"--hard", "--limit", "--max-pages"},
    "services/scrape_events.py": {"--hard", "--limit", "--max-pages", "--genre"},
    "services/scrape_news.py": {"--hard", "--limit", "--max-pages"},
    "services/scrape_media.py": {"--hard", "--limit", "--max-pages", "--type"},
    "services/scrape_youtube.py": {"--limit"},
    "services/one_piece/scrape_products.py": {"--hard"},
    "services/events/geocode_event_locations.py": {"--hard"},
}

SOURCE_CONFIGS: list[SourceConfig] = [
    SourceConfig("one-piece", "bigbang", "Big Bang", "hourly", ["services/scrape_one_piece.py", "--source", "bigbang"], ["docs/data/one_piece/missing_cards.json"]),
    SourceConfig("one-piece", "collectiverse", "Collectiverse", "hourly", ["services/scrape_one_piece.py", "--source", "collectiverse"], ["docs/data/one_piece/missing_cards.json"]),
    SourceConfig("one-piece", "geekhaven", "Geek Haven", "hourly", ["services/scrape_one_piece.py", "--source", "geekhaven"], ["docs/data/one_piece/missing_cards.json"]),
    SourceConfig("one-piece", "knightly", "Knightly Gaming", "hourly", ["services/scrape_one_piece.py", "--source", "knightly"], ["docs/data/one_piece/missing_cards.json"]),
    SourceConfig("one-piece", "marvellous", "Marvellous Gaming", "hourly", ["services/scrape_one_piece.py", "--source", "marvellous"], ["docs/data/one_piece/missing_cards.json"]),
    SourceConfig("one-piece", "tanuki", "Tanuki Games", "hourly", ["services/scrape_one_piece.py", "--source", "tanuki"], ["docs/data/one_piece/missing_cards.json"]),
    SourceConfig("one-piece", "products", "Official products", "hourly", ["services/one_piece/scrape_products.py", "--pages", "1"], ["docs/data/one_piece/products.json"]),
    SourceConfig("release-radar", "pahe", "Pahe latest movies", "daily", ["services/scrape_release_radar.py", "--source", "pahe"], ["docs/data/release_radar/pahe_latest.json"]),
    SourceConfig("release-radar", "coming-soon", "TMDB coming soon", "daily", ["services/scrape_release_radar.py", "--source", "coming-soon"], ["docs/data/release_radar/coming_soon.json"]),
    SourceConfig("release-radar", "games", "RAWG game releases", "daily", ["services/scrape_release_radar.py", "--source", "games"], ["docs/data/release_radar/game_releases.json"]),
    SourceConfig("release-radar", "imax", "V&A Waterfront IMAX", "daily", ["services/scrape_release_radar.py", "--source", "imax"], ["docs/data/release_radar/imax_waterfront.json"]),
    SourceConfig("release-radar", "galileo", "Galileo open air cinema", "daily", ["services/scrape_release_radar.py", "--source", "galileo"], ["docs/data/release_radar/galileo_movies.json"]),
    SourceConfig("release-radar", "labia", "Labia Theatre", "daily", ["services/scrape_release_radar.py", "--source", "labia"], ["docs/data/release_radar/labia_showtimes.json"]),
    SourceConfig("events", "specials", "Notion specials + places", "daily", ["services/scrape_events.py", "--source", "specials"], ["docs/data/events/specials.json", "docs/data/events/places.json"]),
    SourceConfig("events", "bandsintown", "Bandsintown concerts", "daily", ["services/scrape_events.py", "--source", "bandsintown"], ["docs/data/events/bandsintown_events.json"]),
    SourceConfig("events", "quicket", "Quicket events", "daily", ["services/scrape_events.py", "--source", "quicket"], ["docs/data/events/quicket_events.json"]),
    SourceConfig("events", "webtickets", "Webtickets events", "daily", ["services/scrape_events.py", "--source", "webtickets"], ["docs/data/events/webtickets_wc_events.json"]),
    SourceConfig("events", "google-calendar", "Google Calendar", "daily", ["services/scrape_events.py", "--source", "google-calendar"], ["docs/data/events/google_calendar_events.json"]),
    SourceConfig("events", "geocode", "Geocode locations", "daily", ["services/events/geocode_event_locations.py"], ["docs/data/events/locations.json"]),
    SourceConfig("news", "rss", "RSS and Atom feeds", "daily", ["services/scrape_news.py", "--source", "rss"], ["docs/data/news/news.json"]),
    SourceConfig("news", "local-file", "Local file merge", "daily", ["services/scrape_news.py", "--source", "local-file"], ["docs/data/news/news.json"]),
    SourceConfig("news", "f1-snapshot", "F1 snapshot", "daily", ["services/scrape_news.py", "--source", "rss"], ["docs/data/news/news.json"]),
    SourceConfig("media", "watchlist", "Notion watchlist", "daily", ["services/scrape_media.py", "--source", "watchlist"], ["docs/data/media/watchlist.json", "docs/data/media/watchlist_movie_details.json"]),
    SourceConfig("media", "games", "Notion games", "daily", ["services/scrape_media.py", "--source", "games"], ["docs/data/media/gameslist.json", "docs/data/media/games_details.json"]),
    SourceConfig("media", "reading", "Notion reading list", "daily", ["services/scrape_media.py", "--source", "reading"], ["docs/data/reading_list.json", "docs/data/media/reading_details.json"]),
    SourceConfig("media", "tmdb", "TMDB enrichment", "daily", ["services/scrape_media.py", "--source", "watchlist"], ["docs/data/media/watchlist_movie_details.json"]),
    SourceConfig("media", "rawg", "RAWG enrichment", "daily", ["services/scrape_media.py", "--source", "games"], ["docs/data/media/games_details.json"]),
    SourceConfig("youtube", "one-piece", "One Piece channels", "daily", ["services/scrape_youtube.py", "--mode", "daily"], ["docs/data/youtube/latest_uploads.json"]),
    SourceConfig("youtube", "almost-friday-tv", "Almost Friday TV", "daily", ["services/youtube/scrape_almost_friday_tv.py"], ["docs/data/youtube/almost_friday_tv.json"]),
    SourceConfig("youtube", "thats-a-bad-idea", "That's A Bad Idea", "daily", ["services/youtube/scrape_thats_a_bad_idea.py"], ["docs/data/youtube/thats_a_bad_idea.json"]),
    SourceConfig("youtube", "gameranx-tv", "gameranx", "daily", ["services/youtube/scrape_gameranx_tv.py"], ["docs/data/youtube/gameranx_tv.json"]),
]


def state_api_base() -> str:
    value = os.environ.get("DASHBOARD_STATE_API", "").strip()
    if value:
        return value
    if not INDEX_FILE.exists():
        return ""
    match = re.search(r"window\.DASHBOARD_STATE_API\s*=\s*[\"']([^\"']+)[\"']", INDEX_FILE.read_text(encoding="utf-8"))
    return match.group(1).strip() if match else ""


def state_url(key: str) -> str:
    base = state_api_base()
    if not base:
        return ""
    joiner = "&" if "?" in base else "?"
    return f"{base}{joiner}key={urllib.parse.quote(key)}"


def fetch_scrape_controls() -> dict[str, Any]:
    url = state_url(SCRAPE_CONTROLS_KEY)
    if not url:
        print("No DASHBOARD_STATE_API configured; using default scrape controls.", flush=True)
        return {}
    try:
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8-sig"))
            return payload if isinstance(payload, dict) else {}
    except Exception as error:
        print(f"Could not load scrape controls from Cloudflare: {error}. Using defaults.", flush=True)
        return {}


def module_state(controls: dict[str, Any], module_id: str) -> dict[str, Any]:
    modules = controls.get("modules")
    if not isinstance(modules, dict):
        return {}
    state = modules.get(module_id)
    return state if isinstance(state, dict) else {}


def source_state(controls: dict[str, Any], config: SourceConfig) -> dict[str, Any]:
    module = module_state(controls, config.module)
    sources = module.get("sources")
    if not isinstance(sources, dict):
        return {}
    state = sources.get(config.source)
    return state if isinstance(state, dict) else {}


def is_interval_enabled(controls: dict[str, Any], interval: str) -> bool:
    enabled = controls.get("interval_enabled")
    return not isinstance(enabled, dict) or enabled.get(interval, True) is not False


def is_email_enabled(controls: dict[str, Any], interval: str) -> bool:
    if controls.get("email_enabled", True) is False:
        return False
    enabled = controls.get("interval_email_enabled")
    return not isinstance(enabled, dict) or enabled.get(interval, True) is not False


def selected_sources(controls: dict[str, Any], interval: str) -> list[SourceConfig]:
    if not is_interval_enabled(controls, interval):
        return []
    selected: list[SourceConfig] = []
    for config in SOURCE_CONFIGS:
        module = module_state(controls, config.module)
        if module.get("enabled", True) is False:
            continue
        source = source_state(controls, config)
        if source.get("enabled", True) is False:
            continue
        schedule = source.get("schedule") or module.get("schedule") or config.default_schedule
        if schedule == interval:
            selected.append(config)
    return selected


def option_value(controls: dict[str, Any], module_id: str, key: str, default: Any = None) -> Any:
    module = module_state(controls, module_id)
    options = module.get("options")
    if not isinstance(options, dict):
        return default
    return options.get(key, default)


def with_options(command: list[str], config: SourceConfig, controls: dict[str, Any]) -> list[str]:
    result = [sys.executable, *command]
    supported = SCRIPT_OPTION_FLAGS.get(command[0], set())
    hard = bool(option_value(controls, config.module, "hard", False))
    if hard and "--hard" in supported and "--hard" not in result:
        result.append("--hard")
    for option_key, flag in (("limit", "--limit"), ("max_pages", "--max-pages")):
        value = option_value(controls, config.module, option_key, 0)
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = 0
        if number > 0 and flag in supported:
            result.extend([flag, str(number)])
    genre = str(option_value(controls, config.module, "genre", "") or "").strip()
    if config.module == "events" and config.source == "bandsintown" and genre and "--genre" in supported:
        result.extend(["--genre", genre])
    media_type = str(option_value(controls, config.module, "type", "") or "").strip()
    if config.module == "media" and media_type and "--type" in supported:
        result.extend(["--type", media_type])
    return result


def wants_email(controls: dict[str, Any], config: SourceConfig) -> bool:
    source = source_state(controls, config)
    email = source.get("email")
    if isinstance(email, dict) and any(bool(email.get(key)) for key in ("added", "updated", "removed")):
        return True
    module = module_state(controls, config.module)
    email = module.get("email")
    return isinstance(email, dict) and any(bool(email.get(key)) for key in ("added", "updated", "removed"))


def run_command(config: SourceConfig, controls: dict[str, Any]) -> dict[str, Any]:
    command = with_options(config.command, config, controls)
    print(f"Running {config.module}/{config.source}: {' '.join(command)}", flush=True)
    start = time.perf_counter()
    completed = subprocess.run(command, cwd=REPO_DIR)
    duration = time.perf_counter() - start
    record_scrape_outputs(
        [REPO_DIR / output for output in config.outputs],
        module=config.module,
        source=config.source,
        duration_seconds=duration,
        command=command,
        status="ok" if completed.returncode == 0 else "error",
        error="" if completed.returncode == 0 else f"Command failed with exit code {completed.returncode}",
    )
    item_count = sum(output_item_count(REPO_DIR / output) for output in config.outputs)
    return {
        "module": config.module,
        "source": config.source,
        "label": config.label,
        "command": " ".join(command),
        "duration_seconds": round(duration, 3),
        "item_count": item_count,
        "returncode": completed.returncode,
    }


def send_summary_email(interval: str, results: list[dict[str, Any]]) -> None:
    if not results:
        return
    required = ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO"]
    if any(not os.environ.get(name, "").strip() for name in required):
        print("Email summary skipped: SMTP secrets are not configured.", flush=True)
        return
    sender = os.environ.get("EMAIL_FROM") or os.environ.get("SMTP_USER", "")
    subject = f"Dashboard {interval} scrape: {len(results)} source(s)"
    lines = [
        f"Dashboard {interval} scrape summary",
        f"Finished at {datetime.now(timezone.utc).isoformat()}",
        "",
    ]
    for result in results:
        status = "ok" if result["returncode"] == 0 else f"failed ({result['returncode']})"
        lines.append(f"- {result['module']}/{result['source']}: {status}, {result['duration_seconds']}s, {result['item_count']} item(s)")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = os.environ["EMAIL_TO"]
    message.set_content("\n".join(lines))
    port = int(os.environ.get("SMTP_PORT") or "587")
    with smtplib.SMTP(os.environ["SMTP_HOST"], port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        smtp.send_message(message)
    print(f"Sent scrape summary email to {os.environ['EMAIL_TO']}.", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run scrapes selected by the dashboard scrape menu.")
    parser.add_argument("--interval", choices=sorted(INTERVALS), required=True)
    args = parser.parse_args()

    controls = fetch_scrape_controls()
    selected = selected_sources(controls, args.interval)
    if not selected:
        print(f"No enabled {args.interval} scrapers selected.", flush=True)
        return 0

    results: list[dict[str, Any]] = []
    failed = 0
    for config in selected:
        result = run_command(config, controls)
        results.append(result)
        if result["returncode"] != 0:
            failed += 1

    if is_email_enabled(controls, args.interval):
        email_results = [result for result in results if wants_email(controls, next(
            config for config in selected if config.module == result["module"] and config.source == result["source"]
        ))]
        send_summary_email(args.interval, email_results)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
