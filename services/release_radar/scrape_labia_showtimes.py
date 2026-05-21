from __future__ import annotations

import argparse
import html
import json
import re
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))
from services.release_radar.scrape_releases import fetch_tmdb_details


CLIENT_URL = "https://www.webtickets.co.za/v2/client.aspx?clientcode=labia"
EVENT_URL_TEMPLATE = "https://www.webtickets.co.za/v2/event.aspx?itemid={itemid}"
LABIA_SHOWING_JSON_URL = "https://labiahomescreen.s3.af-south-1.amazonaws.com/showing.json"
DATA_DIR = Path(__file__).resolve().parents[2] / "docs" / "data" / "release_radar"
OUTPUT_FILE = DATA_DIR / "labia_showtimes.json"
MONTH_LOOKUP = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
WEEKDAY_ALIASES = {
    "mon": 0,
    "monday": 0,
    "tue": 1,
    "tues": 1,
    "tuesday": 1,
    "wed": 2,
    "wednesday": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "thursday": 3,
    "fri": 4,
    "friday": 4,
    "sat": 5,
    "saturday": 5,
    "sun": 6,
    "sunday": 6,
}


def fetch_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_json(url: str) -> dict:
    try:
        return json.loads(fetch_text(url))
    except Exception:
        return {}


def parse_cards(client_html: str) -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []
    blocks = re.findall(
        r'(?s)<div class="col-md-4 col-sm-6 js-event-item"[^>]*>(.*?)(?=<div class="col-md-4 col-sm-6 js-event-item"|\Z)',
        client_html,
    )
    for block in blocks:
        item_match = re.search(r'href="event\.aspx\?itemid=(\d+)"', block)
        meta_match = re.search(r'<div class="product-card-meta">\s*From\s*([^<]+)</div>', block)
        if not item_match or not meta_match:
            continue

        itemid = item_match.group(1).strip()
        title_match = re.search(
            rf'<h3 class="product-card-title">\s*<a class="spinner" href="event\.aspx\?itemid={re.escape(itemid)}">([^<]+)</a>',
            block,
        )
        image_match = re.search(
            rf'<a href="event\.aspx\?itemid={re.escape(itemid)}" class="spinner">\s*<img src="([^"]+)"',
            block,
        )
        title = html.unescape(title_match.group(1) if title_match else "").strip()
        image = html.unescape(image_match.group(1) if image_match else "").strip()
        from_text = html.unescape(meta_match.group(1)).strip()
        title = re.sub(r"\s+", " ", title)
        if not title or "VOUCHER" in title.upper():
            continue

        cards.append({"from_text": from_text, "itemid": itemid, "title": title, "image": image})
    return cards


def parse_event_dates(event_html: str, itemid: str) -> list[date]:
    pattern = re.compile(rf"setPerformance\({re.escape(itemid)},0,'([0-9]{{1,2}}-[A-Za-z]{{3}}-[0-9]{{4}})'\)")
    days: list[date] = []
    for match in pattern.finditer(event_html):
        day = datetime.strptime(match.group(1), "%d-%b-%Y").date()
        days.append(day)
    return sorted(set(days))


def parse_event_calendar_showings(event_html: str) -> dict[date, set[str]]:
    month_match = re.search(r">\s*([A-Za-z]+)\s+(\d{4})\s*<", event_html)
    if not month_match:
        return {}

    month = MONTH_LOOKUP.get(month_match.group(1).lower())
    year = int(month_match.group(2))
    if not month:
        return {}

    showings: dict[date, set[str]] = {}
    cell_pattern = re.compile(
        r"(?s)<div class=['\"]?ec-date['\"]?>\s*"
        r"<a\s+[^>]*href=Performance\.aspx\?itemid=\d+[^>]*>\s*"
        r"<span class=ec-number>.*?&nbsp;\s*(\d{1,2})</span>\s*"
        r"<span class=ec-description>(.*?)</span>",
    )
    for match in cell_pattern.finditer(event_html):
        try:
            showing_day = date(year, month, int(match.group(1)))
        except ValueError:
            continue
        times = re.findall(r"\d{1,2}:\d{2}", match.group(2))
        if times:
            showings.setdefault(showing_day, set()).update(times)

    return showings


def tmdb_search_title(title: str) -> str:
    cleaned = re.sub(r"\([^)]*\)", "", title)
    cleaned = re.sub(r"\bAfrikaans with English subtitles\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bPG\s*\d{0,2}(?:-\d{0,2})?\s*[A-Z ]*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d{1,2}\s*[A-Z ]{1,8}$", "", cleaned)
    cleaned = cleaned.replace("STAR WARS:", "STAR WARS: ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .:-")
    return cleaned or title


def title_key(title: str) -> str:
    return tmdb_search_title(title).casefold()


def parse_labia_date(value: object) -> date | None:
    raw = re.sub(r"\s+", " ", str(value or "")).strip()
    if not raw:
        return None
    for fmt in ("%d %b %Y", "%d %B %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def date_range(first_day: date, last_day: date) -> list[date]:
    if last_day < first_day:
        return []
    return [first_day + timedelta(days=offset) for offset in range((last_day - first_day).days + 1)]


def excluded_weekdays(value: object) -> set[int]:
    raw = str(value or "").lower()
    if not raw:
        return set()
    raw = raw.replace("(", " ").replace(")", " ")
    raw = re.sub(r"\bexcept\b", " ", raw)
    tokens = re.split(r"[^a-z]+", raw)
    return {WEEKDAY_ALIASES[token] for token in tokens if token in WEEKDAY_ALIASES}


def labia_site_showings() -> dict[str, dict[date, set[str]]]:
    payload = fetch_json(LABIA_SHOWING_JSON_URL)
    if not payload:
        return {}

    start = parse_labia_date(payload.get("startMovieTimes"))
    end = parse_labia_date(payload.get("endMovieTimes"))
    screenings = payload.get("movieScreenings")
    if not start or not end or not isinstance(screenings, list):
        return {}

    week_days = date_range(start, end)
    showings: dict[str, dict[date, set[str]]] = {}
    for screen in screenings:
        if not isinstance(screen, dict) or not isinstance(screen.get("movies"), list):
            continue
        for movie in screen["movies"]:
            if not isinstance(movie, dict):
                continue
            title = re.sub(r"\s+", " ", str(movie.get("movieName") or "")).strip()
            show_time = re.sub(r"\s+", " ", str(movie.get("time") or "")).strip()
            if not title or not show_time:
                continue
            excluded = excluded_weekdays(movie.get("exception") or movie.get("timeException"))
            bucket = showings.setdefault(title_key(title), {})
            for day in week_days:
                if day.weekday() not in excluded:
                    bucket.setdefault(day, set()).add(show_time)
    return showings


def labia_week_start(day: date) -> date:
    # Labia schedules are published in Friday -> Thursday windows.
    return day - timedelta(days=(day.weekday() - 4) % 7)


def display_day(day_key: str) -> str:
    return datetime.strptime(day_key, "%Y-%m-%d").date().strftime("%d %b %Y")


def day_key_date(day_key: str) -> date:
    return datetime.strptime(day_key, "%Y-%m-%d").date()


def date_text_for_range(first_key: str, last_key: str) -> str:
    if first_key == last_key:
        return display_day(first_key)
    return f"{display_day(first_key)} - {display_day(last_key)}"


def format_showtime_summary(showings_by_date: list[dict[str, object]]) -> str:
    if not showings_by_date:
        return ""

    segments: list[dict[str, object]] = []
    for entry in showings_by_date:
        day_key = str(entry.get("date") or "")
        times = tuple(str(time) for time in entry.get("times", []) if time) if isinstance(entry.get("times"), list) else ()
        if not day_key or not times:
            continue

        if segments:
            previous = segments[-1]
            previous_end = day_key_date(str(previous["end"]))
            if previous["times"] == times and day_key_date(day_key) == previous_end + timedelta(days=1):
                previous["end"] = day_key
                continue

        segments.append({"start": day_key, "end": day_key, "times": times})

    lines: list[str] = []
    for segment in segments:
        date_text = date_text_for_range(str(segment["start"]), str(segment["end"]))
        times_text = ", ".join(segment["times"])
        lines.append(f"{date_text}: {times_text}")
    return "\n".join(lines)


def scrape_labia_showtimes(start_date: date, days: int) -> dict[str, object]:
    if days == 14:
        first_week_start = labia_week_start(start_date)
        end_date = first_week_start + timedelta(days=13)
        start_date = first_week_start
    else:
        end_date = start_date + timedelta(days=max(1, days) - 1)

    client_html = fetch_text(CLIENT_URL)
    cards = parse_cards(client_html)
    fuller_labia_showings = labia_site_showings()

    grouped: dict[str, dict[str, object]] = {}
    for card in cards:
        from_dt = datetime.strptime(card["from_text"], "%d %b %Y %H:%M")
        show_time = from_dt.strftime("%H:%M")
        event_url = EVENT_URL_TEMPLATE.format(itemid=card["itemid"])
        event_html = fetch_text(event_url)
        event_showings = parse_event_calendar_showings(event_html)
        if not event_showings:
            event_days = parse_event_dates(event_html, card["itemid"])
            event_showings = {day: {show_time} for day in event_days}
        movie_key = title_key(card["title"])
        if movie_key not in grouped:
            grouped[movie_key] = {
                "title": card["title"],
                "tmdb_search_title": tmdb_search_title(card["title"]),
                "image": card.get("image", ""),
                "book_urls": set(),
                "itemids": set(),
                "times_by_date": {},
            }

        bucket = grouped[movie_key]
        bucket["book_urls"].add(event_url)
        bucket["itemids"].add(card["itemid"])

        if not event_showings:
            event_showings = {from_dt.date(): {show_time}}

        for day, day_times in event_showings.items():
            key = day.isoformat()
            date_times = bucket["times_by_date"].setdefault(key, set())
            date_times.update(day_times or {show_time})

        labia_times = fuller_labia_showings.get(movie_key, {})
        if labia_times:
            labia_count = sum(len(day_times) for day_times in labia_times.values())
            webtickets_count = sum(len(day_times) for day_times in event_showings.values())
            if labia_count > webtickets_count:
                for day, day_times in labia_times.items():
                    key = day.isoformat()
                    date_times = bucket["times_by_date"].setdefault(key, set())
                    date_times.update(day_times)

    items: list[dict[str, object]] = []
    for grouped_movie in grouped.values():
        times_by_date = grouped_movie["times_by_date"]
        if not times_by_date:
            continue

        sorted_dates = sorted(times_by_date)
        showings: list[str] = []
        showings_by_date: list[dict[str, object]] = []
        for day_key in sorted_dates:
            sorted_times = sorted(times_by_date[day_key])
            showings_by_date.append({"date": day_key, "times": sorted_times})
            for t in sorted_times:
                showings.append(f"{day_key} {t}")

        first_day = datetime.strptime(sorted_dates[0], "%Y-%m-%d").date()
        last_day = datetime.strptime(sorted_dates[-1], "%Y-%m-%d").date()
        event_date_text = (
            first_day.strftime("%d %b %Y")
            if first_day == last_day
            else f"{first_day.strftime('%d %b %Y')} - {last_day.strftime('%d %b %Y')}"
        )
        showtime_summary = format_showtime_summary(showings_by_date)

        details = fetch_tmdb_details(grouped_movie["tmdb_search_title"], year=str(first_day.year))
        if not details:
            details = fetch_tmdb_details(grouped_movie["tmdb_search_title"])

        book_url = sorted(grouped_movie["book_urls"])[0]
        itemid = sorted(grouped_movie["itemids"])[0]
        items.append(
            {
                **details,
                "title": grouped_movie["title"],
                "itemid": itemid,
                "source": "Labia Theatre",
                "status": "now_showing",
                "status_label": "Now showing",
                "url": book_url,
                "book_url": book_url,
                "event_date_text": event_date_text,
                "showtime_summary": showtime_summary,
                "release_date": details.get("release_date", "") or first_day.isoformat(),
                "image": details.get("poster_url", "") or grouped_movie.get("image", ""),
                "showings": showings,
                "showings_by_date": showings_by_date,
            }
        )

    items.sort(key=lambda item: (str(item.get("showings", [""])[0]), str(item.get("title", ""))))
    all_showing_dates = sorted(
        datetime.strptime(day_key, "%Y-%m-%d").date()
        for grouped_movie in grouped.values()
        for day_key in grouped_movie["times_by_date"]
    )

    return {
        "source": CLIENT_URL,
        "window": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "days": max(1, days),
        },
        "listed_window": {
            "start_date": all_showing_dates[0].isoformat() if all_showing_dates else "",
            "end_date": all_showing_dates[-1].isoformat() if all_showing_dates else "",
        },
        "weeks": [
            {
                "start_date": start_date.isoformat(),
                "end_date": (start_date + timedelta(days=6)).isoformat(),
            },
            {
                "start_date": (start_date + timedelta(days=7)).isoformat(),
                "end_date": (start_date + timedelta(days=13)).isoformat(),
            },
        ] if days == 14 else [],
        "items": items,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape Labia Theatre showtimes from Webtickets.")
    parser.add_argument("--hard", action="store_true", help="Remove existing output before scraping.")
    parser.add_argument("--days", type=int, default=14, help="Number of days from --start-date to include.")
    parser.add_argument("--start-date", default=date.today().isoformat(), help="Start date in YYYY-MM-DD format.")
    parser.add_argument("--limit", type=int, default=0, help="Accepted for wrapper consistency; ignored.")
    parser.add_argument("--max-pages", type=int, default=0, help="Accepted for wrapper consistency; ignored.")
    args = parser.parse_args()

    start_date = datetime.strptime(args.start_date, "%Y-%m-%d").date()

    if args.hard and OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()

    payload = scrape_labia_showtimes(start_date=start_date, days=args.days)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(payload.get('items', []))} Labia title(s) to {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
