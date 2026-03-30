from __future__ import annotations

import pandas as pd
import streamlit as st

from catalog.indicator_visualisation_registry import (
    PUBLIC_EXPOSURE_LEVELS,
    get_categories,
    get_indicators,
    get_subcategories,
)


EXPLORER_CATEGORY_KEY = "explorer_category_key"
EXPLORER_SUBCATEGORY_KEY = "explorer_subcategory_key"
EXPLORER_INDICATOR_KEY = "explorer_indicator_id"
EXPLORER_SHOW_ADVANCED_KEY = "explorer_show_advanced_indicators"


def _available_indicator_ids(catalog_df: pd.DataFrame) -> list[str]:
    if catalog_df.empty:
        return []
    return catalog_df["indicator_id"].astype(str).drop_duplicates().tolist()


def _exposure_levels(show_advanced: bool) -> list[str]:
    levels = list(PUBLIC_EXPOSURE_LEVELS)
    if show_advanced:
        levels.append("advanced")
    return levels


def _ensure_valid_choice(current: object, options: list[str]) -> str | None:
    if not options:
        return None
    current_text = str(current or "").strip()
    if current_text in options:
        return current_text
    return options[0]


def render_category_nav(catalog_df: pd.DataFrame) -> dict[str, object]:
    available_indicator_ids = _available_indicator_ids(catalog_df)
    if not available_indicator_ids:
        return {"category": None, "subcategory": None, "indicator_id": None, "show_advanced": False}

    show_advanced = st.checkbox(
        "Show advanced indicators",
        value=bool(st.session_state.get(EXPLORER_SHOW_ADVANCED_KEY, False)),
        key=EXPLORER_SHOW_ADVANCED_KEY,
        help="Core and standard indicators are shown by default. Turn this on if you want to see advanced indicators as well.",
    )
    exposure_levels = _exposure_levels(show_advanced)

    categories = get_categories(
        exposure_levels=exposure_levels,
        available_indicator_ids=available_indicator_ids,
    )
    if not categories:
        return {"category": None, "subcategory": None, "indicator_id": None, "show_advanced": show_advanced}

    category_options = [str(item["category"]) for item in categories]
    category_labels = {str(item["category"]): f"{item['category']} ({item['count']})" for item in categories}
    category = _ensure_valid_choice(st.session_state.get(EXPLORER_CATEGORY_KEY), category_options)
    st.markdown("**Choose a section**")
    category = st.radio(
        "Category",
        options=category_options,
        index=category_options.index(category) if category in category_options else 0,
        format_func=lambda value: category_labels.get(value, value),
        key=EXPLORER_CATEGORY_KEY,
        label_visibility="collapsed",
    )

    subcategories = get_subcategories(
        str(category),
        exposure_levels=exposure_levels,
        available_indicator_ids=available_indicator_ids,
    )
    if not subcategories:
        return {"category": category, "subcategory": None, "indicator_id": None, "show_advanced": show_advanced}

    subcategory_options = [str(item["subcategory"]) for item in subcategories]
    subcategory_labels = {str(item["subcategory"]): f"{item['subcategory']} ({item['count']})" for item in subcategories}
    subcategory = _ensure_valid_choice(st.session_state.get(EXPLORER_SUBCATEGORY_KEY), subcategory_options)
    st.markdown("**Choose a topic**")
    subcategory = st.radio(
        "Subcategory",
        options=subcategory_options,
        index=subcategory_options.index(subcategory) if subcategory in subcategory_options else 0,
        format_func=lambda value: subcategory_labels.get(value, value),
        key=EXPLORER_SUBCATEGORY_KEY,
        label_visibility="collapsed",
    )

    indicator_options_df = get_indicators(
        str(category),
        str(subcategory),
        exposure_levels=exposure_levels,
        available_indicator_ids=available_indicator_ids,
    )
    if indicator_options_df.empty:
        return {"category": category, "subcategory": subcategory, "indicator_id": None, "show_advanced": show_advanced}

    indicator_options = indicator_options_df["indicator_id"].astype(str).tolist()
    indicator_labels = {
        str(row.indicator_id): (
            f"{row.ui_title} ({str(row.ui_exposure_level).capitalize()})"
            if show_advanced and str(row.ui_exposure_level).strip().lower() == "advanced"
            else str(row.ui_title)
        )
        for row in indicator_options_df.itertuples(index=False)
    }
    indicator_id = _ensure_valid_choice(st.session_state.get(EXPLORER_INDICATOR_KEY), indicator_options)
    st.markdown("**Choose an indicator**")
    indicator_id = st.radio(
        "Indicator",
        options=indicator_options,
        index=indicator_options.index(indicator_id) if indicator_id in indicator_options else 0,
        format_func=lambda value: indicator_labels.get(value, value),
        key=EXPLORER_INDICATOR_KEY,
        label_visibility="collapsed",
    )

    return {
        "category": str(category),
        "subcategory": str(subcategory),
        "indicator_id": str(indicator_id),
        "show_advanced": bool(show_advanced),
        "category_options": categories,
        "subcategory_options": subcategories,
        "indicator_options": indicator_options_df,
    }
