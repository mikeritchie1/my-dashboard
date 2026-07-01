from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


BASE = "https://marvelloushobbies.com/wp-json/wc/store/v1/products"


@dataclass(frozen=True)
class Method:
    name: str
    params: dict[str, str]


def fetch_page(method: Method, page: int, per_page: int) -> tuple[list[dict[str, Any]], int, int, float]:
    query = {"per_page": str(per_page), "page": str(page), **method.params}
    url = f"{BASE}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    start = time.perf_counter()
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8")
        elapsed = time.perf_counter() - start
        total_items = int(response.headers.get("X-WP-Total") or 0)
        total_pages = int(response.headers.get("X-WP-TotalPages") or 0)
    data = json.loads(raw)
    products = [item for item in data] if isinstance(data, list) else []
    return [item for item in products if isinstance(item, dict)], total_items, total_pages, elapsed


def fetch_all(method: Method, *, per_page: int, max_pages: int) -> dict[str, Any]:
    products: list[dict[str, Any]] = []
    total_items = 0
    total_pages = 0
    elapsed_total = 0.0
    for page in range(1, max_pages + 1):
        page_products, total_items, total_pages, elapsed = fetch_page(method, page, per_page)
        elapsed_total += elapsed
        products.extend(page_products)
        print(f"{method.name}: page {page}/{total_pages or '?'} -> {len(page_products)} product(s), {elapsed:.2f}s")
        if not page_products or (total_pages and page >= total_pages):
            break
    ids = {str(product.get("id")) for product in products if product.get("id") is not None}
    return {
        "method": method,
        "products": products,
        "ids": ids,
        "reported_total": total_items,
        "reported_pages": total_pages,
        "elapsed": elapsed_total,
    }


def print_sample(title: str, products: list[dict[str, Any]], limit: int = 8) -> None:
    print(title)
    for product in products[:limit]:
        print(f"  {product.get('id')} | {product.get('name')} | {product.get('permalink')}")
    if not products:
        print("  none")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare old and optimized Marvellous One Piece product coverage."
    )
    parser.add_argument("--per-page", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=100)
    args = parser.parse_args()

    old_method = Method("old category=36", {"category": "36"})
    new_method = Method("new _unstable_tax_universe=29", {"_unstable_tax_universe": "29"})

    old = fetch_all(old_method, per_page=max(1, min(args.per_page, 100)), max_pages=max(1, args.max_pages))
    new = fetch_all(new_method, per_page=max(1, min(args.per_page, 100)), max_pages=max(1, args.max_pages))

    old_ids = old["ids"]
    new_ids = new["ids"]
    missing_from_new = old_ids - new_ids
    added_by_new = new_ids - old_ids
    shared = old_ids & new_ids

    print("\n=== Marvellous Coverage Comparison ===")
    print(
        f"old category=36: reported {old['reported_total']} product(s), "
        f"{old['reported_pages']} page(s), fetched {len(old['products'])}, {old['elapsed']:.2f}s"
    )
    print(
        f"new _unstable_tax_universe=29: reported {new['reported_total']} product(s), "
        f"{new['reported_pages']} page(s), fetched {len(new['products'])}, {new['elapsed']:.2f}s"
    )
    print(f"shared product ids: {len(shared)}")
    print(f"old product ids missing from new: {len(missing_from_new)}")
    print(f"new product ids not in old: {len(added_by_new)}")

    old_by_id = {str(product.get("id")): product for product in old["products"] if product.get("id") is not None}
    new_by_id = {str(product.get("id")): product for product in new["products"] if product.get("id") is not None}
    print_sample(
        "\nSample old products missing from new:",
        [old_by_id[item_id] for item_id in sorted(missing_from_new) if item_id in old_by_id],
    )
    print_sample(
        "\nSample new products not in old:",
        [new_by_id[item_id] for item_id in sorted(added_by_new) if item_id in new_by_id],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
