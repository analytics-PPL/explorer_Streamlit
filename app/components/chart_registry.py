from __future__ import annotations

from copy import deepcopy
from functools import lru_cache

import pandas as pd
import streamlit as st

from app.components.chart_template_registry import available_template_names, render_template
from app.components.interface_semantics import build_comparator_context
from app.components.layout import render_empty_state
from neighbourhood_explorer.data_access import (
    borough_codes_for_neighbourhood_ids,
    comparison_bundle,
    composition_context_frame,
    indicator_frame,
    indicator_metadata,
    indicator_timeseries_bundle,
    load_neighbourhood_reference,
    map_value_frame,
    place_ranked_distribution,
    ranked_distribution,
)
from neighbourhood_explorer.footprints import resolve_footprint_label


def indicator_detail_frame(indicator_id: str, period: str, current_ids: list[str]) -> pd.DataFrame:
    return _indicator_detail_frame_cached(
        str(indicator_id),
        str(period),
        _normalise_current_ids(current_ids),
    ).copy()


@lru_cache(maxsize=None)
def _indicator_detail_frame_cached(indicator_id: str, period: str, current_ids: tuple[str, ...]) -> pd.DataFrame:
    frame = indicator_frame(indicator_id, period).copy()
    if not current_ids:
        return frame
    selected_set = set(current_ids)
    return frame[frame["neighbourhood_id"].astype(str).isin(selected_set)].copy()


def _normalise_current_ids(current_ids: list[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip() for value in current_ids if str(value).strip()}))


def _copy_visual_context_payload(payload: dict[str, object]) -> dict[str, object]:
    copied: dict[str, object] = {}
    for key, value in payload.items():
        if isinstance(value, pd.DataFrame):
            copied[key] = value.copy()
        elif isinstance(value, dict):
            copied[key] = deepcopy(value)
        elif isinstance(value, list):
            copied[key] = list(value)
        elif isinstance(value, set):
            copied[key] = set(value)
        else:
            copied[key] = value
    return copied


@lru_cache(maxsize=None)
def _cached_indicator_visual_payload(
    indicator_id: str,
    period: str,
    current_ids: tuple[str, ...],
    include_borough: bool,
    include_london: bool,
) -> dict[str, object]:
    bundle = comparison_bundle(indicator_id, period, list(current_ids))
    selection = bundle["selection"]
    selection_descriptor = resolve_footprint_label(list(current_ids), load_neighbourhood_reference())
    effective_include_london = bool(include_london) and selection_descriptor.kind != "region"
    borough_benchmarks = bundle["borough_benchmarks"] if include_borough else pd.DataFrame()
    london_benchmark = bundle["london_benchmark"] if effective_include_london else pd.DataFrame()
    comparator_context = build_comparator_context(
        selection=selection if isinstance(selection, dict) else None,
        selection_label=selection_descriptor.label,
        selection_kind=selection_descriptor.kind,
        selection_is_plural=selection_descriptor.is_plural,
        selected_area_count=int(selection.get("selected_neighbourhood_count", len(current_ids))) if isinstance(selection, dict) else len(current_ids),
        exact_boundary=selection_descriptor.exact_boundary,
        borough_df=borough_benchmarks,
        london_df=london_benchmark,
    )
    return {
        "indicator_id": str(indicator_id),
        "period": str(period),
        "current_ids": list(current_ids),
        "selection": selection,
        "bundle": bundle,
        "selected_meta": bundle["selected_meta"],
        "borough_benchmarks": borough_benchmarks,
        "london_benchmark": london_benchmark,
        "single_borough": bool(bundle.get("single_borough", False)),
        "timeseries_df": indicator_timeseries_bundle(
            indicator_id,
            list(current_ids),
            include_borough=include_borough,
            include_london=effective_include_london,
        ),
        "ranked_df": ranked_distribution(indicator_id, period),
        "place_ranked_df": place_ranked_distribution(indicator_id, period) if selection_descriptor.kind == "place" else pd.DataFrame(),
        "place_selected_codes": borough_codes_for_neighbourhood_ids(list(current_ids), bundle.get("selected_meta")) if selection_descriptor.kind == "place" else set(),
        "detail_df": indicator_detail_frame(indicator_id, period, list(current_ids)),
        "map_values": map_value_frame(indicator_id, period),
        "composition_df": composition_context_frame(
            indicator_id,
            period,
            list(current_ids),
            include_borough=include_borough,
            include_london=effective_include_london,
        ),
        "comparison_loader": comparison_bundle,
        "selection_label": selection_descriptor.label,
        "selection_object_phrase": selection_descriptor.object_phrase,
        "selection_is_plural": selection_descriptor.is_plural,
        "selection_kind": selection_descriptor.kind,
        "selection_exact_boundary": selection_descriptor.exact_boundary,
        "comparator_context": comparator_context,
    }


def build_indicator_visual_context(
    *,
    indicator_id: str,
    period: str,
    current_ids: list[str],
    include_borough: bool,
    include_london: bool,
    meta: dict[str, object] | None = None,
    subcategory_catalog: pd.DataFrame | None = None,
) -> dict[str, object]:
    meta = meta or indicator_metadata(indicator_id)
    payload = _copy_visual_context_payload(
        _cached_indicator_visual_payload(
            str(indicator_id),
            str(period),
            _normalise_current_ids(current_ids),
            bool(include_borough),
            bool(include_london),
        )
    )
    selection = payload["selection"]
    unit = (
        selection.get("unit")
        if isinstance(selection, dict)
        else meta.get("unit")
        or meta.get("unit_type")
        or None
    )
    payload.update({
        "meta": meta,
        "subcategory_catalog": subcategory_catalog.copy() if isinstance(subcategory_catalog, pd.DataFrame) else pd.DataFrame(),
        "unit": unit,
    })
    return payload


def render_indicator_view(view_name: str, context: dict[str, object]) -> bool:
    template_name = str(view_name or "").strip()
    if not template_name or template_name == "none":
        return False
    if template_name not in available_template_names():
        render_empty_state("This chart view is not available yet.")
        return False
    render_count = int(context.get("_render_instance_count", 0))
    context["_render_instance_count"] = render_count + 1
    context["_render_instance_key"] = render_count
    render_template(template_name, context)
    return True


def render_primary_visual(
    meta: dict[str, object],
    *,
    indicator_id: str,
    period: str,
    current_ids: list[str],
    include_borough: bool,
    include_london: bool,
    view_name: str | None = None,
    subcategory_catalog: pd.DataFrame | None = None,
) -> dict[str, object]:
    context = build_indicator_visual_context(
        indicator_id=indicator_id,
        period=period,
        current_ids=current_ids,
        include_borough=include_borough,
        include_london=include_london,
        meta=meta,
        subcategory_catalog=subcategory_catalog,
    )
    template_name = (
        str(view_name or "").strip()
        or str(meta.get("default_view") or "").strip()
        or str(meta.get("primary_visualisation") or "").strip()
        or "benchmark_lollipop"
    )
    render_indicator_view(template_name, context)
    return context
