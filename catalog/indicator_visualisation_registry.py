from __future__ import annotations

from functools import lru_cache
import re
from typing import Any

import pandas as pd

from neighbourhood_explorer.paths import INDICATOR_VISUALISATION_GUIDANCE_PATH, QOF_INDICATOR_CATALOG_PATH


REQUIRED_COLUMNS = {
    "inventory_item_id",
    "indicator_id",
    "ui_title",
    "short_title",
    "category_final",
    "subcategory_final",
    "ui_exposure_level",
    "default_view",
    "primary_visual_final",
    "secondary_visual_final",
    "view_toggle_options_compact",
    "view_toggle_options_full",
}

PUBLIC_EXPOSURE_LEVELS = ["core", "standard"]
EXPOSURE_ORDER = {"core": 0, "standard": 1, "advanced": 2, "hidden": 3}
CATEGORY_ORDER = [
    "Population & Demography",
    "Health & Wellbeing",
    "Social Factors & Wider Determinants",
    "Safety & Crime",
    "Environment & Access",
]
_CATEGORY_ORDER_LOOKUP = {label: index for index, label in enumerate(CATEGORY_ORDER, start=1)}
INDICATOR_RUNTIME_OVERRIDES: dict[str, dict[str, object]] = {
    "nomis_population_total": {
        "default_view": "choropleth_map",
        "primary_visual_final": "choropleth_map",
        "secondary_visual_final": "sorted_bar",
        "view_toggle_options_compact": "choropleth_map|sorted_bar",
        "view_toggle_options_full": "choropleth_map|sorted_bar",
        "map_view_final": "choropleth_map",
        "comparison_view": "sorted_bar",
        "distribution_view": "",
        "composition_view": "",
    },
    "nomis_communal_establishment_share": {
        "ui_exposure_level": "hidden",
        "currently_in_app": False,
    },
}


def _clean_text(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _slugify(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _clean_text(value).lower()).strip("_")


def _parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = _clean_text(value).lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n", ""}:
        return False
    return bool(value)


def _parse_view_list(value: object) -> list[str]:
    parts: list[str] = []
    for raw in _clean_text(value).split("|"):
        item = raw.strip()
        if not item or item.lower() in {"none", "nan"}:
            continue
        if item not in parts:
            parts.append(item)
    return parts


def _candidate_priority(value: object) -> int:
    lookup = {
        "include_in_tiered_nav": 0,
        "currently_in_app": 0,
        "recommended_mvp": 1,
        "recommended_phase2": 2,
        "maybe_later": 3,
        "exclude_for_now": 4,
    }
    return lookup.get(_clean_text(value), 9)


def _normalise_registry(df: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            "indicator_visualisation_guidance_final.csv is missing required columns: "
            + ", ".join(sorted(missing))
        )

    registry = df.copy()
    for column in registry.columns:
        if registry[column].dtype == "object":
            registry[column] = registry[column].map(_clean_text)

    registry["currently_in_app"] = registry["currently_in_app"].map(_parse_bool)
    registry["ui_exposure_level"] = registry["ui_exposure_level"].str.lower().replace("", "standard")
    registry["category_final"] = registry["category_final"].replace("", pd.NA).fillna(registry["category"])
    registry["subcategory_final"] = registry["subcategory_final"].replace("", pd.NA).fillna(registry["subcategory"])
    registry["ui_title"] = registry["ui_title"].replace("", pd.NA).fillna(registry["indicator_title"] if "indicator_title" in registry.columns else registry["indicator_id"])
    registry["short_title"] = registry["short_title"].replace("", pd.NA).fillna(registry["ui_title"])
    registry["default_view"] = registry["default_view"].replace("", pd.NA).fillna(registry["primary_visual_final"])
    registry["primary_visual_final"] = registry["primary_visual_final"].replace("", pd.NA).fillna(registry["default_view"])
    registry["secondary_visual_final"] = registry["secondary_visual_final"].replace("", pd.NA)
    registry["category_key"] = registry["category_final"].map(_slugify)
    registry["subcategory_key"] = registry["subcategory_final"].map(_slugify)
    registry["category_sort_order"] = registry["category_final"].map(
        lambda value: _CATEGORY_ORDER_LOOKUP.get(str(value), len(CATEGORY_ORDER) + 100)
    )
    registry["subcategory_sort_order"] = (
        registry.groupby(["category_final", "subcategory_final"], dropna=False, sort=False).ngroup() + 1
    )
    registry["compact_view_list"] = registry["view_toggle_options_compact"].map(_parse_view_list)
    registry["full_view_list"] = registry["view_toggle_options_full"].map(_parse_view_list)
    registry["available_view_list"] = registry.apply(_resolve_available_views, axis=1)
    registry["module_bundle_view"] = registry["module_bundle_view"].replace("", pd.NA)
    registry["history_available"] = registry.get("history_available", False).map(_parse_bool) if "history_available" in registry.columns else False
    return registry


def _resolve_available_views(row: pd.Series) -> list[str]:
    views: list[str] = []
    for value in [
        row.get("default_view"),
        row.get("primary_visual_final"),
        row.get("secondary_visual_final"),
        row.get("comparison_view"),
        row.get("trend_view"),
        row.get("map_view_final"),
        row.get("distribution_view"),
        row.get("composition_view"),
    ]:
        for item in _parse_view_list(value):
            if item not in views:
                views.append(item)
    for item in row.get("compact_view_list", []):
        if item not in views:
            views.append(item)
    for item in row.get("full_view_list", []):
        if item not in views:
            views.append(item)
    return views


def _apply_runtime_overrides(registry: pd.DataFrame) -> pd.DataFrame:
    if registry.empty or "indicator_id" not in registry.columns:
        return registry
    adjusted = registry.copy()
    for indicator_id, overrides in INDICATOR_RUNTIME_OVERRIDES.items():
        mask = adjusted["indicator_id"].astype(str) == str(indicator_id)
        if not mask.any():
            continue
        for column, value in overrides.items():
            adjusted.loc[mask, column] = value
    if "view_toggle_options_compact" in adjusted.columns:
        adjusted["compact_view_list"] = adjusted["view_toggle_options_compact"].map(_parse_view_list)
    if "view_toggle_options_full" in adjusted.columns:
        adjusted["full_view_list"] = adjusted["view_toggle_options_full"].map(_parse_view_list)
    adjusted["available_view_list"] = adjusted.apply(_resolve_available_views, axis=1)
    return adjusted


def _normalise_public_category(category: object, module_label: object) -> str:
    return _clean_text(category)


@lru_cache(maxsize=1)
def load_visualisation_registry() -> pd.DataFrame:
    registry = pd.read_csv(INDICATOR_VISUALISATION_GUIDANCE_PATH)
    return _apply_runtime_overrides(_normalise_registry(registry))


@lru_cache(maxsize=1)
def load_preferred_indicator_specs() -> pd.DataFrame:
    registry = load_visualisation_registry().copy()
    registry = registry.sort_values(
        by=[
            "indicator_id",
            "currently_in_app",
            "ui_exposure_level",
            "api_candidate_status",
            "inventory_item_id",
        ],
        ascending=[True, False, True, True, True],
        key=lambda series: (
            series.map(EXPOSURE_ORDER)
            if series.name == "ui_exposure_level"
            else series.map(_candidate_priority)
            if series.name == "api_candidate_status"
            else series
        ),
    )
    return registry.drop_duplicates(subset=["indicator_id"], keep="first").reset_index(drop=True)


@lru_cache(maxsize=1)
def _qof_group_lookup() -> dict[str, str]:
    if not QOF_INDICATOR_CATALOG_PATH.exists():
        return {}
    frame = pd.read_csv(QOF_INDICATOR_CATALOG_PATH, usecols=["indicator_id", "qof_group_description"])
    frame["indicator_id"] = frame["indicator_id"].map(_clean_text)
    frame["qof_group_description"] = frame["qof_group_description"].map(_clean_text)
    frame = frame[frame["indicator_id"].ne("") & frame["qof_group_description"].ne("")]
    return dict(zip(frame["indicator_id"], frame["qof_group_description"]))


def template_names() -> list[str]:
    names: set[str] = set()
    registry = load_visualisation_registry()
    for column in [
        "default_view",
        "primary_visual_final",
        "secondary_visual_final",
        "module_bundle_view",
        "comparison_view",
        "trend_view",
        "map_view_final",
        "distribution_view",
        "composition_view",
    ]:
        for value in registry[column].dropna().astype(str):
            names.update(_parse_view_list(value))
    for column in ["compact_view_list", "full_view_list"]:
        for values in registry[column]:
            names.update(values)
    return sorted(item for item in names if item)


def _filter_registry(
    *,
    exposure_levels: list[str] | None = None,
    available_indicator_ids: list[str] | None = None,
) -> pd.DataFrame:
    registry = load_preferred_indicator_specs().copy()
    if available_indicator_ids is not None:
        allowed = {str(value) for value in available_indicator_ids}
        registry = registry[registry["indicator_id"].astype(str).isin(allowed)].copy()
    levels = [str(value).lower() for value in (exposure_levels or []) if str(value).strip()]
    if levels:
        registry = registry[registry["ui_exposure_level"].isin(levels)].copy()
    return registry.reset_index(drop=True)


def get_categories(
    exposure_levels: list[str] | None = None,
    available_indicator_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    registry = _filter_registry(exposure_levels=exposure_levels, available_indicator_ids=available_indicator_ids)
    if registry.empty:
        return []
    counts = registry.groupby("category_final")["indicator_id"].nunique().to_dict()
    categories = (
        registry[["category_final", "category_key", "category_sort_order"]]
        .drop_duplicates()
        .sort_values(["category_sort_order", "category_final"])
    )
    return [
        {
            "category": str(row.category_final),
            "category_key": str(row.category_key),
            "count": int(counts.get(row.category_final, 0)),
            "sort_order": int(row.category_sort_order),
        }
        for row in categories.itertuples(index=False)
    ]


def get_subcategories(
    category: str,
    exposure_levels: list[str] | None = None,
    available_indicator_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    registry = _filter_registry(exposure_levels=exposure_levels, available_indicator_ids=available_indicator_ids)
    registry = registry[registry["category_final"] == str(category)].copy()
    if registry.empty:
        return []
    counts = registry.groupby("subcategory_final")["indicator_id"].nunique().to_dict()
    subcategories = (
        registry[["subcategory_final", "subcategory_key", "subcategory_sort_order"]]
        .drop_duplicates()
        .sort_values(["subcategory_sort_order", "subcategory_final"])
    )
    return [
        {
            "subcategory": str(row.subcategory_final),
            "subcategory_key": str(row.subcategory_key),
            "count": int(counts.get(row.subcategory_final, 0)),
            "sort_order": int(row.subcategory_sort_order),
        }
        for row in subcategories.itertuples(index=False)
    ]


def get_indicators(
    category: str,
    subcategory: str,
    exposure_levels: list[str] | None = None,
    available_indicator_ids: list[str] | None = None,
) -> pd.DataFrame:
    registry = _filter_registry(exposure_levels=exposure_levels, available_indicator_ids=available_indicator_ids)
    registry = registry[
        (registry["category_final"] == str(category))
        & (registry["subcategory_final"] == str(subcategory))
    ].copy()
    if registry.empty:
        return registry
    registry["exposure_sort_order"] = registry["ui_exposure_level"].map(EXPOSURE_ORDER).fillna(9)
    return registry.sort_values(["exposure_sort_order", "ui_title", "indicator_id"]).reset_index(drop=True)


def get_indicator_spec(indicator_id: str) -> dict[str, Any]:
    registry = load_preferred_indicator_specs()
    match = registry[registry["indicator_id"].astype(str) == str(indicator_id)]
    if match.empty:
        raise KeyError(f"Indicator not found in visualisation registry: {indicator_id}")
    return match.iloc[0].to_dict()


def get_default_view(indicator_id: str) -> str:
    return str(get_indicator_spec(indicator_id).get("default_view") or "")


def get_compact_views(indicator_id: str) -> list[str]:
    spec = get_indicator_spec(indicator_id)
    views = list(spec.get("compact_view_list") or [])
    default_view = str(spec.get("default_view") or "")
    if default_view and default_view not in views:
        views.insert(0, default_view)
    return views


def get_full_views(indicator_id: str) -> list[str]:
    spec = get_indicator_spec(indicator_id)
    views = list(spec.get("full_view_list") or [])
    default_view = str(spec.get("default_view") or "")
    if default_view and default_view not in views:
        views.insert(0, default_view)
    return views


def get_bundle_view(indicator_id: str) -> str | None:
    value = _clean_text(get_indicator_spec(indicator_id).get("module_bundle_view"))
    return value or None


def get_tier(indicator_id: str) -> str:
    return str(get_indicator_spec(indicator_id).get("ui_exposure_level") or "standard")


def apply_visualisation_contract(catalog_df: pd.DataFrame) -> pd.DataFrame:
    if catalog_df.empty:
        return catalog_df

    guidance = load_preferred_indicator_specs().copy()
    merge_cols = [
        "indicator_id",
        "ui_title",
        "short_title",
        "category_final",
        "subcategory_final",
        "ui_exposure_level",
        "default_view",
        "primary_visual_final",
        "secondary_visual_final",
        "module_bundle_view",
        "view_toggle_options_compact",
        "view_toggle_options_full",
        "comparison_view",
        "benchmark_style",
        "comparator_note",
        "trend_view",
        "trend_note",
        "map_view_final",
        "map_role",
        "map_note",
        "distribution_view",
        "composition_view",
        "axis_guidance",
        "labelling_guidance",
        "accessibility_guidance",
        "misinterpretation_risks",
        "visual_rationale",
        "direction_hint",
        "history_available",
        "available_view_list",
        "category_key",
        "subcategory_key",
        "category_sort_order",
        "subcategory_sort_order",
    ]
    merged = catalog_df.merge(
        guidance[merge_cols],
        on="indicator_id",
        how="left",
        suffixes=("", "_guidance"),
    )

    merged["top_level_category"] = merged["category_final"].replace("", pd.NA).fillna(merged["top_level_category"])
    merged["module_label"] = merged["subcategory_final"].replace("", pd.NA).fillna(merged.get("module_label", ""))
    merged["subcategory"] = merged["subcategory_final"].replace("", pd.NA).fillna(merged.get("subcategory", ""))
    qof_mask = merged["indicator_id"].astype(str).str.startswith("qof_")
    qof_groups = merged.loc[qof_mask, "indicator_id"].astype(str).map(_qof_group_lookup())
    merged.loc[qof_mask, "module_label"] = qof_groups.fillna(merged.loc[qof_mask, "module_label"]).map(
        lambda value: _clean_text(value).removeprefix("QOF: ")
    )
    merged.loc[qof_mask, "subcategory"] = merged.loc[qof_mask, "module_label"]
    merged["top_level_category"] = merged.apply(
        lambda row: _normalise_public_category(row.get("top_level_category"), row.get("module_label")),
        axis=1,
    )
    merged["category_key"] = merged["top_level_category"].map(_slugify)
    merged["module_key"] = merged["subcategory_key"].replace("", pd.NA).fillna(
        merged["module_label"].map(_slugify)
    )
    merged["category_sort_order"] = merged["top_level_category"].map(
        lambda value: _CATEGORY_ORDER_LOOKUP.get(str(value), len(CATEGORY_ORDER) + 100)
    )
    existing_module_sort_order = pd.to_numeric(merged.get("module_sort_order"), errors="coerce")
    merged["module_sort_order"] = existing_module_sort_order.fillna(merged["subcategory_sort_order"]).fillna(999).astype(int)
    if "indicator_sort_order" in merged.columns:
        merged["indicator_sort_order"] = pd.to_numeric(merged["indicator_sort_order"], errors="coerce").fillna(999).astype(int)
    else:
        merged["indicator_sort_order"] = 999
    merged["ui_title"] = merged["ui_title_guidance"].replace("", pd.NA).fillna(merged.get("ui_title", merged.get("title", "")))
    merged["ui_short_title"] = merged["short_title"].replace("", pd.NA).fillna(merged.get("ui_short_title", merged["ui_title"]))
    merged["default_view"] = merged["default_view"].replace("", pd.NA).fillna(merged.get("primary_visualisation", "benchmark_lollipop"))
    merged["primary_visualisation"] = merged["primary_visual_final"].replace("", pd.NA).fillna(merged["default_view"])
    merged["secondary_visualisation"] = merged["secondary_visual_final"].replace("", pd.NA).fillna(
        merged.get("secondary_visualisation", "")
    )
    merged["ui_exposure_level"] = merged["ui_exposure_level"].replace("", pd.NA).fillna("standard")
    merged = _apply_runtime_overrides(merged)
    if "map_allowed" in merged.columns:
        merged["map_allowed"] = (
            merged["map_view_final"]
            .astype(str)
            .fillna("")
            .str.strip()
            .str.lower()
            .isin({"choropleth_map"})
        ) | merged["map_allowed"].fillna(False)
    return merged.sort_values(
        ["category_sort_order", "module_sort_order", "indicator_sort_order", "ui_exposure_level", "ui_title", "indicator_id"],
        key=lambda series: series.map(EXPOSURE_ORDER) if series.name == "ui_exposure_level" else series,
    ).reset_index(drop=True)
