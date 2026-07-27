import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROCESSED_COLUMNS = [
    "name",
    "url",
    "image",
    "price_omr",
    "condition",
    "make",
    "model",
    "trim",
    "year",
    "year_valid",
    "km_min",
    "km_max",
    "km_mid",
    "engine_cc_min",
    "engine_cc_max",
    "body_type",
    "seats",
    "fuel",
    "transmission",
    "exterior_color",
    "interior_color",
    "regional_specs",
    "car_license",
    "insurance",
    "body_condition",
    "paint",
    "payment_method",
    "city",
    "neighborhood",
    "category",
    "subcategory",
    "source_file",
    "scraped_at",
    "flag_missing_core",
    "flag_year_invalid",
    "flag_km_suspicious",
    "flag_price_outlier",
    "flag_duplicate",
    "has_anomaly",
]


def build_metadata(df: pd.DataFrame, source_files: list[str]) -> dict:
    flag_columns = [
        "flag_missing_core",
        "flag_year_invalid",
        "flag_km_suspicious",
        "flag_price_outlier",
        "flag_duplicate",
    ]
    anomaly_summary = {column: int(df[column].sum()) for column in flag_columns if column in df.columns}

    return {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "row_count": int(len(df)),
        "source_files": source_files,
        "anomaly_summary": anomaly_summary,
        "price_median_omr": float(df["price_omr"].median()) if df["price_omr"].notna().any() else None,
        "makes_count": int(df["make"].nunique(dropna=True)),
        "cities_count": int(df["city"].nunique(dropna=True)),
    }


def save_processed(df: pd.DataFrame, processed_dir: Path | str, source_files: list[str]) -> tuple[Path, Path]:
    output_dir = Path(processed_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    columns = [column for column in PROCESSED_COLUMNS if column in df.columns]
    cleaned = df[columns].copy()

    parquet_path = output_dir / "listings.parquet"
    metadata_path = output_dir / "metadata.json"

    cleaned.to_parquet(parquet_path, index=False)
    metadata_path.write_text(json.dumps(build_metadata(cleaned, source_files), indent=2), encoding="utf-8")

    return parquet_path, metadata_path


def load_processed(processed_dir: Path | str) -> tuple[pd.DataFrame, dict]:
    base = Path(processed_dir)
    parquet_path = base / "listings.parquet"
    metadata_path = base / "metadata.json"

    if not parquet_path.exists():
        raise FileNotFoundError(f"Processed data not found at {parquet_path}")

    df = pd.read_parquet(parquet_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    return df, metadata
