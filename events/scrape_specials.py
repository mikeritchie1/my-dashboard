from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path


NOTION_VERSION = "2022-06-28"
PAGE_URL = "https://www.notion.so/Specials-082fa9625a9f4f949d03a8d1517c76f8"
PAGE_ID = "082fa9625a9f4f949d03a8d1517c76f8"
REPO_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path(__file__).resolve().parent / "data"
OUTPUT_FILE = DATA_DIR / "specials.json"
LOCAL_SECRETS_FILE = REPO_DIR / "secrets.env"

TEXT_BLOCK_TYPES = {
    "paragraph",
    "heading_1",
    "heading_2",
    "heading_3",
    "bulleted_list_item",
    "numbered_list_item",
    "to_do",
    "quote",
    "callout",
    "toggle",
}

DAY_ORDER = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

SECTION_TITLES = {
    "Everyday",
    "Monday to Thursday",
    "Location",
    "Locations",
    *DAY_ORDER,
}


def local_secret(name: str) -> str:
    if not LOCAL_SECRETS_FILE.exists():
        return ""

    for line in LOCAL_SECRETS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == name:
            return value.strip().strip('"').strip("'")
    return ""


def secret(name: str) -> str:
    return os.environ.get(name, "").strip() or local_secret(name)


def rich_text_plain(rich_text: list[dict], include_strikethrough: bool = False) -> str:
    parts: list[str] = []
    for part in rich_text:
        annotations = part.get("annotations") or {}
        if annotations.get("strikethrough") and not include_strikethrough:
            continue
        parts.append(part.get("plain_text", ""))
    return "".join(parts).strip()


def notion_request(path: str, token: str) -> dict:
    request = urllib.request.Request(
        f"https://api.notion.com/v1/{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def page_title(page: dict) -> str:
    for property_value in page.get("properties", {}).values():
        if property_value.get("type") == "title":
            return rich_text_plain(property_value.get("title", []))
    return "Specials"


def block_text(block: dict) -> str:
    block_type = block.get("type", "")
    if block_type not in TEXT_BLOCK_TYPES:
        return ""
    value = block.get(block_type, {})
    text = rich_text_plain(value.get("rich_text", []))
    if block_type == "to_do":
        checked = "x" if value.get("checked") else " "
        return f"[{checked}] {text}" if text else ""
    return text


def get_block_children(block_id: str, token: str) -> list[dict]:
    blocks: list[dict] = []
    cursor = ""
    while True:
        query = f"?page_size=100&start_cursor={cursor}" if cursor else "?page_size=100"
        payload = notion_request(f"blocks/{block_id}/children{query}", token)
        blocks.extend(payload.get("results", []))
        if not payload.get("has_more"):
            return blocks
        cursor = payload.get("next_cursor") or ""


def plain_text_from_block(block: dict) -> str:
    block_type = block.get("type", "")
    if block_type not in TEXT_BLOCK_TYPES:
        return ""
    return rich_text_plain((block.get(block_type, {}) or {}).get("rich_text", []))


def item_from_text(text: str, default_venue: str = "") -> dict[str, str]:
    urls = re.findall(r"https?://\S+", text)
    url = urls[0].rstrip(").,") if urls else ""
    parts = re.split(r"\s+[-–]\s+", text, maxsplit=1)
    if len(parts) == 2:
        venue = parts[0].strip()
        deal = parts[1].strip()
    else:
        venue = default_venue or text
        deal = text

    if venue.endswith(":"):
        venue = venue[:-1].strip()
    return {
        "venue": venue,
        "title": venue,
        "deal": deal,
        "description": f"{venue} - {deal}" if default_venue and venue == default_venue else text,
        "url": url,
    }


def normalized_section_title(text: str) -> str:
    cleaned = text.strip().strip("*").strip()
    cleaned = cleaned.rstrip(":").strip()
    for title in SECTION_TITLES:
        if cleaned.lower() == title.lower():
            return title
    return ""


def days_for_group(title: str) -> list[str]:
    if title == "Everyday":
        return DAY_ORDER[:]
    if title == "Monday to Thursday":
        return DAY_ORDER[:4]
    if title in DAY_ORDER:
        return [title]
    return []


def parse_location(text: str) -> dict | None:
    match = re.match(
        r"^\s*(?P<venue>[^:]+):\s*(?P<lat>-?\d+(?:\.\d+)?)\s*,\s*(?P<lng>-?\d+(?:\.\d+)?)(?:\s*\|\s*(?P<url>https?://\S+))?",
        text,
    )
    if not match:
        return None
    return {
        "venue": match.group("venue").strip(),
        "lat": float(match.group("lat")),
        "lng": float(match.group("lng")),
        "url": (match.group("url") or "").strip(),
    }


def specials_from_blocks(blocks: list[dict]) -> list[dict]:
    groups: list[dict] = []
    current_group: dict | None = None
    current_venue = ""

    for block in blocks:
        text = plain_text_from_block(block)
        block_type = block.get("type", "")
        if not text:
            continue

        section_title = normalized_section_title(text)
        if block_type in {"heading_1", "heading_2", "heading_3"} or section_title:
            current_group = {
                "title": section_title or text,
                "days": days_for_group(section_title or text),
                "items": [],
            }
            current_venue = ""
            groups.append(current_group)
            continue

        if block_type in {"paragraph", "quote", "callout"} and re.search(r"https?://", text):
            if current_group is None:
                current_group = {"title": "General", "days": [], "items": []}
                groups.append(current_group)
            current_group["items"].append(item_from_text(text, current_venue))
            continue

        if block_type in {"bulleted_list_item", "numbered_list_item", "to_do", "paragraph"}:
            if current_group is None:
                current_group = {"title": "General", "days": [], "items": []}
                groups.append(current_group)
            if text.endswith(":"):
                current_venue = text[:-1].strip()
                continue
            current_group["items"].append(item_from_text(text, current_venue))

    return [group for group in groups if group["items"]]


def split_specials_and_locations(groups: list[dict]) -> tuple[list[dict], dict[str, dict]]:
    locations: dict[str, dict] = {}
    special_groups: list[dict] = []

    for group in groups:
        if group["title"] in {"Location", "Locations"}:
            for item in group["items"]:
                location = parse_location(item["description"])
                if location:
                    locations[location["venue"]] = location
            continue
        special_groups.append(group)

    return special_groups, locations


def write_payload(payload: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def scrape_specials() -> dict:
    token = secret("NOTION_TOKEN") or secret("NOTION_API_TOKEN")
    if not token:
        return {
            "source": PAGE_URL,
            "title": "Specials",
            "error": "Missing NOTION_TOKEN",
            "groups": [],
        }

    try:
        page = notion_request(f"pages/{PAGE_ID}", token)
        blocks = get_block_children(PAGE_ID, token)
        groups, locations = split_specials_and_locations(specials_from_blocks(blocks))
        return {
            "source": PAGE_URL,
            "title": page_title(page),
            "locations": locations,
            "groups": groups,
        }
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        return {
            "source": PAGE_URL,
            "title": "Specials",
            "error": f"Notion API error {error.code}: {detail}",
            "groups": [],
        }


def main() -> int:
    payload = scrape_specials()
    write_payload(payload)
    print(f"Wrote {len(payload.get('groups', []))} special group(s) to {OUTPUT_FILE}")
    if payload.get("error"):
        print(payload["error"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
