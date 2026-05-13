from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_DIR))
sys.path.append(str(REPO_DIR / "services" / "one_piece"))

from one_piece_missing import (
    BIG_BANG_COLLECTION_URL,
    BIG_BANG_PRODUCTS_URL,
    KNIGHTLY_COLLECTION_URL,
    KNIGHTLY_PRODUCTS_URL,
    MARVELLOUS_COLLECTION_URL,
    MARVELLOUS_PRODUCTS_URL,
    TANUKI_COLLECTION_URL,
    TANUKI_PRODUCTS_URL,
    match_big_bang,
    match_knightly,
    match_marvellous,
    match_tanuki,
    missing_card_numbers,
    sorted_matches,
)

SITES = ["bigbang", "knightly", "marvellous", "tanuki"]


def _fetch_json(url: str) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_shopify(url_template: str, store: str, pages: int = 0) -> list[dict]:
    products: list[dict] = []
    for page in range(1, 9999):
        if pages and page > pages:
            print(f"  Page limit reached ({pages} pages)", flush=True)
            break
        url = url_template.format(page=page)
        print(f"  Fetching page {page}: {url}", flush=True)
        data = _fetch_json(url)
        page_products = (data or {}).get("products", [])
        print(f"  Page {page}: {len(page_products)} product(s)", flush=True)
        if not page_products:
            break
        products.extend(page_products)
    return products


def fetch_woo(url_template: str, store: str, pages: int = 0) -> list[dict]:
    products: list[dict] = []
    for page in range(1, 9999):
        if pages and page > pages:
            print(f"  Page limit reached ({pages} pages)", flush=True)
            break
        url = url_template.format(page=page)
        print(f"  Fetching page {page}: {url}", flush=True)
        data = _fetch_json(url)
        page_products = data if isinstance(data, list) else []
        print(f"  Page {page}: {len(page_products)} product(s)", flush=True)
        if not page_products:
            break
        products.extend(page_products)
    return products


def _first_image(product: dict) -> str:
    images = product.get("images") or []
    if not images:
        return ""
    src = images[0].get("src") or ""
    return str(src)


def _image_map_shopify(products: list[dict]) -> dict[str, str]:
    return {
        str(p.get("handle") or ""): _first_image(p)
        for p in products
        if p.get("handle")
    }


def _image_map_woo(products: list[dict]) -> dict[str, str]:
    return {
        str(p.get("permalink") or ""): _first_image(p)
        for p in products
        if p.get("permalink")
    }


def _image_for_shopify_match(match: dict, image_map: dict[str, str]) -> str:
    url = str(match.get("url") or "")
    for handle, image_url in image_map.items():
        if handle and handle in url:
            return image_url
    return ""


def _print_match(match: dict, image_url: str = "") -> None:
    print(f"  Card:     {match.get('card_number', '')}")
    print(f"  Title:    {match.get('title', '')}")
    print(f"  Price:    R {float(match.get('price') or 0):.2f}")
    if match.get("rarity"):
        print(f"  Rarity:   {match['rarity']}")
    if match.get("set_name"):
        print(f"  Set:      {match['set_name']}")
    if match.get("condition"):
        print(f"  Condition:{match['condition']}")
    if match.get("available_variants"):
        print(f"  Variants: {match['available_variants']}")
    print(f"  Store URL:{match.get('url', '')}")
    if image_url:
        print(f"  Image:    {image_url}")
    print()


def run_knightly(missing: set[str], pages: int) -> list[dict[str, object]]:
    print("\n=== Knightly Gaming ===", flush=True)
    products = fetch_shopify(KNIGHTLY_PRODUCTS_URL, "Knightly Gaming", pages=pages)
    print(f"Total products fetched: {len(products)}", flush=True)
    matches = sorted_matches(match_knightly(missing, products))
    image_map = _image_map_shopify(products)
    print(f"\nAvailable missing card listings: {len(matches)}", flush=True)
    for match in matches:
        _print_match(match, _image_for_shopify_match(match, image_map))
    return matches


def run_big_bang(missing: set[str], pages: int) -> list[dict[str, object]]:
    print("\n=== Big Bang Shop ===", flush=True)
    products = fetch_shopify(BIG_BANG_PRODUCTS_URL, "Big Bang Shop", pages=pages)
    print(f"Total products fetched: {len(products)}", flush=True)
    matches = sorted_matches(match_big_bang(missing, products))
    image_map = _image_map_shopify(products)
    print(f"\nAvailable missing card listings: {len(matches)}", flush=True)
    for match in matches:
        _print_match(match, _image_for_shopify_match(match, image_map))
    return matches


def run_marvellous(missing: set[str], pages: int) -> list[dict[str, object]]:
    print("\n=== Marvellous Hobbies ===", flush=True)
    products = fetch_woo(MARVELLOUS_PRODUCTS_URL, "Marvellous Hobbies", pages=pages)
    print(f"Total products fetched: {len(products)}", flush=True)
    matches = sorted_matches(match_marvellous(missing, products))
    image_map = _image_map_woo(products)
    print(f"\nAvailable missing card listings: {len(matches)}", flush=True)
    for match in matches:
        _print_match(match, image_map.get(str(match.get("url") or ""), ""))
    return matches


def run_tanuki(missing: set[str], pages: int) -> list[dict[str, object]]:
    print("\n=== Tanuki Trader ===", flush=True)
    products = fetch_woo(TANUKI_PRODUCTS_URL, "Tanuki Trader", pages=pages)
    print(f"Total products fetched: {len(products)}", flush=True)
    matches = sorted_matches(match_tanuki(missing, products))
    image_map = _image_map_woo(products)
    print(f"\nAvailable missing card listings: {len(matches)}", flush=True)
    for match in matches:
        _print_match(match, image_map.get(str(match.get("url") or ""), ""))
    return matches


RUNNERS = {
    "bigbang": run_big_bang,
    "knightly": run_knightly,
    "marvellous": run_marvellous,
    "tanuki": run_tanuki,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Test scrape for One Piece missing cards.")
    parser.add_argument(
        "site",
        nargs="?",
        choices=SITES + ["all"],
        default="all",
        help="Which store to scrape (default: all).",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=0,
        metavar="N",
        help="Max pages to fetch per site (default: all pages).",
    )
    args = parser.parse_args()

    print("Loading missing card numbers from workbook...", flush=True)
    missing = missing_card_numbers()
    print(f"Missing card numbers loaded: {len(missing)}", flush=True)

    sites = SITES if args.site == "all" else [args.site]

    all_matches: list[dict[str, object]] = []
    for site in sites:
        try:
            matches = RUNNERS[site](missing, pages=args.pages)
            all_matches.extend(matches)
        except Exception as error:
            print(f"ERROR scraping {site}: {error}", file=sys.stderr, flush=True)

    if len(sites) > 1:
        print("\n=== Overall Summary ===")
        print(f"Total available missing card listings: {len(all_matches)}")
        distinct = {m["card_number"] for m in all_matches}
        print(f"Distinct missing cards available: {len(distinct)}")
        print(f"Total value across all listings: R {sum(float(m['price']) for m in all_matches):.2f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
