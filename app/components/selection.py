from __future__ import annotations

import streamlit as st


SELECTION_KEY = "selected_neighbourhood_ids"
MAP_MODE_KEY = "map_mode"
INDICATOR_KEY = "indicator_id"
PERIOD_KEY = "period"
TOPIC_KEY = "topic_filter"
BOROUGH_FILTER_KEY = "borough_filter"
SOURCE_FILTER_KEY = "source_filter"
CATEGORY_SELECTION_KEY = "selected_topic_categories"
INDICATOR_SELECTION_KEY = "selected_indicator_ids"
COMPARISON_SELECTION_KEY = "selected_comparisons"
APP_SECTION_KEY = "active_app_section"
SPATIAL_PERSPECTIVE_KEY = "spatial_perspective"
INDICATOR_SELECTOR_ACTIVE_THEME_KEY = "indicator_selector_active_theme"
INDICATOR_SELECTOR_ACTIVE_TOPIC_KEY = "indicator_selector_active_topic"
INDICATOR_SELECTOR_GLOBAL_SEARCH_KEY = "indicator_selector_global_search"
INDICATOR_SELECTOR_THEME_FILTER_KEY = "indicator_selector_theme_filter"
INDICATOR_SELECTOR_SUBTHEME_FILTER_KEY = "indicator_selector_subtheme_filter"
INDICATOR_SELECTOR_INDICATOR_FILTER_KEY = "indicator_selector_indicator_filter"
INDICATOR_SELECTOR_TOPIC_SEARCH_KEY = "indicator_selector_topic_search"
INDICATOR_SELECTOR_SHOW_SELECTED_ONLY_KEY = "indicator_selector_show_selected_only"
INDICATOR_SELECTOR_SHOW_ADVANCED_KEY = "indicator_selector_show_advanced"
INDICATOR_SELECTION_INITIALIZED_KEY = "indicator_selection_initialized"
EXPLORER_THEME_FILTER_KEY = "explorer_theme_filter"


def init_state(
    default_indicator_id: str | None = None,
    default_period: str | None = None,
    default_topic: str = "All",
    default_categories: list[str] | None = None,
    default_comparisons: list[str] | None = None,
) -> None:
    st.session_state.setdefault(SELECTION_KEY, [])
    st.session_state.setdefault(MAP_MODE_KEY, "Hex map")
    if default_indicator_id is not None:
        st.session_state.setdefault(INDICATOR_KEY, default_indicator_id)
    if default_period is not None:
        st.session_state.setdefault(PERIOD_KEY, default_period)
    st.session_state.setdefault(TOPIC_KEY, default_topic)
    st.session_state.setdefault(BOROUGH_FILTER_KEY, [])
    st.session_state.setdefault(SOURCE_FILTER_KEY, "All")
    st.session_state.setdefault(CATEGORY_SELECTION_KEY, default_categories or [])
    st.session_state.setdefault(INDICATOR_SELECTION_KEY, [])
    st.session_state.setdefault(COMPARISON_SELECTION_KEY, default_comparisons or [])
    st.session_state.setdefault(APP_SECTION_KEY, "Guide")
    st.session_state.setdefault(SPATIAL_PERSPECTIVE_KEY, "Neighbourhood")
    st.session_state.setdefault(INDICATOR_SELECTOR_ACTIVE_THEME_KEY, "")
    st.session_state.setdefault(INDICATOR_SELECTOR_ACTIVE_TOPIC_KEY, "")
    st.session_state.setdefault(INDICATOR_SELECTOR_GLOBAL_SEARCH_KEY, "")
    st.session_state.setdefault(INDICATOR_SELECTOR_THEME_FILTER_KEY, "")
    st.session_state.setdefault(INDICATOR_SELECTOR_SUBTHEME_FILTER_KEY, "")
    st.session_state.setdefault(INDICATOR_SELECTOR_INDICATOR_FILTER_KEY, "")
    st.session_state.setdefault(INDICATOR_SELECTOR_TOPIC_SEARCH_KEY, "")
    st.session_state.setdefault(INDICATOR_SELECTOR_SHOW_SELECTED_ONLY_KEY, False)
    st.session_state.setdefault(INDICATOR_SELECTOR_SHOW_ADVANCED_KEY, False)
    st.session_state.setdefault(INDICATOR_SELECTION_INITIALIZED_KEY, False)
    st.session_state.setdefault(EXPLORER_THEME_FILTER_KEY, "All themes")


def selected_ids() -> list[str]:
    return [str(value) for value in st.session_state.get(SELECTION_KEY, [])]


def set_selected_ids(values: list[str] | list[int]) -> None:
    st.session_state[SELECTION_KEY] = [str(value) for value in values]


def toggle_selected_id(value: str | int) -> None:
    target = str(value)
    current = selected_ids()
    if target in current:
        current = [item for item in current if item != target]
    else:
        current.append(target)
    set_selected_ids(sorted(current))


def clear_selection() -> None:
    st.session_state[SELECTION_KEY] = []


def _multi_select_checkbox_on_change(
    state_key: str,
    option_value: str,
    option_keys: dict[str, str],
) -> None:
    option_value = str(option_value)
    option_key = option_keys[option_value]
    selected = {
        str(value)
        for value in st.session_state.get(state_key, [])
        if str(value).strip()
    }
    if bool(st.session_state.get(option_key, False)):
        selected.add(option_value)
    else:
        selected.discard(option_value)
    st.session_state[state_key] = sorted(selected)


def render_scrollable_multi_select_checkbox_list(
    options: list[tuple[str, str]],
    default_selected_ids: list[str] | tuple[str, ...] | set[str] | None,
    widget_prefix: str,
    height: int = 520,
) -> list[str]:
    if not options:
        return []

    option_ids = [str(option_id) for option_id, _ in options]
    option_id_set = set(option_ids)
    default_ids = {
        str(value)
        for value in (default_selected_ids or [])
        if str(value) in option_id_set
    }

    selected_key = f"{widget_prefix}_selected_ids"
    defaults_key = f"{widget_prefix}_defaults_snapshot"
    raw_selected = st.session_state.get(selected_key)
    default_snapshot = sorted(default_ids)
    previous_snapshot = st.session_state.get(defaults_key)
    if previous_snapshot != default_snapshot:
        selected = set(default_ids)
    elif raw_selected is None:
        selected = set(default_ids)
    elif isinstance(raw_selected, (list, set, tuple)):
        selected = {
            str(value)
            for value in raw_selected
            if str(value).strip() and str(value) in option_id_set
        }
    else:
        raw_value = str(raw_selected)
        selected = {raw_value} if raw_value in option_id_set else set(default_ids)
    st.session_state[selected_key] = sorted(selected)
    st.session_state[defaults_key] = default_snapshot

    option_keys = {
        str(option_id): f"{widget_prefix}_option_{str(option_id)}"
        for option_id in option_ids
    }
    for option_id, option_key in option_keys.items():
        st.session_state[option_key] = option_id in selected

    with st.container(height=int(height), border=False):
        for option_id, option_label in options:
            option_id = str(option_id)
            st.checkbox(
                str(option_label),
                key=option_keys[option_id],
                on_change=_multi_select_checkbox_on_change,
                args=(selected_key, option_id, option_keys),
            )

    return [
        str(value)
        for value in st.session_state.get(selected_key, [])
        if str(value).strip() and str(value) in option_id_set
    ]


def render_selection_chips(reference_df, *, editable: bool = True) -> None:
    current = selected_ids()
    if not current:
        st.caption("No neighbourhoods selected yet. Use the map, the hex selection menu, or the neighbourhood multiselect.")
        return

    selected = (
        reference_df[reference_df["neighbourhood_id"].astype(str).isin(current)]
        .sort_values(["borough_name", "neighbourhood_name"])
        .reset_index(drop=True)
    )
    st.markdown("**Current selection**")
    if not editable:
        chip_markup = "".join(
            [
                (
                    "<span style=\"display:inline-block; margin:0 0.35rem 0.35rem 0; "
                    "padding:0.36rem 0.7rem; border-radius:999px; "
                    "background:rgba(15,59,95,0.08); border:1px solid rgba(15,59,95,0.10); "
                    "color:#142033; font-size:0.92rem;\">"
                    f"{row.neighbourhood_name} ({row.borough_name})"
                    "</span>"
                )
                for row in selected.itertuples(index=False)
            ]
        )
        st.markdown(chip_markup, unsafe_allow_html=True)
        return

    for row in selected.itertuples(index=False):
        if st.button(f"Remove {row.neighbourhood_name}", key=f"remove_{row.neighbourhood_id}", width="stretch"):
            toggle_selected_id(row.neighbourhood_id)
            st.rerun()
    if st.button("Clear all", key="clear_all_selection", width="stretch"):
        clear_selection()
        st.rerun()
