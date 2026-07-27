import csv
import re
from datetime import datetime
from io import StringIO
from pathlib import Path

import pandas as pd

TAIL_COLUMNS = [
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

FULL_COPY_PATTERN = re.compile(
    r"^(.+?)\s*,\s*([\d.,]+)\s+OMR\s*,\s*(https://\S+?)\s*,\s*(https://\S+?)\s*,\s*(.*)$"
)


def _strip_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(col).strip() for col in df.columns]
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace({"nan": None, "None": None, "": None})
    return df


def _parse_full_copy_line(line: str) -> dict | None:
    match = FULL_COPY_PATTERN.match(line.strip())
    if not match:
        return None

    name, price, url, image, tail = match.groups()
    tail_fields = next(csv.reader(StringIO(tail)), [])

    if len(tail_fields) < len(TAIL_COLUMNS):
        tail_fields.extend([""] * (len(TAIL_COLUMNS) - len(tail_fields)))
    elif len(tail_fields) > len(TAIL_COLUMNS):
        overflow = tail_fields[len(TAIL_COLUMNS) - 1 :]
        tail_fields = tail_fields[: len(TAIL_COLUMNS) - 1] + [", ".join(overflow)]

    row = {
        "Name": name.strip(),
        "Price": f"{price.strip()} OMR",
        "URL": url.strip(),
        "Image": image.strip(),
    }
    row.update(dict(zip(TAIL_COLUMNS, tail_fields)))
    return row


def _load_full_copy_csv(path: Path) -> pd.DataFrame:
    rows: list[dict] = []
    with path.open(encoding="utf-8", errors="replace") as handle:
        next(handle, None)
        for line in handle:
            parsed = _parse_full_copy_line(line)
            if parsed:
                rows.append(parsed)
    return pd.DataFrame(rows)


def _load_slim_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, engine="python", on_bad_lines="warn")
    return _strip_columns(df)


def _load_generic_csv(path: Path) -> pd.DataFrame:
    try:
        df = pd.read_csv(path, engine="python", on_bad_lines="warn")
        if len(df.columns) >= 10:
            return _strip_columns(df)
    except Exception:
        pass

    try:
        return _load_full_copy_csv(path)
    except Exception:
        return pd.DataFrame()


def _scraped_at_from_path(path: Path) -> datetime:
    match = re.search(r"listings_(\d{8})", path.name)
    if match:
        return datetime.strptime(match.group(1), "%Y%m%d")
    # Use file date (not time) so batches group cleanly by day.
    return datetime.fromtimestamp(path.stat().st_mtime).replace(hour=0, minute=0, second=0, microsecond=0)


def find_raw_files(raw_dir: Path) -> list[Path]:
    if not raw_dir.exists():
        return []
    return sorted(raw_dir.glob("*.csv"), key=lambda path: path.stat().st_mtime, reverse=True)


def load_raw_listings(raw_dir: Path | str) -> pd.DataFrame:
    raw_path = Path(raw_dir)
    files = find_raw_files(raw_path)
    if not files:
        raise FileNotFoundError(f"No CSV files found in {raw_path}")

    frames: list[pd.DataFrame] = []
    for file_path in files:
        if "copy" in file_path.name.lower() or "oldraw" in file_path.name.lower():
            frame = _load_full_copy_csv(file_path)
        else:
            frame = _load_generic_csv(file_path)

        if frame.empty:
            continue

        frame = _strip_columns(frame)
        frame["source_file"] = file_path.name
        frame["scraped_at"] = _scraped_at_from_path(file_path)
        frames.append(frame)

    if not frames:
        raise ValueError("Unable to parse any raw listing files")

    combined = pd.concat(frames, ignore_index=True)
    combined["flag_duplicate"] = False

    with_url = combined[combined["URL"].notna() & (combined["URL"] != "")]
    without_url = combined[combined["URL"].isna() | (combined["URL"] == "")]

    if not with_url.empty:
        duplicate_mask = with_url.duplicated(subset=["URL"], keep="last")
        with_url = with_url.copy()
        with_url.loc[duplicate_mask, "flag_duplicate"] = True
        with_url = with_url.sort_values("scraped_at").drop_duplicates(subset=["URL"], keep="last")

    if not without_url.empty:
        dedupe_cols = ["Name", "Price", "Car Make", "Model", "Year", "City"]
        available_cols = [col for col in dedupe_cols if col in without_url.columns]
        if not with_url.empty and available_cols:
            match_keys = with_url[available_cols].drop_duplicates()
            without_url = without_url.merge(match_keys, on=available_cols, how="left", indicator=True)
            without_url = without_url[without_url["_merge"] == "left_only"].drop(columns="_merge")

        duplicate_mask = without_url.duplicated(subset=available_cols, keep="last")
        without_url = without_url.copy()
        without_url.loc[duplicate_mask, "flag_duplicate"] = True
        without_url = without_url.sort_values("scraped_at").drop_duplicates(subset=available_cols, keep="last")

    combined = pd.concat([with_url, without_url], ignore_index=True)

    combined = combined.reset_index(drop=True)
    return combined
