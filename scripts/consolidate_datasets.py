#!/usr/bin/env python3
"""Merge all raw CSVs, deduplicate by URL, write one combined file, rebuild Parquet."""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from src.cleanse import add_anomaly_flags, load_raw_listings, normalize_listings
from src.scraper.opensooq import FIELDNAMES
from src.storage import save_processed


def _count_raw_rows(raw_dir: Path) -> int:
    total = 0
    for path in raw_dir.glob("*.csv"):
        with path.open(encoding="utf-8", errors="replace") as handle:
            total += max(sum(1 for _ in handle) - 1, 0)
    return total


def consolidate(raw_dir: Path, processed_dir: Path, combined_name: str) -> None:
    archive_dir = raw_dir / "archive"
    archive_dir.mkdir(exist_ok=True)

    raw_before = _count_raw_rows(raw_dir)
    combined_df = load_raw_listings(raw_dir)
    raw_after = len(combined_df)

    export_cols = [col for col in FIELDNAMES if col in combined_df.columns]
    combined_path = raw_dir / combined_name
    combined_df[export_cols].to_csv(combined_path, index=False)

    archived: list[str] = []
    for path in sorted(raw_dir.glob("*.csv")):
        if path.name == combined_name:
            continue
        destination = archive_dir / path.name
        if destination.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            destination = archive_dir / f"{path.stem}_{stamp}{path.suffix}"
        shutil.move(str(path), str(destination))
        archived.append(destination.name)

    normalized = normalize_listings(combined_df)
    flagged = add_anomaly_flags(normalized)
    save_processed(flagged, processed_dir, source_files=[combined_name])

    print(f"Raw rows before dedup: {raw_before:,}")
    print(f"Unique listings after dedup: {raw_after:,}")
    print(f"Duplicates removed: {raw_before - raw_after:,}")
    print(f"Combined CSV: {combined_path}")
    if archived:
        print(f"Archived {len(archived)} file(s) to {archive_dir}/")
        for name in archived:
            print(f"  - {name}")
    print(f"Processed Parquet updated in {processed_dir}/")


def main() -> None:
    parser = argparse.ArgumentParser(description="Combine raw CSVs and deduplicate listings")
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument("--processed-dir", type=Path, default=ROOT / "data" / "processed")
    parser.add_argument(
        "--combined-name",
        default="listings_combined.csv",
        help="Output filename in data/raw/",
    )
    args = parser.parse_args()

    try:
        consolidate(args.raw_dir, args.processed_dir, args.combined_name)
    except Exception as exc:
        print(f"Consolidate failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
