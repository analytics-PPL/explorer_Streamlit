from __future__ import annotations

import ast
import json
import re
from typing import Any

import pandas as pd

from app.components.formatting import format_indicator_value, scale_value_for_display


AGGREGATION_STATISTIC_LABELS = {
    "sum_counts": "Combined total across the selected footprint",
    "recompute_share_from_category_counts": "Combined percentage rebuilt from summed counts",
    "recompute_rate_from_numerator_denominator": "Combined rate rebuilt from summed numerators and denominators",
    "weighted_mean": "Weighted average across the selected areas",
    "population_weighted_mean": "Population-weighted average across the selected areas",
    "area_weighted_mean": "Area-weighted average across the selected areas",
    "non_additive_display_only": "Descriptive summary across the selected areas",
}

LOW_VARIANCE_RELATIVE_TOLERANCE = {
    "count": 0.01,
    "share": 0.02,
    "rate_per_1000": 0.02,
    "density_per_sq_km": 0.02,
    "currency_gbp": 0.01,
    "score": 0.01,
    "decile": 0.04,
}
LOW_VARIANCE_ABSOLUTE_TOLERANCE = {
    "count": 1.0,
    "share": 0.3,
    "rate_per_1000": 0.2,
    "density_per_sq_km": 0.1,
    "currency_gbp": 100.0,
    "score": 0.05,
    "decile": 0.1,
}

PROFILE_STRUCTURE_VIEWS = {
    "stacked_100_bar",
    "grouped_bar",
    "population_pyramid",
    "crime_mix_chart",
    "domain_tile_matrix",
}
PROFILE_BREAKDOWN_ALLOWED_VIEWS = PROFILE_STRUCTURE_VIEWS | {"table_support_only"}
CENSUS_BREAKDOWN_SOURCE_NAMES = {"Nomis API", "ONS Census 2021"}
PROFILE_BREAKDOWN_TITLE_BY_TABLE_CODE = {
    "ts001": "Residence type",
    "ts007a": "Age profile",
    "ts008": "Sex split",
    "ts011": "Household deprivation",
    "ts015": "Year of arrival",
    "ts016": "Length of residence in the UK",
    "ts017": "Household size",
    "ts021": "Ethnicity composition",
    "ts023": "Age of arrival",
    "ts024": "Country of birth",
    "ts027": "National identity",
    "ts029": "Main language and English proficiency",
    "ts030": "Religion",
    "ts031": "Passports held",
    "ts037": "General health",
    "ts038": "Disability",
    "ts039": "Unpaid care",
    "ts040": "Household disability",
    "ts045": "Car or van access",
    "ts046": "Heating type",
    "ts050": "Bedrooms",
    "ts051": "Rooms",
    "ts052": "Bedroom occupancy",
    "ts053": "Room occupancy",
    "ts054": "Tenure",
    "ts056": "Household ethnic diversity",
    "ts061": "Travel to work",
    "ts062": "Socio-economic class",
    "ts063": "Hours worked",
    "ts064": "Occupation",
    "ts065": "Employment history",
    "ts066": "Economic activity",
    "ts067": "Qualifications",
    "ts068": "Schoolchildren and full-time students",
    "ts075": "Second address purpose",
}
PROFILE_BREAKDOWN_VIEWS_BY_TABLE_CODE = {
    "ts007a": ["population_pyramid", "grouped_bar", "stacked_100_bar", "table_support_only"],
}


def meta_clean_text(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def meta_sequence(value: object) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = meta_clean_text(value)
    if not text:
        return []
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(text)
        except Exception:
            continue
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    return [item.strip() for item in text.split(";") if item.strip()]


def breakdown_groups_from_meta(meta: dict[str, object] | pd.Series) -> list[dict[str, object]]:
    raw_value = meta.get("breakdown_groups_json") if hasattr(meta, "get") else None
    if isinstance(raw_value, list):
        return [item for item in raw_value if isinstance(item, dict)]
    text = meta_clean_text(raw_value)
    if not text:
        return []
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(text)
        except Exception:
            continue
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
    return []


def census_table_code(meta: dict[str, object] | pd.Series) -> str:
    source_key = meta_clean_text(meta.get("source_key") if hasattr(meta, "get") else "")
    match = re.search(r"(ts\d+[a-z]?)", source_key, flags=re.IGNORECASE)
    return match.group(1).lower() if match else ""


def inferred_profile_breakdown_views(meta: dict[str, object] | pd.Series) -> list[str]:
    table_code = census_table_code(meta)
    if table_code in PROFILE_BREAKDOWN_VIEWS_BY_TABLE_CODE:
        return PROFILE_BREAKDOWN_VIEWS_BY_TABLE_CODE[table_code].copy()
    if table_code in PROFILE_BREAKDOWN_TITLE_BY_TABLE_CODE:
        return ["grouped_bar", "stacked_100_bar", "table_support_only"]
    return []


def profile_breakdown_title_override(meta: dict[str, object] | pd.Series) -> str:
    return PROFILE_BREAKDOWN_TITLE_BY_TABLE_CODE.get(census_table_code(meta), "")


def is_profile_breakdown_indicator(meta: dict[str, object] | pd.Series, *, min_groups: int = 2) -> bool:
    groups = breakdown_groups_from_meta(meta)
    default_view = meta_clean_text(
        meta.get("default_view")
        or meta.get("primary_visualisation")
        or meta.get("primary_visual_final")
    )
    unit = meta_clean_text(meta.get("unit") or meta.get("unit_type")).lower()
    source_name = meta_clean_text(meta.get("source_name"))
    source_key = meta_clean_text(meta.get("source_key"))
    census_breakdown = source_name in CENSUS_BREAKDOWN_SOURCE_NAMES or source_key.startswith("nomis_c2021")
    inferred_views = inferred_profile_breakdown_views(meta)
    has_explicit_groups = len(groups) >= min_groups
    return unit == "share" and (
        default_view in PROFILE_STRUCTURE_VIEWS
        or (census_breakdown and (has_explicit_groups or bool(inferred_views)))
    )


def is_direct_value_breakdown_indicator(meta: dict[str, object] | pd.Series, *, min_groups: int = 2) -> bool:
    groups = breakdown_groups_from_meta(meta)
    breakdown_mode = meta_clean_text(meta.get("breakdown_mode") if hasattr(meta, "get") else "").lower()
    return breakdown_mode == "direct_value" and len(groups) >= min_groups


def is_structured_breakdown_indicator(meta: dict[str, object] | pd.Series, *, min_groups: int = 2) -> bool:
    return is_profile_breakdown_indicator(meta, min_groups=min_groups) or is_direct_value_breakdown_indicator(meta, min_groups=min_groups)


def filter_profile_breakdown_views(
    meta: dict[str, object] | pd.Series,
    views: list[str],
) -> list[str]:
    if not is_profile_breakdown_indicator(meta):
        return [str(view).strip() for view in views if str(view).strip()]
    filtered: list[str] = []
    for view in views:
        clean_view = str(view).strip()
        if clean_view and clean_view in PROFILE_BREAKDOWN_ALLOWED_VIEWS and clean_view not in filtered:
            filtered.append(clean_view)
    return filtered


def grouped_summary_card(
    meta: dict[str, object] | pd.Series,
    *,
    label: str,
    selection_value: object,
    unit: str | None,
) -> dict[str, object]:
    if is_structured_breakdown_indicator(meta):
        group_count = len(breakdown_groups_from_meta(meta))
        breakdown_mode = meta_clean_text(meta.get("breakdown_mode") if hasattr(meta, "get") else "").lower()
        if breakdown_mode == "direct_value":
            group_label = "score" if group_count == 1 else "scores"
        else:
            group_label = "group" if group_count == 1 else "groups"
        return {
            "label": label,
            "value": f"{group_count} {group_label}",
            "caption": "Full breakdown available in the chart below.",
        }
    return {
        "label": label,
        "value": format_indicator_value(selection_value, unit),
        "caption": str(meta.get("ui_title") or label),
    }


def safe_focus_label(label: object, *, selection_kind: object = "") -> str:
    clean_label = str(label or "").strip()
    if clean_label.lower() == "london" and str(selection_kind or "").strip().lower() != "region":
        return "Selected areas"
    return clean_label or "Selected areas"


def aggregation_statistic_label(aggregation_method: object, *, fallback: str = "Combined summary for the selected areas") -> str:
    return AGGREGATION_STATISTIC_LABELS.get(str(aggregation_method or "").strip(), fallback)


def selection_statistic_caption(
    *,
    selection_label: object,
    selection_kind: object,
    selection_count: int,
    exact_boundary: bool,
    aggregation_method: object,
) -> str:
    focus_label = safe_focus_label(selection_label, selection_kind=selection_kind)
    statistic_label = aggregation_statistic_label(aggregation_method)
    if str(selection_kind or "").strip() == "region":
        return "London-wide figure shown directly."
    if selection_count <= 1:
        if exact_boundary:
            return f"Exact boundary for {focus_label}."
        return f"Single selected area. {statistic_label}."
    if exact_boundary and str(selection_kind or "").strip() in {"place", "system"}:
        return f"Exact boundary made up of {selection_count} neighbourhoods. {statistic_label}."
    return f"{selection_count} neighbourhoods combined. {statistic_label}."


def _numeric_values(values: pd.Series | list[object], unit: str | None) -> list[float]:
    scaled = [
        scale_value_for_display(value, unit)
        for value in pd.to_numeric(pd.Series(values), errors="coerce").dropna().tolist()
    ]
    return [float(value) for value in scaled if value is not None]


def detect_low_variance(values: pd.Series | list[object], unit: str | None) -> bool:
    numeric = _numeric_values(values, unit)
    if len(numeric) <= 1:
        return False
    minimum = min(numeric)
    maximum = max(numeric)
    spread = maximum - minimum
    baseline = max(abs((minimum + maximum) / 2.0), 1.0)
    relative_tolerance = LOW_VARIANCE_RELATIVE_TOLERANCE.get(str(unit or "").strip(), 0.015)
    absolute_tolerance = LOW_VARIANCE_ABSOLUTE_TOLERANCE.get(str(unit or "").strip(), 0.05)
    return spread <= max(absolute_tolerance, baseline * relative_tolerance)


def compare_values(
    selection_value: float | int | None,
    benchmark_value: float | int | None,
    unit: str | None,
) -> str:
    if selection_value is None or benchmark_value is None or pd.isna(selection_value) or pd.isna(benchmark_value):
        return "unknown"
    if detect_low_variance([selection_value, benchmark_value], unit):
        return "same"
    if float(selection_value) > float(benchmark_value):
        return "above"
    if float(selection_value) < float(benchmark_value):
        return "below"
    return "same"


def format_range_value(low: float | int | None, high: float | int | None, unit: str | None) -> str:
    if low is None or high is None or pd.isna(low) or pd.isna(high):
        return "No data"
    if detect_low_variance([low, high], unit):
        return format_indicator_value(low, unit)
    if unit == "share":
        return f"{float(low) * 100:.1f}% to {float(high) * 100:.1f}%"
    if unit == "rate_per_1000":
        return f"{float(low) * 1000:.1f} to {float(high) * 1000:.1f} per 1,000"
    if unit == "count":
        return f"{int(round(float(low))):,} to {int(round(float(high))):,}"
    if unit == "currency_gbp":
        return f"£{float(low):,.0f} to £{float(high):,.0f}"
    if unit == "density_per_sq_km":
        return f"{float(low):.2f} to {float(high):.2f} per sq km"
    if unit == "score":
        return f"{float(low):.2f} to {float(high):.2f}"
    if unit == "decile":
        return f"{float(low):.1f} to {float(high):.1f}"
    return f"{float(low):.2f} to {float(high):.2f}"


def build_comparator_context(
    *,
    selection: dict[str, object] | None,
    selection_label: object,
    selection_kind: object,
    selection_is_plural: bool,
    selected_area_count: int,
    exact_boundary: bool,
    borough_df: pd.DataFrame,
    london_df: pd.DataFrame,
) -> dict[str, object]:
    safe_label = safe_focus_label(selection_label, selection_kind=selection_kind)
    selection_kind_value = str(selection_kind or "").strip()
    unit = str(selection.get("unit") or "") if isinstance(selection, dict) else ""
    aggregation_method = str(selection.get("aggregation_method") or "") if isinstance(selection, dict) else ""
    selection_value = selection.get("value") if isinstance(selection, dict) else None
    safe_london_df = (
        pd.DataFrame()
        if selection_kind_value == "region"
        else london_df.copy() if isinstance(london_df, pd.DataFrame) else pd.DataFrame()
    )
    borough_values = (
        pd.to_numeric(borough_df["value"], errors="coerce").dropna().tolist()
        if isinstance(borough_df, pd.DataFrame) and not borough_df.empty and "value" in borough_df.columns
        else []
    )
    london_value = (
        safe_london_df.iloc[0]["value"]
        if isinstance(safe_london_df, pd.DataFrame) and not safe_london_df.empty and "value" in safe_london_df.columns
        else None
    )
    displayed_values: list[object] = []
    if selection_value is not None and not pd.isna(selection_value):
        displayed_values.append(selection_value)
    displayed_values.extend(borough_values)
    if london_value is not None and not pd.isna(london_value):
        displayed_values.append(london_value)
    return {
        "selection_label": safe_label,
        "selection_kind": selection_kind_value,
        "selection_is_plural": bool(selection_is_plural),
        "selection_value": selection_value,
        "unit": unit,
        "aggregation_method": aggregation_method,
        "aggregation_label": aggregation_statistic_label(aggregation_method),
        "selection_caption": selection_statistic_caption(
            selection_label=safe_label,
            selection_kind=selection_kind,
            selection_count=selected_area_count,
            exact_boundary=exact_boundary,
            aggregation_method=aggregation_method,
        ),
        "borough_df": borough_df.copy() if isinstance(borough_df, pd.DataFrame) else pd.DataFrame(),
        "london_df": safe_london_df,
        "borough_values": borough_values,
        "london_value": london_value,
        "displayed_values": displayed_values,
        "all_values_low_variance": detect_low_variance(displayed_values, unit) if len(displayed_values) > 1 else False,
    }


def build_summary_cards(comparator_context: dict[str, object]) -> list[dict[str, object]]:
    selection_value = comparator_context.get("selection_value")
    unit = comparator_context.get("unit")
    if selection_value is None or pd.isna(selection_value):
        return []

    cards = [
        {
            "label": str(comparator_context.get("selection_label") or "Selected areas"),
            "value": format_indicator_value(selection_value, unit),
            "caption": str(comparator_context.get("selection_caption") or ""),
        }
    ]

    borough_df = comparator_context.get("borough_df", pd.DataFrame())
    if isinstance(borough_df, pd.DataFrame) and not borough_df.empty:
        if len(borough_df) == 1:
            row = borough_df.iloc[0]
            cards.append(
                {
                    "label": "Borough benchmark",
                    "value": format_indicator_value(row.get("value"), unit),
                    "caption": str(row.get("benchmark_name") or "Relevant borough"),
                }
            )
        else:
            low = pd.to_numeric(borough_df["value"], errors="coerce").min()
            high = pd.to_numeric(borough_df["value"], errors="coerce").max()
            caption = (
                "No meaningful variation across selected boroughs"
                if detect_low_variance([low, high], unit)
                else f"Across {len(borough_df)} relevant boroughs"
            )
            cards.append(
                {
                    "label": "Borough range",
                    "value": format_range_value(low, high, unit),
                    "caption": caption,
                }
            )

    london_df = comparator_context.get("london_df", pd.DataFrame())
    if isinstance(london_df, pd.DataFrame) and not london_df.empty:
        cards.append(
            {
                "label": "London overall",
                "value": format_indicator_value(london_df.iloc[0].get("value"), unit),
                "caption": "All London neighbourhoods combined",
            }
        )

    return cards[:3]


def format_comparison_narrative(comparator_context: dict[str, object]) -> str:
    selection_value = comparator_context.get("selection_value")
    unit = comparator_context.get("unit")
    if selection_value is None or pd.isna(selection_value):
        return "No comparison summary is available for this indicator."

    subject = str(comparator_context.get("selection_label") or "Selected areas")
    verb = "are" if comparator_context.get("selection_is_plural") else "is"
    borough_df = comparator_context.get("borough_df", pd.DataFrame())
    london_df = comparator_context.get("london_df", pd.DataFrame())
    displayed_values = comparator_context.get("displayed_values", [])

    if len(displayed_values) > 1 and detect_low_variance(displayed_values, unit):
        if isinstance(borough_df, pd.DataFrame) and not borough_df.empty and isinstance(london_df, pd.DataFrame) and not london_df.empty:
            return "Values are effectively the same across the selected boroughs and London."
        if isinstance(london_df, pd.DataFrame) and not london_df.empty:
            return f"{subject} {verb} broadly in line with London overall."
        if isinstance(borough_df, pd.DataFrame) and not borough_df.empty:
            return "Values are effectively the same across the relevant boroughs."
        return f"{subject} {verb} shown as a standalone summary for the selected footprint."

    sentences: list[str] = []
    if isinstance(borough_df, pd.DataFrame) and not borough_df.empty:
        if len(borough_df) == 1:
            borough_name = str(borough_df.iloc[0].get("benchmark_name") or "the relevant borough benchmark")
            direction = compare_values(selection_value, borough_df.iloc[0].get("value"), unit)
            if direction == "same":
                sentences.append(f"{subject} {verb} broadly in line with the {borough_name} benchmark.")
            elif direction == "above":
                sentences.append(f"{subject} {verb} above the {borough_name} benchmark.")
            elif direction == "below":
                sentences.append(f"{subject} {verb} below the {borough_name} benchmark.")
        else:
            borough_values = pd.to_numeric(borough_df["value"], errors="coerce").dropna().tolist()
            if borough_values:
                borough_low = min(borough_values)
                borough_high = max(borough_values)
                if detect_low_variance([borough_low, borough_high], unit):
                    sentences.append("There is no meaningful variation across the relevant borough benchmarks.")
                elif float(selection_value) < float(borough_low):
                    sentences.append(f"{subject} {verb} below the selected borough range.")
                elif float(selection_value) > float(borough_high):
                    sentences.append(f"{subject} {verb} above the selected borough range.")
                else:
                    sentences.append(f"{subject} {verb} within the selected borough range.")

    if isinstance(london_df, pd.DataFrame) and not london_df.empty:
        direction = compare_values(selection_value, london_df.iloc[0].get("value"), unit)
        if direction == "same":
            sentences.append(f"{subject} {verb} broadly in line with London overall.")
        elif direction == "above":
            sentences.append(f"{subject} {verb} above London overall.")
        elif direction == "below":
            sentences.append(f"{subject} {verb} below London overall.")

    if not sentences:
        return f"{subject} {verb} shown as a standalone summary for the selected footprint."
    return " ".join(sentence.strip() for sentence in sentences if sentence.strip())


def should_use_horizontal_bars(labels: list[object], *, max_chars: int = 16, item_threshold: int = 5) -> bool:
    clean_labels = [str(label or "").strip() for label in labels if str(label or "").strip()]
    if not clean_labels:
        return False
    longest = max(len(label) for label in clean_labels)
    return longest > max_chars or len(clean_labels) >= item_threshold


def composition_view_prefers_grouped_bar(composition_df: pd.DataFrame) -> bool:
    if not isinstance(composition_df, pd.DataFrame) or composition_df.empty or "category" not in composition_df.columns:
        return False
    labels = composition_df["category"].dropna().astype(str).tolist()
    category_count = len(set(labels))
    longest = max((len(label) for label in labels), default=0)
    return category_count > 5 or longest > 18


def choose_default_view(
    *,
    default_view: str,
    compact_views: list[str],
    full_views: list[str],
    context: dict[str, object] | None,
) -> str:
    if not context:
        return default_view

    available_views = [view for view in compact_views + full_views if view]
    comparator_context = context.get("comparator_context", {})
    detail_df = context.get("detail_df", pd.DataFrame())
    ranked_df = context.get("ranked_df", pd.DataFrame())
    composition_df = context.get("composition_df", pd.DataFrame())
    timeseries_df = context.get("timeseries_df", pd.DataFrame())
    selection = context.get("selection")

    if default_view == "stacked_100_bar" and composition_view_prefers_grouped_bar(composition_df):
        if "grouped_bar" in available_views:
            return "grouped_bar"
        if "table_support_only" in available_views:
            return "table_support_only"

    if default_view != "grouped_bar" and isinstance(composition_df, pd.DataFrame) and not composition_df.empty:
        breakdown_mode = str(composition_df.get("breakdown_mode", pd.Series(dtype=object)).dropna().astype(str).iloc[0]) if "breakdown_mode" in composition_df.columns and not composition_df.get("breakdown_mode", pd.Series(dtype=object)).dropna().empty else ""
        if breakdown_mode == "direct_value" and "grouped_bar" in available_views:
            return "grouped_bar"

    if default_view in {"kpi_card", "text_badges_or_indexed_note"}:
        if selection is not None and not detail_df.empty:
            for candidate in ("sorted_bar", "ranked_distribution", "ranked_strip", "table_support_only"):
                if candidate in available_views:
                    return candidate

    if default_view in {"benchmark_lollipop", "lollipop_compare", "benchmark_only_compare"} and selection is not None:
        borough_df = comparator_context.get("borough_df", pd.DataFrame())
        london_df = comparator_context.get("london_df", pd.DataFrame())
        if (
            (not isinstance(borough_df, pd.DataFrame) or borough_df.empty)
            and (not isinstance(london_df, pd.DataFrame) or london_df.empty)
            and not ranked_df.empty
            and not bool(context.get("selection_exact_boundary", False))
        ):
            for candidate in ("ranked_distribution", "ranked_strip", "sorted_bar", "table_support_only"):
                if candidate in available_views:
                    return candidate

    if default_view == "trend_line_with_rolling_average" and isinstance(timeseries_df, pd.DataFrame) and not timeseries_df.empty:
        series_count = timeseries_df["series"].astype(str).nunique()
        if series_count > 4 and "trend_line" in available_views:
            return "trend_line"

    return default_view


def should_render_module_overview(subcategory_catalog: pd.DataFrame, bundle_view: str) -> bool:
    if not isinstance(subcategory_catalog, pd.DataFrame) or subcategory_catalog.empty:
        return False
    if int(subcategory_catalog["indicator_id"].nunique()) <= 1:
        return False
    return bool(str(bundle_view or "").strip())


def should_render_advanced_section(
    overview_catalog: pd.DataFrame,
    advanced_catalog: pd.DataFrame,
) -> bool:
    if not isinstance(advanced_catalog, pd.DataFrame) or advanced_catalog.empty:
        return False
    overview_ids = (
        set(overview_catalog["indicator_id"].astype(str).tolist())
        if isinstance(overview_catalog, pd.DataFrame) and not overview_catalog.empty and "indicator_id" in overview_catalog.columns
        else set()
    )
    advanced_ids = set(advanced_catalog["indicator_id"].astype(str).tolist())
    return bool(advanced_ids - overview_ids)


def has_inline_advanced_indicators(advanced_catalog: pd.DataFrame, overview_catalog: pd.DataFrame | None = None) -> bool:
    if not isinstance(advanced_catalog, pd.DataFrame) or advanced_catalog.empty:
        return False
    module_label = str(advanced_catalog.iloc[0].get("module_label") or "").strip().lower()
    if "screen" in module_label or "vaccination" in module_label or "immunisation" in module_label:
        return True
    if overview_catalog is None or overview_catalog.empty:
        return int(advanced_catalog["indicator_id"].nunique()) <= 4
    overview_ids = set(overview_catalog["indicator_id"].astype(str).tolist())
    advanced_ids = set(advanced_catalog["indicator_id"].astype(str).tolist())
    return advanced_ids.isdisjoint(overview_ids) and int(advanced_catalog["indicator_id"].nunique()) <= 4
