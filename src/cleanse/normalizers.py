import re
from datetime import datetime

import pandas as pd

MISSING_VALUES = {"", "not available", "other", "none", "nan", "null"}


def _nullify(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if text.lower() in MISSING_VALUES:
        return None
    return text


def parse_price(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    match = re.search(r"([\d,]+(?:\.\d+)?)", str(value).replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def parse_numeric_range(value) -> tuple[float | None, float | None]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None, None

    text = str(value).strip().replace(",", "")
    if text in {"0", "0.0"}:
        return 0.0, 0.0

    plus_match = re.match(r"^\+\s*([\d.]+)$", text)
    if plus_match:
        lower = float(plus_match.group(1))
        return lower, None

    range_match = re.match(r"^([\d.]+)\s*-\s*([\d.]+)", text)
    if range_match:
        return float(range_match.group(1)), float(range_match.group(2))

    single_match = re.match(r"^([\d.]+)", text)
    if single_match:
        number = float(single_match.group(1))
        return number, number

    return None, None


def parse_year(value) -> int | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    match = re.search(r"(19|20)\d{2}", str(value))
    if not match:
        return None
    return int(match.group(0))


def normalize_condition(value) -> str | None:
    text = _nullify(value)
    if not text:
        return None
    lowered = text.lower()
    if "new" in lowered:
        return "New"
    if "used" in lowered:
        return "Used"
    return text.title()


def normalize_listings(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()

    result["name"] = result.get("Name", pd.Series(dtype=object)).map(_nullify)
    result["url"] = result.get("URL", pd.Series(dtype=object)).map(_nullify)
    result["image"] = result.get("Image", pd.Series(dtype=object)).map(_nullify)
    result["condition"] = result.get("Condition", pd.Series(dtype=object)).map(normalize_condition)
    result["make"] = result.get("Car Make", pd.Series(dtype=object)).map(_nullify)
    result["model"] = result.get("Model", pd.Series(dtype=object)).map(_nullify)
    result["trim"] = result.get("Trim", pd.Series(dtype=object)).map(_nullify)
    result["body_type"] = result.get("Body Type", pd.Series(dtype=object)).map(_nullify)
    result["fuel"] = result.get("Fuel", pd.Series(dtype=object)).map(_nullify)
    result["transmission"] = result.get("Transmission", pd.Series(dtype=object)).map(_nullify)
    result["exterior_color"] = result.get("Exterior Color", pd.Series(dtype=object)).map(_nullify)
    result["interior_color"] = result.get("Interior Color", pd.Series(dtype=object)).map(_nullify)
    result["regional_specs"] = result.get("Regional Specs", pd.Series(dtype=object)).map(_nullify)
    result["car_license"] = result.get("Car License", pd.Series(dtype=object)).map(_nullify)
    result["insurance"] = result.get("Insurance", pd.Series(dtype=object)).map(_nullify)
    result["body_condition"] = result.get("Body Condition", pd.Series(dtype=object)).map(_nullify)
    result["paint"] = result.get("Paint", pd.Series(dtype=object)).map(_nullify)
    result["payment_method"] = result.get("Payment Method", pd.Series(dtype=object)).map(_nullify)
    result["city"] = result.get("City", pd.Series(dtype=object)).map(_nullify)
    result["neighborhood"] = result.get("Neighborhood", pd.Series(dtype=object)).map(_nullify)
    result["category"] = result.get("Category", pd.Series(dtype=object)).map(_nullify)
    result["subcategory"] = result.get("Subcategory", pd.Series(dtype=object)).map(_nullify)

    result["price_omr"] = result.get("Price", pd.Series(dtype=object)).map(parse_price)
    result["year"] = result.get("Year", pd.Series(dtype=object)).map(parse_year)

    km_bounds = result.get("Kilometers", pd.Series(dtype=object)).map(parse_numeric_range)
    result["km_min"] = km_bounds.map(lambda pair: pair[0])
    result["km_max"] = km_bounds.map(lambda pair: pair[1])
    result["km_mid"] = result.apply(
        lambda row: (
            (row["km_min"] + row["km_max"]) / 2
            if pd.notna(row["km_min"]) and pd.notna(row["km_max"])
            else row["km_min"] if pd.notna(row["km_min"]) else row["km_max"]
        ),
        axis=1,
    )

    engine_bounds = result.get("Engine Size (cc)", pd.Series(dtype=object)).map(parse_numeric_range)
    result["engine_cc_min"] = engine_bounds.map(lambda pair: pair[0])
    result["engine_cc_max"] = engine_bounds.map(lambda pair: pair[1])

    current_year = datetime.now().year
    result["year_valid"] = result["year"].between(1990, current_year + 1)

    seats = result.get("Number of Seats", pd.Series(dtype=object))
    result["seats"] = pd.to_numeric(seats, errors="coerce")

    if "scraped_at" in result.columns:
        result["scraped_at"] = pd.to_datetime(result["scraped_at"], errors="coerce")
    else:
        result["scraped_at"] = pd.Timestamp.utcnow()

    return result
