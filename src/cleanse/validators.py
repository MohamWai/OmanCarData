from datetime import datetime

import pandas as pd


def _price_outliers(df: pd.DataFrame) -> pd.Series:
    flags = pd.Series(False, index=df.index)
    grouped = df.dropna(subset=["make", "model", "price_omr"]).groupby(["make", "model"])

    for _, group in grouped:
        prices = group["price_omr"]
        if len(prices) < 4:
            continue
        q1 = prices.quantile(0.25)
        q3 = prices.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        flags.loc[group.index] = (prices < lower) | (prices > upper)

    return flags


def add_anomaly_flags(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    current_year = datetime.now().year

    result["flag_missing_core"] = (
        result["make"].isna() | result["model"].isna() | result["price_omr"].isna()
    )
    result["flag_year_invalid"] = result["year"].notna() & ~result["year"].between(1990, current_year + 1)
    result["flag_km_suspicious"] = (
        (result["condition"] == "New")
        & result["km_mid"].notna()
        & (result["km_mid"] > 1000)
    ) | (
        result["km_mid"].notna()
        & (result["km_mid"] > 400000)
    )
    result["flag_price_outlier"] = _price_outliers(result)

    if "flag_duplicate" not in result.columns:
        result["flag_duplicate"] = False

    result["has_anomaly"] = (
        result["flag_missing_core"]
        | result["flag_year_invalid"]
        | result["flag_km_suspicious"]
        | result["flag_price_outlier"]
        | result["flag_duplicate"]
    )

    return result
