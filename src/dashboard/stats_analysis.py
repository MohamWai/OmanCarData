"""Inferential statistics helpers for the dashboard methodology page."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def _engine_cc_mid(df: pd.DataFrame) -> pd.Series:
    if "engine_cc_min" in df.columns and "engine_cc_max" in df.columns:
        mid = (df["engine_cc_min"] + df["engine_cc_max"]) / 2
        return mid.where(df["engine_cc_min"].notna() | df["engine_cc_max"].notna())
    return pd.Series(np.nan, index=df.index)


def depreciation_regression(
    df: pd.DataFrame,
    make: str,
    min_n: int = 30,
) -> dict | None:
    """Fit log(price) ~ year for a single make. Returns stats and plot-ready frame."""
    subset = df[
        (df["make"] == make)
        & df["price_omr"].notna()
        & (df["price_omr"] > 0)
        & df["year"].notna()
    ].copy()
    if len(subset) < min_n:
        return None

    subset["log_price"] = np.log(subset["price_omr"])
    slope, intercept, r_value, p_value, std_err = stats.linregress(subset["year"], subset["log_price"])
    annual_pct = (np.exp(slope) - 1) * 100

    years = np.linspace(subset["year"].min(), subset["year"].max(), 50)
    fitted = intercept + slope * years

    return {
        "make": make,
        "n": len(subset),
        "slope": slope,
        "intercept": intercept,
        "r_squared": r_value**2,
        "p_value": p_value,
        "std_err": std_err,
        "annual_pct_change": annual_pct,
        "scatter": subset[["year", "log_price", "price_omr"]],
        "line": pd.DataFrame({"year": years, "log_price_fitted": fitted}),
    }


def group_price_comparison(
    df: pd.DataFrame,
    group_col: str,
    min_group_size: int = 20,
    max_groups: int = 12,
) -> dict | None:
    """One-way ANOVA and Kruskal-Wallis on price across groups."""
    if group_col not in df.columns:
        return None

    priced = df.dropna(subset=["price_omr", group_col])
    if priced.empty:
        return None

    counts = priced[group_col].value_counts()
    keep = counts[counts >= min_group_size].head(max_groups).index.tolist()
    if len(keep) < 2:
        return None

    subset = priced[priced[group_col].isin(keep)]
    samples = [group["price_omr"].values for _, group in subset.groupby(group_col)]

    anova_stat, anova_p = stats.f_oneway(*samples)
    kruskal_stat, kruskal_p = stats.kruskal(*samples)

    summary = (
        subset.groupby(group_col)
        .agg(
            n=("price_omr", "size"),
            median=("price_omr", "median"),
            mean=("price_omr", "mean"),
        )
        .reset_index()
        .sort_values("median", ascending=False)
    )

    return {
        "group_col": group_col,
        "groups": keep,
        "n_total": len(subset),
        "anova_stat": anova_stat,
        "anova_p": anova_p,
        "kruskal_stat": kruskal_stat,
        "kruskal_p": kruskal_p,
        "summary": summary,
    }


def bootstrap_median_ci(
    values: np.ndarray,
    n_bootstrap: int = 2000,
    ci: float = 0.95,
    seed: int = 42,
) -> tuple[float, float, float]:
    """Return (median, ci_low, ci_high) via percentile bootstrap."""
    rng = np.random.default_rng(seed)
    values = values[~np.isnan(values)]
    if len(values) == 0:
        return np.nan, np.nan, np.nan

    observed = float(np.median(values))
    if len(values) < 2:
        return observed, observed, observed

    boot_medians = np.empty(n_bootstrap)
    for i in range(n_bootstrap):
        sample = rng.choice(values, size=len(values), replace=True)
        boot_medians[i] = np.median(sample)

    alpha = (1 - ci) / 2
    low, high = np.quantile(boot_medians, [alpha, 1 - alpha])
    return observed, float(low), float(high)


def bootstrap_median_by_make_model(
    df: pd.DataFrame,
    min_n: int = 25,
    top_n: int = 15,
    n_bootstrap: int = 2000,
) -> pd.DataFrame:
    """Bootstrap 95% CIs for median price by make/model."""
    priced = df.dropna(subset=["make", "model", "price_omr"])
    if priced.empty:
        return pd.DataFrame()

    counts = priced.groupby(["make", "model"]).size().reset_index(name="n")
    eligible = counts[counts["n"] >= min_n].sort_values("n", ascending=False).head(top_n)

    rows: list[dict] = []
    for _, row in eligible.iterrows():
        mask = (priced["make"] == row["make"]) & (priced["model"] == row["model"])
        prices = priced.loc[mask, "price_omr"].to_numpy(dtype=float)
        median, low, high = bootstrap_median_ci(prices, n_bootstrap=n_bootstrap)
        rows.append(
            {
                "make": row["make"],
                "model": row["model"],
                "n": int(row["n"]),
                "median_omr": median,
                "ci_low_omr": low,
                "ci_high_omr": high,
            }
        )

    return pd.DataFrame(rows)


def numeric_correlation_matrix(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pearson and Spearman correlation for key numeric fields."""
    frame = pd.DataFrame(
        {
            "year": df["year"],
            "km_mid": df["km_mid"],
            "engine_cc_mid": _engine_cc_mid(df),
            "price_omr": df["price_omr"],
            "log_price": np.log(df["price_omr"].where(df["price_omr"] > 0)),
        }
    ).dropna()

    if frame.empty or len(frame) < 10:
        return pd.DataFrame(), pd.DataFrame()

    pearson = frame.corr(method="pearson")
    spearman = frame.corr(method="spearman")
    return pearson, spearman


def interpret_p_value(p_value: float, alpha: float = 0.05) -> str:
    if p_value < alpha:
        return f"Statistically significant at α = {alpha} (p = {p_value:.4g})."
    return f"Not statistically significant at α = {alpha} (p = {p_value:.4g})."
