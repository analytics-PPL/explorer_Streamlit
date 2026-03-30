from __future__ import annotations

import pandas as pd

from app.components.interface_semantics import build_comparator_context, format_comparison_narrative
from app.components.formatting import system_name
from neighbourhood_explorer.footprints import resolve_footprint_label

BOROUGH_AVERAGE_THRESHOLD = 4


def selection_context_summary(reference_df: pd.DataFrame, selected_ids: list[str]) -> str:
    if not selected_ids:
        return "No footprint is selected yet."
    selected = reference_df[reference_df["neighbourhood_id"].astype(str).isin({str(value) for value in selected_ids})].copy()
    if selected.empty:
        return "No geography metadata are available for the current selection."
    descriptor = resolve_footprint_label(selected_ids, reference_df)

    boroughs: list[str] = []
    for raw in selected["borough_name"].dropna().astype(str):
        boroughs.extend([item.strip() for item in raw.split(";") if item.strip()])
    unique_boroughs = sorted(set(boroughs))

    if descriptor.kind == "region":
        return "The explorer is currently focused on London, so London-wide context is shown directly across the full region."
    if descriptor.kind == "system":
        if descriptor.item_count == 1:
            return (
                f"The explorer is currently focused on the {descriptor.label} system footprint, "
                f"covering {len(unique_boroughs)} borough{'s' if len(unique_boroughs) != 1 else ''}."
            )
        return (
            f"The current footprint combines {descriptor.item_count} London systems across {len(unique_boroughs)} boroughs. "
            "London remains comparable, and borough context is shown where it is still meaningful."
        )
    if descriptor.kind == "place":
        if descriptor.item_count == 1:
            row = selected.iloc[0]
            return (
                f"The explorer is currently focused on {descriptor.label}. "
                f"It also sits within the {system_name(row['icb_code'])} system footprint."
            )
        return (
            f"The current footprint combines {descriptor.label if descriptor.item_count <= 2 else f'{descriptor.item_count} places'} "
            f"across {len(unique_boroughs)} boroughs. London remains comparable, and borough context is shown where it is still meaningful."
        )
    if len(selected_ids) == 1:
        row = selected.iloc[0]
        return (
            f"The explorer is currently focused on {row['neighbourhood_name']} in {row['borough_name']}. "
            f"It also sits within the {system_name(row['icb_code'])} system footprint."
        )
    if len(unique_boroughs) == 1:
        return (
            f"The current footprint combines {len(selected_ids)} neighbourhoods within {unique_boroughs[0]}, "
            "so borough and London comparisons can be shown side by side."
        )
    if len(unique_boroughs) >= BOROUGH_AVERAGE_THRESHOLD:
        return (
            f"The current footprint combines {len(selected_ids)} neighbourhoods across {len(unique_boroughs)} boroughs. "
            "London is still comparable, and the borough comparator is shown as an average of those boroughs."
        )
    return (
        f"The current footprint combines {len(selected_ids)} neighbourhoods across {len(unique_boroughs)} boroughs. "
        "London is still comparable, and the relevant borough benchmarks are shown alongside the selection."
    )


def category_summary_text(category_label: str, indicator_count: int, module_count: int) -> str:
    if category_label == "Overview":
        return "This overview brings together a compact set of headline indicators so users can orient themselves before moving into themed detail."
    if module_count <= 1:
        return f"This section brings together {indicator_count} indicator{'s' if indicator_count != 1 else ''} in a single coherent topic block."
    return (
        f"This section is organised into {module_count} related modules, covering {indicator_count} indicators without losing the bigger story."
    )


def indicator_summary(
    selection_label: str,
    selection: dict[str, object] | None,
    london_df: pd.DataFrame,
    borough_df: pd.DataFrame,
    unit: str | None,
    use_mode: str | None,
    *,
    selection_is_plural: bool = False,
) -> str:
    if selection is None:
        return "No estimate is available for the current selection."

    comparator_context = build_comparator_context(
        selection=selection,
        selection_label=selection_label,
        selection_kind="neighbourhood",
        selection_is_plural=selection_is_plural,
        selected_area_count=int(selection.get("selected_neighbourhood_count", 0) or 0),
        exact_boundary=False,
        borough_df=borough_df,
        london_df=london_df,
    )
    base = format_comparison_narrative(comparator_context)
    if str(use_mode) == "neighbourhood_estimate_with_caveats":
        return f"{base} This value should be treated as a descriptive neighbourhood summary rather than a fully additive estimate."
    if str(use_mode) == "benchmark_only":
        return "This metric is shown as benchmark context only and should not be read as a direct estimate for the current footprint."
    return base
