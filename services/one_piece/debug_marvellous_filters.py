from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


BASE = "https://marvelloushobbies.com/wp-json/wc/store/v1/products"
CATEGORIES_URL = "https://marvelloushobbies.com/wp-json/wc/store/v1/products/categories?per_page=100&_fields=id,name,slug,parent,count"
UNIVERSE_URL = "https://marvelloushobbies.com/wp-json/wp/v2/universe?per_page=100&_fields=id,slug,name,count"


@dataclass(frozen=True)
class Probe:
    name: str
    params: dict[str, str]


def fetch_json_with_headers(url: str) -> tuple[Any, dict[str, str], float]:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    start = time.perf_counter()
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8")
        elapsed = time.perf_counter() - start
        headers = {key: value for key, value in response.headers.items()}
    return json.loads(raw), headers, elapsed


def product_url(product: dict[str, Any]) -> str:
    return str(product.get("permalink") or product.get("add_to_cart") or "")


def looks_like_one_piece(product: dict[str, Any]) -> bool:
    text = " ".join(
        [
            str(product.get("name") or ""),
            str(product.get("sku") or ""),
            product_url(product),
            " ".join(str(category.get("name") or "") for category in product.get("categories") or [] if isinstance(category, dict)),
        ]
    ).lower()
    return "one-piece" in text or "one piece" in text or "one_piece" in text


def build_url(params: dict[str, str], page: int, per_page: int) -> str:
    query = {"per_page": str(per_page), "page": str(page), **params}
    return f"{BASE}?{urllib.parse.urlencode(query)}"


def summarize_product(product: dict[str, Any]) -> str:
    categories = ", ".join(
        str(category.get("name") or "") for category in product.get("categories") or [] if isinstance(category, dict)
    )
    return f"{product.get('id')} | {product.get('name')} | {product_url(product)} | {categories}"


def probe_filter(probe: Probe, *, per_page: int, max_pages: int) -> None:
    total_seen = 0
    one_piece_seen = 0
    first_matches: list[str] = []
    reported_total = 0
    reported_pages = 0
    elapsed_total = 0.0

    for page in range(1, max_pages + 1):
        url = build_url(probe.params, page, per_page)
        try:
            data, headers, elapsed = fetch_json_with_headers(url)
        except Exception as error:
            print(f"{probe.name}: page {page} failed: {error}")
            break

        products = data if isinstance(data, list) else []
        total_seen += len(products)
        elapsed_total += elapsed
        reported_total = int(headers.get("X-WP-Total") or reported_total or 0)
        reported_pages = int(headers.get("X-WP-TotalPages") or reported_pages or 0)

        for product in products:
            if isinstance(product, dict) and looks_like_one_piece(product):
                one_piece_seen += 1
                if len(first_matches) < 5:
                    first_matches.append(summarize_product(product))

        print(
            f"{probe.name}: page {page}/{reported_pages or '?'} -> "
            f"{len(products)} products, {elapsed:.2f}s, one-piece-like so far {one_piece_seen}"
        )
        if not products or (reported_pages and page >= reported_pages):
            break

    print()
    print(f"=== {probe.name} ===")
    print(f"params: {probe.params or '(none)'}")
    print(f"reported total/pages: {reported_total}/{reported_pages}")
    print(f"sampled products: {total_seen}")
    print(f"one-piece-like sampled: {one_piece_seen}")
    print(f"elapsed sampled: {elapsed_total:.2f}s")
    if first_matches:
        print("sample one-piece-like products:")
        for item in first_matches:
            print(f"  {item}")
    else:
        print("sample one-piece-like products: none")
    print()


def list_taxonomies() -> None:
    for label, url in [("product categories", CATEGORIES_URL), ("universe terms", UNIVERSE_URL)]:
        print(f"\n--- {label} ---")
        try:
            data, _headers, _elapsed = fetch_json_with_headers(url)
        except Exception as error:
            print(f"failed: {error}")
            continue
        if not isinstance(data, list):
            print(f"unexpected payload: {type(data).__name__}")
            continue
        for item in sorted(data, key=lambda row: str(row.get("name") or "").lower()):
            name = str(item.get("name") or "")
            slug = str(item.get("slug") or "")
            if re.search(r"one|piece|card|single|bandai", f"{name} {slug}", re.IGNORECASE):
                print(f"[{item.get('id')}] {name!r} slug={slug!r} count={item.get('count')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Marvellous Hobbies WooCommerce filters for One Piece scraping.")
    parser.add_argument("--per-page", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=3, help="Pages to sample per filter, not full scrape.")
    parser.add_argument("--categories", action="store_true", help="List likely category/universe terms before probing.")
    args = parser.parse_args()

    if args.categories:
        list_taxonomies()

    probes = [
        Probe("unfiltered", {}),
        Probe("category=36", {"category": "36"}),
        Probe("category_ids[]=36", {"category_ids[]": "36"}),
        Probe("universe=29", {"universe": "29"}),
        Probe("universe[]=29", {"universe[]": "29"}),
        Probe("_unstable_tax_universe=29", {"_unstable_tax_universe": "29"}),
        Probe("_unstable_tax_universe[]=29", {"_unstable_tax_universe[]": "29"}),
        Probe("category=36 + universe=29", {"category": "36", "universe": "29"}),
        Probe("category=36 + _unstable_tax_universe=29", {"category": "36", "_unstable_tax_universe": "29"}),
        Probe("search=one piece", {"search": "one piece"}),
        Probe("search=one-piece", {"search": "one-piece"}),
        Probe("slug one-piece-singles", {"slug": "one-piece-singles"}),
    ]
    for probe in probes:
        probe_filter(probe, per_page=max(1, min(args.per_page, 100)), max_pages=max(1, args.max_pages))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
