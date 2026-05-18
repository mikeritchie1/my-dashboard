from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_DIR))
sys.path.append(str(REPO_DIR / "services" / "one_piece"))

from one_piece_missing import clean_text, missing_card_numbers, normalize_card_number, sorted_matches
from one_piece_missing import resolve_card_info_from_image


ARMCHAIR_COLLECTION_URL = "https://armchairgenerals.co.za/collections/other-tcgs"
ARMCHAIR_PRODUCTS_URL = ARMCHAIR_COLLECTION_URL + "/products.json?limit=250&page={page}"


def _extract_split_card_number(text: str) -> str | None:
    cleaned = clean_text(text).upper()
    set_match = re.search(r"\((OP|ST|EB|PRB)\s*-?\s*(\d{1,2})\)", cleaned)
    number_match = re.search(r"\((\d{3})\)", cleaned)
    if not set_match or not number_match:
        return None
    prefix = set_match.group(1)
    set_no = int(set_match.group(2))
    card_no = int(number_match.group(1))
    return f"{prefix}{set_no:02d}-{card_no:03d}"


def _fetch_json(url: str) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_armchair_products(pages: int = 0) -> list[dict]:
    products: list[dict] = []
    for page in range(1, 9999):
        if pages and page > pages:
            print(f"  Page limit reached ({pages} pages)", flush=True)
            break
        url = ARMCHAIR_PRODUCTS_URL.format(page=page)
        print(f"  Fetching page {page}: {url}", flush=True)
        data = _fetch_json(url)
        page_products = (data or {}).get("products", [])
        print(f"  Page {page}: {len(page_products)} product(s)", flush=True)
        if not page_products:
            break
        products.extend(page_products)
    return products


def _variant_price(variant: dict) -> float:
    try:
        return float(variant.get("price") or 0)
    except (TypeError, ValueError):
        return 0.0


def _first_image(product: dict) -> str:
    images = product.get("images") or []
    if not images:
        return ""
    return str(images[0].get("src") or "")


def match_armchair(missing: set[str], products: list[dict]) -> list[dict[str, object]]:
    matches: list[dict[str, object]] = []
    misses = 0
    image_attempts = 0
    image_hits = 0
    for product in products:
        title = clean_text(product.get("title"))
        body_html = str(product.get("body_html") or "")
        tags = clean_text(product.get("tags"))
        search_text = " | ".join([title, body_html, tags])
        card_number = normalize_card_number(search_text) or _extract_split_card_number(search_text)
        rarity = ""
        if not card_number:
            image_attempts += 1
            product_for_image = dict(product)
            product_for_image["permalink"] = (
                f"{ARMCHAIR_COLLECTION_URL}/products/{product.get('handle', '')}"
            )
            card_number, rarity = resolve_card_info_from_image(product_for_image, card_number="", rarity="")
            if card_number:
                image_hits += 1
        if not card_number:
            misses += 1
            if misses <= 20 or misses % 50 == 0:
                print(f"  Card-number miss {misses}: {title[:100]}", flush=True)
            continue
        if card_number not in missing:
            continue

        available_variants = [v for v in (product.get("variants") or []) if v.get("available")]
        if not available_variants:
            continue
        cheapest = min(available_variants, key=_variant_price)

        matches.append(
            {
                "store": "Armchair Generals",
                "card_number": card_number,
                "title": title,
                "set_name": "",
                "rarity": rarity,
                "condition": str(cheapest.get("title") or "").strip(),
                "stock": "In stock",
                "price": _variant_price(cheapest),
                "available_variants": "; ".join(
                    f"{str(v.get('title') or '').strip()} R{_variant_price(v):.2f}"
                    for v in available_variants
                ),
                "url": f"{ARMCHAIR_COLLECTION_URL}/products/{product.get('handle', '')}",
                "image_url": _first_image(product),
            }
        )
    print(f"  Card-number misses: {misses}", flush=True)
    if image_attempts:
        print(f"  Image detection hits: {image_hits}/{image_attempts}", flush=True)
    return matches


def _print_match(match: dict[str, object]) -> None:
    print(f"  Card:      {match.get('card_number', '')}")
    print(f"  Title:     {match.get('title', '')}")
    print(f"  Price:     R {float(match.get('price') or 0):.2f}")
    if match.get("condition"):
        print(f"  Condition: {match.get('condition', '')}")
    if match.get("available_variants"):
        print(f"  Variants:  {match.get('available_variants', '')}")
    print(f"  Store URL: {match.get('url', '')}")
    if match.get("image_url"):
        print(f"  Image:     {match.get('image_url', '')}")
    print("")


def main() -> int:
    parser = argparse.ArgumentParser(description="Test scrape Armchair Generals for missing One Piece cards.")
    parser.add_argument(
        "--pages",
        type=int,
        default=0,
        metavar="N",
        help="Max pages to fetch (default: all pages).",
    )
    args = parser.parse_args()

    print("Loading missing card numbers from workbook...", flush=True)
    missing = missing_card_numbers()
    print(f"Missing card numbers loaded: {len(missing)}", flush=True)

    print("\n=== Armchair Generals ===", flush=True)
    products = fetch_armchair_products(pages=args.pages)
    print(f"Total products fetched: {len(products)}", flush=True)

    matches = sorted_matches(match_armchair(missing, products))
    print(f"\nAvailable missing card listings: {len(matches)}", flush=True)
    for match in matches:
        _print_match(match)

    distinct = {m["card_number"] for m in matches}
    print("=== Summary ===")
    print(f"Distinct missing cards available: {len(distinct)}")
    print(f"Total listing value: R {sum(float(m['price']) for m in matches):.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
