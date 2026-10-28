"""Independent enrichment tasks used by the scrape menu."""
import argparse

from services.common.scrape_metadata import load_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", choices=["tmdb", "rawg", "f1-snapshot"])
    args = parser.parse_args()
    if args.source == "f1-snapshot":
        from services import scrape_news as news
        payload = load_json(news.NEWS_FILE) or {"items": []}
        snapshot = news.build_f1_snapshot(25)
        if snapshot is None:
            raise RuntimeError("F1 snapshot could not be fetched")
        payload["items"] = [row for row in payload.get("items", []) if row.get("id") != snapshot["id"]] + [snapshot]
        news.write_payload(payload)
    else:
        from services.media import scrape_watchlist as media
        root = media.DATA_DIR
        path = root / ("watchlist.json" if args.source == "tmdb" else "gameslist.json")
        payload = load_json(path)
        if not isinstance(payload, dict):
            raise RuntimeError(f"Sync the corresponding Notion list first: {path}")
        if args.source == "tmdb":
            media.enrich_payload_with_movie_details(payload)
        else:
            media.enrich_payload_with_game_details(payload)


if __name__ == "__main__":
    main()
