"""Scrape OpenSooq Oman car listings from __NEXT_DATA__ SERP pages."""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://om.opensooq.com/en/cars/cars-for-sale"
SITE_ORIGIN = "https://om.opensooq.com"
IMAGE_CDN = "https://opensooq-images.os-cdn.com/previews/2048x0"

FIELDNAMES = [
    "Name",
    "Price",
    "URL",
    "Image",
    "Condition",
    "Car Make",
    "Model",
    "Trim",
    "Year",
    "Kilometers",
    "Body Type",
    "Number of Seats",
    "Fuel",
    "Transmission",
    "Engine Size (cc)",
    "Exterior Color",
    "Interior Color",
    "Regional Specs",
    "Car License",
    "Insurance",
    "Body Condition",
    "Paint",
    "Payment Method",
    "City",
    "Neighborhood",
    "Category",
    "Subcategory",
    "Interior Options",
    "Exterior Options",
    "Technology Options",
    "VIN Number",
]

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

YEAR_PATTERN = re.compile(r"^(19|20)\d{2}$")
KM_PATTERN = re.compile(r"[\d,]+\s*km", re.I)
BODY_TYPES = {
    "sedan",
    "suv",
    "pickup",
    "pick up",
    "coupe",
    "hatchback",
    "van",
    "minivan",
    "convertible",
    "wagon",
    "crossover",
}


def _fetch_html(url: str, retries: int = 3, delay: float = 2.0) -> str:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(delay * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url}: {last_error}")


def _parse_serp_page(html: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return [], {}

    payload = json.loads(script.string)
    listings = payload.get("props", {}).get("pageProps", {}).get("serpApiResponse", {}).get("listings", {})
    items = listings.get("items") or []
    meta = listings.get("meta") or {}
    if not isinstance(items, list):
        items = []
    return items, meta


def _clean_token(value: str | None) -> str:
    if not value:
        return ""
    return str(value).strip().strip(",")


def _parse_highlights(highlights: str | None) -> dict[str, str]:
    parts = [_clean_token(p) for p in (highlights or "").split("»")]
    result: dict[str, str] = {}
    if len(parts) >= 4:
        result["Car Make"] = parts[0]
        result["Model"] = parts[1]
        year = parts[2].replace(",", "")
        if YEAR_PATTERN.match(year):
            result["Year"] = year
        condition = parts[3]
        if condition.lower() in {"used", "new"}:
            result["Condition"] = condition.title()
    return result


def _parse_cps(cps: list[str] | None) -> dict[str, str]:
    tokens = [_clean_token(t) for t in (cps or []) if _clean_token(t)]
    result: dict[str, str] = {}

    if not tokens:
        return result

    idx = 0
    if tokens[0].lower() in {"used", "new"}:
        result["Condition"] = tokens[0].title()
        idx = 1

    if idx < len(tokens):
        result["Car Make"] = tokens[idx]
        idx += 1
    if idx < len(tokens):
        result["Model"] = tokens[idx]
        idx += 1
    if idx < len(tokens) and not YEAR_PATTERN.match(tokens[idx].replace(",", "")):
        result["Trim"] = tokens[idx]
        idx += 1
    if idx < len(tokens):
        year = tokens[idx].replace(",", "")
        if YEAR_PATTERN.match(year):
            result["Year"] = year
            idx += 1
    if idx < len(tokens):
        token = tokens[idx]
        if KM_PATTERN.search(token):
            result["Kilometers"] = token.replace("km", "").strip()
            idx += 1
        elif token.lower() in BODY_TYPES or token.upper() in {b.upper() for b in BODY_TYPES}:
            result["Body Type"] = token
            idx += 1

    for token in tokens[idx:]:
        lower = token.lower()
        if KM_PATTERN.search(token) and "Kilometers" not in result:
            result["Kilometers"] = token.replace("km", "").strip()
        elif lower in BODY_TYPES and "Body Type" not in result:
            result["Body Type"] = token

    return result


def _parse_star_cps(star_cps: list[dict[str, Any]] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for entry in star_cps or []:
        label = _clean_token(entry.get("label"))
        icon = (entry.get("icon") or "").lower()
        if not label:
            continue
        if "kilometer" in icon or KM_PATTERN.search(label):
            result["Kilometers"] = label.replace("km", "").strip()
        elif "fuel" in icon:
            result["Fuel"] = label
        elif "regional" in icon or "spec" in icon:
            result["Regional Specs"] = label
        elif "condition" in icon and label.lower() in {"used", "new"}:
            result["Condition"] = label.title()
    return result


def _build_image_url(image_uri: str | None) -> str:
    if not image_uri:
        return ""
    if image_uri.startswith("http"):
        return image_uri
    return f"{IMAGE_CDN}/{image_uri.lstrip('/')}"


def _item_to_row(item: dict[str, Any]) -> dict[str, str]:
    mapped: dict[str, str] = {field: "" for field in FIELDNAMES}

    mapped.update(_parse_highlights(item.get("highlights")))
    for key, value in _parse_cps(item.get("cps")).items():
        if value:
            mapped[key] = value
    for key, value in _parse_star_cps(item.get("starCps")).items():
        if value:
            mapped[key] = value

    mapped["Name"] = _clean_token(item.get("secondary_title")) or _clean_token(item.get("title"))
    mapped["Price"] = _clean_token(item.get("price_amount"))
    post_url = _clean_token(item.get("post_url"))
    if post_url:
        mapped["URL"] = post_url if post_url.startswith("http") else f"{SITE_ORIGIN}/en{post_url}"
    mapped["Image"] = _build_image_url(item.get("image_uri"))
    mapped["City"] = _clean_token(item.get("city_label")) or _clean_token(item.get("city_reporting"))
    mapped["Neighborhood"] = _clean_token(item.get("nhood_label")) or _clean_token(item.get("nhood_reporting"))
    mapped["Category"] = _clean_token(item.get("cat1_label"))
    mapped["Subcategory"] = _clean_token(item.get("cat2_label"))

    km_value = item.get("kilometers_Cars_value_i")
    if km_value is not None and str(km_value).strip():
        mapped["Kilometers"] = str(km_value).strip()

    return mapped


def _load_existing_ids(raw_dir: Path) -> set[str]:
    seen: set[str] = set()
    for file_path in sorted(raw_dir.glob("*.csv")):
        try:
            with file_path.open(encoding="utf-8", errors="replace") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    url = (row.get("URL") or "").strip()
                    if url:
                        match = re.search(r"/search/(\d+)", url)
                        if match:
                            seen.add(match.group(1))
        except Exception:
            continue
    return seen


def scrape_page(page_number: int, seen_ids: set[str]) -> tuple[list[dict[str, str]], dict[str, Any], int]:
    url = f"{BASE_URL}?search=true&page={page_number}"
    print(f"Scraping page {page_number}...")
    html = _fetch_html(url)
    items, meta = _parse_serp_page(html)
    if not items:
        return [], meta, 0

    rows: list[dict[str, str]] = []
    for item in items:
        post_id = str(item.get("id", "")).strip()
        if not post_id or post_id in seen_ids:
            continue
        seen_ids.add(post_id)
        rows.append(_item_to_row(item))

    return rows, meta, len(items)


def run_scraper(raw_dir: Path | str, max_pages: int | None = None, page_delay: float = 2.0) -> Path:
    raw_path = Path(raw_dir)
    raw_path.mkdir(parents=True, exist_ok=True)
    output_path = raw_path / f"listings_{datetime.now().strftime('%Y%m%d')}.csv"
    seen_ids = _load_existing_ids(raw_path)

    file_exists = output_path.exists()
    total_written = 0
    page_number = 1
    total_pages: int | None = None

    with output_path.open("a" if file_exists else "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, quoting=csv.QUOTE_MINIMAL)
        if not file_exists:
            writer.writeheader()

        while True:
            rows, meta, items_on_page = scrape_page(page_number, seen_ids)
            if total_pages is None and meta.get("pages"):
                total_pages = int(meta["pages"])

            if items_on_page == 0:
                print(f"  Page {page_number}: no listings returned — stopping.")
                break

            for row in rows:
                writer.writerow(row)
                total_written += 1

            skipped = items_on_page - len(rows)
            skip_note = f", {skipped} already seen" if skipped else ""
            print(
                f"  Page {page_number}: saved {len(rows)} new listings"
                f" ({items_on_page} on page{skip_note}, total this run: {total_written})"
            )

            if total_pages is not None and page_number >= total_pages:
                break
            if max_pages is not None and page_number >= max_pages:
                break

            page_number += 1
            time.sleep(page_delay)

    if total_written == 0:
        print(f"No new listings to save (all IDs already in {raw_path}).")
    else:
        print(f"Wrote {total_written} listings to {output_path}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape OpenSooq Oman car listings")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--page-delay", type=float, default=2.0)
    args = parser.parse_args()
    output = run_scraper(raw_dir=args.raw_dir, max_pages=args.max_pages, page_delay=args.page_delay)
    print(f"Done: {output}")


if __name__ == "__main__":
    main()
