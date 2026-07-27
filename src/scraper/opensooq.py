import argparse
import csv
import json
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://om.opensooq.com/en/cars/cars-for-sale"
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
    "User-Agent": "Mozilla/5.0 (compatible; OpenSooqCarPipeline/1.0)",
}


def _request(url: str, retries: int = 3, delay: float = 2.0) -> requests.Response:
    last_error = None
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(delay * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url}: {last_error}")


def _load_existing_urls(raw_dir: Path) -> set[str]:
    urls: set[str] = set()
    for file_path in sorted(raw_dir.glob("*.csv")):
        try:
            with file_path.open(encoding="utf-8", errors="replace") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    url = (row.get("URL") or "").strip()
                    if url:
                        urls.add(url)
        except Exception:
            continue
    return urls


def _extract_details(listing_url: str) -> dict[str, str]:
    response = _request(listing_url)
    soup = BeautifulSoup(response.text, "html.parser")
    section = soup.find("section", {"id": "PostViewInformation"})
    if not section:
        return {}

    details: dict[str, str] = {}
    for item in section.find_all("li"):
        label_tag = item.find("p")
        value_tag = item.find("a")
        label = label_tag.get_text(strip=True) if label_tag else "Unknown"
        value = value_tag.get_text(strip=True) if value_tag else "Not available"
        details[label] = value
    return details


def scrape_page(page_number: int, writer: csv.DictWriter, seen_urls: set[str]) -> bool:
    print(f"Scraping page {page_number}...")
    url = f"{BASE_URL}?search=true&page={page_number}"
    response = _request(url)
    soup = BeautifulSoup(response.text, "html.parser")
    scripts = soup.find_all("script", type="application/ld+json")

    if not scripts:
        print(f"No listings found on page {page_number}")
        return False

    found_items = False
    for script in scripts:
        try:
            payload = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue

        if payload.get("@type") != "ItemList":
            continue

        for item in payload.get("itemListElement", []):
            listing_url = item.get("url", "").strip()
            if not listing_url or listing_url in seen_urls:
                continue

            found_items = True
            seen_urls.add(listing_url)
            details = _extract_details(listing_url)
            row = {
                "Name": item.get("name", ""),
                "Price": f"{item['offers']['price']} {item['offers']['priceCurrency']}",
                "URL": listing_url,
                "Image": item.get("image", ""),
                **details,
            }
            writer.writerow(row)
            print(f"Saved listing: {row['Name'][:60]}")

    return found_items


def run_scraper(raw_dir: Path | str, max_pages: int | None = None) -> Path:
    raw_path = Path(raw_dir)
    raw_path.mkdir(parents=True, exist_ok=True)
    output_path = raw_path / f"listings_{datetime.now().strftime('%Y%m%d')}.csv"
    seen_urls = _load_existing_urls(raw_path)

    file_exists = output_path.exists()
    with output_path.open("a" if file_exists else "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, quoting=csv.QUOTE_MINIMAL)
        if not file_exists:
            writer.writeheader()

        page_number = 1
        while True:
            has_items = scrape_page(page_number, writer, seen_urls)
            if not has_items:
                break
            if max_pages is not None and page_number >= max_pages:
                break
            page_number += 1
            time.sleep(2)

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape OpenSooq Oman car listings")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--max-pages", type=int, default=None)
    args = parser.parse_args()
    output = run_scraper(raw_dir=args.raw_dir, max_pages=args.max_pages)
    print(f"Wrote listings to {output}")


if __name__ == "__main__":
    main()
