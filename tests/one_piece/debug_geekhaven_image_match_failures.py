from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_DIR / "services" / "one_piece"))

from one_piece_missing import (  # noqa: E402
    fetch_geek_haven_products,
    load_image_match_cache,
    normalize_card_number,
    resolve_card_info_from_image,
)


def audit_geekhaven_image_number_detection(limit: int = 0) -> int:
    products = fetch_geek_haven_products()
    if limit > 0:
        products = products[:limit]

    total = len(products)
    cache = load_image_match_cache()
    title_has_number = 0
    image_attempts = 0
    image_hits = 0
    misses: list[dict[str, str]] = []

    for idx, product in enumerate(products, start=1):
        name = str(product.get("name") or "").strip()
        url = str(product.get("url") or "").strip()

        direct_number = normalize_card_number(name)
        if direct_number:
            title_has_number += 1
            if idx <= 10 or idx % 50 == 0:
                print(f"[{idx}/{total}] title-hit  {direct_number} | {name[:90]}", flush=True)
            continue

        image_attempts += 1
        cached = cache.get(url) if url else None
        cached_number = normalize_card_number(str((cached or {}).get("card_number") or ""))
        if cached_number:
            image_hits += 1
            if idx <= 10 or idx % 50 == 0:
                print(f"[{idx}/{total}] cache-hit  {cached_number} | {name[:90]}", flush=True)
            continue

        detected_number, _detected_rarity = resolve_card_info_from_image(product)
        detected_number = normalize_card_number(detected_number or "")
        if detected_number:
            image_hits += 1
            print(f"[{idx}/{total}] image-hit  {detected_number} | {name[:90]}", flush=True)
        else:
            misses.append({"name": name, "url": url})
            print(f"[{idx}/{total}] IMAGE-MISS -> {name}", flush=True)

    print("", flush=True)
    print(f"GeekHaven products: {total}", flush=True)
    print(f"Title already had card number: {title_has_number}", flush=True)
    print(f"Image-hash attempts: {image_attempts}", flush=True)
    print(f"Image-hash resolved: {image_hits}", flush=True)
    print(f"Image-hash unresolved: {len(misses)}", flush=True)

    if misses:
        print("\nUnresolved cards:", flush=True)
        for row in misses:
            print(f"- {row['name']} | {row['url']}", flush=True)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit GeekHaven card-number detection via title + image hash fallback."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max number of GeekHaven products to test.",
    )
    args = parser.parse_args()
    return audit_geekhaven_image_number_detection(limit=args.limit)


if __name__ == "__main__":
    raise SystemExit(main())

