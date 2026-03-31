from __future__ import annotations

import logging
from copy import deepcopy
from functools import lru_cache
import json
import re
from typing import TYPE_CHECKING

import pandas as pd

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import geopandas as gpd

from catalog.indicator_visualisation_registry import apply_visualisation_contract
from catalog.indicator_visualisation_registry import load_preferred_indicator_specs
from neighbourhood_explorer.aggregation import aggregate_records
from neighbourhood_explorer.catalog import build_unified_indicator_catalog
from neighbourhood_explorer.catalog_dedup import drop_overlapping_catalog_metrics
from neighbourhood_explorer.config import load_indicator_catalog, load_sources_config
from neighbourhood_explorer.footprints import resolve_footprint_label, selection_label as footprint_selection_label
from neighbourhood_explorer.geography import load_crosswalk
from neighbourhood_explorer.pipeline_contract import apply_pipeline_contract
from neighbourhood_explorer.paths import (
    BOROUGH_BENCHMARKS_PATH,
    INDICATOR_CATALOG_EXPORT_PATH,
    HEX_ICB_GEOJSON_PATH,
    LONDON_BENCHMARKS_PATH,
    NEIGHBOURHOOD_BOUNDARIES_GEOJSON_PATH,
    NEIGHBOURHOOD_HEX_GEOJSON_PATH,
    NEIGHBOURHOOD_INDICATOR_VALUES_PATH,
    NEIGHBOURHOOD_REFERENCE_PATH,
    ROOT_DIR,
)

BOROUGH_AVERAGE_THRESHOLD = 4
MIN_TREND_YEARS = 3.0
AVERAGEABLE_BOROUGH_BENCHMARK_METHODS = {
    "recompute_rate_from_numerator_denominator",
    "recompute_share_from_category_counts",
    "weighted_mean",
    "population_weighted_mean",
    "area_weighted_mean",
}
LONDON_BENCHMARK_UNITS = {
    "share",
    "rate_per_1000",
    "density_per_sq_km",
    "currency_gbp",
    "score",
}
POLICE_DENOMINATOR_REFERENCE_INDICATOR_ID = "police_all_crimes_rate_per_1000"
TREND_VIEW_NAMES = {"trend_line", "trend_line_with_rolling_average"}
QOF_HISTORY_CODE_GROUPS = (
    ("AF007", "AF008"),
    ("AST006", "AST011"),
    ("CHD008", "CHD015"),
    ("CHD009", "CHD016"),
    ("COPD008", "COPD014"),
    ("DEP003", "DEP004"),
    ("DM019", "DM033"),
    ("HF005", "HF008"),
    ("HYP003", "HYP008"),
    ("HYP007", "HYP009"),
    ("NDH001", "NDH002"),
    ("STIA010", "STIA014"),
    ("STIA011", "STIA015"),
)
_QOF_HISTORY_CODE_LOOKUP = {
    code: group
    for group in QOF_HISTORY_CODE_GROUPS
    for code in group
}
CATALOG_EXPORT_RUNTIME_VERSION = 1
CATALOG_RUNTIME_COLUMNS = {
    "default_view",
    "view_toggle_options_compact",
    "view_toggle_options_full",
    "available_view_list",
    "subcategory_key",
    "timeseries_period_count",
    "timeseries_years_available",
    "_catalog_runtime_version",
}
CATALOG_PIPELINE_COLUMNS = {
    "metric_domain",
    "source_priority",
    "fallback_source",
    "benchmark_source",
    "duplicate_group_id",
    "time_series_complete",
    "time_series_status",
    "earliest_available_period",
    "latest_available_period",
    "update_frequency",
    "last_updated",
}
CATALOG_VIEW_LIST_COLUMNS = (
    "compact_view_list",
    "full_view_list",
    "available_view_list",
)
RUNTIME_HIDDEN_INDICATOR_IDS = {
    # Built from a direct neighbourhood BikePoint join rather than an LSOA-backed source.
    "tfl_cycle_docking_station_density",
    # Shown inside composite transport indicators rather than as standalone public indicators.
    "naptan_access_node_density",
    "naptan_bus_access_node_count",
    "naptan_rail_and_tube_node_count",
    "tfl_cycle_dock_capacity_total",
    "tfl_cycle_dock_capacity_density",
}
PROFILE_BREAKDOWN_VIEWS_BY_TABLE_CODE = {
    "ts007a": ["population_pyramid", "grouped_bar", "stacked_100_bar", "table_support_only"],
}
DEFAULT_PROFILE_BREAKDOWN_VIEWS = ["grouped_bar", "stacked_100_bar", "table_support_only"]
PROFILE_BREAKDOWN_EXCLUDED_INDICATOR_IDS = {"nomis_population_total"}
IMD_SCORE_BREAKDOWN_FIELDS = {
    "Education, Skills and Training Score": [
        "Children and Young People Sub-domain Score",
        "Adult Skills Sub-domain Score",
    ],
    "Barriers to Housing and Services Score": [
        "Geographical Barriers Sub-domain Score",
        "Wider Barriers Sub-domain Score",
    ],
    "Living Environment Score": [
        "Indoors Sub-domain Score",
        "Outdoors Sub-domain Score",
    ],
}
DERIVED_BREAKDOWN_VIEWS = [
    "grouped_bar",
    "choropleth_map",
    "ranked_distribution",
    "table_support_only",
]
STANDALONE_KPI_MAP_BASE_VIEWS = {
    "benchmark_lollipop",
    "benchmark_only_compare",
    "lollipop_compare",
    "kpi_card",
}
WEIGHTED_AGGREGATION_METHODS = {
    "weighted_mean",
    "population_weighted_mean",
    "area_weighted_mean",
}


def _period_sort_key(value: object) -> tuple[int, object]:
    text = str(value).strip()
    if not text:
        return (99, text)
    if re.fullmatch(r"\d{4}-\d{2}", text):
        return (0, pd.Period(text, freq="M").ordinal)
    if re.fullmatch(r"\d{4}-Q[1-4]", text):
        return (1, pd.Period(text, freq="Q").ordinal)
    if re.fullmatch(r"\d{4}/\d{2}", text):
        start_year = int(text[:4])
        return (2, start_year)
    if re.fullmatch(r"\d{4}", text):
        return (3, int(text))
    parsed = pd.to_datetime(text, errors="coerce")
    if not pd.isna(parsed):
        return (4, parsed.toordinal())
    return (98, text)


def _sort_period_values(values: list[object]) -> list[str]:
    ordered = sorted({str(value).strip() for value in values if str(value).strip()}, key=_period_sort_key)
    return ordered


def _parse_view_toggle_text(value: object) -> list[str]:
    views: list[str] = []
    for raw in str(value or "").split("|"):
        item = str(raw).strip()
        if not item or item in views:
            continue
        views.append(item)
    return views


def _join_view_toggle_text(values: list[str]) -> str:
    return "|".join(item for item in values if item and item != "none")


def _ordered_unique_strings(values: list[object]) -> list[str]:
    ordered: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if not item or item in ordered:
            continue
        ordered.append(item)
    return ordered


def _humanise_score_breakdown_field(field_name: object) -> str:
    text = str(field_name or "").strip()
    if not text:
        return ""
    text = re.sub(r"\s+Score$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+Sub-domain$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    return text[0].upper() + text[1:]


def _table_code_from_source_key(source_key: object) -> str:
    text = str(source_key or "").strip()
    match = re.search(r"(ts\d+[a-z]?)", text, flags=re.IGNORECASE)
    return match.group(1).lower() if match else ""


def _preferred_breakdown_views_for_table_code(table_code: str) -> list[str]:
    if table_code in PROFILE_BREAKDOWN_VIEWS_BY_TABLE_CODE:
        return PROFILE_BREAKDOWN_VIEWS_BY_TABLE_CODE[table_code].copy()
    return DEFAULT_PROFILE_BREAKDOWN_VIEWS.copy()


def _census_breakdown_spec_lookup(df: pd.DataFrame) -> dict[str, tuple[str, str]]:
    lookup: dict[str, tuple[str, str]] = {}
    if df.empty or "source_key" not in df.columns:
        return lookup
    for row in df.to_dict(orient="records"):
        source_name = str(row.get("source_name") or "").strip()
        source_key = str(row.get("source_key") or "").strip()
        if source_name not in {"Nomis API", "ONS Census 2021"} and "ts" not in source_key.lower():
            continue
        breakdown_json = str(row.get("breakdown_groups_json") or "").strip()
        if not breakdown_json:
            continue
        table_code = _table_code_from_source_key(source_key)
        if not table_code or table_code in lookup:
            continue
        lookup[table_code] = (breakdown_json, source_key)
    return lookup


def _derived_breakdown_groups_for_row(
    row: pd.Series | dict[str, object],
    available_columns: set[str],
) -> list[dict[str, object]]:
    value_field = str(row.get("value_field") or "").strip()
    subdomain_fields = IMD_SCORE_BREAKDOWN_FIELDS.get(value_field, [])
    if not value_field or not subdomain_fields:
        return []
    required_fields = [value_field] + subdomain_fields
    if not all(field in available_columns for field in required_fields):
        return []
    groups: list[dict[str, object]] = [{"label": "Overall score", "fields": [value_field]}]
    for field_name in subdomain_fields:
        label = _humanise_score_breakdown_field(field_name)
        if label:
            groups.append({"label": label, "fields": [field_name]})
    return groups


def _apply_derived_breakdown_contract(df: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    if df.empty or "indicator_id" not in df.columns or "source_key" not in df.columns or "value_field" not in df.columns:
        return df, False

    adjusted = df.copy()
    source_columns_cache: dict[str, set[str]] = {}
    changed = False

    for index, row in adjusted.iterrows():
        value_field = str(row.get("value_field") or "").strip()
        if value_field not in IMD_SCORE_BREAKDOWN_FIELDS:
            continue
        source_key = str(row.get("source_key") or "").strip()
        if not source_key:
            continue
        if source_key not in source_columns_cache:
            source_frame = _load_indicator_source_frame(source_key)
            source_columns_cache[source_key] = set(source_frame.columns.tolist())
        breakdown_groups = _derived_breakdown_groups_for_row(row, source_columns_cache[source_key])
        if not breakdown_groups:
            continue

        breakdown_json = json.dumps(breakdown_groups, separators=(",", ":"))
        current_breakdown_json = str(row.get("breakdown_groups_json") or "").strip()
        if current_breakdown_json != breakdown_json:
            adjusted.at[index, "breakdown_groups_json"] = breakdown_json
            changed = True

        if str(row.get("breakdown_mode") or "").strip() != "direct_value":
            adjusted.at[index, "breakdown_mode"] = "direct_value"
            changed = True

        desired_views = DERIVED_BREAKDOWN_VIEWS.copy()
        for column, expected in [
            ("default_view", "grouped_bar"),
            ("primary_visualisation", "grouped_bar"),
            ("secondary_visualisation", "choropleth_map"),
            ("view_toggle_options_compact", _join_view_toggle_text(desired_views)),
            ("view_toggle_options_full", _join_view_toggle_text(desired_views)),
        ]:
            if column not in adjusted.columns:
                continue
            current_value = str(row.get(column) or "").strip()
            if current_value != expected:
                adjusted.at[index, column] = expected
                changed = True

        for column in ("compact_view_list", "full_view_list", "available_view_list"):
            if column not in adjusted.columns:
                continue
            current_list = [str(value).strip() for value in (row.get(column) or []) if str(value).strip()]
            if current_list != desired_views:
                adjusted.at[index, column] = desired_views.copy()
                changed = True

    return adjusted, changed


def _apply_derived_census_breakdown_contract(df: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    if df.empty or "indicator_id" not in df.columns or "source_key" not in df.columns:
        return df, False

    adjusted = df.copy()
    breakdown_lookup = _census_breakdown_spec_lookup(adjusted)
    changed = False

    for index, row in adjusted.iterrows():
        indicator_id = str(row.get("indicator_id") or "").strip()
        if indicator_id in PROFILE_BREAKDOWN_EXCLUDED_INDICATOR_IDS:
            continue
        unit = str(row.get("unit") or row.get("unit_type") or "").strip().lower()
        if unit != "share":
            continue
        source_key = str(row.get("source_key") or "").strip()
        table_code = _table_code_from_source_key(source_key)
        if not table_code:
            continue
        breakdown_spec = breakdown_lookup.get(table_code)
        if not breakdown_spec:
            continue
        breakdown_json, _ = breakdown_spec
        current_breakdown = str(row.get("breakdown_groups_json") or "").strip()
        if current_breakdown != breakdown_json:
            adjusted.at[index, "breakdown_groups_json"] = breakdown_json
            changed = True

        desired_views = _preferred_breakdown_views_for_table_code(table_code)
        desired_default = desired_views[0]
        for column, expected in [
            ("default_view", desired_default),
            ("primary_visualisation", desired_default),
            ("view_toggle_options_compact", _join_view_toggle_text(desired_views)),
            ("view_toggle_options_full", _join_view_toggle_text(desired_views)),
        ]:
            if column not in adjusted.columns:
                continue
            current_value = str(row.get(column) or "").strip()
            if current_value != expected:
                adjusted.at[index, column] = expected
                changed = True

        secondary_view = desired_views[1] if len(desired_views) > 1 else ""
        if "secondary_visualisation" in adjusted.columns and str(row.get("secondary_visualisation") or "").strip() != secondary_view:
            adjusted.at[index, "secondary_visualisation"] = secondary_view
            changed = True

        for column in ("compact_view_list", "full_view_list", "available_view_list"):
            if column not in adjusted.columns:
                continue
            current_list = [str(value).strip() for value in (row.get(column) or []) if str(value).strip()]
            if current_list != desired_views:
                adjusted.at[index, column] = desired_views.copy()
                changed = True

    return adjusted, changed


def _periods_per_year(periods: list[str], period_type_hint: object) -> int | None:
    hint = str(period_type_hint or "").strip().lower()
    if "month" in hint:
        return 12
    if "quarter" in hint:
        return 4
    if hint in {"annual", "year", "yearly", "snapshot"}:
        return 1
    if periods and all(re.fullmatch(r"\d{4}-\d{2}", value) for value in periods):
        return 12
    if periods and all(re.fullmatch(r"\d{4}-Q[1-4]", value) for value in periods):
        return 4
    if periods and all(re.fullmatch(r"\d{4}/\d{2}", value) or re.fullmatch(r"\d{4}", value) for value in periods):
        return 1
    return None


def _is_standalone_kpi_map_candidate(row: pd.Series | dict[str, object]) -> bool:
    if not _metadata_value_missing(row.get("breakdown_groups_json")):
        return False

    map_allowed = row.get("map_allowed")
    if _metadata_value_missing(map_allowed):
        return False
    if isinstance(map_allowed, str):
        if map_allowed.strip().lower() not in {"true", "1", "yes", "y"}:
            return False
    else:
        try:
            if not bool(map_allowed):
                return False
        except TypeError:
            return False

    default_view = str(row.get("default_view") or row.get("primary_visualisation") or "").strip()
    if default_view not in STANDALONE_KPI_MAP_BASE_VIEWS:
        return False

    available_views = _ordered_unique_strings(
        list(row.get("available_view_list") or [])
        + _parse_view_toggle_text(row.get("view_toggle_options_compact"))
        + _parse_view_toggle_text(row.get("view_toggle_options_full"))
    )
    return "choropleth_map" not in available_views


def _apply_standalone_kpi_map_contract(df: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    if df.empty or "indicator_id" not in df.columns:
        return df, False

    adjusted = df.copy()
    changed = False

    for index, row in adjusted.iterrows():
        if not _is_standalone_kpi_map_candidate(row):
            continue

        default_view = str(row.get("default_view") or row.get("primary_visualisation") or "").strip()
        compact_views = _ordered_unique_strings(_parse_view_toggle_text(row.get("view_toggle_options_compact")))
        full_views = _ordered_unique_strings(_parse_view_toggle_text(row.get("view_toggle_options_full")))
        available_views = _ordered_unique_strings(list(row.get("available_view_list") or []) + compact_views + full_views)

        target_full_views = full_views.copy() if full_views else _ordered_unique_strings([default_view] + compact_views + available_views)
        if "choropleth_map" not in target_full_views:
            target_full_views.append("choropleth_map")
        target_available_views = _ordered_unique_strings(available_views + ["choropleth_map"])
        target_full_text = _join_view_toggle_text(target_full_views)

        if str(row.get("map_view_final") or "").strip() != "choropleth_map":
            adjusted.at[index, "map_view_final"] = "choropleth_map"
            changed = True
        if "map_role" in adjusted.columns and str(row.get("map_role") or "").strip() != "secondary":
            adjusted.at[index, "map_role"] = "secondary"
            changed = True
        if "view_toggle_options_full" in adjusted.columns and str(row.get("view_toggle_options_full") or "").strip() != target_full_text:
            adjusted.at[index, "view_toggle_options_full"] = target_full_text
            changed = True
        if "full_view_list" in adjusted.columns:
            current_full = [str(value).strip() for value in (row.get("full_view_list") or []) if str(value).strip()]
            if current_full != target_full_views:
                adjusted.at[index, "full_view_list"] = target_full_views.copy()
                changed = True
        if "available_view_list" in adjusted.columns:
            current_available = [str(value).strip() for value in (row.get("available_view_list") or []) if str(value).strip()]
            if current_available != target_available_views:
                adjusted.at[index, "available_view_list"] = target_available_views.copy()
                changed = True

    return adjusted, changed


def _timeseries_periods_for_catalog_row(
    indicator_row: pd.Series,
    catalog: pd.DataFrame,
    periods_by_indicator: dict[str, list[str]],
) -> list[str]:
    indicator_id = str(indicator_row.get("indicator_id") or "").strip()
    if not indicator_id:
        return []
    if not indicator_id.startswith("qof_"):
        return periods_by_indicator.get(indicator_id, [])

    code = str(indicator_row.get("qof_indicator_code") or "").strip().upper()
    metric_kind = str(indicator_row.get("qof_metric_kind") or "").strip().lower()
    patient_list_type = str(indicator_row.get("qof_patient_list_type") or "").strip().upper()
    group_code = str(indicator_row.get("qof_group_code") or "").strip().upper()
    if not code or code not in _QOF_HISTORY_CODE_LOOKUP:
        return periods_by_indicator.get(indicator_id, [])

    related_codes = set(_QOF_HISTORY_CODE_LOOKUP[code])
    related = catalog[
        catalog["qof_indicator_code"].astype(str).str.upper().isin(related_codes)
        & (catalog["qof_metric_kind"].astype(str).fillna("").str.lower() == metric_kind)
        & (catalog["qof_patient_list_type"].astype(str).fillna("").str.upper() == patient_list_type)
        & (catalog["qof_group_code"].astype(str).fillna("").str.upper() == group_code)
    ].copy()
    if related.empty:
        return periods_by_indicator.get(indicator_id, [])

    periods: list[str] = []
    ordered_ids = [indicator_id] + [
        related_id
        for related_id in related["indicator_id"].astype(str).tolist()
        if related_id != indicator_id
    ]
    for related_id in ordered_ids:
        periods.extend(periods_by_indicator.get(related_id, []))
    return _sort_period_values(periods)


def _first_non_trend_view(
    row: pd.Series,
    *,
    default: str = "benchmark_lollipop",
) -> str:
    candidates = [
        str(row.get("default_view") or "").strip(),
        str(row.get("primary_visualisation") or "").strip(),
        str(row.get("secondary_visualisation") or "").strip(),
    ]
    candidates.extend(_parse_view_toggle_text(row.get("view_toggle_options_compact")))
    candidates.extend(_parse_view_toggle_text(row.get("view_toggle_options_full")))
    for view in candidates:
        if view and view not in TREND_VIEW_NAMES and view != "none":
            return view
    return default


def _apply_minimum_trend_history_contract(catalog: pd.DataFrame) -> pd.DataFrame:
    if catalog.empty or "indicator_id" not in catalog.columns:
        return catalog

    source_catalog = catalog.copy()
    adjusted = catalog.copy()
    values = load_neighbourhood_indicator_values()
    periods_by_indicator = {
        str(indicator_id): _sort_period_values(group["period"].dropna().astype(str).tolist())
        for indicator_id, group in values.groupby("indicator_id", dropna=False, observed=False)
    }

    for index, row in source_catalog.iterrows():
        available_views = list(row.get("available_view_list") or [])
        available_views.extend(_parse_view_toggle_text(row.get("view_toggle_options_compact")))
        available_views.extend(_parse_view_toggle_text(row.get("view_toggle_options_full")))
        available_views = _ordered_unique_strings(available_views)
        has_trend_view = any(view in TREND_VIEW_NAMES for view in available_views) or str(row.get("secondary_visualisation") or "").strip() in TREND_VIEW_NAMES

        periods = _timeseries_periods_for_catalog_row(row, source_catalog, periods_by_indicator)
        periods_per_year = _periods_per_year(periods, row.get("period_type"))
        years_available = float(len(periods)) / float(periods_per_year) if periods and periods_per_year else 0.0
        adjusted.at[index, "timeseries_period_count"] = int(len(periods))
        adjusted.at[index, "timeseries_years_available"] = float(years_available)
        adjusted.at[index, "history_available"] = bool(years_available >= MIN_TREND_YEARS)

        if not has_trend_view or years_available >= MIN_TREND_YEARS:
            continue

        filtered_views = [view for view in available_views if view not in TREND_VIEW_NAMES]
        fallback_view = _first_non_trend_view(row)
        if fallback_view and fallback_view not in filtered_views:
            filtered_views.insert(0, fallback_view)

        compact_views = [
            view for view in _parse_view_toggle_text(row.get("view_toggle_options_compact"))
            if view not in TREND_VIEW_NAMES
        ]
        full_views = [
            view for view in _parse_view_toggle_text(row.get("view_toggle_options_full"))
            if view not in TREND_VIEW_NAMES
        ]
        if not compact_views and fallback_view:
            compact_views = [fallback_view]
        if not full_views and fallback_view:
            full_views = compact_views.copy()

        default_view = str(row.get("default_view") or "").strip()
        primary_view = str(row.get("primary_visualisation") or "").strip()
        secondary_view = str(row.get("secondary_visualisation") or "").strip()
        if default_view in TREND_VIEW_NAMES:
            default_view = fallback_view
        if primary_view in TREND_VIEW_NAMES:
            primary_view = fallback_view
        if secondary_view in TREND_VIEW_NAMES:
            secondary_view = next(
                (
                    view
                    for view in filtered_views
                    if view and view not in {default_view, primary_view}
                ),
                "",
            )

        adjusted.at[index, "default_view"] = default_view
        adjusted.at[index, "primary_visualisation"] = primary_view
        adjusted.at[index, "secondary_visualisation"] = secondary_view
        adjusted.at[index, "trend_view"] = ""
        adjusted.at[index, "trend_allowed"] = False
        adjusted.at[index, "view_toggle_options_compact"] = _join_view_toggle_text(compact_views)
        adjusted.at[index, "view_toggle_options_full"] = _join_view_toggle_text(full_views)
        adjusted.at[index, "available_view_list"] = filtered_views

    return adjusted


def _split_borough_names(values: pd.Series) -> list[str]:
    boroughs: list[str] = []
    for raw_value in values.dropna().astype(str):
        boroughs.extend([item.strip() for item in raw_value.split(";") if item.strip()])
    return sorted(set(boroughs))


def _joined_place_label(values: list[str]) -> str:
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return f"{', '.join(values[:-1])} and {values[-1]}"


def _average_borough_rows(borough_rows: pd.DataFrame, boroughs: list[str]) -> pd.DataFrame:
    if borough_rows.empty:
        return borough_rows
    average_row = borough_rows.iloc[[0]].copy()
    average_row.loc[:, "benchmark_name"] = f"Average of {_joined_place_label(boroughs)} boroughs"
    average_row.loc[:, "benchmark_code"] = "MULTI_BOROUGH_AVERAGE"
    average_row.loc[:, "value"] = pd.to_numeric(borough_rows["value"], errors="coerce").mean()
    for column in ["numerator", "denominator", "record_count", "summary_min", "summary_max", "summary_median"]:
        if column in average_row.columns:
            average_row[column] = average_row[column].astype(object)
            average_row.loc[:, column] = float("nan")
    if "benchmark_scope" in average_row.columns:
        average_row.loc[:, "benchmark_scope"] = "borough_average"
    return average_row.reset_index(drop=True)


def _borough_membership_mask(values: pd.Series, borough_name: str) -> pd.Series:
    target = str(borough_name).strip().lower()
    return values.astype(str).fillna("").map(
        lambda value: target in {item.strip().lower() for item in str(value).split(";") if item.strip()}
    )


def _single_borough_selection(reference: pd.DataFrame, selected_meta: pd.DataFrame) -> tuple[bool, str]:
    if selected_meta.empty:
        return False, ""
    boroughs = _split_borough_names(selected_meta["borough_name"])
    if len(boroughs) != 1:
        return False, ""
    borough_name = boroughs[0]
    selected_ids = set(selected_meta["neighbourhood_id"].astype(str))
    borough_ids = set(reference.loc[_borough_membership_mask(reference["borough_name"], borough_name), "neighbourhood_id"].astype(str))
    if not borough_ids:
        return False, borough_name
    return selected_ids == borough_ids, borough_name


def _supports_borough_average(aggregation_method: object) -> bool:
    return str(aggregation_method).strip() in AVERAGEABLE_BOROUGH_BENCHMARK_METHODS


def _supports_london_benchmark(summary: dict[str, object] | None) -> bool:
    if not isinstance(summary, dict):
        return False
    aggregation_method = str(summary.get("aggregation_method") or "").strip()
    unit = str(summary.get("unit") or "").strip()
    return aggregation_method in AVERAGEABLE_BOROUGH_BENCHMARK_METHODS or unit in LONDON_BENCHMARK_UNITS


def _selection_resolves_to_region(
    selected_ids: tuple[str, ...] | list[str] | set[str],
    reference_df: pd.DataFrame,
) -> bool:
    return resolve_footprint_label(list(selected_ids), reference_df).kind == "region"


def _single_borough_average_row(
    indicator_id: str,
    period: str,
    borough_name: str,
    template_rows: pd.DataFrame,
    reference: pd.DataFrame,
) -> pd.DataFrame:
    if template_rows.empty:
        return template_rows
    frame = indicator_frame(indicator_id, period)
    if frame.empty:
        return pd.DataFrame()
    borough_frame = frame.copy()
    if "borough_name" not in borough_frame.columns:
        borough_frame = borough_frame.merge(reference[["neighbourhood_id", "borough_name"]], on="neighbourhood_id", how="left")
    borough_name_column = "borough_name"
    if borough_name_column not in borough_frame.columns:
        borough_name_column = next(
            (column for column in borough_frame.columns if str(column).startswith("borough_name")),
            "",
        )
    if not borough_name_column:
        return pd.DataFrame()
    borough_frame = borough_frame[_borough_membership_mask(borough_frame[borough_name_column], borough_name)].copy()
    if borough_frame.empty:
        return pd.DataFrame()
    values = pd.to_numeric(borough_frame["value"], errors="coerce").dropna()
    if values.empty:
        return pd.DataFrame()
    average_row = template_rows.iloc[[0]].copy()
    average_row.loc[:, "benchmark_name"] = f"Average of {borough_name} neighbourhoods"
    average_row.loc[:, "value"] = float(values.mean())
    if "record_count" in average_row.columns:
        average_row.loc[:, "record_count"] = int(len(values))
    for column in ["numerator", "denominator", "summary_min", "summary_max", "summary_median"]:
        if column in average_row.columns:
            average_row.loc[:, column] = float("nan")
    if "benchmark_scope" in average_row.columns:
        average_row.loc[:, "benchmark_scope"] = "borough_average_neighbourhoods"
    return average_row.reset_index(drop=True)


def _mean_comparator_row(frame: pd.DataFrame, *, label: str) -> dict[str, object] | None:
    if frame.empty or "value" not in frame.columns:
        return None
    values = pd.to_numeric(frame["value"], errors="coerce").dropna()
    if values.empty:
        return None
    unit = None
    if "unit" in frame.columns:
        units = frame["unit"].dropna().astype(str)
        if not units.empty:
            unit = str(units.iloc[0])
    return {
        "series": str(label),
        "value": float(values.mean()),
        "unit": unit,
    }


def _timeseries_comparator_row(
    indicator_id: str,
    period: str,
    selected_ids: list[str] | list[int] | set[int],
    selection: dict[str, object] | None,
    reference: pd.DataFrame,
) -> dict[str, object] | None:
    selected_set = {str(value) for value in selected_ids}
    if selection is None or not selected_set:
        return None

    if len(selected_set) == 1:
        return _mean_comparator_row(indicator_frame(indicator_id, period), label="Average neighbourhood")

    selected_meta = reference[reference["neighbourhood_id"].astype(str).isin(selected_set)].copy()
    full_single_borough_selection, _ = _single_borough_selection(reference, selected_meta)
    if not full_single_borough_selection:
        return None

    borough_rows = load_borough_benchmarks()
    place_rows = borough_rows[
        (borough_rows["indicator_id"] == indicator_id) & (borough_rows["period"].astype(str) == str(period))
    ].copy()
    return _mean_comparator_row(place_rows, label="Average place")


def _average_borough_composition_rows(
    subject_df: pd.DataFrame,
    breakdown_groups: list[dict[str, object]],
    *,
    subject_label: str,
    subject_order: int,
) -> list[dict[str, object]]:
    neighbourhood_rows: list[dict[str, object]] = []
    for neighbourhood_id, neighbourhood_df in subject_df.groupby("neighbourhood_id", dropna=False, sort=True):
        counts_by_group: list[tuple[int, str, float]] = []
        total = 0.0
        for index, group in enumerate(breakdown_groups):
            fields = [field for field in group["fields"] if field in neighbourhood_df.columns]
            if not fields:
                continue
            count = float(neighbourhood_df[fields].apply(pd.to_numeric, errors="coerce").sum().sum())
            counts_by_group.append((index, str(group["label"]), count))
            total += count
        if total <= 0:
            continue
        for category_order, category_label, count in counts_by_group:
            neighbourhood_rows.append(
                {
                    "neighbourhood_id": str(neighbourhood_id),
                    "category": category_label,
                    "category_order": category_order,
                    "share": count / total,
                }
            )
    if not neighbourhood_rows:
        return []
    neighbourhood_frame = pd.DataFrame(neighbourhood_rows)
    averaged = (
        neighbourhood_frame.groupby(["category", "category_order"], dropna=False)["share"]
        .mean()
        .reset_index()
        .sort_values(["category_order", "category"])
    )
    return [
        {
            "subject": subject_label,
            "subject_order": subject_order,
            "subject_kind": "borough_average",
            "category": str(row.category),
            "category_order": int(row.category_order),
            "count": pd.NA,
            "share": float(row.share),
        }
        for row in averaged.itertuples(index=False)
    ]


def _serialise_for_export(frame: pd.DataFrame) -> pd.DataFrame:
    serialised = frame.copy()
    for column in serialised.columns:
        if serialised[column].dtype != "object":
            continue
        if column in CATALOG_VIEW_LIST_COLUMNS:
            serialised[column] = serialised[column].map(
                lambda value: (
                    "|".join(str(item) for item in value if str(item).strip())
                    if isinstance(value, (list, tuple, set))
                    else str(value or "")
                )
            )
            continue
        if not serialised[column].map(lambda value: isinstance(value, (list, dict, tuple, set))).any():
            continue
        serialised[column] = serialised[column].map(
            lambda value: (
                "; ".join(str(item) for item in value)
                if isinstance(value, (list, tuple, set))
                else str(value)
                if isinstance(value, dict)
                else value
            )
        )
    return serialised


def _restore_catalog_export_types(frame: pd.DataFrame) -> pd.DataFrame:
    restored = frame.copy()
    for column in CATALOG_VIEW_LIST_COLUMNS:
        if column not in restored.columns:
            continue
        restored[column] = restored[column].map(
            lambda value: list(value)
            if isinstance(value, list)
            else _parse_view_toggle_text(value)
        )
    if "history_available" in restored.columns:
        restored["history_available"] = restored["history_available"].map(
            lambda value: str(value).strip().lower() in {"true", "1", "yes"}
            if not isinstance(value, bool)
            else value
        )
    return restored


def _catalog_export_missing_guided_live_indicators(frame: pd.DataFrame) -> bool:
    if frame.empty or "indicator_id" not in frame.columns:
        return True
    guidance = load_preferred_indicator_specs()
    if guidance.empty or "indicator_id" not in guidance.columns:
        return False
    current_mask = guidance["currently_in_app"].fillna(False).map(bool)
    exposure_mask = guidance["ui_exposure_level"].astype(str).replace("nan", "standard").str.lower().ne("hidden")
    expected_ids = {
        str(value).strip()
        for value in guidance.loc[current_mask & exposure_mask, "indicator_id"].tolist()
        if str(value).strip()
    }
    if not expected_ids:
        return False
    present_ids = {str(value).strip() for value in frame["indicator_id"].tolist() if str(value).strip()}
    missing_ids = expected_ids - present_ids
    if missing_ids:
        logger.warning(
            "Catalog export missing %s guided live indicator(s); forcing rebuild. Missing ids: %s",
            len(missing_ids),
            ", ".join(sorted(missing_ids)),
        )
    return bool(missing_ids)


@lru_cache(maxsize=1)
def load_catalog_df() -> pd.DataFrame:
    logger.info("Loading indicator catalog")
    required_columns = {
        "category_key",
        "top_level_category",
        "module_label",
        "indicator_sort_order",
        "primary_visualisation",
        "neighbourhood_use_mode",
    }
    needs_export_refresh = False
    if INDICATOR_CATALOG_EXPORT_PATH.exists():
        df = pd.read_parquet(INDICATOR_CATALOG_EXPORT_PATH)
    else:
        df = build_unified_indicator_catalog()
        needs_export_refresh = True
    if df.empty or not required_columns.issubset(set(df.columns)):
        df = build_unified_indicator_catalog()
        needs_export_refresh = True
    has_suffixed_pipeline_columns = any(
        f"{column}_x" in df.columns or f"{column}_y" in df.columns
        for column in CATALOG_PIPELINE_COLUMNS
    )
    has_pipeline_contract = CATALOG_PIPELINE_COLUMNS.issubset(set(df.columns)) and not has_suffixed_pipeline_columns
    if not has_pipeline_contract and not df.empty:
        df = apply_pipeline_contract(df)
        needs_export_refresh = True
    export_version = int(df.get("_catalog_runtime_version", pd.Series([0])).iloc[0]) if not df.empty and "_catalog_runtime_version" in df.columns else 0
    has_runtime_contract = CATALOG_RUNTIME_COLUMNS.issubset(set(df.columns)) and export_version == CATALOG_EXPORT_RUNTIME_VERSION
    if has_runtime_contract:
        df = _restore_catalog_export_types(df)
    elif not df.empty:
        df = apply_visualisation_contract(df)
        df = _apply_minimum_trend_history_contract(df)
        df["_catalog_runtime_version"] = CATALOG_EXPORT_RUNTIME_VERSION
        needs_export_refresh = True
    if df.empty or not required_columns.issubset(set(df.columns)):
        df = build_unified_indicator_catalog()
        if not df.empty:
            df = apply_visualisation_contract(df)
            df = _apply_minimum_trend_history_contract(df)
            df["_catalog_runtime_version"] = CATALOG_EXPORT_RUNTIME_VERSION
            needs_export_refresh = True
    if not df.empty and _catalog_export_missing_guided_live_indicators(df):
        df = build_unified_indicator_catalog()
        if not df.empty:
            df = apply_visualisation_contract(df)
            df = _apply_minimum_trend_history_contract(df)
            df["_catalog_runtime_version"] = CATALOG_EXPORT_RUNTIME_VERSION
            needs_export_refresh = True
    if not df.empty:
        df, breakdown_changed = _apply_derived_breakdown_contract(df)
        df, census_breakdown_changed = _apply_derived_census_breakdown_contract(df)
        df, standalone_map_changed = _apply_standalone_kpi_map_contract(df)
        needs_export_refresh = needs_export_refresh or breakdown_changed or census_breakdown_changed or standalone_map_changed
    if needs_export_refresh and not df.empty:
        _serialise_for_export(df).to_parquet(INDICATOR_CATALOG_EXPORT_PATH, index=False)
    if df.empty:
        return df
    df = drop_overlapping_catalog_metrics(df)
    sort_cols = [
        col
        for col in [
            "category_sort_order",
            "module_sort_order",
            "indicator_sort_order",
            "top_level_category",
            "module_label",
            "ui_title",
            "title",
        ]
        if col in df.columns
    ]
    return df.sort_values(sort_cols).reset_index(drop=True)


def load_public_catalog_df() -> pd.DataFrame:
    return _load_public_catalog_df_cached().copy()


@lru_cache(maxsize=1)
def _load_public_catalog_df_cached() -> pd.DataFrame:
    catalog = load_catalog_df().copy()
    if catalog.empty:
        return catalog
    if "ui_exposure_level" in catalog.columns:
        catalog = catalog[catalog["ui_exposure_level"].astype(str).replace("nan", "standard").str.lower() != "hidden"].copy()
    if {"indicator_id", "qof_metric_kind"}.issubset(catalog.columns):
        non_public_qof_metric_kinds = {"points", "points_raw", "pcas"}
        non_public_qof_mask = (
            catalog["indicator_id"].astype(str).str.startswith("qof_")
            & catalog["qof_metric_kind"].astype(str).fillna("").str.lower().isin(non_public_qof_metric_kinds)
        )
        catalog = catalog[~non_public_qof_mask].copy()
    if "indicator_id" in catalog.columns:
        catalog = catalog[
            ~catalog["indicator_id"].astype(str).str.contains("qipddmi", case=False, na=False)
        ].copy()
        catalog = catalog[
            ~catalog["indicator_id"].astype(str).isin(RUNTIME_HIDDEN_INDICATOR_IDS)
        ].copy()
    if "display_status" in catalog.columns:
        catalog = catalog[catalog["display_status"].astype(str).replace("nan", "public") == "public"].copy()
    if "data_status" in catalog.columns:
        catalog = catalog[catalog["data_status"].astype(str).replace("nan", "available").isin(["available", "cached"])].copy()
    for geography_column in ["geography_level", "geography_type", "source_geography"]:
        if geography_column not in catalog.columns:
            continue
        catalog = catalog[
            ~catalog[geography_column].astype(str).fillna("").str.contains("MSOA", case=False, na=False)
        ].copy()
    catalog = drop_overlapping_catalog_metrics(catalog)
    sort_cols = [
        col
        for col in [
            "category_sort_order",
            "module_sort_order",
            "indicator_sort_order",
            "top_level_category",
            "module_label",
            "ui_title",
            "title",
        ]
        if col in catalog.columns
    ]
    return catalog.sort_values(sort_cols).reset_index(drop=True)


@lru_cache(maxsize=1)
def _catalog_metadata_lookup() -> dict[str, dict[str, object]]:
    catalog = load_catalog_df()
    if catalog.empty or "indicator_id" not in catalog.columns:
        return {}
    lookup: dict[str, dict[str, object]] = {}
    for row in catalog.to_dict(orient="records"):
        indicator_id = str(row.get("indicator_id") or "").strip()
        if indicator_id:
            lookup[indicator_id] = _supplement_indicator_metadata(indicator_id, row)
    return lookup


def _metadata_value_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return str(value).strip().lower() in {"", "nan", "none"}


def _supplement_indicator_metadata(indicator_id: str, metadata: dict[str, object] | None) -> dict[str, object]:
    supplemented = dict(metadata or {})
    configured = _configured_indicator_lookup().get(str(indicator_id), {})
    if not configured:
        return supplemented
    for column in [
        "breakdown_groups_json",
        "numerator_field",
        "numerator_fields",
        "denominator_field",
        "source_key",
        "source_name",
        "aggregation_method",
        "unit",
        "value_field",
    ]:
        if _metadata_value_missing(supplemented.get(column)) and not _metadata_value_missing(configured.get(column)):
            supplemented[column] = configured.get(column)
    return supplemented


@lru_cache(maxsize=1)
def _available_periods_lookup() -> dict[str, tuple[str, ...]]:
    values = load_neighbourhood_indicator_values()
    if values.empty or "indicator_id" not in values.columns or "period" not in values.columns:
        return {}
    return {
        str(indicator_id): tuple(_sort_period_values(group["period"].dropna().astype(str).tolist()))
        for indicator_id, group in values.groupby("indicator_id", dropna=False, observed=False)
    }


def _normalise_selected_ids(selected_ids: list[str] | list[int] | set[int] | set[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip() for value in selected_ids if str(value).strip()}))


def _copy_bundle(bundle: dict[str, object]) -> dict[str, object]:
    copied: dict[str, object] = {}
    for key, value in bundle.items():
        if isinstance(value, pd.DataFrame):
            copied[key] = value.copy()
        elif isinstance(value, dict):
            copied[key] = deepcopy(value)
        else:
            copied[key] = value
    return copied


@lru_cache(maxsize=256)
def _history_indicator_ids(indicator_id: str) -> tuple[str, ...]:
    indicator_id = str(indicator_id).strip()
    if not indicator_id.startswith("qof_"):
        return (indicator_id,)

    catalog = load_catalog_df().copy()
    match = catalog[catalog["indicator_id"].astype(str) == indicator_id]
    if match.empty:
        return (indicator_id,)

    row = match.iloc[0]
    code = str(row.get("qof_indicator_code") or "").strip().upper()
    metric_kind = str(row.get("qof_metric_kind") or "").strip().lower()
    patient_list_type = str(row.get("qof_patient_list_type") or "").strip().upper()
    group_code = str(row.get("qof_group_code") or "").strip().upper()
    if not code or not metric_kind or code not in _QOF_HISTORY_CODE_LOOKUP:
        return (indicator_id,)

    related_codes = set(_QOF_HISTORY_CODE_LOOKUP[code])
    related = catalog[
        catalog["qof_indicator_code"].astype(str).str.upper().isin(related_codes)
        & (catalog["qof_metric_kind"].astype(str).fillna("").str.lower() == metric_kind)
        & (catalog["qof_patient_list_type"].astype(str).fillna("").str.upper() == patient_list_type)
        & (catalog["qof_group_code"].astype(str).fillna("").str.upper() == group_code)
    ].copy()
    if related.empty:
        return (indicator_id,)

    ordered_ids = [indicator_id]
    for related_id in related["indicator_id"].astype(str).tolist():
        if related_id not in ordered_ids:
            ordered_ids.append(related_id)
    return tuple(ordered_ids)


@lru_cache(maxsize=256)
def _timeseries_period_source_map(indicator_id: str) -> tuple[tuple[str, str], ...]:
    ordered_indicator_ids = _history_indicator_ids(indicator_id)
    period_to_indicator: dict[str, str] = {}
    for history_indicator_id in ordered_indicator_ids:
        for period in available_periods(history_indicator_id):
            period_key = str(period).strip()
            if period_key and period_key not in period_to_indicator:
                period_to_indicator[period_key] = str(history_indicator_id)
    ordered_periods = _sort_period_values(list(period_to_indicator))
    return tuple((period, period_to_indicator[period]) for period in ordered_periods)


def _optimise_runtime_text_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    optimised = frame.copy()
    for column in optimised.columns:
        if optimised[column].dtype != "object":
            continue
        # These runtime tables repeat the same labels thousands of times.
        # Categorical storage dramatically reduces per-worker memory use.
        optimised[column] = pd.Categorical(optimised[column].astype(str).fillna(""))
    return optimised


@lru_cache(maxsize=1)
def load_neighbourhood_reference() -> pd.DataFrame:
    logger.info("Loading neighbourhood reference from %s", NEIGHBOURHOOD_REFERENCE_PATH)
    frame = pd.read_parquet(NEIGHBOURHOOD_REFERENCE_PATH)
    frame = _optimise_runtime_text_frame(frame)
    return frame.sort_values(["icb_code", "borough_name", "neighbourhood_name"]).reset_index(drop=True)


@lru_cache(maxsize=2)
def load_map_geography(map_mode: str) -> "gpd.GeoDataFrame":
    import geopandas as gpd

    if map_mode == "hex":
        return gpd.read_file(NEIGHBOURHOOD_HEX_GEOJSON_PATH)
    return gpd.read_file(NEIGHBOURHOOD_BOUNDARIES_GEOJSON_PATH)


@lru_cache(maxsize=1)
def load_hex_icb_geography() -> "gpd.GeoDataFrame":
    import geopandas as gpd

    return gpd.read_file(HEX_ICB_GEOJSON_PATH)


@lru_cache(maxsize=1)
def load_neighbourhood_indicator_values() -> pd.DataFrame:
    frame = pd.read_parquet(NEIGHBOURHOOD_INDICATOR_VALUES_PATH)
    return _optimise_runtime_text_frame(frame)


@lru_cache(maxsize=1)
def load_borough_benchmarks() -> pd.DataFrame:
    frame = pd.read_parquet(BOROUGH_BENCHMARKS_PATH)
    return _optimise_runtime_text_frame(frame)


@lru_cache(maxsize=1)
def load_london_benchmarks() -> pd.DataFrame:
    frame = pd.read_parquet(LONDON_BENCHMARKS_PATH)
    return _optimise_runtime_text_frame(frame)


@lru_cache(maxsize=64)
def _load_indicator_source_frame(source_key: str) -> pd.DataFrame:
    sources = load_sources_config().get("sources", {})
    source_cfg = sources.get(str(source_key), {})
    path = ROOT_DIR / str(source_cfg.get("path", ""))
    if not path.exists() or path.is_dir():
        return pd.DataFrame()
    return pd.read_csv(path)


@lru_cache(maxsize=1)
def _configured_indicator_lookup() -> dict[str, dict[str, object]]:
    lookup: dict[str, dict[str, object]] = {}
    for row in load_indicator_catalog():
        indicator_id = str(row.get("indicator_id") or "").strip()
        if indicator_id:
            lookup[indicator_id] = dict(row)
    return lookup


@lru_cache(maxsize=256)
def _related_census_breakdown_spec(indicator_id: str) -> tuple[list[dict[str, object]], str]:
    configured_meta = _configured_indicator_lookup().get(indicator_id, {})
    try:
        meta = indicator_metadata(indicator_id)
    except KeyError:
        meta = dict(configured_meta)
    source_key = str(meta.get("source_key") or "").strip()
    table_code = _table_code_from_source_key(source_key)
    if not table_code:
        return [], source_key
    catalog = load_catalog_df().copy()
    candidates = catalog[
        catalog["source_key"].astype(str).fillna("").str.contains(table_code, case=False, na=False)
        & catalog["breakdown_groups_json"].astype(str).fillna("").ne("")
    ].copy()
    if not candidates.empty:
        candidates["_priority"] = candidates["source_name"].astype(str).fillna("").map(
            lambda value: 0 if value == "Nomis API" else 1
        )
        candidates = candidates.sort_values(["_priority", "indicator_id"]).reset_index(drop=True)
        for row in candidates.to_dict(orient="records"):
            groups = _parse_breakdown_groups(row.get("breakdown_groups_json"))
            candidate_source_key = str(row.get("source_key") or "").strip()
            if groups and candidate_source_key:
                return groups, candidate_source_key
    for row in _configured_indicator_lookup().values():
        candidate_source_key = str(row.get("source_key") or "").strip()
        if _table_code_from_source_key(candidate_source_key) != table_code:
            continue
        groups = _parse_breakdown_groups(row.get("breakdown_groups_json"))
        if groups and candidate_source_key:
            return groups, candidate_source_key
    return [], source_key


@lru_cache(maxsize=1)
def _crosswalk_breakdown_frame() -> pd.DataFrame:
    return load_crosswalk()[["lsoa21cd", "neighbourhood_id", "borough_name"]].copy()


def indicator_metadata(indicator_id: str) -> dict[str, object]:
    match = _catalog_metadata_lookup().get(str(indicator_id))
    if match is not None:
        return dict(match)
    configured = _configured_indicator_lookup().get(str(indicator_id))
    if configured is not None:
        return _supplement_indicator_metadata(str(indicator_id), configured)
    raise KeyError(f"Unknown indicator_id: {indicator_id}")


def _parse_breakdown_groups(raw: object) -> list[dict[str, object]]:
    if raw is None:
        return []
    if isinstance(raw, list):
        loaded = raw
    else:
        text = str(raw).strip()
        if not text:
            return []
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError:
            return []
    if not isinstance(loaded, list):
        return []

    groups: list[dict[str, object]] = []
    for item in loaded:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()
        fields = [str(field).strip() for field in item.get("fields", []) or [] if str(field).strip()]
        if label and fields:
            groups.append({"label": label, "fields": fields})
    return groups


def _canonical_breakdown_field_name(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"\s*;\s*measures:\s*value\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text.casefold()


def _resolve_breakdown_fields(
    requested_fields: list[object],
    available_columns: pd.Index | list[object],
) -> list[str]:
    column_names = [str(column).strip() for column in available_columns if str(column).strip()]
    if not column_names:
        return []

    exact_lookup = {name: name for name in column_names}
    canonical_lookup: dict[str, str] = {}
    for name in column_names:
        canonical = _canonical_breakdown_field_name(name)
        if canonical and canonical not in canonical_lookup:
            canonical_lookup[canonical] = name

    resolved: list[str] = []
    for field in requested_fields:
        candidate = str(field or "").strip()
        if not candidate:
            continue
        exact_match = exact_lookup.get(candidate)
        if exact_match:
            resolved.append(exact_match)
            continue
        canonical_match = canonical_lookup.get(_canonical_breakdown_field_name(candidate))
        if canonical_match:
            resolved.append(canonical_match)

    return _ordered_unique_strings(resolved)


def available_periods(indicator_id: str) -> list[str]:
    return list(_available_periods_lookup().get(str(indicator_id), ()))


def latest_period(indicator_id: str) -> str | None:
    periods = available_periods(indicator_id)
    return periods[-1] if periods else None


def _police_zero_fill_indicator_frame(indicator_id: str, frame: pd.DataFrame) -> pd.DataFrame:
    indicator_id = str(indicator_id).strip()
    if not indicator_id.startswith("police_") or indicator_id in {
        "police_all_crimes_count",
        POLICE_DENOMINATOR_REFERENCE_INDICATOR_ID,
    }:
        return frame

    values = load_neighbourhood_indicator_values()
    base = values[values["indicator_id"] == POLICE_DENOMINATOR_REFERENCE_INDICATOR_ID].copy()
    if base.empty:
        return frame

    if not frame.empty and "period" in frame.columns:
        base = base[base["period"].astype(str).isin(frame["period"].astype(str).unique().tolist())].copy()
    if base.empty:
        return frame

    meta = indicator_metadata(indicator_id)
    template = frame.iloc[0].to_dict() if not frame.empty else {}
    merged = base.merge(
        frame,
        on=["neighbourhood_id", "period"],
        how="left",
        suffixes=("_base", ""),
    )
    if merged.empty:
        return frame

    base_denominator = pd.to_numeric(merged.get("denominator_base"), errors="coerce")
    merged["numerator"] = pd.to_numeric(merged.get("numerator"), errors="coerce").fillna(0.0)
    merged["record_count"] = pd.to_numeric(merged.get("record_count"), errors="coerce").fillna(0.0)
    merged["denominator"] = pd.to_numeric(merged.get("denominator"), errors="coerce").fillna(base_denominator)
    merged["value"] = pd.to_numeric(merged.get("value"), errors="coerce")

    unit = str(meta.get("unit") or template.get("unit") or "")
    aggregation_method = str(meta.get("aggregation_method") or template.get("aggregation_method") or "")
    if aggregation_method == "recompute_rate_from_numerator_denominator" and unit == "rate_per_1000":
        merged.loc[:, "value"] = merged["value"].fillna(
            (merged["numerator"] / merged["denominator"]).replace([pd.NA, pd.NaT], 0.0) * 1000.0
        )
        merged.loc[merged["denominator"].fillna(0.0) <= 0, "value"] = 0.0
    else:
        merged.loc[:, "value"] = merged["value"].fillna(merged["numerator"])

    for column, default in [
        ("indicator_id", indicator_id),
        ("title", meta.get("title") or template.get("title") or ""),
        ("topic", meta.get("topic") or template.get("topic") or ""),
        ("unit", unit),
        ("aggregation_method", aggregation_method),
        ("benchmark_method", meta.get("benchmark_method") or template.get("benchmark_method") or ""),
        ("source_name", meta.get("source_name") or template.get("source_name") or ""),
        ("source_file_or_api", meta.get("source_file_or_api") or template.get("source_file_or_api") or ""),
        ("source_geography", meta.get("source_geography") or template.get("source_geography") or ""),
        ("geography_version", meta.get("geography_version") or template.get("geography_version") or ""),
        ("source_period", meta.get("source_period") or template.get("source_period") or ""),
        ("polarity", meta.get("polarity") or template.get("polarity") or ""),
        ("caveats", meta.get("caveats") or template.get("caveats") or ""),
        ("review_required", meta.get("review_required") if meta.get("review_required") is not None else template.get("review_required")),
        ("source_key", meta.get("source_key") or template.get("source_key") or ""),
        ("value_field", meta.get("value_field") or template.get("value_field") or ""),
        ("numerator_field", meta.get("numerator_field") or template.get("numerator_field") or ""),
        ("denominator_field", meta.get("denominator_field") or template.get("denominator_field") or ""),
        ("last_refresh_date", meta.get("last_refresh_date") or template.get("last_refresh_date") or ""),
    ]:
        if column not in merged.columns:
            merged[column] = default
        else:
            merged[column] = merged[column].where(merged[column].notna(), default)

    for column in [
        "neighbourhood_name",
        "borough_name",
        "borough_code",
        "borough_count",
        "icb_code",
    ]:
        base_column = f"{column}_base"
        if base_column in merged.columns:
            merged[column] = merged[column].fillna(merged[base_column])

    ordered_columns = [
        column
        for column in load_neighbourhood_indicator_values().columns
        if column in merged.columns
    ]
    if ordered_columns:
        merged = merged[ordered_columns].copy()
    return merged.sort_values(["period", "neighbourhood_id"]).reset_index(drop=True)


@lru_cache(maxsize=256)
def _indicator_frame_all_periods_cached(indicator_id: str) -> pd.DataFrame:
    values = load_neighbourhood_indicator_values()
    frame = values[values["indicator_id"] == str(indicator_id)].copy()
    return _police_zero_fill_indicator_frame(indicator_id, frame)


@lru_cache(maxsize=256)
def _indicator_frame_period_cached(indicator_id: str, period: str) -> pd.DataFrame:
    frame = _indicator_frame_all_periods_cached(indicator_id)
    return frame[frame["period"].astype(str) == str(period)].copy()


def indicator_frame(indicator_id: str, period: str | None = None) -> pd.DataFrame:
    if period is None:
        return _indicator_frame_all_periods_cached(str(indicator_id)).copy()
    return _indicator_frame_period_cached(str(indicator_id), str(period)).copy()


def map_value_frame(indicator_id: str, period: str | None = None) -> pd.DataFrame:
    frame = indicator_frame(indicator_id, period)
    return frame[["neighbourhood_id", "value", "unit", "title", "aggregation_method"]].copy()


def map_indicator_options(category_key: str | None = None) -> pd.DataFrame:
    return _map_indicator_options_cached(None if category_key is None else str(category_key)).copy()


@lru_cache(maxsize=256)
def _map_indicator_options_cached(category_key: str | None = None) -> pd.DataFrame:
    catalog = _load_public_catalog_df_cached().copy()
    if catalog.empty:
        return catalog
    if category_key is not None and "category_key" in catalog.columns:
        catalog = catalog[catalog["category_key"].astype(str) == str(category_key)].copy()
    if "map_allowed" in catalog.columns:
        catalog = catalog[catalog["map_allowed"].fillna(True)]
    return catalog.reset_index(drop=True)


def composition_context_frame(
    indicator_id: str,
    period: str,
    current_ids: list[str] | list[int] | set[int],
    *,
    include_borough: bool = True,
    include_london: bool = True,
) -> pd.DataFrame:
    return _composition_context_frame_cached(
        str(indicator_id),
        str(period),
        _normalise_selected_ids(current_ids),
        bool(include_borough),
        bool(include_london),
    ).copy()


def _aggregate_breakdown_value(
    subject_df: pd.DataFrame,
    *,
    field_name: str,
    aggregation_method: str,
    denominator_field: str,
) -> float | None:
    if field_name not in subject_df.columns:
        return None

    frame = pd.DataFrame({"value": pd.to_numeric(subject_df[field_name], errors="coerce")}).dropna(subset=["value"])
    if frame.empty:
        return None

    if aggregation_method in WEIGHTED_AGGREGATION_METHODS and denominator_field and denominator_field in subject_df.columns:
        frame["denominator"] = pd.to_numeric(subject_df[denominator_field], errors="coerce")
        weighted_frame = frame.dropna(subset=["denominator"]).copy()
        if not weighted_frame.empty and float(weighted_frame["denominator"].sum()) > 0:
            summary = aggregate_records(weighted_frame[["value", "denominator"]], aggregation_method)
            value = summary.get("value")
            return float(value) if value is not None and not pd.isna(value) else None

    mean_value = pd.to_numeric(frame["value"], errors="coerce").dropna()
    if mean_value.empty:
        return None
    return float(mean_value.mean())


@lru_cache(maxsize=256)
def _composition_context_frame_cached(
    indicator_id: str,
    period: str,
    current_ids: tuple[str, ...],
    include_borough: bool,
    include_london: bool,
) -> pd.DataFrame:
    configured_meta = _configured_indicator_lookup().get(indicator_id, {})
    try:
        meta = indicator_metadata(indicator_id)
    except KeyError:
        meta = dict(configured_meta)
    if not meta:
        return pd.DataFrame()
    breakdown_groups = _parse_breakdown_groups(configured_meta.get("breakdown_groups_json"))
    if not breakdown_groups:
        breakdown_groups = _parse_breakdown_groups(meta.get("breakdown_groups_json"))
    breakdown_mode = str(meta.get("breakdown_mode") or "share").strip().lower()
    source_key = str(meta.get("source_key") or "").strip()
    if not breakdown_groups or not source_key or _load_indicator_source_frame(source_key).empty:
        related_groups, related_source_key = _related_census_breakdown_spec(indicator_id)
        if not breakdown_groups and related_groups:
            breakdown_groups = related_groups
        if related_source_key and _load_indicator_source_frame(related_source_key).shape[0] > 0:
            source_key = related_source_key
    if not breakdown_groups or not source_key:
        return pd.DataFrame()

    source_df = _load_indicator_source_frame(source_key).copy()
    if source_df.empty:
        return pd.DataFrame()
    if "geography code" in source_df.columns:
        source_df = source_df.rename(columns={"geography code": "lsoa21cd"}).copy()
    elif "LSOA code (2021)" in source_df.columns:
        source_df = source_df.rename(columns={"LSOA code (2021)": "lsoa21cd"}).copy()
    elif "lsoa21cd" not in source_df.columns:
        return pd.DataFrame()
    source_df["lsoa21cd"] = source_df["lsoa21cd"].astype(str)
    if "date" in source_df.columns:
        dated = source_df[source_df["date"].astype(str) == str(period)].copy()
        if not dated.empty:
            source_df = dated
    elif "period" in source_df.columns:
        dated = source_df[source_df["period"].astype(str) == str(period)].copy()
        if not dated.empty:
            source_df = dated

    crosswalk = _crosswalk_breakdown_frame()
    source_df = source_df.merge(crosswalk, on="lsoa21cd", how="inner")
    if source_df.empty:
        return pd.DataFrame()

    reference = load_neighbourhood_reference()
    selected_set = set(current_ids)
    selected_df = source_df[source_df["neighbourhood_id"].astype(str).isin(selected_set)].copy()
    if selected_df.empty:
        return pd.DataFrame()
    selection_descriptor = resolve_footprint_label(list(selected_set), reference)

    full_single_borough_selection, single_borough_name = _single_borough_selection(reference, reference[reference["neighbourhood_id"].astype(str).isin(selected_set)].copy())
    use_borough_average = full_single_borough_selection and _supports_borough_average(meta.get("aggregation_method"))

    rows: list[dict[str, object]] = []
    selection_subject_label = selection_descriptor.label
    subjects: list[tuple[str, pd.DataFrame, int, str]] = [
        (selection_subject_label, selected_df, 0, "selection")
    ]

    selected_boroughs = _split_borough_names(selected_df["borough_name"])
    if include_borough and len(selected_boroughs) == 1:
        borough_name = selected_boroughs[0]
        borough_df = source_df[_borough_membership_mask(source_df["borough_name"], borough_name)].copy()
        if not borough_df.empty:
            if use_borough_average and borough_name == single_borough_name:
                rows.extend(
                    _average_borough_composition_rows(
                        borough_df,
                        breakdown_groups,
                        subject_label=f"Average of {borough_name} neighbourhoods",
                        subject_order=1,
                    )
                )
            else:
                subjects.append((f"Borough: {borough_name}", borough_df, 1, "borough"))
    if include_london and selection_descriptor.kind != "region":
        subjects.append(("London overall", source_df, 2, "london"))

    aggregation_method = str(meta.get("aggregation_method") or "").strip()
    denominator_field = str(meta.get("denominator_field") or "").strip()
    unit = str(meta.get("unit") or "").strip()
    for subject_label, subject_df, subject_order, subject_kind in subjects:
        if breakdown_mode == "direct_value":
            for group_order, group in enumerate(breakdown_groups):
                fields = _resolve_breakdown_fields(group["fields"], subject_df.columns)
                if not fields:
                    continue
                value = _aggregate_breakdown_value(
                    subject_df,
                    field_name=fields[0],
                    aggregation_method=aggregation_method,
                    denominator_field=denominator_field,
                )
                if value is None or pd.isna(value):
                    continue
                rows.append(
                    {
                        "subject": subject_label,
                        "subject_order": subject_order,
                        "subject_kind": subject_kind,
                        "category": str(group["label"]),
                        "category_order": group_order,
                        "value": value,
                        "unit": unit,
                        "breakdown_mode": breakdown_mode,
                    }
                )
            continue

        counts_by_group: list[tuple[int, str, float]] = []
        total = 0.0
        for index, group in enumerate(breakdown_groups):
            fields = _resolve_breakdown_fields(group["fields"], subject_df.columns)
            if not fields:
                continue
            count = float(subject_df[fields].apply(pd.to_numeric, errors="coerce").sum().sum())
            counts_by_group.append((index, str(group["label"]), count))
            total += count
        if total <= 0:
            continue
        for group_order, group_label, count in counts_by_group:
            rows.append(
                {
                    "subject": subject_label,
                    "subject_order": subject_order,
                    "subject_kind": subject_kind,
                    "category": group_label,
                    "category_order": group_order,
                    "count": count,
                    "share": count / total,
                }
            )

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["subject_order", "category_order"]).reset_index(drop=True)


def selection_aggregate(indicator_id: str, period: str, selected_ids: list[str] | list[int] | set[int]) -> dict[str, object] | None:
    selected_set = {str(x) for x in selected_ids}
    if not selected_set:
        return None
    frame = indicator_frame(indicator_id, period)
    selected = frame[frame["neighbourhood_id"].astype(str).isin(selected_set)].copy()
    if selected.empty:
        return None
    summary = aggregate_records(selected[["value", "numerator", "denominator"]], str(selected.iloc[0]["aggregation_method"]))
    summary["aggregation_method"] = selected.iloc[0]["aggregation_method"]
    summary["title"] = selected.iloc[0]["title"]
    summary["unit"] = selected.iloc[0]["unit"]
    summary["topic"] = selected.iloc[0]["topic"]
    summary["period"] = str(period)
    summary["selected_neighbourhood_count"] = int(selected["neighbourhood_id"].nunique())
    return summary


def ranked_distribution(indicator_id: str, period: str) -> pd.DataFrame:
    return _ranked_distribution_cached(str(indicator_id), str(period)).copy()


@lru_cache(maxsize=256)
def _ranked_distribution_cached(indicator_id: str, period: str) -> pd.DataFrame:
    frame = indicator_frame(indicator_id, period).copy()
    if frame.empty:
        return frame
    frame["rank_desc"] = frame["value"].rank(method="min", ascending=False, na_option="bottom")
    return frame.sort_values(["value", "neighbourhood_name"], ascending=[False, True]).reset_index(drop=True)


def place_ranked_distribution(indicator_id: str, period: str) -> pd.DataFrame:
    return _place_ranked_distribution_cached(str(indicator_id), str(period)).copy()


@lru_cache(maxsize=256)
def _place_ranked_distribution_cached(indicator_id: str, period: str) -> pd.DataFrame:
    """Aggregate neighbourhood values to borough (place) level and return a ranked frame.

    The returned DataFrame uses the same schema as ``ranked_distribution`` so it
    can be passed directly to ``render_ranked_distribution_chart``, with
    ``neighbourhood_id`` containing the borough code and ``neighbourhood_name``
    containing the borough name.
    """
    frame = indicator_frame(indicator_id, period).copy()
    if frame.empty:
        return pd.DataFrame()
    reference = load_neighbourhood_reference()
    if reference.empty or "borough_code" not in reference.columns:
        return pd.DataFrame()

    agg_method = str(frame.iloc[0].get("aggregation_method", "recompute_rate_from_numerator_denominator"))
    unit = str(frame.iloc[0].get("unit", ""))

    ref_subset = (
        reference[["neighbourhood_id", "borough_code", "borough_name"]]
        .drop_duplicates()
        .copy()
    )
    ref_subset["neighbourhood_id"] = ref_subset["neighbourhood_id"].astype(str)
    frame["neighbourhood_id"] = frame["neighbourhood_id"].astype(str)
    merged = frame.merge(ref_subset, on="neighbourhood_id", how="left", suffixes=("", "_reference"))
    borough_code_column = next(
        (
            column
            for column in ("borough_code_reference", "borough_code", "borough_code_y", "borough_code_x")
            if column in merged.columns
        ),
        "",
    )
    borough_name_column = next(
        (
            column
            for column in ("borough_name_reference", "borough_name", "borough_name_y", "borough_name_x")
            if column in merged.columns
        ),
        "",
    )
    if not borough_code_column or not borough_name_column:
        return pd.DataFrame()

    # For neighbourhoods that span multiple boroughs (semicolon-delimited), take first
    merged["borough_code"] = (
        merged[borough_code_column].astype(str).fillna("").str.split(";").str[0].str.strip()
    )
    merged["borough_name"] = (
        merged[borough_name_column].astype(str).fillna("").str.split(";").str[0].str.strip()
    )
    merged = merged[merged["borough_code"].str.len() > 0].copy()
    if merged.empty:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    for (code, name), group in merged.groupby(["borough_code", "borough_name"]):
        try:
            summary = aggregate_records(group[["value", "numerator", "denominator"]], agg_method)
        except Exception:
            continue
        value = summary.get("value")
        if value is None or (isinstance(value, float) and pd.isna(value)):
            continue
        rows.append({
            "neighbourhood_id": str(code),
            "neighbourhood_name": str(name),
            "value": value,
            "numerator": summary.get("numerator"),
            "denominator": summary.get("denominator"),
            "unit": unit,
            "aggregation_method": agg_method,
        })

    if not rows:
        return pd.DataFrame()
    result = pd.DataFrame(rows)
    result["rank_desc"] = result["value"].rank(method="min", ascending=False, na_option="bottom")
    return result.sort_values(["value", "neighbourhood_name"], ascending=[False, True]).reset_index(drop=True)


def borough_codes_for_neighbourhood_ids(
    neighbourhood_ids: list[str] | set[str],
    selected_meta: pd.DataFrame | None = None,
) -> set[str]:
    """Return the set of borough codes for the given neighbourhood IDs."""
    ref = selected_meta if isinstance(selected_meta, pd.DataFrame) and not selected_meta.empty else load_neighbourhood_reference()
    if ref.empty or "borough_code" not in ref.columns:
        return set()
    selected_set = {str(x) for x in neighbourhood_ids}
    rows = ref[ref["neighbourhood_id"].astype(str).isin(selected_set)]
    codes: set[str] = set()
    for code_str in rows["borough_code"].dropna().astype(str):
        for part in code_str.split(";"):
            clean = part.strip()
            if clean:
                codes.add(clean)
    return codes


def indicator_timeseries_bundle(
    indicator_id: str,
    selected_ids: list[str] | list[int] | set[int],
    *,
    include_borough: bool = True,
    include_london: bool = True,
) -> pd.DataFrame:
    return _indicator_timeseries_bundle_cached(
        str(indicator_id),
        _normalise_selected_ids(selected_ids),
        bool(include_borough),
        bool(include_london),
    ).copy()


@lru_cache(maxsize=256)
def _indicator_timeseries_bundle_cached(
    indicator_id: str,
    selected_ids: tuple[str, ...],
    include_borough: bool,
    include_london: bool,
) -> pd.DataFrame:
    period_source_pairs = list(_timeseries_period_source_map(indicator_id))
    if len(period_source_pairs) <= 1:
        return pd.DataFrame()
    reference = load_neighbourhood_reference()
    selection_series_label = footprint_selection_label(selected_ids, reference)
    rows: list[dict[str, object]] = []
    for period, source_indicator_id in period_source_pairs:
        bundle = _comparison_bundle_cached(source_indicator_id, period, selected_ids)
        selection = bundle["selection"]
        if selection is not None:
            rows.append(
                {
                    "period": str(period),
                    "series": selection_series_label,
                    "series_kind": "selection",
                    "value": selection["value"],
                    "unit": selection["unit"],
                }
            )
        if include_borough:
            borough_rows = bundle.get("borough_benchmarks", pd.DataFrame())
            if isinstance(borough_rows, pd.DataFrame) and not borough_rows.empty:
                for row in borough_rows.itertuples(index=False):
                    rows.append(
                        {
                            "period": str(period),
                            "series": str(row.benchmark_name),
                            "series_kind": "borough",
                            "value": float(row.value),
                            "unit": selection["unit"] if selection is not None else None,
                        }
                    )
        if include_london:
            london_rows = bundle.get("london_benchmark", pd.DataFrame())
            if isinstance(london_rows, pd.DataFrame) and not london_rows.empty:
                london_row = london_rows.iloc[0]
                rows.append(
                    {
                        "period": str(period),
                        "series": "London overall",
                        "series_kind": "london",
                        "value": float(london_row["value"]),
                        "unit": selection["unit"] if selection is not None else None,
                    }
                )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def comparison_bundle(indicator_id: str, period: str, selected_ids: list[str] | list[int] | set[int]) -> dict[str, object]:
    return _copy_bundle(
        _comparison_bundle_cached(
            str(indicator_id),
            str(period),
            _normalise_selected_ids(selected_ids),
        )
    )


@lru_cache(maxsize=256)
def _comparison_bundle_cached(
    indicator_id: str,
    period: str,
    selected_ids: tuple[str, ...],
) -> dict[str, object]:
    reference = load_neighbourhood_reference()
    selected_set = set(selected_ids)
    selected_meta = reference[reference["neighbourhood_id"].astype(str).isin(selected_set)].copy()
    selection = selection_aggregate(indicator_id, period, selected_ids)
    borough_benchmarks = load_borough_benchmarks()
    london_benchmarks = load_london_benchmarks()

    bundle: dict[str, object] = {
        "selection": selection,
        "selected_meta": selected_meta,
        "borough_benchmarks": pd.DataFrame(),
        "london_benchmark": pd.DataFrame(),
        "single_borough": False,
        "full_single_borough_selection": False,
    }
    if selection is None:
        return bundle

    if _supports_london_benchmark(selection) and not _selection_resolves_to_region(selected_ids, reference):
        london = london_benchmarks[
            (london_benchmarks["indicator_id"] == indicator_id) & (london_benchmarks["period"].astype(str) == str(period))
        ].copy()
    else:
        london = pd.DataFrame(columns=london_benchmarks.columns)
    bundle["london_benchmark"] = london

    boroughs = _split_borough_names(selected_meta["borough_name"])
    if len(boroughs) == 1:
        bundle["single_borough"] = True
    full_single_borough_selection, single_borough_name = _single_borough_selection(reference, selected_meta)
    bundle["full_single_borough_selection"] = full_single_borough_selection
    borough_rows = borough_benchmarks[
        (borough_benchmarks["indicator_id"] == indicator_id)
        & (borough_benchmarks["period"].astype(str) == str(period))
        & (borough_benchmarks["benchmark_name"].isin(boroughs))
    ].copy()
    if full_single_borough_selection and len(boroughs) == 1:
        if _supports_borough_average(selection.get("aggregation_method")):
            borough_rows = _single_borough_average_row(
                indicator_id,
                period,
                single_borough_name,
                borough_rows,
                reference,
            )
        else:
            borough_rows = pd.DataFrame(columns=borough_rows.columns)
    elif len(boroughs) >= BOROUGH_AVERAGE_THRESHOLD and not borough_rows.empty:
        borough_rows = _average_borough_rows(borough_rows, boroughs)
    bundle["borough_benchmarks"] = borough_rows
    return bundle
