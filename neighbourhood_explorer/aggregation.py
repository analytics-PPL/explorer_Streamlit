from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd


SUPPORTED_AGGREGATION_METHODS = {
    "sum_counts",
    "recompute_rate_from_numerator_denominator",
    "recompute_share_from_category_counts",
    "weighted_mean",
    "population_weighted_mean",
    "area_weighted_mean",
    "non_additive_display_only",
}


def _to_numeric_series(values: Iterable[object]) -> pd.Series:
    return pd.to_numeric(pd.Series(list(values)), errors="coerce")


def aggregate_records(df: pd.DataFrame, method: str) -> dict[str, float | int | str | None]:
    if method not in SUPPORTED_AGGREGATION_METHODS:
        raise ValueError(f"Unsupported aggregation method: {method}")

    if df.empty:
        return {"value": np.nan, "numerator": np.nan, "denominator": np.nan, "record_count": 0}

    values = _to_numeric_series(df.get("value", []))
    numerators = _to_numeric_series(df.get("numerator", []))
    denominators = _to_numeric_series(df.get("denominator", []))

    if method == "sum_counts":
        value = float(values.sum(min_count=1))
        return {"value": value, "numerator": value, "denominator": np.nan, "record_count": int(len(df))}

    if method in {"recompute_rate_from_numerator_denominator", "recompute_share_from_category_counts"}:
        numerator = float(numerators.sum(min_count=1))
        denominator = float(denominators.sum(min_count=1))
        value = numerator / denominator if denominator and not np.isnan(denominator) and denominator != 0 else np.nan
        return {"value": value, "numerator": numerator, "denominator": denominator, "record_count": int(len(df))}

    if method in {"weighted_mean", "population_weighted_mean", "area_weighted_mean"}:
        denominator = float(denominators.sum(min_count=1))
        numerator = float((values * denominators).sum(min_count=1)) if "weighted_value" not in df.columns else float(
            _to_numeric_series(df["weighted_value"]).sum(min_count=1)
        )
        value = numerator / denominator if denominator and not np.isnan(denominator) and denominator != 0 else np.nan
        return {"value": value, "numerator": numerator, "denominator": denominator, "record_count": int(len(df))}

    distribution = values.dropna()
    return {
        "value": distribution.median() if not distribution.empty else np.nan,
        "numerator": np.nan,
        "denominator": np.nan,
        "record_count": int(len(df)),
        "summary_min": float(distribution.min()) if not distribution.empty else np.nan,
        "summary_max": float(distribution.max()) if not distribution.empty else np.nan,
        "summary_median": float(distribution.median()) if not distribution.empty else np.nan,
    }


def aggregate_grouped(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for keys, subset in df.groupby(group_cols, dropna=False, sort=True):
        key_tuple = keys if isinstance(keys, tuple) else (keys,)
        row = dict(zip(group_cols, key_tuple, strict=False))
        metadata_cols = ["indicator_id", "aggregation_method", "benchmark_method", "topic", "unit", "period"]
        for col in metadata_cols:
            if col in subset.columns and col not in row:
                row[col] = subset.iloc[0][col]
        row.update(aggregate_records(subset, str(subset.iloc[0]["aggregation_method"])))
        rows.append(row)
    return pd.DataFrame(rows)
