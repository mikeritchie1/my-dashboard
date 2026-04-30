# One Piece Scraper + Personal Dashboard

This repo contains:
- a local dashboard in `docs/`
- scraper pipelines in `one-piece/`, `events/`, and `release-radar/`

## Configuration

Configuration is centralized in [env.py](C:/Users/mjrit/OneDrive/Desktop/one-piece-scraper/env.py).

- `CONFIG["dashboard"]`: dashboard-level settings
- `CONFIG["scraping"]`: scraper tokens, IDs, URLs, and source templates

Scripts import config directly from `env.py` (via `from env import get as env_get`), not from OS environment variables.

## Dashboard Use

1. Run scrapers and copy outputs into `docs/data`:

```powershell
python run_local_dashboard_update.py all
```

2. Start local server:

```powershell
cd docs
python -m http.server 8080
```

3. Open:

`http://localhost:8080`

## Scraping

### Pipeline flow

1. `run_local_dashboard_update.py` picks scraper commands by task.
2. Each scraper reads config from `env.py`.
3. Scrapers write outputs to local `data/` directories.
4. Runner copies `.json` and `.csv` files to `docs/data/`.
5. Runner writes `docs/data/metadata.json` with timestamp.

### Task selector

```powershell
python run_local_dashboard_update.py [all|cards|specials|events|releases|coming-soon|watchlist]
```

### Individual scraper params

Watchlist:

```powershell
python events\scrape_watchlist.py --type [all|movies|series|anime] [--hard]
```

Webtickets:

```powershell
python events\scrape_webtickets_events.py --limit 50
```

### Timing guidance

- `events`: hourly or every few hours
- `watchlist`: on-demand after Notion updates
- `releases` / `coming-soon`: daily
- `cards`: daily or on-demand

## Project Structure

- [run_local_dashboard_update.py](C:/Users/mjrit/OneDrive/Desktop/one-piece-scraper/run_local_dashboard_update.py): runs scraper tasks and syncs outputs to `docs/data`.
- [env.py](C:/Users/mjrit/OneDrive/Desktop/one-piece-scraper/env.py): single source of config values.
- [docs/index.html](C:/Users/mjrit/OneDrive/Desktop/one-piece-scraper/docs/index.html): dashboard shell.
- [docs/app.js](C:/Users/mjrit/OneDrive/Desktop/one-piece-scraper/docs/app.js): dashboard logic.
- [docs/styles.css](C:/Users/mjrit/OneDrive/Desktop/one-piece-scraper/docs/styles.css): dashboard styles.
- `docs/data/`: rendered data used by dashboard.
- [events/scrape_watchlist.py](C:/Users/mjrit/OneDrive/Desktop/one-piece-scraper/events/scrape_watchlist.py): Notion watchlist scrape + TMDB enrichment/cache.
- [events/scrape_specials.py](C:/Users/mjrit/OneDrive/Desktop/one-piece-scraper/events/scrape_specials.py): Notion specials + places enrichment.
- [events/scrape_quicket_events.py](C:/Users/mjrit/OneDrive/Desktop/one-piece-scraper/events/scrape_quicket_events.py): Quicket scrape + geocoding cache.
- [events/scrape_webtickets_events.py](C:/Users/mjrit/OneDrive/Desktop/one-piece-scraper/events/scrape_webtickets_events.py): Webtickets scrape.
- [events/scrape_google_calendar.py](C:/Users/mjrit/OneDrive/Desktop/one-piece-scraper/events/scrape_google_calendar.py): Google Calendar scrape.
- `events/data/`: events/watchlist/specials outputs and caches.
- [release-radar/scrape_releases.py](C:/Users/mjrit/OneDrive/Desktop/one-piece-scraper/release-radar/scrape_releases.py): release list scrape.
- [release-radar/scrape_coming_soon.py](C:/Users/mjrit/OneDrive/Desktop/one-piece-scraper/release-radar/scrape_coming_soon.py): TMDB upcoming scrape.
- `release-radar/data/`: release outputs.
- [one-piece/one_piece_missing.py](C:/Users/mjrit/OneDrive/Desktop/one-piece-scraper/one-piece/one_piece_missing.py): One Piece store scraping and normalization.
- [one-piece/notify_new_cards.py](C:/Users/mjrit/OneDrive/Desktop/one-piece-scraper/one-piece/notify_new_cards.py): missing-card update workflow.
- `one-piece/data/`: card outputs.
- `tests/`: manual utility test scripts.
