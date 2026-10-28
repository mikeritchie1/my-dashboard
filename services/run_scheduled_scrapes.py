from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_DIR = Path(__file__).resolve().parents[1]
if str(REPO_DIR) not in sys.path:
    sys.path.append(str(REPO_DIR))

from services.common.scrape_metadata import output_item_count, record_scrape_outputs, record_source_history
from services.common.scrape_notifications import read_source_rows, change_sections, send_sections
from services.common.scrape_summary import load_summary, save_summary, collect, send_if_due

DOCS_DIR = REPO_DIR / "docs"
INDEX_FILE = DOCS_DIR / "index.html"
SCRAPE_CONTROLS_KEY = "scrape-controls"
INTERVALS = {"ten-minute", "hourly", "daily", "weekly"}
CONTROLS_UNAVAILABLE_KEY = "_controls_unavailable"
TRUE_VALUES = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class SourceConfig:
    module: str
    source: str
    label: str
    default_schedule: str
    command: list[str]
    outputs: list[str]
    fail_workflow: bool = True
    default_enabled: bool = True


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
    SourceConfig("one-piece", "marvellous", "Marvellous Gaming", "hourly", ["services/scrape_one_piece.py", "--source", "marvellous"], ["docs/data/one_piece/missing_cards.json"], fail_workflow=False, default_enabled=False),
    SourceConfig("one-piece", "tanuki", "Tanuki Games", "hourly", ["services/scrape_one_piece.py", "--source", "tanuki"], ["docs/data/one_piece/missing_cards.json"], fail_workflow=False),
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
    SourceConfig("news", "f1-snapshot", "F1 snapshot", "daily", ["-m", "services.common.scheduled_source_tasks", "f1-snapshot"], ["docs/data/news/news.json"]),
    SourceConfig("media", "watchlist", "Notion watchlist", "daily", ["services/scrape_media.py", "--source", "watchlist"], ["docs/data/media/watchlist.json"]),
    SourceConfig("media", "games", "Notion games", "daily", ["services/scrape_media.py", "--source", "games"], ["docs/data/media/gameslist.json"]),
    SourceConfig("media", "reading", "Notion reading list", "daily", ["services/scrape_media.py", "--source", "reading"], ["docs/data/reading_list.json", "docs/data/media/reading_details.json"]),
    SourceConfig("media", "tmdb", "TMDB enrichment", "daily", ["-m", "services.common.scheduled_source_tasks", "tmdb"], ["docs/data/media/watchlist_movie_details.json"]),
    SourceConfig("media", "rawg", "RAWG enrichment", "daily", ["-m", "services.common.scheduled_source_tasks", "rawg"], ["docs/data/media/games_details.json"]),
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
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            },
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8-sig"))
            return payload if isinstance(payload, dict) else {}
    except Exception as error:
        print(f"Could not load scrape controls from Cloudflare: {error}. Skipping selected scrapes for safety.", flush=True)
        return {
            CONTROLS_UNAVAILABLE_KEY: True,
            "interval_enabled": {interval: False for interval in INTERVALS},
            "email_enabled": False,
        }


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


def selected_sources(controls: dict[str, Any], interval: str) -> list[SourceConfig]:
    if controls.get(CONTROLS_UNAVAILABLE_KEY):
        return []
    if not is_interval_enabled(controls, interval):
        return []
    try:
        controls_version = int(controls.get("version") or 0)
    except (TypeError, ValueError):
        controls_version = 0
    selected: list[SourceConfig] = []
    for config in SOURCE_CONFIGS:
        module = module_state(controls, config.module)
        if module.get("enabled", True) is False:
            continue
        source = source_state(controls, config)
        if controls_version < 2 and not config.default_enabled:
            continue
        if source.get("enabled", config.default_enabled) is False:
            continue
        schedule = source.get("schedule") or module.get("schedule") or config.default_schedule
        if config.module == "events" and config.source == "geocode" and option_value(controls, "events", "skip_geocode", False):
            continue
        if schedule == "disabled":
            continue
        if schedule == interval:
            selected.append(config)
    return selected


def option_value(controls: dict[str, Any], module_id: str, key: str, default: Any = None) -> Any:
    module = module_state(controls, module_id)
    options = module.get("options")
    if not isinstance(options, dict):
        return default
    return options.get(key, default)


def allow_scheduled_hard() -> bool:
    return os.environ.get("DASHBOARD_ALLOW_SCHEDULED_HARD", "").strip().lower() in TRUE_VALUES


def with_options(command: list[str], config: SourceConfig, controls: dict[str, Any]) -> list[str]:
    result = [sys.executable, *command]
    if command[0] == "services/scrape_one_piece.py":
        result.append("--skip-products")
    if config.module == "youtube" and config.source == "one-piece":
        result[result.index("--mode") + 1] = str(option_value(controls, "youtube", "mode", "daily"))
    if command[0] == "services/scrape_media.py" and config.source in {"watchlist", "games"}:
        result.append("--skip-enrichment")
    if command[0] == "services/scrape_news.py" and config.source == "rss":
        result.append("--skip-f1")
    supported = SCRIPT_OPTION_FLAGS.get(command[0], set())
    hard = bool(option_value(controls, config.module, "hard", False))
    if hard and allow_scheduled_hard() and "--hard" in supported and "--hard" not in result:
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


def run_command(config: SourceConfig, controls: dict[str, Any]) -> dict[str, Any]:
    command = with_options(config.command, config, controls)
    print(f"Running {config.module}/{config.source}: {' '.join(command)}", flush=True)
    start = time.perf_counter()
    returncode = 1
    status = "error"
    error = ""
    try:
        completed = subprocess.run(command, cwd=REPO_DIR)
        returncode = completed.returncode
        status = "ok" if returncode == 0 else "error"
        error = "" if returncode == 0 else f"Command failed with exit code {returncode}"
    except KeyboardInterrupt:
        status = "interrupted"
        error = "Interrupted by user"
        raise
    except Exception as exc:
        error = str(exc) or exc.__class__.__name__
        raise
    finally:
        duration = time.perf_counter() - start
        record_scrape_outputs(
            [REPO_DIR / output for output in config.outputs],
            module=config.module,
            source=config.source,
            duration_seconds=duration,
            command=command,
            status=status,
            error=error,
        )
    item_count = sum(output_item_count(REPO_DIR / output) for output in config.outputs)
    return {
        "module": config.module,
        "source": config.source,
        "label": config.label,
        "command": " ".join(command),
        "duration_seconds": round(duration, 3),
        "item_count": item_count,
        "returncode": returncode,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run scrapes selected by the dashboard scrape menu.")
    parser.add_argument("--interval", choices=sorted(INTERVALS), required=True)
    args = parser.parse_args()

    controls = fetch_scrape_controls()
    summary_path = DOCS_DIR / "data" / "scrape_summary.json"
    summary = load_summary(summary_path)
    selected = selected_sources(controls, args.interval)
    if not selected:
        print(f"No enabled {args.interval} scrapers selected.", flush=True)
        send_if_due(summary_path, summary, controls, args.interval)
        return 0

    results: list[dict[str, Any]] = []
    failed = 0
    sections: list[str] = []
    for config in selected:
        before = read_source_rows(REPO_DIR, config)
        try:
            result = run_command(config, controls)
        except Exception as error:
            print(f"{config.module}/{config.source} failed: {error}", flush=True)
            failed += int(config.fail_workflow)
            continue
        results.append(result)
        if result["returncode"] == 0:
            after = read_source_rows(REPO_DIR, config)
            record_source_history(config.module, config.source, before, after)
            collect(summary, config, before, after)
            save_summary(summary_path, summary)
            sections.extend(change_sections(config, controls, args.interval, before, after))
        if result["returncode"] != 0 and config.fail_workflow:
            failed += 1
        elif result["returncode"] != 0:
            print(f"{config.module}/{config.source} failed but is configured as non-fatal.", flush=True)

    try:
        send_sections(sections, args.interval)
    finally:
        send_if_due(summary_path, summary, controls, args.interval)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
