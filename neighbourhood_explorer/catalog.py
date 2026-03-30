from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pandas as pd

from neighbourhood_explorer.config import (
    load_categories_config,
    load_fingertips_curation_config,
    load_indicator_catalog,
    load_visualisations_config,
)
from neighbourhood_explorer.pipeline_contract import apply_pipeline_contract, resolve_indicator_definition


TOPIC_TO_CATEGORY_KEY = {
    "Population": "population_demographics",
    "Deprivation": "poverty_deprivation",
    "Health & Wider Determinants": "health_wellbeing",
    "Safety / Crime": "safety_crime",
}


def _category_rows() -> list[dict[str, object]]:
    categories = load_categories_config().get("categories", [])
    return [dict(row) for row in categories]


def category_frame() -> pd.DataFrame:
    frame = pd.DataFrame(_category_rows())
    if frame.empty:
        return frame
    return frame.sort_values(["sort_order", "label"]).reset_index(drop=True)


def module_frame() -> pd.DataFrame:
    modules = load_categories_config().get("modules", [])
    frame = pd.DataFrame(modules)
    if frame.empty:
        return frame
    return frame.sort_values(["category_key", "sort_order", "label"]).reset_index(drop=True)


def module_lookup_by_indicator() -> dict[str, dict[str, object]]:
    lookup: dict[str, dict[str, object]] = {}
    modules = module_frame()
    for row in modules.itertuples(index=False):
        for indicator_sort_order, indicator_id in enumerate(getattr(row, "indicator_ids", []) or [], start=1):
            lookup[str(indicator_id)] = {
                "module_key": str(row.module_key),
                "module_label": str(row.label),
                "module_description": str(row.description),
                "category_key": str(row.category_key),
                "module_sort_order": int(row.sort_order),
                "indicator_sort_order": int(indicator_sort_order),
            }
    return lookup


def category_lookup() -> dict[str, dict[str, object]]:
    lookup: dict[str, dict[str, object]] = {}
    for row in category_frame().itertuples(index=False):
        lookup[str(row.category_key)] = row._asdict()
    return lookup


def _infer_metric_family(indicator: dict[str, object]) -> str:
    indicator_id = str(indicator.get("indicator_id", ""))
    topic = str(indicator.get("topic", ""))
    unit = str(indicator.get("unit", ""))
    aggregation = str(indicator.get("aggregation_method", ""))
    source_period = str(indicator.get("source_period", "")).lower()

    if indicator_id.startswith("police_"):
        return "crime_count_monthly" if unit == "count" else "crime_rate_monthly"
    if aggregation == "non_additive_display_only":
        return "deprivation_distribution"
    if topic == "Population" and unit == "count":
        return "population_count"
    if topic == "Population":
        return "demographic_share"
    if topic == "Deprivation" and unit == "score":
        return "deprivation_score"
    if topic == "Deprivation":
        return "deprivation_rate"
    if topic == "Health & Wider Determinants":
        if "household" in indicator_id or "car_" in indicator_id:
            return "housing_share"
        if "work" in indicator_id or "unemployment" in indicator_id:
            return "work_share"
        return "health_share"
    if "monthly" in source_period:
        return "crime_rate_monthly"
    return "demographic_share"


def _infer_period_type(indicator: dict[str, object]) -> str:
    source_period = str(indicator.get("source_period", "")).lower()
    if "monthly" in source_period:
        return "monthly"
    if "quarter" in source_period:
        return "quarterly"
    return "snapshot"


def _infer_neighbourhood_use_mode(indicator: dict[str, object]) -> str:
    aggregation = str(indicator.get("aggregation_method", ""))
    if aggregation == "non_additive_display_only":
        return "neighbourhood_estimate_with_caveats"
    return "direct_neighbourhood_candidate"


def _methodology_summary(indicator: dict[str, object]) -> str:
    method = str(indicator.get("aggregation_method", ""))
    source_geography = str(indicator.get("source_geography", ""))
    if method == "sum_counts":
        return f"Built by summing contributing {source_geography} counts inside the selected footprint."
    if method == "recompute_share_from_category_counts":
        return f"Built by summing category counts across contributing {source_geography}s and recomputing the share."
    if method == "recompute_rate_from_numerator_denominator":
        return f"Built by summing numerators and denominators across contributing {source_geography}s and recomputing the rate."
    if method == "weighted_mean":
        return f"Built as a weighted average across contributing {source_geography}s using the configured weight field."
    if method == "population_weighted_mean":
        return f"Built as a population-weighted mean across contributing {source_geography}s."
    if method == "non_additive_display_only":
        return f"Shown as a descriptive summary of the underlying {source_geography} distribution rather than a true additive neighbourhood statistic."
    return f"Built from contributing {source_geography} records using the configured aggregation policy."


def _ui_short_title(title: str) -> str:
    replacements = {
        "Residents reporting ": "",
        "Residents ": "",
        "Households ": "",
        "Recorded ": "",
    }
    short = title
    for old, new in replacements.items():
        short = short.replace(old, new)
    return short


def _enrich_current_indicator(indicator: dict[str, object]) -> dict[str, object]:
    indicator = resolve_indicator_definition(indicator)
    module_map = module_lookup_by_indicator()
    category_map = category_lookup()
    vis_cfg = load_visualisations_config()
    metric_family = _infer_metric_family(indicator)
    module = module_map.get(str(indicator["indicator_id"]), {})
    category_key = str(module.get("category_key") or TOPIC_TO_CATEGORY_KEY.get(str(indicator.get("topic")), "benchmark_context"))
    category = category_map.get(category_key, {})
    vis_defaults = vis_cfg.get("metric_family_defaults", {}).get(metric_family, {})
    vis_overrides = vis_cfg.get("indicator_overrides", {}).get(str(indicator["indicator_id"]), {})
    use_mode = _infer_neighbourhood_use_mode(indicator)

    enriched = dict(indicator)
    enriched.update(
        {
            "source_profile": "",
            "source_domain": "",
            "source_title": str(indicator.get("title", "")),
            "ui_title": str(indicator.get("title", "")),
            "ui_short_title": _ui_short_title(str(indicator.get("title", ""))),
            "description": str(module.get("module_description") or category.get("description") or indicator.get("caveats") or ""),
            "category_key": category_key,
            "top_level_category": str(category.get("label", indicator.get("topic", ""))),
            "subcategory": str(module.get("module_label", indicator.get("topic", ""))),
            "module_key": str(module.get("module_key", "")),
            "module_label": str(module.get("module_label", indicator.get("topic", ""))),
            "module_description": str(module.get("module_description", "")),
            "category_sort_order": int(category.get("sort_order", 999)),
            "module_sort_order": int(module.get("module_sort_order", 999)),
            "indicator_sort_order": int(module.get("indicator_sort_order", 999)),
            "metric_family": metric_family,
            "unit_type": str(indicator.get("unit", "")),
            "geography_level": "neighbourhood",
            "geography_type": "custom_london_neighbourhood",
            "neighbourhood_use_mode": use_mode,
            "aggregation_policy": str(indicator.get("aggregation_method", "")),
            "benchmark_mode": "borough_and_london",
            "period_type": _infer_period_type(indicator),
            "default_sort_order": int(module.get("indicator_sort_order", 999)),
            "display_status": "public",
            "primary_visualisation": str(vis_overrides.get("primary_visualisation") or vis_defaults.get("primary_visualisation") or "benchmark_lollipop"),
            "secondary_visualisation": str(vis_overrides.get("secondary_visualisation") or vis_defaults.get("secondary_visualisation") or "ranked_distribution"),
            "map_allowed": use_mode != "benchmark_only",
            "comparison_allowed": True,
            "trend_allowed": _infer_period_type(indicator) == "monthly",
            "methodology_summary": _methodology_summary(indicator),
            "source_url": "",
            "data_status": "available",
        }
    )
    return enriched


def build_current_indicator_catalog() -> pd.DataFrame:
    raw = load_indicator_catalog()
    rows = [_enrich_current_indicator(indicator) for indicator in raw]
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame = frame.sort_values(
        ["category_sort_order", "module_sort_order", "indicator_sort_order", "top_level_category", "module_label", "ui_title"]
    ).reset_index(drop=True)
    return apply_pipeline_contract(frame)


def build_fingertips_catalog(metadata: pd.DataFrame | None = None) -> pd.DataFrame:
    metadata = metadata.copy() if metadata is not None else pd.DataFrame()
    curation_cfg = load_fingertips_curation_config()
    defaults = curation_cfg.get("curation_defaults", {})
    category_mapping = curation_cfg.get("category_mapping", {})
    category_map = category_lookup()
    rows: list[dict[str, object]] = []

    if metadata.empty:
        return pd.DataFrame(columns=[
            "indicator_id",
            "source_name",
            "source_profile",
            "source_domain",
            "source_title",
            "ui_title",
            "ui_short_title",
            "description",
            "top_level_category",
            "subcategory",
            "metric_family",
            "unit_type",
            "polarity",
            "geography_level",
            "geography_type",
            "neighbourhood_use_mode",
            "aggregation_policy",
            "benchmark_mode",
            "period_type",
            "default_sort_order",
            "display_status",
            "primary_visualisation",
            "secondary_visualisation",
            "map_allowed",
            "comparison_allowed",
            "trend_allowed",
            "methodology_summary",
            "caveats",
            "source_url",
            "last_refresh_date",
            "data_status",
            "category_key",
            "source_geography",
            "geography_version",
        ])

    for row in metadata.to_dict(orient="records"):
        profile_key = str(row.get("profile_key", "")).strip().lower()
        mapped = category_mapping.get(profile_key, {})
        category_key = str(mapped.get("top_level_category", "benchmark_context"))
        category = category_map.get(category_key, {})
        indicator_id = str(row.get("indicator_id") or row.get("IndicatorId") or "")
        title = str(row.get("indicator_name") or row.get("IndicatorName") or row.get("title") or indicator_id)
        rows.append(
            {
                "indicator_id": indicator_id,
                "title": title,
                "source_name": defaults.get("source_name", "OHID Fingertips"),
                "source_profile": str(row.get("profile_name") or defaults.get("source_profile", "")),
                "source_domain": str(row.get("domain_name") or row.get("domain") or ""),
                "source_title": title,
                "ui_title": title,
                "ui_short_title": title,
                "description": str(row.get("definition") or row.get("description") or ""),
                "category_key": category_key,
                "top_level_category": str(category.get("label", "Benchmark Context")),
                "subcategory": str(mapped.get("subcategory", "Fingertips review queue")),
                "metric_family": "benchmark_context",
                "unit_type": str(row.get("unit") or row.get("unit_type") or ""),
                "polarity": str(row.get("polarity") or ""),
                "source_geography": str(row.get("area_type") or row.get("geography_type") or ""),
                "geography_version": "",
                "geography_level": str(row.get("area_type") or row.get("geography_type") or ""),
                "geography_type": str(row.get("area_type") or row.get("geography_type") or ""),
                "neighbourhood_use_mode": str(row.get("neighbourhood_use_mode") or defaults.get("neighbourhood_use_mode", "hidden_for_now")),
                "aggregation_policy": str(row.get("aggregation_policy") or ""),
                "benchmark_mode": str(row.get("benchmark_mode") or defaults.get("benchmark_mode", "benchmark_context")),
                "period_type": str(row.get("period_type") or "snapshot"),
                "default_sort_order": int(category.get("sort_order", 999)),
                "display_status": str(row.get("display_status") or defaults.get("display_status", "hidden_for_now")),
                "primary_visualisation": str(row.get("primary_visualisation") or "benchmark_lollipop"),
                "secondary_visualisation": str(row.get("secondary_visualisation") or "ranked_distribution"),
                "map_allowed": bool(row.get("map_allowed", defaults.get("map_allowed", False))),
                "comparison_allowed": bool(row.get("comparison_allowed", defaults.get("comparison_allowed", True))),
                "trend_allowed": bool(row.get("trend_allowed", defaults.get("trend_allowed", False))),
                "methodology_summary": str(row.get("methodology_summary") or "Requires review before public use."),
                "caveats": str(row.get("caveats") or "Fingertips metadata retained for curation; not currently surfaced publicly."),
                "source_url": str(row.get("source_url") or ""),
                "last_refresh_date": str(row.get("last_refresh_date") or ""),
                "data_status": "metadata_only",
            }
        )

    return pd.DataFrame(rows)


def build_unified_indicator_catalog(
    *,
    fingertips_metadata: pd.DataFrame | None = None,
) -> pd.DataFrame:
    current = build_current_indicator_catalog()
    fingertips = build_fingertips_catalog(fingertips_metadata)
    if fingertips.empty:
        return current
    combined = pd.concat([current, fingertips], ignore_index=True, sort=False)
    combined = combined.sort_values(
        ["category_sort_order", "module_sort_order", "indicator_sort_order", "top_level_category", "subcategory", "ui_title"]
    ).reset_index(drop=True)
    return apply_pipeline_contract(combined)


def category_modules(catalog_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    modules = defaultdict(list)
    if catalog_df.empty:
        return {}
    for row in catalog_df.to_dict(orient="records"):
        key = str(row.get("module_key") or row.get("subcategory") or row.get("category_key"))
        modules[key].append(row)
    return {
        key: pd.DataFrame(rows).sort_values(["default_sort_order", "ui_title"]).reset_index(drop=True)
        for key, rows in modules.items()
    }
