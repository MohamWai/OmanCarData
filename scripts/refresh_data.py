#!/usr/bin/env python3
"""Scrape OpenSooq, cleanse listings, and write processed Parquet for the dashboard."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.cleanse import add_anomaly_flags, load_raw_listings, normalize_listings
from src.scraper.opensooq import run_scraper
from src.storage import save_processed


def refresh(
    raw_dir: Path,
    processed_dir: Path,
    max_pages: int | None,
    skip_scrape: bool,
    page_delay: float,
) -> None:
    scrape_path = None
    if not skip_scrape:
        scrape_path = run_scraper(raw_dir=raw_dir, max_pages=max_pages, page_delay=page_delay)
        print(f"Scrape complete: {scrape_path}")

    raw_df = load_raw_listings(raw_dir)
    if raw_df.empty:
        raise RuntimeError(f"No listings found in {raw_dir}")

    normalized = normalize_listings(raw_df)
    flagged = add_anomaly_flags(normalized)

    source_files = sorted(raw_df["source_file"].dropna().unique().tolist()) if "source_file" in raw_df.columns else []
    parquet_path, metadata_path = save_processed(flagged, processed_dir, source_files=source_files)

    print(f"Processed {len(flagged):,} listings")
    print(f"Parquet: {parquet_path}")
    print(f"Metadata: {metadata_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh OpenSooq data for the dashboard")
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument("--processed-dir", type=Path, default=ROOT / "data" / "processed")
    parser.add_argument("--max-pages", type=int, default=None, help="Limit SERP pages (use 2-5 for dev)")
    parser.add_argument("--page-delay", type=float, default=2.0)
    parser.add_argument(
        "--skip-scrape",
        action="store_true",
        help="Only re-process existing raw CSVs without scraping",
    )
    args = parser.parse_args()

    try:
        refresh(
            raw_dir=args.raw_dir,
            processed_dir=args.processed_dir,
            max_pages=args.max_pages,
            skip_scrape=args.skip_scrape,
            page_delay=args.page_delay,
        )
    except Exception as exc:
        print(f"Refresh failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
