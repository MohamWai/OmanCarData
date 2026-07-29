"""Quantile- and hedonic-residual-based market position labeling."""

from __future__ import annotations

import numpy as np
import pandas as pd

MIN_GROUP_SIZE = 5
RELIABLE_GROUP_SIZE = 10
HEDONIC_MIN_N = 20


def _confidence_tier(n: int, unreliable: bool) -> str:
    if unreliable or n < MIN_GROUP_SIZE:
        return "Unreliable"
    if n >= RELIABLE_GROUP_SIZE * 2:
        return "High"
    if n >= RELIABLE_GROUP_SIZE:
        return "Moderate"
    return "Low"


def _confidence_note(n: int, confidence: str, method: str) -> str:
    method_label = "hedonic peer comparison" if method == "hedonic_residual" else "make/model price quantiles"
    if confidence == "Unreliable":
        return f"Unreliable comparison (n={int(n)})"
    return f"Based on {int(n)} comparable listings ({confidence.lower()} confidence, {method_label})"


def _fit_hedonic_residuals(group: pd.DataFrame) -> tuple[pd.Series, float | None, float | None]:
    """Fit log(price) ~ year + km_mid; return residuals and residual Q1/Q3."""
    model_df = group.dropna(subset=["price_omr", "year", "km_mid"]).copy()
    model_df = model_df[(model_df["price_omr"] > 0) & (model_df["year"].notna())]

    empty = pd.Series(np.nan, index=group.index, dtype=float)
    if len(model_df) < HEDONIC_MIN_N or model_df["year"].nunique() < 2:
        return empty, None, None

    y = np.log(model_df["price_omr"].to_numpy(dtype=float))
    year = model_df["year"].to_numpy(dtype=float)
    km = model_df["km_mid"].to_numpy(dtype=float)
    design = np.column_stack([np.ones(len(model_df)), year, km])

    try:
        coeffs, _, _, _ = np.linalg.lstsq(design, y, rcond=None)
    except np.linalg.LinAlgError:
        return empty, None, None

    predict_mask = group["price_omr"].notna() & (group["price_omr"] > 0) & group["year"].notna() & group["km_mid"].notna()
    predict_df = group.loc[predict_mask]
    if predict_df.empty:
        return empty, None, None

    pred_log = (
        coeffs[0]
        + coeffs[1] * predict_df["year"].to_numpy(dtype=float)
        + coeffs[2] * predict_df["km_mid"].to_numpy(dtype=float)
    )
    expected = np.exp(pred_log)
    actual = predict_df["price_omr"].to_numpy(dtype=float)
    residuals = actual - expected

    residual_series = pd.Series(np.nan, index=group.index, dtype=float)
    residual_series.loc[predict_df.index] = residuals

    if len(residuals) < MIN_GROUP_SIZE:
        return residual_series, None, None

    residual_q1 = float(np.quantile(residuals, 0.25))
    residual_q3 = float(np.quantile(residuals, 0.75))
    if residual_q3 - residual_q1 == 0:
        return residual_series, None, None

    return residual_series, residual_q1, residual_q3


def _classify_row(row: pd.Series) -> tuple[str, str, str, str, bool]:
    n = row.get("group_size")
    if pd.isna(n) or n < MIN_GROUP_SIZE:
        n_display = 0 if pd.isna(n) else int(n)
        return (
            "Unknown",
            "none",
            "Unreliable",
            f"Insufficient comparables (n={n_display})",
            True,
        )

    n = int(n)
    price = row["price_omr"]
    iqr = row.get("market_iqr")
    residual = row.get("price_residual")
    residual_q1 = row.get("residual_q1")
    residual_q3 = row.get("residual_q3")
    residual_iqr = row.get("residual_iqr")

    use_hedonic = (
        pd.notna(residual)
        and pd.notna(residual_q1)
        and pd.notna(residual_q3)
        and pd.notna(residual_iqr)
        and residual_iqr > 0
    )

    if use_hedonic:
        method = "hedonic_residual"
        if residual < residual_q1:
            position = "Below Market"
        elif residual > residual_q3:
            position = "Above Market"
        else:
            position = "Fair Price"
    else:
        method = "quantile"
        if pd.isna(iqr) or iqr == 0:
            return (
                "Unknown",
                "none",
                "Unreliable",
                f"No price spread among {n} peers (IQR = 0)",
                True,
            )
        q1 = row["market_q1"]
        q3 = row["market_q3"]
        if price < q1:
            position = "Below Market"
        elif price > q3:
            position = "Above Market"
        else:
            position = "Fair Price"

    confidence = _confidence_tier(n, unreliable=False)
    note = _confidence_note(n, confidence, method)
    if method == "quantile" and n < HEDONIC_MIN_N:
        note += "; year/km model not used (small peer group)"

    return position, method, confidence, note, False


def enrich_market_position(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    valid = result["make"].notna() & result["model"].notna() & result["price_omr"].notna()

    for col in (
        "market_q1",
        "market_median",
        "market_q3",
        "market_iqr",
        "group_size",
        "price_vs_market_pct",
        "expected_price_omr",
        "price_residual",
        "price_vs_expected_pct",
        "residual_q1",
        "residual_q3",
        "residual_iqr",
        "market_method",
        "market_confidence",
        "market_position_note",
        "market_unreliable",
        "market_position",
    ):
        if col not in result.columns:
            result[col] = pd.NA

    if not valid.any():
        result["market_position"] = "Unknown"
        result["market_confidence"] = "Unreliable"
        result["market_position_note"] = "Missing make, model, or price"
        result["market_unreliable"] = True
        return result

    grouped = result.loc[valid].groupby(["make", "model"])["price_omr"]
    result.loc[valid, "market_q1"] = grouped.transform(lambda s: s.quantile(0.25))
    result.loc[valid, "market_median"] = grouped.transform("median")
    result.loc[valid, "market_q3"] = grouped.transform(lambda s: s.quantile(0.75))
    result.loc[valid, "group_size"] = grouped.transform("size")
    result.loc[valid, "market_iqr"] = result.loc[valid, "market_q3"] - result.loc[valid, "market_q1"]

    result.loc[valid, "price_vs_market_pct"] = (
        (result.loc[valid, "price_omr"] - result.loc[valid, "market_median"])
        / result.loc[valid, "market_median"]
        * 100
    )

    for (make, model), group in result.loc[valid].groupby(["make", "model"]):
        residuals, rq1, rq3 = _fit_hedonic_residuals(group)
        if not residuals.notna().any():
            continue

        idx = group.index
        result.loc[idx, "price_residual"] = residuals
        expected = group["price_omr"] - residuals
        result.loc[idx, "expected_price_omr"] = expected.where(residuals.notna())
        result.loc[idx, "price_vs_expected_pct"] = (
            (result.loc[idx, "price_residual"] / result.loc[idx, "expected_price_omr"]) * 100
        ).where(residuals.notna())

        if rq1 is not None and rq3 is not None:
            result.loc[idx, "residual_q1"] = rq1
            result.loc[idx, "residual_q3"] = rq3
            result.loc[idx, "residual_iqr"] = rq3 - rq1

    classified = result.loc[valid].apply(_classify_row, axis=1, result_type="expand")
    classified.columns = [
        "market_position",
        "market_method",
        "market_confidence",
        "market_position_note",
        "market_unreliable",
    ]
    for col in classified.columns:
        result.loc[valid, col] = classified[col].values

    missing = ~valid
    result.loc[missing, "market_position"] = "Unknown"
    result.loc[missing, "market_unreliable"] = True
    result.loc[missing, "market_confidence"] = "Unreliable"
    result.loc[missing, "market_position_note"] = "Missing make, model, or price"

    return result
