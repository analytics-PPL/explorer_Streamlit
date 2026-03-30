from __future__ import annotations

import re
from typing import Any

import pandas as pd


UNIT_LABELS = {
    "count": "Count",
    "share": "Percent",
    "rate_per_1000": "Rate per 1,000 residents",
    "density_per_sq_km": "Access nodes per sq km",
    "currency_gbp": "Pounds sterling",
    "score": "Score",
    "decile": "Decile",
}

AGGREGATION_LABELS = {
    "sum_counts": "Count added across the selected footprint",
    "recompute_share_from_category_counts": "Percentage rebuilt from summed counts",
    "recompute_rate_from_numerator_denominator": "Rate rebuilt from summed numerators and denominators",
    "weighted_mean": "Weighted average",
    "population_weighted_mean": "Population-weighted average",
    "area_weighted_mean": "Area-weighted average",
    "non_additive_display_only": "Display-only summary",
}

USE_MODE_LABELS = {
    "direct_neighbourhood_candidate": "Direct neighbourhood estimate",
    "neighbourhood_estimate_with_caveats": "Neighbourhood summary with caveats",
    "benchmark_only": "Benchmark context only",
    "hidden_for_now": "Hidden for now",
    "not_recommended": "Not recommended",
}

BENCHMARK_MODE_LABELS = {
    "borough_and_london": "Borough and London comparisons",
    "direct_aggregate": "Directly comparable neighbourhood figure",
    "distribution_summary": "Distribution summary only",
}

VISUAL_LABELS = {
    "benchmark_lollipop": "Comparison chart",
    "benchmark_only_compare": "Benchmark comparison",
    "lollipop_compare": "Neighbourhood comparison",
    "trend_line": "Trend chart",
    "trend_line_with_rolling_average": "Trend chart with rolling average",
    "kpi_card": "Headline summary",
    "stacked_100_bar": "100% stacked bar",
    "grouped_bar": "Grouped bar chart",
    "population_pyramid": "Population pyramid",
    "distribution_band": "Distribution band",
    "ranked_distribution": "London distribution view",
    "ranked_strip": "Ranked strip",
    "sorted_bar": "Sorted bar chart",
    "choropleth_map": "Neighbourhood map",
    "crime_mix_chart": "Crime mix chart",
    "domain_tile_matrix": "Domain summary tiles",
    "table_support_only": "Supporting table",
    "text_badges_or_indexed_note": "Summary note",
}

DIRECTION_HINT_LABELS = {
    "higher_is_better": "Interpret with context",
    "higher_is_worse": "Interpret with context",
    "higher_is_context_dependent": "Interpret with context",
}

COLUMN_LABELS = {
    "indicator_id": "Indicator ID",
    "ui_title": "Indicator",
    "title": "Indicator",
    "top_level_category": "Theme",
    "category_key": "Theme Key",
    "module_label": "Module",
    "source_name": "Source",
    "source_geography": "Source Geography",
    "source_period": "Metric Date",
    "period_type": "Time Pattern",
    "aggregation_policy": "How It Is Combined",
    "aggregation_method": "How It Is Combined",
    "neighbourhood_use_mode": "How It Is Used",
    "primary_visualisation": "Main Chart",
    "secondary_visualisation": "Supporting Chart",
    "indicator_count": "Indicators",
    "sort_order": "Order",
    "label": "Label",
    "description": "Description",
    "neighbourhood_name": "Neighbourhood Name",
    "borough_name": "Place",
    "benchmark_name": "Benchmark",
    "value": "Value",
    "unit": "Unit",
    "last_refresh_date": "Last Updated",
}

ACRONYM_LABELS = {
    "icb": "ICB",
    "imd": "IMD",
    "idaci": "IDACI",
    "idaopi": "IDAOPI",
    "lsoa": "LSOA",
    "msoa": "MSOA",
    "oa": "OA",
    "api": "API",
    "uk": "UK",
}

SYSTEM_NAME_BY_CODE = {
    "NCL": "North Central London",
    "NEL": "North East London",
    "NWL": "North West London",
    "SEL": "South East London",
    "SWL": "South West London",
}


def format_indicator_value(value: float | int | None, unit: str | None) -> str:
    if value is None or pd.isna(value):
        return "No data"
    if unit == "count":
        return f"{int(round(float(value))):,}"
    if unit == "share":
        return f"{float(value) * 100:.1f}%"
    if unit == "rate_per_1000":
        return f"{float(value) * 1000:.1f} per 1,000"
    if unit == "density_per_sq_km":
        return f"{float(value):.2f} per sq km"
    if unit == "currency_gbp":
        return f"£{float(value):,.0f}"
    if unit == "score":
        return f"{float(value):.2f}"
    if unit == "decile":
        return f"{float(value):.1f}"
    return f"{float(value):.2f}"


def scale_value_for_display(value: float | int | None, unit: str | None) -> float | None:
    if value is None or pd.isna(value):
        return None
    raw = float(value)
    if unit == "share":
        return raw * 100.0
    if unit == "rate_per_1000":
        return raw * 1000.0
    return raw


def axis_label_for_unit(unit: str | None) -> str | None:
    if not unit:
        return None
    return UNIT_LABELS.get(str(unit), humanise_label(str(unit)))


def humanise_label(label: Any) -> str:
    if label is None or (isinstance(label, float) and pd.isna(label)):
        return ""
    raw = str(label).strip()
    if not raw:
        return ""
    if raw in COLUMN_LABELS:
        return COLUMN_LABELS[raw]
    pieces = [piece for piece in re.split(r"[_\s]+", raw) if piece]
    converted: list[str] = []
    for piece in pieces:
        lower = piece.lower()
        if lower in ACRONYM_LABELS:
            converted.append(ACRONYM_LABELS[lower])
        else:
            converted.append(piece.capitalize())
    return " ".join(converted)


def humanise_enum(value: Any, *, kind: str | None = None) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    mappings = {
        "aggregation": AGGREGATION_LABELS,
        "use_mode": USE_MODE_LABELS,
        "benchmark_mode": BENCHMARK_MODE_LABELS,
        "visual": VISUAL_LABELS,
        "unit": UNIT_LABELS,
    }
    if kind in mappings and raw in mappings[kind]:
        return mappings[kind][raw]
    if raw in AGGREGATION_LABELS:
        return AGGREGATION_LABELS[raw]
    if raw in USE_MODE_LABELS:
        return USE_MODE_LABELS[raw]
    if raw in BENCHMARK_MODE_LABELS:
        return BENCHMARK_MODE_LABELS[raw]
    if raw in VISUAL_LABELS:
        return VISUAL_LABELS[raw]
    if raw in UNIT_LABELS:
        return UNIT_LABELS[raw]
    return humanise_label(raw)


def humanise_direction_hint(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    return DIRECTION_HINT_LABELS.get(raw, humanise_label(raw))


def format_period_label(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "Not available"
    text = str(value).strip()
    if not text:
        return "Not available"
    try:
        parsed = pd.to_datetime(text)
        if re.fullmatch(r"\d{4}-\d{2}", text):
            return parsed.strftime("%b %Y")
        if re.fullmatch(r"\d{4}", text):
            return parsed.strftime("%Y")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            if parsed.day == 1:
                return parsed.strftime("%b %Y")
            return parsed.strftime("%d %b %Y")
    except Exception:
        pass
    return text


def system_name(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    return SYSTEM_NAME_BY_CODE.get(text, text)


def format_dataframe_for_display(
    frame: pd.DataFrame,
    *,
    unit: str | None = None,
    formatted_value_columns: list[str] | None = None,
    humanise_headers: bool = True,
    value_map: dict[str, str] | None = None,
) -> pd.DataFrame:
    display = frame.copy()
    for column in formatted_value_columns or []:
        if column in display.columns:
            display[column] = display[column].map(lambda value: format_indicator_value(value, unit))
    if value_map:
        for column, kind in value_map.items():
            if column in display.columns:
                display[column] = display[column].map(lambda value: humanise_enum(value, kind=kind))
    if humanise_headers:
        display = display.rename(columns={column: humanise_label(column) for column in display.columns})
    return display
