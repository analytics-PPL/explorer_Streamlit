from __future__ import annotations

import pandas as pd
import streamlit as st

from app.components.layout import render_empty_state
from app.components.maps import render_selection_map
from neighbourhood_explorer.data_access import (
    available_periods,
    indicator_metadata,
    load_hex_icb_geography,
    load_map_geography,
    map_indicator_options,
    map_value_frame,
)


EXPLORER_MAP_MODE_KEY = "explorer_map_mode"
EXPLORER_MAP_INDICATOR_KEY = "explorer_map_indicator_id"


def _legend_label(value: float | int | None, unit: str | None) -> str:
    if value is None or pd.isna(value):
        return "No data"
    if unit == "count":
        return f"{int(round(float(value))):,}"
    if unit == "share":
        return f"{float(value) * 100:.1f}%"
    if unit == "rate_per_1000":
        return f"{float(value) * 1000:.1f} per 1,000"
    if unit == "score":
        return f"{float(value):.2f}"
    if unit == "decile":
        return f"{float(value):.1f}"
    return f"{float(value):.2f}"


def _render_map_legend(value_frame: pd.DataFrame, unit: str | None) -> None:
    values = pd.to_numeric(value_frame["value"], errors="coerce").dropna()
    if values.empty:
        st.caption("No mapped values are available for this indicator.")
        return
    low = float(values.min())
    mid = float(values.median())
    high = float(values.max())
    st.markdown(
        """
        <div style="display:flex; gap:0.4rem; align-items:center; margin:0.35rem 0 0.2rem 0;">
          <span style="display:inline-block; width:14px; height:14px; border-radius:50%; background:#e5eef4;"></span>
          <span style="font-size:0.88rem; color:#4f6278;">Lower</span>
          <span style="display:inline-block; width:14px; height:14px; border-radius:50%; background:#6da8c4;"></span>
          <span style="font-size:0.88rem; color:#4f6278;">Middle</span>
          <span style="display:inline-block; width:14px; height:14px; border-radius:50%; background:#0f3b5f;"></span>
          <span style="font-size:0.88rem; color:#4f6278;">Higher</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        f"{_legend_label(low, unit)} to {_legend_label(high, unit)} | median {_legend_label(mid, unit)}"
    )


def render_explorer_map_panel(category_keys: list[str] | str, current_ids: list[str]) -> None:
    selected_keys = [str(value) for value in category_keys] if isinstance(category_keys, (list, tuple, set)) else [str(category_keys)]
    selected_key_set = {key for key in selected_keys if key.strip()}

    map_catalog = map_indicator_options(None)
    if selected_key_set and "overview" not in selected_key_set:
        map_catalog = map_catalog[map_catalog["category_key"].astype(str).isin(selected_key_set)].copy()
    if map_catalog.empty:
        render_empty_state("No map-enabled indicators are available in this category yet.", icon="🗺️")
        return

    valid_indicator_ids = map_catalog["indicator_id"].astype(str).tolist()
    indicator_titles: dict[str, str] = {}
    for indicator_id in valid_indicator_ids:
        meta = indicator_metadata(indicator_id)
        indicator_titles[indicator_id] = str(meta.get("ui_title") or meta["title"])
    current_indicator = str(st.session_state.get(EXPLORER_MAP_INDICATOR_KEY, valid_indicator_ids[0]))
    if current_indicator not in valid_indicator_ids:
        current_indicator = valid_indicator_ids[0]
        st.session_state[EXPLORER_MAP_INDICATOR_KEY] = current_indicator
    current_map_mode = str(st.session_state.get(EXPLORER_MAP_MODE_KEY, "Hex map"))
    if current_map_mode not in {"Hex map", "Real map"}:
        current_map_mode = "Hex map"
        st.session_state[EXPLORER_MAP_MODE_KEY] = current_map_mode

    st.markdown("**Map context**")
    st.radio("Map mode", ["Hex map", "Real map"], key=EXPLORER_MAP_MODE_KEY, horizontal=True)
    st.selectbox(
        "Map shading",
        valid_indicator_ids,
        index=valid_indicator_ids.index(current_indicator),
        key=EXPLORER_MAP_INDICATOR_KEY,
        format_func=lambda value: indicator_titles.get(str(value), str(value)),
    )

    meta = indicator_metadata(str(st.session_state[EXPLORER_MAP_INDICATOR_KEY]))
    periods = available_periods(str(st.session_state[EXPLORER_MAP_INDICATOR_KEY]))
    period = periods[-1] if periods else ""
    value_frame = map_value_frame(str(st.session_state[EXPLORER_MAP_INDICATOR_KEY]), period)

    variant = "hex" if st.session_state[EXPLORER_MAP_MODE_KEY] == "Hex map" else "real"
    overlay = load_hex_icb_geography() if variant == "hex" else None
    geo_df = load_map_geography("hex" if variant == "hex" else "real")
    render_selection_map(
        geo_df,
        value_frame,
        current_ids,
        map_key=f"explorer_map_{variant}_{st.session_state[EXPLORER_MAP_INDICATOR_KEY]}",
        variant=variant,
        overlay_geo_df=overlay,
        height=390,
    )
    _render_map_legend(value_frame, meta.get("unit"))
    st.caption(f"{meta.get('ui_title') or meta.get('title')} | {period or meta.get('source_period', '')}")
