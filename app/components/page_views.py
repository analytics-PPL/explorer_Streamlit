from __future__ import annotations

import json
import logging
from html import escape
from itertools import zip_longest
import re
import pandas as pd
import streamlit as st

from catalog.indicator_visualisation_registry import (
    get_bundle_view,
    get_compact_views,
    get_default_view,
    get_full_views,
)
from app.components.charts import (
    format_indicator_value,
    render_download_button,
    render_metric_cards,
)
from app.components.chart_templates import (
    _population_pyramid_subject_options,
)
from app.components.display_helpers import (
    _DESCRIPTION_SUBJECT_OVERRIDES,
    _DISPLAY_TITLE_OVERRIDES,
    _FRIENDLY_SOURCE_NAMES,
    _GENERIC_PERIOD_LABELS,
    STRUCTURE_LED_VIEWS,
    active_profile_slice_label,
    breakdown_groups_from_meta as _breakdown_groups_from_meta,
    clean_text as _clean_text,
    denominator_population_phrase,
    friendly_source_name as _friendly_source_name,
    indicator_active_slice_caption as _indicator_active_slice_caption,
    indicator_active_title as _indicator_active_title,
    indicator_display_title as _indicator_display_title,
    indicator_history_range_label as _indicator_history_range_label,
    indicator_panel_subtitle as _indicator_panel_subtitle,
    indicator_source_summary as _indicator_source_summary,
    indicator_subject_phrase as _indicator_subject_phrase,
    metric_period_label as _metric_period_label,
    normalise_search_text as _normalise_search_text,
    normalised_field_set as _normalised_field_set,
    plain_english_clinical_text,
    plain_english_indicator_label as _plain_english_indicator_label,
    profile_primary_slice_label,
    qof_display_title as _qof_display_title,
    qof_guidance_lookup as _qof_guidance_lookup,
    row_available_views as _row_available_views,
    safe_filename as _safe_filename,
    sentence_case_phrase as _sentence_case_phrase,
    sequence_from_meta as _sequence_from_meta,
    theme_widget_slug as _theme_widget_slug,
    truncate_text as _truncate_text,
    unique_views as _unique_views,
)
from app.components.formatting import (
    format_dataframe_for_display,
    format_period_label,
    humanise_enum,
)
from app.components.interface_semantics import (
    breakdown_groups_from_meta,
    build_summary_cards,
    choose_default_view,
    filter_profile_breakdown_views,
    inferred_profile_breakdown_views,
    is_direct_value_breakdown_indicator,
    is_profile_breakdown_indicator,
    profile_breakdown_title_override,
    should_render_advanced_section,
    should_render_module_overview,
)
from app.components.layout import (
    POWERPOINT_CAROUSEL_WORDS,
    dismiss_loading_overlay,
    inject_theme,
    page_header,
    render_empty_state,
    render_loading_button,
    render_loading_overlay,
    set_page,
)
from app.components.maps import render_selection_map
from app.components.narrative_summaries import (
    indicator_summary,
    selection_context_summary,
)
from app.components.selection import (
    APP_SECTION_KEY,
    BOROUGH_FILTER_KEY,
    CATEGORY_SELECTION_KEY,
    COMPARISON_SELECTION_KEY,
    INDICATOR_SELECTOR_ACTIVE_THEME_KEY,
    INDICATOR_SELECTOR_ACTIVE_TOPIC_KEY,
    INDICATOR_SELECTOR_INDICATOR_FILTER_KEY,
    INDICATOR_SELECTION_INITIALIZED_KEY,
    INDICATOR_SELECTOR_SHOW_ADVANCED_KEY,
    INDICATOR_SELECTOR_SUBTHEME_FILTER_KEY,
    INDICATOR_SELECTOR_THEME_FILTER_KEY,
    INDICATOR_SELECTOR_TOPIC_SEARCH_KEY,
    INDICATOR_KEY,
    INDICATOR_SELECTION_KEY,
    EXPLORER_THEME_FILTER_KEY,
    MAP_MODE_KEY,
    PERIOD_KEY,
    SPATIAL_PERSPECTIVE_KEY,
    init_state,
    render_scrollable_multi_select_checkbox_list,
    render_selection_chips,
    selected_ids,
    set_selected_ids,
    toggle_selected_id,
)
from neighbourhood_explorer.catalog import category_frame
from neighbourhood_explorer.data_access import (
    available_periods,
    comparison_bundle,
    indicator_metadata,
    latest_period,
    load_catalog_df,
    load_hex_icb_geography,
    load_map_geography,
    load_neighbourhood_reference,
    load_public_catalog_df,
)
from neighbourhood_explorer.footprints import resolve_footprint_label
from neighbourhood_explorer.paths import ROOT_DIR
logger = logging.getLogger(__name__)


SECTION_TARGETS = {
    "Guide": "Home.py",
    "Setup": "Home.py",
    "Explorer": "pages/0_Explorer.py",
    "Methodology & Data Coverage": "pages/1_Methodology_and_Data_Coverage.py",
}
COMPARISON_OPTIONS = ["Borough benchmark", "London benchmark"]
MAP_INTERFACE_OPTIONS = ["Hex map", "Real map"]
SPATIAL_PERSPECTIVE_OPTIONS = ["Neighbourhood", "Place", "System", "Region"]
SETUP_SELECTOR_PANEL_HEIGHT = 680
SPATIAL_PERSPECTIVE_USER_SET_KEY = "spatial_perspective_user_set"
PPT_SLIDE_OPTIONS = [
    ("overview", "Overview slide"),
    ("detail_tables", "Neighbourhood detail tables"),
    ("methodology", "Methodology slide"),
]
PPT_REPORT_BYTES_KEY = "ppt_report_bytes"
PPT_REPORT_FILENAME_KEY = "ppt_report_filename"
PPT_REPORT_SIGNATURE_KEY = "ppt_report_signature"

COMPOSITE_INDICATOR_GROUPS = {
    "naptan_public_transport_access_node_count": {
        "description": "This bundled indicator brings together overall public transport stops and stations, density, bus stops, and rail and Tube stations.",
        "indicator_ids": [
            "naptan_public_transport_access_node_count",
            "naptan_access_node_density",
            "naptan_bus_access_node_count",
            "naptan_rail_and_tube_node_count",
        ],
    },
    "tfl_cycle_docking_station_count": {
        "description": "This bundled indicator brings together cycle hire docking station counts and dock-capacity measures.",
        "indicator_ids": [
            "tfl_cycle_docking_station_count",
            "tfl_cycle_dock_capacity_total",
            "tfl_cycle_dock_capacity_density",
        ],
    },
}
ICB_NAME_BY_CODE = {
    "NCL": "North Central London",
    "NEL": "North East London",
    "NWL": "North West London",
    "SEL": "South East London",
    "SWL": "South West London",
}
OVERVIEW_HEADLINE_IDS = [
    "nomis_population_total",
    "imd_score",
    "nomis_general_health_bad_very_bad_share",
    "police_all_crimes_rate_per_1000",
]
SUPPRESSED_SUBCATEGORY_BUNDLE_LABELS = {
    "Population size, age & density",
}
ALL_EXPLORER_THEMES_LABEL = "All themes"
EXPLORER_PRIMARY_INDICATOR_LIMIT = 4
EXPLORER_PRIMARY_VIEW_LIMIT = 2
ANY_THEME_FILTER_LABEL = "Any theme"
ANY_SUBTHEME_FILTER_LABEL = "Any subtheme"
ANY_INDICATOR_FILTER_LABEL = "Any indicator"


def build_indicator_visual_context(*args, **kwargs):
    from app.components.chart_registry import build_indicator_visual_context as _impl

    return _impl(*args, **kwargs)


def indicator_detail_frame(*args, **kwargs):
    from app.components.chart_registry import indicator_detail_frame as _impl

    return _impl(*args, **kwargs)


def render_indicator_view(*args, **kwargs):
    from app.components.chart_registry import render_indicator_view as _impl

    return _impl(*args, **kwargs)


def _powerpoint_available() -> bool:
    from neighbourhood_explorer.powerpoint import powerpoint_available as _impl

    return _impl()


def _build_powerpoint_report(*args, **kwargs):
    from neighbourhood_explorer.powerpoint import build_powerpoint_report as _impl

    return _impl(*args, **kwargs)


def _selection_label(current_ids: list[str], reference_df: pd.DataFrame | None = None) -> str:
    return resolve_footprint_label(current_ids, reference_df).label


def _section_intro(title: str, text: str, kicker: str | None = None, *, inline_heading: bool = False) -> None:
    if kicker and inline_heading:
        st.markdown(
            (
                "<div class='section-heading-inline'>"
                f"<div class='section-kicker'>{escape(kicker)}</div>"
                f"<div class='section-card-title'>{escape(title)}</div>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
    else:
        if kicker:
            st.markdown(f"<div class='section-kicker'>{escape(kicker)}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='section-card-title'>{escape(title)}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='section-card-text'>{text}</div>", unsafe_allow_html=True)


def _render_user_guide_tab(category_labels: list[str]) -> None:
    st.markdown("### About this tool")
    st.markdown(
        """
        This tool helps you explore publicly available datasets through a neighbourhood lens. It brings together maps, indicators and comparisons so that you can see how neighbourhoods differ, where patterns of need or inequality may matter, and where a closer look may be useful.

        It is designed to support exploration, shared understanding and better questions. It is not a replacement for local operational data, professional judgement or detailed bespoke analysis. As a public-data tool, it works best as a starting point for conversations, planning and hypothesis generation.

        The tool uses a consolidated set of London neighbourhood boundaries as of March 2025. This allows users to explore data at a more meaningful local level than standard administrative geographies such as wards or boroughs.
        """
    )

    st.markdown("### What you can do")
    st.markdown(
        """
        Use the tool to:

        - view neighbourhoods on a map
        - compare neighbourhoods within a place, borough or wider system
        - explore indicators across different themes
        - spot variation, patterns and outliers
        - use a public-data view to identify where more detailed local analysis may be needed
        - export selected views and indicators into a PowerPoint report for use in meetings and workshops
        """
    )
    if category_labels:
        st.caption(f"Current public themes in the live tool: {', '.join(category_labels)}")

    st.markdown("### How to use it")
    st.markdown(
        """
        Start in the Guide, then move to Setup to define your footprint.

        In Setup:

        - choose your geography (region, system, place, or neighbourhood)
        - select your areas using a checklist or map
        - choose themes and indicators
        - select whether to include borough and/or London comparisons

        Then click `Visualize data` to open the Explorer.

        In the Explorer:

        - browse themes and modules
        - open indicators to see charts, comparisons and tables
        - use the built-in summaries to understand how your selection compares to benchmarks
        - optionally export your selection as a PowerPoint report
        """
    )

    st.markdown("### Questions this tool can help with")
    st.markdown(
        """
        This tool is useful for questions such as:

        - Which neighbourhoods look different from others on this measure?
        - Where do we see concentrated need, variation or inequality?
        - How does one neighbourhood compare with the wider place?
        - Are there clusters of similar patterns across nearby areas?
        - Where might a public-data view suggest a case for deeper local work?
        """
    )

    st.markdown("### Good uses for the tool")
    st.markdown(
        """
        This tool is especially helpful for:

        - orienting new teams to a neighbourhood picture
        - supporting workshops and planning conversations
        - preparing for discussions about variation and inequality
        - sense-checking early hypotheses
        - identifying where more detailed modelling, evaluation or local data work may be worthwhile
        - generating slide-ready outputs for meetings and briefings
        """
    )

    st.markdown("### How to interpret the results")
    st.markdown(
        """
        Look for patterns, not just rankings.

        Compare like with like. A small difference between two places may not be meaningful on its own.

        Treat public data as a signal, not the whole story. It can show where something may be happening, but not always why.

        Be aware that:

        - neighbourhoods may span multiple boroughs
        - borough comparisons are shown separately rather than combined artificially
        - some indicators are snapshots, while others are time series

        Use the tool to support discussion alongside local knowledge, lived experience and service insight.
        """
    )

    st.markdown("### Things to bear in mind")
    st.markdown(
        """
        Because the tool uses public datasets, different indicators may come from different time periods, publishers or geographic levels.

        Some measures may lag behind current conditions.

        A neighbourhood pattern does not explain itself. Public data often needs to be combined with local context to become genuinely actionable.

        That is why this tool is best used as a shared evidence base for exploration rather than a final decision engine.
        """
    )


def _render_more_info_tab() -> None:
    st.markdown("### About this tool")
    st.markdown(
        """
        This tool was developed by PPL as part of our wider work on neighbourhood health, population health analytics and system modelling.

        We built it to make public data easier to explore through a neighbourhood lens, helping teams build a shared understanding of place, variation and need. The aim is to support better questions, more informed conversations and more grounded planning across health and care systems.
        """
    )

    st.markdown("### Contact")
    st.markdown(
        """
        For questions, feedback or ideas:

        Adam Wall  
        Head of Data & Analytics, PPL  
        adam.wall@ppl.org.uk
        """
    )

    st.markdown("### Working with us")
    st.markdown(
        """
        This tool focuses on what can be done with public data.

        In many cases, that is enough to support exploration and shared understanding. In others, teams may want to go further, for example by working with linked NHS and local government data, developing bespoke neighbourhood definitions, or building models tailored to specific planning or operational questions.

        Our wider work in partnership with NHS organisations, local government and other system partners includes neighbourhood modelling, demand, workforce and finance analysis, interactive tools, and evaluation.

        This work is typically done in partnership with local teams, combining data, context and practical insight to support real-world decision-making.

        If the approach behind this tool is useful, we are always open to conversations about how it could be applied more deeply in a local context.
        """
    )


def render_guide_page() -> None:
    set_page("Guide")
    inject_theme()
    ready = _data_readiness_guard()
    if ready is None:
        return
    _, catalog_df = ready
    category_labels, _ = _ensure_configuration_state(catalog_df)
    st.session_state[APP_SECTION_KEY] = "Guide"

    page_header("", "")
    _section_switcher("Guide", home_page=True)

    with st.container(border=True):
        user_tab, more_info_tab = st.tabs(["User guide", "More info"])
        with user_tab:
            _render_user_guide_tab(category_labels)
        with more_info_tab:
            _render_more_info_tab()

def _borough_filtered(frame: pd.DataFrame, selected_boroughs: list[str]) -> pd.DataFrame:
    if not selected_boroughs:
        return frame.copy()
    selected = {str(value).strip() for value in selected_boroughs}
    mask = frame["borough_name"].astype(str).fillna("").map(
        lambda raw: bool({item.strip() for item in raw.split(";") if item.strip()}.intersection(selected))
    )
    return frame[mask].copy()


def _split_multi_value(value: object) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    return [item.strip() for item in str(value).split(";") if item.strip()]


def _place_membership_frame(reference_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    membership = reference_df[["neighbourhood_id", "borough_code", "borough_name"]].drop_duplicates()
    for row in membership.itertuples(index=False):
        codes = _split_multi_value(row.borough_code)
        names = _split_multi_value(row.borough_name)
        if not codes and not names:
            continue
        if len(codes) == len(names):
            pairs = zip(codes, names, strict=False)
        else:
            pairs = zip_longest(codes, names, fillvalue="")
        for code, name in pairs:
            code = str(code).strip()
            name = str(name).strip()
            if not code and not name:
                continue
            rows.append(
                {
                    "neighbourhood_id": str(row.neighbourhood_id),
                    "borough_code": code,
                    "borough_name": name,
                }
            )
    exploded = pd.DataFrame(rows).drop_duplicates().reset_index(drop=True)
    return exploded


def _derive_neighbourhood_ids_for_places(reference_df: pd.DataFrame, selected_place_codes: list[str]) -> list[str]:
    if not selected_place_codes:
        return []
    selected = {str(value).strip() for value in selected_place_codes if str(value).strip()}
    if not selected:
        return []
    place_membership = _place_membership_frame(reference_df)
    if place_membership.empty:
        return []
    return sorted(
        place_membership.loc[
            place_membership["borough_code"].astype(str).isin(selected),
            "neighbourhood_id",
        ]
        .astype(str)
        .unique()
        .tolist()
    )


def _data_readiness_guard() -> tuple[pd.DataFrame, pd.DataFrame] | None:
    try:
        reference_df = load_neighbourhood_reference()
        catalog_df = load_public_catalog_df()
        return reference_df, catalog_df
    except FileNotFoundError as exc:
        st.error(
            "Processed app data is missing. Run the ETL first:\n"
            "`python3 etl/inspect_sources.py`\n"
            "`python3 etl/standardise_sources.py`\n"
            "`python3 etl/aggregate_to_neighbourhoods.py`\n"
            "`python3 etl/build_benchmarks.py`\n"
            "`python3 etl/build_indicator_catalog.py`"
        )
        st.exception(exc)
        return None


def _apply_explorer_category_order(configured_labels: list[str]) -> list[str]:
    if not configured_labels:
        return []
    ordered: list[str] = []
    category_meta = category_frame()
    if not category_meta.empty:
        known_labels = category_meta["label"].astype(str).tolist()
        ordered.extend([label for label in known_labels if label in configured_labels])
    ordered.extend([label for label in configured_labels if label not in ordered])
    return ordered


def _available_category_labels(catalog_df: pd.DataFrame) -> list[str]:
    if catalog_df.empty:
        return []
    categories = (
        catalog_df[["top_level_category", "category_sort_order"]]
        .drop_duplicates()
        .sort_values(["category_sort_order", "top_level_category"])
    )
    return _apply_explorer_category_order(categories["top_level_category"].astype(str).tolist())


def _ensure_configuration_state(catalog_df: pd.DataFrame) -> tuple[list[str], list[str]]:
    category_labels = _available_category_labels(catalog_df)
    default_indicator_id = str(catalog_df.iloc[0]["indicator_id"])
    default_period = latest_period(default_indicator_id)
    init_state(
        default_indicator_id=default_indicator_id,
        default_period=str(default_period) if default_period else None,
        default_topic="All",
        default_categories=category_labels,
        default_comparisons=COMPARISON_OPTIONS,
    )

    valid_categories = [
        label for label in st.session_state.get(CATEGORY_SELECTION_KEY, []) if label in category_labels
    ]
    if not valid_categories:
        valid_categories = category_labels
    st.session_state[CATEGORY_SELECTION_KEY] = valid_categories

    valid_comparisons = [
        item for item in st.session_state.get(COMPARISON_SELECTION_KEY, []) if item in COMPARISON_OPTIONS
    ]
    st.session_state[COMPARISON_SELECTION_KEY] = valid_comparisons
    return category_labels, valid_categories


def _indicator_options_for_categories(catalog_df: pd.DataFrame, categories: list[str]) -> pd.DataFrame:
    frame = catalog_df[catalog_df["top_level_category"].isin(categories)].copy()
    if frame.empty:
        return frame
    sort_columns = [
        column
        for column in ["category_sort_order", "module_sort_order", "indicator_sort_order", "ui_title"]
        if column in frame.columns
    ]
    return frame.sort_values(sort_columns).reset_index(drop=True)


def _ensure_indicator_configuration_state(catalog_df: pd.DataFrame, configured_categories: list[str]) -> list[str]:
    in_scope = _indicator_options_for_categories(catalog_df, configured_categories)
    valid_ids = in_scope["indicator_id"].astype(str).tolist()
    current_ids = [str(value) for value in st.session_state.get(INDICATOR_SELECTION_KEY, []) if str(value) in set(valid_ids)]
    if not bool(st.session_state.get(INDICATOR_SELECTION_INITIALIZED_KEY, False)):
        current_ids = valid_ids
        st.session_state[INDICATOR_SELECTION_INITIALIZED_KEY] = True
    st.session_state[INDICATOR_SELECTION_KEY] = current_ids
    return current_ids


def _ensure_checkbox_state(widget_key: str, default: bool) -> None:
    if widget_key not in st.session_state:
        st.session_state[widget_key] = bool(default)


def _render_theme_indicator_tree(
    *,
    category_label: str,
    category_df: pd.DataFrame,
    previous_category_set: set[str],
    previous_indicator_ids: list[str],
) -> list[str]:
    selected_indicator_ids: list[str] = []
    category_was_previously_selected = category_label in previous_category_set
    theme_slug = _theme_widget_slug(category_label)

    for subcategory_label, subcategory_catalog in _subcategory_groups_for_theme(category_df):
        subcategory_catalog = _ordered_indicator_catalog_for_display(subcategory_catalog)
        subcategory_indicator_ids = subcategory_catalog["indicator_id"].astype(str).tolist()
        subcategory_indicator_set = set(subcategory_indicator_ids)
        previously_selected_for_subcategory = [
            indicator_id
            for indicator_id in previous_indicator_ids
            if indicator_id in subcategory_indicator_set
        ]
        subcategory_slug = f"{theme_slug}_{_theme_widget_slug(subcategory_label)}"
        include_subcategory_key = f"include_theme_subcategory_{subcategory_slug}"
        default_subcategory_selected = (
            True if not category_was_previously_selected else bool(previously_selected_for_subcategory)
        )
        _ensure_checkbox_state(include_subcategory_key, default_subcategory_selected)

        with st.container(border=False):
            header_col, count_col = st.columns([0.76, 0.24], gap="small")
            count_slot = count_col.empty()
            with header_col:
                include_subcategory = st.checkbox(
                    subcategory_label,
                    key=include_subcategory_key,
                )

            subcategory_selected_ids: list[str] = []
            if include_subcategory:
                module_description = _clean_text(subcategory_catalog.iloc[0].get("module_description"))
                if module_description:
                    st.caption(module_description)

                if _is_qof_module_catalog(subcategory_catalog):
                    subcategory_selected_ids = _render_qof_configuration_groups(
                        subcategory_catalog=subcategory_catalog,
                        subcategory_slug=subcategory_slug,
                        category_was_previously_selected=category_was_previously_selected,
                        previously_selected_for_subcategory=previously_selected_for_subcategory,
                    )
                else:
                    subcategory_selected_ids = _render_indicator_configuration_checkboxes(
                        subcategory_catalog=subcategory_catalog,
                        subcategory_slug=subcategory_slug,
                        category_was_previously_selected=category_was_previously_selected,
                        previously_selected_for_subcategory=previously_selected_for_subcategory,
                    )

                if not subcategory_selected_ids:
                    subcategory_selected_ids = subcategory_indicator_ids

            count_slot.caption(
                f"{len(subcategory_selected_ids) if include_subcategory else 0}/{len(subcategory_indicator_ids)}"
            )
            selected_indicator_ids.extend(subcategory_selected_ids)

    return selected_indicator_ids


def _render_indicator_configuration_checkboxes(
    *,
    subcategory_catalog: pd.DataFrame,
    subcategory_slug: str,
    category_was_previously_selected: bool,
    previously_selected_for_subcategory: list[str],
) -> list[str]:
    selected_indicator_ids: list[str] = []
    for row in subcategory_catalog.to_dict(orient="records"):
        indicator_id = str(row["indicator_id"])
        indicator_key = f"include_theme_indicator_{subcategory_slug}_{indicator_id}"
        default_indicator_selected = (
            True if not category_was_previously_selected else indicator_id in previously_selected_for_subcategory
        )
        _ensure_checkbox_state(indicator_key, default_indicator_selected)
        indent_col, checkbox_col = st.columns([0.05, 0.95], gap="small")
        with indent_col:
            st.markdown("&nbsp;", unsafe_allow_html=True)
        with checkbox_col:
            if st.checkbox(_indicator_expander_label(row), key=indicator_key):
                selected_indicator_ids.append(indicator_id)
    return selected_indicator_ids


def _render_qof_configuration_groups(
    *,
    subcategory_catalog: pd.DataFrame,
    subcategory_slug: str,
    category_was_previously_selected: bool,
    previously_selected_for_subcategory: list[str],
) -> list[str]:
    selected_indicator_ids: list[str] = []
    ordered_catalog = _ordered_indicator_catalog_for_display(_qof_public_metric_catalog(subcategory_catalog))
    prevalence_catalog = _qof_metric_catalog(ordered_catalog, {"prevalence"})
    advanced_catalog = _qof_metric_catalog(ordered_catalog, {"achievement", "newly_diagnosed", "register"})

    if not prevalence_catalog.empty:
        st.caption("Prevalence")
        selected_indicator_ids.extend(
            _render_indicator_configuration_checkboxes(
                subcategory_catalog=prevalence_catalog,
                subcategory_slug=subcategory_slug,
                category_was_previously_selected=category_was_previously_selected,
                previously_selected_for_subcategory=previously_selected_for_subcategory,
            )
        )

    if not advanced_catalog.empty:
        with st.expander("Advanced indicators", expanded=False):
            st.caption("These QOF drill-down measures are grouped together to match the Explorer.")
            selected_indicator_ids.extend(
                _render_indicator_configuration_checkboxes(
                    subcategory_catalog=advanced_catalog,
                    subcategory_slug=subcategory_slug,
                    category_was_previously_selected=category_was_previously_selected,
                    previously_selected_for_subcategory=previously_selected_for_subcategory,
                )
            )

    return selected_indicator_ids


def _reference_with_system_names(reference_df: pd.DataFrame) -> pd.DataFrame:
    enriched = reference_df.copy()
    enriched["icb_name"] = enriched["icb_code"].astype(str).map(ICB_NAME_BY_CODE).fillna(enriched["icb_code"].astype(str))
    return enriched


def _matching_scope_defaults(reference_df: pd.DataFrame, current_ids: list[str], perspective: str) -> list[str]:
    if perspective in {"System", "Place", "Neighbourhood"}:
        return []

    current_set = {str(value) for value in current_ids}
    if not current_set:
        return []

    scoped = reference_df[reference_df["neighbourhood_id"].astype(str).isin(current_set)].copy()
    if scoped.empty:
        return []
    if perspective == "System":
        return sorted(scoped["icb_code"].dropna().astype(str).unique().tolist())
    if perspective == "Place":
        borough_codes: list[str] = []
        for raw in scoped["borough_code"].dropna().astype(str):
            borough_codes.extend([item.strip() for item in raw.split(";") if item.strip()])
        return sorted(set(borough_codes))
    if perspective == "Neighbourhood":
        return sorted(scoped["neighbourhood_id"].dropna().astype(str).unique().tolist())
    return []


def _available_comparison_options(current_ids: list[str] | None = None) -> list[str]:
    if current_ids is None:
        current_ids = selected_ids()
    if resolve_footprint_label(current_ids).kind == "region":
        return ["Borough benchmark"]
    return COMPARISON_OPTIONS.copy()


def _comparison_preferences(current_ids: list[str] | None = None) -> tuple[bool, bool]:
    available = set(_available_comparison_options(current_ids))
    configured = [
        str(value)
        for value in st.session_state.get(COMPARISON_SELECTION_KEY, COMPARISON_OPTIONS)
        if str(value).strip() in available
    ]
    return "Borough benchmark" in configured, "London benchmark" in configured


def _status_badges(meta: dict[str, object]) -> None:
    badge_pairs = [
        ("Neighbourhood estimate" if str(meta.get("neighbourhood_use_mode")) == "direct_neighbourhood_candidate" else "Use with caveats" if str(meta.get("neighbourhood_use_mode")) == "neighbourhood_estimate_with_caveats" else "Benchmark context"),
        str(meta.get("source_geography") or meta.get("geography_level") or "").strip(),
        str(meta.get("source_name") or "").strip(),
        str(meta.get("last_refresh_date") or "").strip(),
    ]
    chips = "".join(
        [
            (
                "<span style=\"display:inline-block; margin:0 0.35rem 0.35rem 0; "
                "padding:0.28rem 0.65rem; border-radius:999px; "
                "background:rgba(15,59,95,0.06); border:1px solid rgba(15,59,95,0.10); "
                "color:#4f6278; font-size:0.82rem;\">"
                f"{value}"
                "</span>"
            )
            for value in badge_pairs
            if value
        ]
    )
    if chips:
        st.markdown(chips, unsafe_allow_html=True)


def _section_switcher(active_section: str, *, home_page: bool = False) -> None:
    labels = list(SECTION_TARGETS.keys())
    cols = st.columns(len(labels), gap="small")
    for col, label in zip(cols, labels, strict=False):
        with col:
            if st.button(
                label,
                key=f"section_tab_{label.replace(' ', '_').replace('&', 'and').lower()}",
                type="primary" if label == active_section else "secondary",
                use_container_width=True,
            ):
                if label == active_section:
                    continue
                st.session_state[APP_SECTION_KEY] = label
                if label in {"Guide", "Setup"}:
                    if home_page:
                        st.rerun()
                    else:
                        st.switch_page("Home.py")
                else:
                    st.switch_page(SECTION_TARGETS[label])


def _explorer_period_for_indicator(indicator_id: str) -> str:
    configured_period = str(st.session_state.get(PERIOD_KEY, ""))
    configured_indicator = str(st.session_state.get(INDICATOR_KEY, ""))
    period_options = available_periods(indicator_id)
    if indicator_id == configured_indicator and configured_period in period_options:
        return configured_period
    latest = latest_period(indicator_id)
    if latest is not None:
        return str(latest)
    return configured_period


def _current_borough_context(reference_df: pd.DataFrame, current_ids: list[str]) -> str:
    if not current_ids:
        return "No borough context yet"
    selected = reference_df[reference_df["neighbourhood_id"].astype(str).isin({str(value) for value in current_ids})].copy()
    boroughs: list[str] = []
    for raw in selected["borough_name"].dropna().astype(str):
        boroughs.extend([item.strip() for item in raw.split(";") if item.strip()])
    unique_boroughs = sorted(set(boroughs))
    if not unique_boroughs:
        return "No borough context available"
    if len(unique_boroughs) == 1:
        return unique_boroughs[0]
    return f"{len(unique_boroughs)} boroughs"


def _powerpoint_report_signature(
    *,
    selected_ids_in_scope: list[str],
    selected_indicator_ids: list[str],
    report_categories: list[str],
    current_indicator_id: str,
    current_period: str,
    include_borough: bool,
    include_london: bool,
    include_overview: bool,
    include_detail_tables: bool,
    include_methodology: bool,
    report_title: str,
    visual_overrides: dict[str, str],
    visual_config_overrides: dict[str, dict[str, object]],
) -> str:
    payload = {
        "selected_ids": sorted(str(value) for value in selected_ids_in_scope),
        "indicator_ids": sorted(str(value) for value in selected_indicator_ids),
        "report_categories": list(report_categories),
        "current_indicator_id": str(current_indicator_id),
        "current_period": str(current_period),
        "include_borough": bool(include_borough),
        "include_london": bool(include_london),
        "include_overview": bool(include_overview),
        "include_detail_tables": bool(include_detail_tables),
        "include_methodology": bool(include_methodology),
        "report_title": str(report_title).strip(),
        "visual_overrides": dict(sorted((str(key), str(value)) for key, value in visual_overrides.items())),
        "visual_config_overrides": visual_config_overrides,
    }
    return json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True)


def _powerpoint_report_ready(current_signature: str) -> bool:
    return bool(st.session_state.get(PPT_REPORT_BYTES_KEY)) and (
        st.session_state.get(PPT_REPORT_SIGNATURE_KEY) == current_signature
    )


def _render_powerpoint_report_control(
    *,
    catalog_df: pd.DataFrame,
    current_category_labels: list[str],
    current_indicator_id: str,
    current_period: str,
    selected_ids_in_scope: list[str],
    include_borough: bool,
    include_london: bool,
) -> None:
    with st.popover("PowerPoint report"):
        st.markdown("**Configure slide content**")
        st.caption("Choose what to include in the report.")

        if not selected_ids_in_scope:
            st.info("Select one or more neighbourhoods before generating a PowerPoint report.")
            return

        if not _powerpoint_available():
            st.warning("PowerPoint export requires the `python-pptx` package in the active Streamlit environment.")
            return

        report_categories, selected_indicator_ids = _render_powerpoint_indicator_group_configuration(
            catalog_df,
            current_category_labels,
            current_indicator_id=current_indicator_id,
        )
        indicator_catalog = (
            catalog_df[catalog_df["top_level_category"].isin(report_categories)]
            .sort_values(["category_sort_order", "module_sort_order", "indicator_sort_order", "ui_title"])
            .reset_index(drop=True)
        )
        if indicator_catalog.empty:
            st.info("Choose at least one category to populate the slide list.")
            return

        report_title = st.text_input(
            "Report title",
            value=st.session_state.get(
                "ppt_report_title",
                f"London neighbourhood report - {_selection_label(selected_ids_in_scope)}",
            ),
            key="ppt_report_title",
        )
        include_overview, include_detail_tables, include_methodology = _render_powerpoint_slide_options()
        visual_overrides, visual_config_overrides = _render_powerpoint_visual_configuration(
            selected_indicator_ids,
            current_ids=selected_ids_in_scope,
            include_borough=include_borough,
            include_london=include_london,
        )
        if _gp_registered_population_requires_distribution_only("gp_registered_population_total", selected_ids_in_scope):
            visual_overrides.setdefault("gp_registered_population_total", "ranked_distribution")

        comparisons = []
        if include_borough:
            comparisons.append("borough benchmark")
        if include_london:
            comparisons.append("London benchmark")
        st.caption(
            f"Comparisons in report: {', '.join(comparisons) if comparisons else 'none'}. "
            "The current preview period is used for the active map indicator; other indicators use their latest available period."
        )

        if not selected_indicator_ids:
            st.info("Choose at least one indicator to prepare the PowerPoint.")
            return

        current_signature = _powerpoint_report_signature(
            selected_ids_in_scope=selected_ids_in_scope,
            selected_indicator_ids=[str(value) for value in selected_indicator_ids],
            report_categories=report_categories,
            current_indicator_id=str(current_indicator_id),
            current_period=str(current_period),
            include_borough=include_borough,
            include_london=include_london,
            include_overview=include_overview,
            include_detail_tables=include_detail_tables,
            include_methodology=include_methodology,
            report_title=report_title,
            visual_overrides=visual_overrides,
            visual_config_overrides=visual_config_overrides,
        )

        action_slot = st.empty()
        status_slot = st.empty()

        def _render_download_action() -> None:
            with action_slot.container():
                st.markdown("<div class='ppt-download-ready-marker' data-ppt-download-ready='true'></div>", unsafe_allow_html=True)
                st.download_button(
                    "Download PowerPoint",
                    data=st.session_state[PPT_REPORT_BYTES_KEY],
                    file_name=st.session_state.get(PPT_REPORT_FILENAME_KEY, "neighbourhood_report.pptx"),
                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    use_container_width=True,
                    type="primary",
                    key="download_powerpoint_report",
                    on_click="ignore",
                )

        if _powerpoint_report_ready(current_signature):
            _render_download_action()
            return

        if action_slot.button("Prepare PowerPoint", type="primary", use_container_width=True, key="prepare_powerpoint_report"):
            with action_slot.container():
                render_loading_button(
                    button_key="prepare_powerpoint_report",
                    prefix="Preparing",
                    words=POWERPOINT_CAROUSEL_WORDS,
                )
            try:
                ppt_bytes = _build_powerpoint_report(
                    selected_ids=selected_ids_in_scope,
                    indicator_ids=[str(value) for value in selected_indicator_ids],
                    current_indicator_id=str(current_indicator_id),
                    current_period=str(current_period),
                    include_borough=include_borough,
                    include_london=include_london,
                    include_overview_slide=include_overview,
                    include_detail_tables=include_detail_tables,
                    include_methodology_slide=include_methodology,
                    report_title=report_title,
                    configured_topics=report_categories,
                    indicator_visual_overrides=visual_overrides,
                    indicator_visual_config_overrides=visual_config_overrides,
                )
                st.session_state[PPT_REPORT_BYTES_KEY] = ppt_bytes
                st.session_state[PPT_REPORT_FILENAME_KEY] = f"{_safe_filename(report_title)}.pptx"
                st.session_state[PPT_REPORT_SIGNATURE_KEY] = current_signature
                status_slot.empty()
                _render_download_action()
            except Exception as exc:
                st.session_state.pop(PPT_REPORT_SIGNATURE_KEY, None)
                action_slot.empty()
                status_slot.error("PowerPoint generation failed.")
                st.exception(exc)


def _render_powerpoint_header_panel(
    *,
    catalog_df: pd.DataFrame,
    current_category_labels: list[str],
    current_indicator_id: str,
    current_period: str,
    selected_ids_in_scope: list[str],
    include_borough: bool,
    include_london: bool,
) -> None:
    st.markdown("<div class='section-kicker'>Export</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-card-title'>PowerPoint report</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-card-text'>Open the export setup window to build a shareable slide deck.</div>",
        unsafe_allow_html=True,
    )
    _render_powerpoint_report_control(
        catalog_df=catalog_df,
        current_category_labels=current_category_labels,
        current_indicator_id=current_indicator_id,
        current_period=current_period,
        selected_ids_in_scope=selected_ids_in_scope,
        include_borough=include_borough,
        include_london=include_london,
    )


def _render_setup_selector(reference_df: pd.DataFrame) -> None:
    reference_with_systems = _reference_with_system_names(reference_df).sort_values(
        ["icb_name", "borough_name", "neighbourhood_name"]
    ).reset_index(drop=True)
    current_ids = selected_ids()
    perspective = str(st.session_state.get(SPATIAL_PERSPECTIVE_KEY, "Neighbourhood"))
    if perspective not in SPATIAL_PERSPECTIVE_OPTIONS:
        perspective = "Neighbourhood"
        st.session_state[SPATIAL_PERSPECTIVE_KEY] = perspective

    if perspective == "Neighbourhood":
        boroughs = sorted(
            {
                item.strip()
                for raw in reference_with_systems["borough_name"].dropna().astype(str)
                for item in raw.split(";")
                if item.strip()
            }
        )
        st.multiselect("Filter the neighbourhood list by borough", boroughs, key=BOROUGH_FILTER_KEY)
        filtered_reference = _borough_filtered(reference_with_systems, st.session_state.get(BOROUGH_FILTER_KEY, []))
        checked_ids = render_scrollable_multi_select_checkbox_list(
            options=[
                (str(row.neighbourhood_id), f"{row.borough_name} - {row.neighbourhood_name}")
                for row in filtered_reference.itertuples(index=False)
            ],
            default_selected_ids=_matching_scope_defaults(reference_with_systems, current_ids, perspective),
            widget_prefix="configuration_neighbourhood_scope",
            height=470,
        )
        if sorted(current_ids) != sorted(checked_ids):
            set_selected_ids(sorted(checked_ids))
    elif perspective == "System":
        system_df = (
            reference_with_systems[["icb_code", "icb_name"]]
            .drop_duplicates()
            .sort_values(["icb_name", "icb_code"])
            .reset_index(drop=True)
        )
        checked_ids = render_scrollable_multi_select_checkbox_list(
            options=[(str(row.icb_code), f"{row.icb_name} ({row.icb_code})") for row in system_df.itertuples(index=False)],
            default_selected_ids=_matching_scope_defaults(reference_with_systems, current_ids, perspective),
            widget_prefix="configuration_system_scope",
            height=520,
        )
        derived_ids = sorted(
            reference_with_systems[
                reference_with_systems["icb_code"].astype(str).isin(set(checked_ids))
            ]["neighbourhood_id"].astype(str).unique().tolist()
        )
        if sorted(current_ids) != derived_ids:
            set_selected_ids(derived_ids)
    elif perspective == "Place":
        place_df = (
            _place_membership_frame(reference_with_systems)[["borough_code", "borough_name"]]
            .drop_duplicates()
            .loc[lambda frame: frame["borough_code"].astype(str).str.strip().ne("") & frame["borough_name"].astype(str).str.strip().ne("")]
            .sort_values(["borough_name", "borough_code"])
            .reset_index(drop=True)
        )
        checked_ids = render_scrollable_multi_select_checkbox_list(
            options=[(str(row.borough_code), str(row.borough_name)) for row in place_df.itertuples(index=False)],
            default_selected_ids=_matching_scope_defaults(reference_with_systems, current_ids, perspective),
            widget_prefix="configuration_place_scope",
            height=520,
        )
        derived_ids = _derive_neighbourhood_ids_for_places(reference_with_systems, checked_ids)
        if sorted(current_ids) != derived_ids:
            set_selected_ids(derived_ids)
    else:
        all_ids = sorted(reference_with_systems["neighbourhood_id"].astype(str).unique().tolist())
        if sorted(current_ids) != all_ids:
            set_selected_ids(all_ids)
        st.info("All neighbourhoods are currently in scope for the London-wide region view.")

    selection_descriptor = resolve_footprint_label(selected_ids(), reference_with_systems)
    if selection_descriptor.kind == "region":
        st.caption(f"Current scope: London ({reference_with_systems['neighbourhood_id'].nunique()} neighbourhoods)")
    elif selection_descriptor.kind == "system":
        if selection_descriptor.item_count == 1:
            st.caption(f"Selected system: {selection_descriptor.label}")
        else:
            system_total = reference_with_systems["icb_code"].dropna().astype(str).nunique()
            st.caption(f"Selected systems: {selection_descriptor.item_count} of {system_total}")
    elif selection_descriptor.kind == "place":
        if selection_descriptor.item_count == 1:
            st.caption(f"Selected place: {selection_descriptor.label}")
        elif selection_descriptor.item_count == 2:
            st.caption(f"Selected places: {selection_descriptor.label}")
        else:
            place_total = _place_membership_frame(reference_with_systems)["borough_code"].dropna().astype(str).nunique()
            st.caption(f"Selected places: {selection_descriptor.item_count} of {place_total}")
    elif selection_descriptor.item_count == 1:
        st.caption(f"Selected neighbourhood: {selection_descriptor.label}")
    else:
        st.caption(f"Selected neighbourhoods: {len(selected_ids())} of {reference_with_systems['neighbourhood_id'].nunique()}")


def _render_setup_map(map_mode: str) -> None:
    value_df = pd.DataFrame(columns=["neighbourhood_id", "value", "unit"])
    overlay = load_hex_icb_geography()
    current_ids = selected_ids()

    def _maybe_toggle(clicked_id: str | None) -> None:
        if clicked_id:
            toggle_selected_id(clicked_id)
            st.rerun()

    variant = "hex" if map_mode == "Hex map" else "real"
    clicked = render_selection_map(
        load_map_geography("hex" if variant == "hex" else "real"),
        value_df,
        current_ids,
        map_key=f"configuration_{variant}",
        variant=variant,
        overlay_geo_df=overlay if variant == "hex" else None,
        height=520,
    )
    if variant == "real":
        _maybe_toggle(clicked)


def _indicator_selector_topic_catalog(topic_catalog: pd.DataFrame) -> pd.DataFrame:
    catalog = topic_catalog.copy()
    if _is_qof_module_catalog(catalog):
        catalog = _qof_public_metric_catalog(catalog)
    if catalog.empty:
        return catalog
    return _ordered_indicator_catalog_for_display(catalog).reset_index(drop=True)


def _indicator_selector_label(row: pd.Series | dict[str, object]) -> str:
    title = _clean_text(row.get("ui_title")) or _clean_text(row.get("title")) or _clean_text(row.get("indicator_id"))
    short_title = _clean_text(row.get("ui_short_title")) or _clean_text(row.get("short_title"))
    indicator_id = _clean_text(row.get("indicator_id"))
    use_short_title = (
        short_title
        and short_title.lower() != title.lower()
        and (indicator_id.startswith("qof_") or len(title) > 56)
    )
    return short_title if use_short_title else title


def _indicator_selector_help_text(row: pd.Series | dict[str, object]) -> str:
    description = _truncate_text(row.get("description") or row.get("module_description"), max_chars=180)
    methodology = _truncate_text(row.get("methodology_summary"), max_chars=180)
    source_name = _clean_text(row.get("source_name"))
    help_parts = [part for part in [description, methodology] if part]
    if source_name:
        help_parts.append(f"Source: {source_name}")
    return "\n\n".join(help_parts)


def _indicator_selector_search_text(row: pd.Series | dict[str, object]) -> str:
    parts = [
        _indicator_selector_label(row),
        row.get("description"),
        row.get("module_description"),
        row.get("methodology_summary"),
        row.get("source_name"),
    ]
    return _normalise_search_text(" ".join(_clean_text(part) for part in parts if _clean_text(part)))


def _selected_count_for_ids(indicator_ids: list[str], selected_ids: set[str]) -> int:
    return sum(1 for indicator_id in indicator_ids if str(indicator_id) in selected_ids)


def _selection_state_from_counts(selected_count: int, total_count: int) -> str:
    if total_count <= 0 or selected_count <= 0:
        return "none"
    if selected_count >= total_count:
        return "full"
    return "partial"


def _get_topic_selection_state(topic_node: dict[str, object]) -> str:
    return _selection_state_from_counts(int(topic_node["selected_count"]), int(topic_node["total_count"]))


def _get_theme_selection_state(theme_node: dict[str, object]) -> str:
    return _selection_state_from_counts(int(theme_node["selected_count"]), int(theme_node["total_count"]))


def _selection_meta_html(selected_count: int, total_count: int) -> str:
    state = _selection_state_from_counts(selected_count, total_count)
    return (
        "<div class='selector-row-meta'>"
        f"<span class='selector-count'>{selected_count}/{total_count} selected</span>"
        f"<span class='selector-state selector-state--{state}'>{state.capitalize()}</span>"
        "</div>"
    )


def _ordered_selected_indicator_ids(valid_indicator_ids: list[str], selected_ids: list[str] | set[str]) -> list[str]:
    selected_set = {str(value) for value in selected_ids if str(value).strip()}
    return [indicator_id for indicator_id in valid_indicator_ids if indicator_id in selected_set]


def _store_selected_indicator_ids(valid_indicator_ids: list[str], selected_ids: list[str] | set[str]) -> list[str]:
    ordered = _ordered_selected_indicator_ids(valid_indicator_ids, selected_ids)
    st.session_state[INDICATOR_SELECTION_KEY] = ordered
    return ordered


def _apply_indicator_selection(indicator_ids: list[str], include: bool, valid_indicator_ids: list[str]) -> None:
    selected = set(_ordered_selected_indicator_ids(valid_indicator_ids, st.session_state.get(INDICATOR_SELECTION_KEY, [])))
    indicator_id_set = {str(value) for value in indicator_ids}
    if include:
        selected.update(indicator_id_set)
    else:
        selected.difference_update(indicator_id_set)
    _store_selected_indicator_ids(valid_indicator_ids, selected)


def _apply_topic_selection(topic_indicator_ids: list[str], include: bool, valid_indicator_ids: list[str]) -> None:
    _apply_indicator_selection(topic_indicator_ids, include, valid_indicator_ids)


def _apply_theme_selection(theme_indicator_ids: list[str], include: bool, valid_indicator_ids: list[str]) -> None:
    _apply_indicator_selection(theme_indicator_ids, include, valid_indicator_ids)


def _apply_theme_selection_from_widget(widget_key: str, theme_indicator_ids: list[str], valid_indicator_ids: list[str]) -> None:
    include = bool(st.session_state.get(widget_key))
    _apply_theme_selection(theme_indicator_ids, include, valid_indicator_ids)


def _apply_topic_selection_from_widget(widget_key: str, topic_indicator_ids: list[str], valid_indicator_ids: list[str]) -> None:
    include = bool(st.session_state.get(widget_key))
    _apply_topic_selection(topic_indicator_ids, include, valid_indicator_ids)


def _apply_indicator_selection_from_widget(widget_key: str, indicator_id: str, valid_indicator_ids: list[str]) -> None:
    include = bool(st.session_state.get(widget_key))
    _apply_indicator_selection([indicator_id], include, valid_indicator_ids)


def _indicator_selector_topic_key(theme_label: str, topic_label: str, topic_catalog: pd.DataFrame) -> str:
    module_key = _clean_text(topic_catalog.iloc[0].get("module_key")) if not topic_catalog.empty else ""
    key_body = module_key or _theme_widget_slug(topic_label)
    return f"{_theme_widget_slug(theme_label)}::{key_body}"


def _build_indicator_selection_hierarchy(
    in_scope: pd.DataFrame,
    category_labels: list[str],
) -> list[dict[str, object]]:
    selected_ids = {
        str(value)
        for value in st.session_state.get(INDICATOR_SELECTION_KEY, [])
        if str(value).strip()
    }
    theme_nodes: list[dict[str, object]] = []

    for category_label in category_labels:
        category_df = in_scope[in_scope["top_level_category"].astype(str) == str(category_label)].copy()
        if category_df.empty:
            continue

        topic_nodes: list[dict[str, object]] = []
        for topic_label, raw_topic_catalog in _subcategory_groups_for_theme(category_df):
            topic_catalog = _indicator_selector_topic_catalog(raw_topic_catalog)
            if topic_catalog.empty:
                continue

            exposure_series = (
                topic_catalog.get("ui_exposure_level", pd.Series("standard", index=topic_catalog.index))
                .astype(str)
                .replace("nan", "standard")
                .str.lower()
            )
            core_catalog = topic_catalog[exposure_series != "advanced"].copy().reset_index(drop=True)
            advanced_catalog = topic_catalog[exposure_series == "advanced"].copy().reset_index(drop=True)
            indicator_ids = topic_catalog["indicator_id"].astype(str).tolist()
            description = (
                _clean_text(topic_catalog.iloc[0].get("module_description"))
                or _clean_text(topic_catalog.iloc[0].get("description"))
            )

            topic_nodes.append(
                {
                    "key": _indicator_selector_topic_key(category_label, topic_label, topic_catalog),
                    "label": str(topic_label),
                    "description": description,
                    "indicator_ids": indicator_ids,
                    "selected_count": _selected_count_for_ids(indicator_ids, selected_ids),
                    "total_count": len(indicator_ids),
                    "advanced_selected_count": _selected_count_for_ids(
                        advanced_catalog["indicator_id"].astype(str).tolist(),
                        selected_ids,
                    ),
                    "catalog": topic_catalog,
                    "core_catalog": core_catalog,
                    "advanced_catalog": advanced_catalog,
                    "search_text": _normalise_search_text(
                        " ".join(
                            [
                                str(category_label),
                                str(topic_label),
                                description,
                                " ".join(
                                    _indicator_selector_search_text(row)
                                    for row in topic_catalog.to_dict(orient="records")
                                ),
                            ]
                        )
                    ),
                }
            )

        if not topic_nodes:
            continue

        theme_indicator_ids = list(
            dict.fromkeys(
                indicator_id
                for topic_node in topic_nodes
                for indicator_id in topic_node["indicator_ids"]
            )
        )
        theme_nodes.append(
            {
                "label": str(category_label),
                "topics": topic_nodes,
                "indicator_ids": theme_indicator_ids,
                "selected_count": _selected_count_for_ids(theme_indicator_ids, selected_ids),
                "total_count": len(theme_indicator_ids),
                "search_text": _normalise_search_text(
                    " ".join([str(category_label)] + [str(topic["search_text"]) for topic in topic_nodes])
                ),
            }
        )

    return theme_nodes


def _filter_hierarchy_for_selector(
    theme_nodes: list[dict[str, object]],
    *,
    theme_filter: str,
    subtheme_filter: str,
    indicator_filter: str,
) -> list[dict[str, object]]:
    filtered_nodes: list[dict[str, object]] = []

    for theme_node in theme_nodes:
        theme_label = _clean_text(theme_node.get("label"))
        if theme_filter != ANY_THEME_FILTER_LABEL and theme_label != theme_filter:
            continue

        matched_topics: list[dict[str, object]] = []
        for topic_node in theme_node["topics"]:
            topic_label = _clean_text(topic_node.get("label"))
            if subtheme_filter != ANY_SUBTHEME_FILTER_LABEL and topic_label != subtheme_filter:
                continue

            topic_catalog = _selector_catalog_for_toolbar(topic_node)
            if indicator_filter != ANY_INDICATOR_FILTER_LABEL and not topic_catalog.empty:
                topic_catalog = topic_catalog[
                    topic_catalog.apply(
                        lambda row: _indicator_selector_label(row) == indicator_filter,
                        axis=1,
                    )
                ].copy()
            if topic_catalog.empty:
                continue

            exposure_series = (
                topic_catalog.get("ui_exposure_level", pd.Series("standard", index=topic_catalog.index))
                .astype(str)
                .replace("nan", "standard")
                .str.lower()
            )
            matched_topics.append(
                {
                    **topic_node,
                    "catalog": topic_catalog.reset_index(drop=True),
                    "core_catalog": topic_catalog[exposure_series != "advanced"].copy().reset_index(drop=True),
                    "advanced_catalog": topic_catalog[exposure_series == "advanced"].copy().reset_index(drop=True),
                }
            )

        if not matched_topics:
            continue

        filtered_nodes.append({**theme_node, "topics": matched_topics})

    return filtered_nodes


def _set_active_indicator_selector_context(theme_label: str, topic_key: str) -> None:
    st.session_state[INDICATOR_SELECTOR_ACTIVE_THEME_KEY] = str(theme_label)
    st.session_state[INDICATOR_SELECTOR_ACTIVE_TOPIC_KEY] = str(topic_key)
    st.session_state[INDICATOR_SELECTOR_TOPIC_SEARCH_KEY] = ""


def _ensure_indicator_selector_focus(theme_nodes: list[dict[str, object]]) -> tuple[str, str]:
    if not theme_nodes:
        st.session_state[INDICATOR_SELECTOR_ACTIVE_THEME_KEY] = ""
        st.session_state[INDICATOR_SELECTOR_ACTIVE_TOPIC_KEY] = ""
        return "", ""

    theme_lookup = {str(theme_node["label"]): theme_node for theme_node in theme_nodes}
    active_theme_label = str(st.session_state.get(INDICATOR_SELECTOR_ACTIVE_THEME_KEY, ""))
    if active_theme_label not in theme_lookup:
        active_theme_label = str(theme_nodes[0]["label"])
        st.session_state[INDICATOR_SELECTOR_ACTIVE_THEME_KEY] = active_theme_label

    topic_nodes = list(theme_lookup[active_theme_label]["topics"])
    topic_lookup = {str(topic_node["key"]): topic_node for topic_node in topic_nodes}
    active_topic_key = str(st.session_state.get(INDICATOR_SELECTOR_ACTIVE_TOPIC_KEY, ""))
    if active_topic_key not in topic_lookup:
        active_topic_key = str(topic_nodes[0]["key"]) if topic_nodes else ""
        st.session_state[INDICATOR_SELECTOR_ACTIVE_TOPIC_KEY] = active_topic_key
        st.session_state[INDICATOR_SELECTOR_TOPIC_SEARCH_KEY] = ""

    return active_theme_label, active_topic_key


def _active_selector_nodes(
    theme_nodes: list[dict[str, object]],
    active_theme_label: str,
    active_topic_key: str,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    active_theme_node = next(
        (theme_node for theme_node in theme_nodes if str(theme_node["label"]) == str(active_theme_label)),
        None,
    )
    if active_theme_node is None:
        return None, None
    active_topic_node = next(
        (
            topic_node
            for topic_node in active_theme_node["topics"]
            if str(topic_node["key"]) == str(active_topic_key)
        ),
        None,
    )
    return active_theme_node, active_topic_node


def _render_panel_header(
    *,
    step_number: int,
    title: str,
    helper_text: str,
    dependency_prefix: str = "",
    dependency_value: str = "",
    dependency_empty_text: str = "",
) -> None:
    if dependency_value.strip():
        dependency_markup = (
            "<div class='selector-panel-context'>"
            f"{escape(dependency_prefix)} <strong>{escape(dependency_value)}</strong>"
            "</div>"
        )
    elif dependency_empty_text.strip():
        dependency_markup = (
            "<div class='selector-panel-context selector-panel-context--muted'>"
            f"{escape(dependency_empty_text)}"
            "</div>"
        )
    else:
        dependency_markup = ""

    st.markdown(
        (
            "<div class='selector-panel-header'>"
            f"<div class='selector-panel-title'>{escape(title)}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _render_empty_panel_state(title: str, message: str) -> None:
    st.markdown(
        (
            "<div class='selector-empty-state'>"
            f"<div class='selector-empty-title'>{escape(title)}</div>"
            f"<div class='selector-empty-text'>{escape(message)}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _selector_catalog_for_toolbar(
    topic_node: dict[str, object],
) -> pd.DataFrame:
    topic_catalog = topic_node.get("catalog", pd.DataFrame())
    if not isinstance(topic_catalog, pd.DataFrame) or topic_catalog.empty:
        return pd.DataFrame()
    return topic_catalog.copy().reset_index(drop=True)


def _selector_theme_filter_options(
    theme_nodes: list[dict[str, object]],
) -> list[str]:
    options = [ANY_THEME_FILTER_LABEL]
    for theme_node in theme_nodes:
        has_visible_topic = any(
            not _selector_catalog_for_toolbar(topic_node).empty
            for topic_node in theme_node.get("topics", [])
        )
        theme_label = _clean_text(theme_node.get("label"))
        if has_visible_topic and theme_label and theme_label not in options:
            options.append(theme_label)
    return options


def _selector_subtheme_filter_options(
    theme_nodes: list[dict[str, object]],
    theme_filter: str,
) -> list[str]:
    options = [ANY_SUBTHEME_FILTER_LABEL]
    for theme_node in theme_nodes:
        theme_label = _clean_text(theme_node.get("label"))
        if theme_filter != ANY_THEME_FILTER_LABEL and theme_label != theme_filter:
            continue
        for topic_node in theme_node.get("topics", []):
            filtered_catalog = _selector_catalog_for_toolbar(topic_node)
            topic_label = _clean_text(topic_node.get("label"))
            if not filtered_catalog.empty and topic_label and topic_label not in options:
                options.append(topic_label)
    return options


def _selector_indicator_filter_options(
    theme_nodes: list[dict[str, object]],
    theme_filter: str,
    subtheme_filter: str,
) -> list[str]:
    options = [ANY_INDICATOR_FILTER_LABEL]
    for theme_node in theme_nodes:
        theme_label = _clean_text(theme_node.get("label"))
        if theme_filter != ANY_THEME_FILTER_LABEL and theme_label != theme_filter:
            continue
        for topic_node in theme_node.get("topics", []):
            topic_label = _clean_text(topic_node.get("label"))
            if subtheme_filter != ANY_SUBTHEME_FILTER_LABEL and topic_label != subtheme_filter:
                continue
            filtered_catalog = _selector_catalog_for_toolbar(topic_node)
            if filtered_catalog.empty:
                continue
            for row in filtered_catalog.to_dict(orient="records"):
                indicator_label = _indicator_selector_label(row)
                if indicator_label and indicator_label not in options:
                    options.append(indicator_label)
    return options


def _clear_selector_filter_if_invalid(state_key: str, valid_options: list[str]) -> None:
    current_value = _clean_text(st.session_state.get(state_key))
    if current_value and current_value not in valid_options:
        st.session_state[state_key] = valid_options[0] if valid_options else ""


def _render_selection_toolbar(
    theme_nodes: list[dict[str, object]],
) -> None:
    theme_filter_options = _selector_theme_filter_options(theme_nodes)
    _clear_selector_filter_if_invalid(INDICATOR_SELECTOR_THEME_FILTER_KEY, theme_filter_options)
    theme_filter = _clean_text(st.session_state.get(INDICATOR_SELECTOR_THEME_FILTER_KEY)) or ANY_THEME_FILTER_LABEL

    subtheme_filter_options = _selector_subtheme_filter_options(
        theme_nodes,
        theme_filter=theme_filter,
    )
    _clear_selector_filter_if_invalid(INDICATOR_SELECTOR_SUBTHEME_FILTER_KEY, subtheme_filter_options)
    subtheme_filter = _clean_text(st.session_state.get(INDICATOR_SELECTOR_SUBTHEME_FILTER_KEY)) or ANY_SUBTHEME_FILTER_LABEL

    indicator_filter_options = _selector_indicator_filter_options(
        theme_nodes,
        theme_filter=theme_filter,
        subtheme_filter=subtheme_filter,
    )
    _clear_selector_filter_if_invalid(INDICATOR_SELECTOR_INDICATOR_FILTER_KEY, indicator_filter_options)

    top_toolbar_cols = st.columns([1.0, 1.0, 1.0, 1.0], gap="small", vertical_alignment="bottom")
    with top_toolbar_cols[0]:
        st.selectbox(
            "Theme",
            options=theme_filter_options,
            key=INDICATOR_SELECTOR_THEME_FILTER_KEY,
        )
    with top_toolbar_cols[1]:
        st.selectbox(
            "Subtheme",
            options=subtheme_filter_options,
            key=INDICATOR_SELECTOR_SUBTHEME_FILTER_KEY,
        )
    with top_toolbar_cols[2]:
        st.selectbox(
            "Indicator",
            options=indicator_filter_options,
            key=INDICATOR_SELECTOR_INDICATOR_FILTER_KEY,
        )
    with top_toolbar_cols[3]:
        st.toggle(
            "Show advanced indicators",
            key=INDICATOR_SELECTOR_SHOW_ADVANCED_KEY,
        )

def _render_selector_header_col(
    *,
    title: str,
    select_key: str,
    deselect_key: str,
    select_disabled: bool,
    deselect_disabled: bool,
    on_select=None,
    on_deselect=None,
    hide_actions: bool = False,
) -> None:
    """Render a panel header: title on the left, Select all / Deselect all
    on the right.  All three panels use the same column structure so the
    bordered containers keep them vertically aligned."""
    _hdr = st.columns([1, 0.48, 0.58], gap="small", vertical_alignment="center")
    with _hdr[0]:
        st.markdown(
            f"<span class='selector-panel-title'>{escape(title)}</span>",
            unsafe_allow_html=True,
        )
    sel_label = "\u200b" if hide_actions else "Select all"
    desel_label = "\u200b" if hide_actions else "Deselect all"
    with _hdr[1]:
        if st.button(sel_label, key=select_key, disabled=select_disabled, type="tertiary"):
            if on_select:
                on_select()
                st.rerun()
    with _hdr[2]:
        if st.button(desel_label, key=deselect_key, disabled=deselect_disabled, type="tertiary"):
            if on_deselect:
                on_deselect()
                st.rerun()


def _render_theme_list(
    theme_nodes: list[dict[str, object]],
    active_theme_label: str,
    valid_indicator_ids: list[str],
) -> None:
    if not theme_nodes:
        _render_empty_panel_state(
            "No themes available",
            "No themes match the current filters. Clear or change the search to continue.",
        )
        return

    _THEME_SHORT_LABELS = {
        "Social Factors & Wider Determinants": "Social & Wider Determinants",
    }

    with st.container(height=500, border=False):
        for theme_node in theme_nodes:
            is_active = str(theme_node["label"]) == str(active_theme_label)
            theme_slug = _theme_widget_slug(str(theme_node["label"]))
            widget_key = f"selector_theme_include_{theme_slug}"
            st.session_state[widget_key] = int(theme_node["selected_count"]) > 0
            display_label = _THEME_SHORT_LABELS.get(str(theme_node["label"]), str(theme_node["label"]))

            with st.container(border=True):
                row_cols = st.columns([0.1, 0.9], gap="small")
                with row_cols[0]:
                    st.checkbox(
                        f"Toggle {theme_node['label']}",
                        key=widget_key,
                        label_visibility="collapsed",
                        on_change=_apply_theme_selection_from_widget,
                        args=(widget_key, list(theme_node["indicator_ids"]), valid_indicator_ids),
                    )
                with row_cols[1]:
                    if st.button(
                        display_label,
                        key=f"selector_theme_{theme_slug}",
                        type="primary" if is_active else "secondary",
                        use_container_width=True,
                    ):
                        first_topic_key = str(theme_node["topics"][0]["key"]) if theme_node["topics"] else ""
                        _set_active_indicator_selector_context(str(theme_node["label"]), first_topic_key)
                        st.rerun()


def _render_topic_list(
    theme_nodes: list[dict[str, object]],
    active_theme_label: str,
    active_topic_key: str,
    valid_indicator_ids: list[str],
) -> None:
    active_theme_node, _ = _active_selector_nodes(theme_nodes, active_theme_label, active_topic_key)
    if active_theme_node is None:
        _render_empty_panel_state(
            "Choose a theme first",
            "The topics panel updates once you choose a theme in the first column.",
        )
        return

    with st.container(height=500, border=False):
        for topic_node in active_theme_node["topics"]:
            topic_slug = str(topic_node["key"]).replace(":", "_")
            widget_key = f"selector_topic_include_{topic_slug}"
            st.session_state[widget_key] = int(topic_node["selected_count"]) > 0

            is_active = str(topic_node["key"]) == str(active_topic_key)
            with st.container(border=True):
                row_cols = st.columns([0.12, 0.88], gap="small")
                with row_cols[0]:
                    st.checkbox(
                        f"Toggle {topic_node['label']}",
                        key=widget_key,
                        label_visibility="collapsed",
                        on_change=_apply_topic_selection_from_widget,
                        args=(widget_key, list(topic_node["indicator_ids"]), valid_indicator_ids),
                    )
                with row_cols[1]:
                    if st.button(
                        str(topic_node["label"]),
                        key=f"selector_topic_{topic_slug}",
                        type="primary" if is_active else "secondary",
                        use_container_width=True,
                    ):
                        _set_active_indicator_selector_context(str(active_theme_label), str(topic_node["key"]))
                        st.rerun()


def _render_indicator_checkbox_group(
    *,
    heading: str,
    catalog: pd.DataFrame,
    valid_indicator_ids: list[str],
) -> None:
    if catalog.empty:
        return

    selected_ids = {
        str(value)
        for value in st.session_state.get(INDICATOR_SELECTION_KEY, [])
        if str(value).strip()
    }
    if heading:
        st.markdown(f"**{heading}**")

    for row in catalog.to_dict(orient="records"):
        indicator_id = str(row["indicator_id"])
        widget_key = f"selector_indicator_{indicator_id}"
        st.session_state[widget_key] = indicator_id in selected_ids
        st.checkbox(
            _indicator_selector_label(row),
            key=widget_key,
            help=_indicator_selector_help_text(row),
            on_change=_apply_indicator_selection_from_widget,
            args=(widget_key, indicator_id, valid_indicator_ids),
        )


def _compute_indicator_panel_state(
    theme_nodes: list[dict[str, object]],
    active_theme_label: str,
    active_topic_key: str,
) -> tuple[dict[str, object] | None, list[str], int, pd.DataFrame, pd.DataFrame]:
    """Pre-compute indicator panel state needed by both the header row and
    the panel body.  Returns (active_topic_node, visible_indicator_ids,
    visible_selected_count, filtered_core_catalog, filtered_advanced_catalog)."""
    _, active_topic_node = _active_selector_nodes(theme_nodes, active_theme_label, active_topic_key)

    selected_ids = {
        str(value)
        for value in st.session_state.get(INDICATOR_SELECTION_KEY, [])
        if str(value).strip()
    } if active_topic_node is not None else set()

    show_advanced = bool(st.session_state.get(INDICATOR_SELECTOR_SHOW_ADVANCED_KEY, False))
    if active_topic_node is not None:
        filtered_core_catalog = active_topic_node["core_catalog"].copy().reset_index(drop=True)
        filtered_advanced_catalog = active_topic_node["advanced_catalog"].copy().reset_index(drop=True)
        visible_catalog_parts = [filtered_core_catalog]
        if show_advanced and not filtered_advanced_catalog.empty:
            visible_catalog_parts.append(filtered_advanced_catalog)
        visible_catalog = (
            pd.concat(visible_catalog_parts, ignore_index=True)
            if any(not catalog.empty for catalog in visible_catalog_parts)
            else pd.DataFrame()
        )
        visible_indicator_ids = visible_catalog["indicator_id"].astype(str).tolist() if not visible_catalog.empty else []
        visible_selected_count = _selected_count_for_ids(visible_indicator_ids, selected_ids)
    else:
        filtered_core_catalog = pd.DataFrame()
        filtered_advanced_catalog = pd.DataFrame()
        visible_indicator_ids = []
        visible_selected_count = 0

    return active_topic_node, visible_indicator_ids, visible_selected_count, filtered_core_catalog, filtered_advanced_catalog


def _render_indicator_panel(
    active_topic_node: dict[str, object] | None,
    filtered_core_catalog: pd.DataFrame,
    filtered_advanced_catalog: pd.DataFrame,
    valid_indicator_ids: list[str],
    show_advanced: bool = False,
) -> None:
    if active_topic_node is None:
        _render_empty_panel_state(
            "Choose a topic first",
            "The indicators panel updates once you select a topic in the middle column.",
        )
        return

    with st.container(height=500, border=False):
        if filtered_core_catalog.empty and filtered_advanced_catalog.empty:
            _render_empty_panel_state(
                "No indicators match this filter",
                "Try clearing the current theme, subtheme, or indicator filter to see more indicators.",
            )
            return

        if not filtered_core_catalog.empty:
            _render_indicator_checkbox_group(
                heading="",
                catalog=filtered_core_catalog,
                valid_indicator_ids=valid_indicator_ids,
            )

        if not filtered_advanced_catalog.empty:
            if show_advanced:
                _render_indicator_checkbox_group(
                    heading="Advanced indicators",
                    catalog=filtered_advanced_catalog,
                    valid_indicator_ids=valid_indicator_ids,
                )
            else:
                st.markdown(
                    (
                        "<div class='selector-advanced-callout'>"
                        f"<strong>{len(filtered_advanced_catalog)} advanced indicators hidden.</strong> "
                        "Turn on 'Show advanced indicators' in the toolbar to browse them."
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )


def _render_indicator_group_configuration(catalog_df: pd.DataFrame, category_labels: list[str]) -> tuple[list[str], list[str]]:
    in_scope = _indicator_options_for_categories(catalog_df, category_labels)
    if in_scope.empty:
        st.info("Choose at least one theme to make indicators available in the explorer.")
        st.session_state[CATEGORY_SELECTION_KEY] = []
        st.session_state[INDICATOR_SELECTION_KEY] = []
        return [], []

    valid_indicator_ids = in_scope["indicator_id"].astype(str).tolist()
    current_indicator_ids = _ordered_selected_indicator_ids(
        valid_indicator_ids,
        st.session_state.get(INDICATOR_SELECTION_KEY, []),
    )
    if not bool(st.session_state.get(INDICATOR_SELECTION_INITIALIZED_KEY, False)):
        current_indicator_ids = valid_indicator_ids.copy()
        st.session_state[INDICATOR_SELECTION_KEY] = current_indicator_ids
        st.session_state[INDICATOR_SELECTION_INITIALIZED_KEY] = True

    theme_nodes = _build_indicator_selection_hierarchy(in_scope, category_labels)
    theme_filter = _clean_text(st.session_state.get(INDICATOR_SELECTOR_THEME_FILTER_KEY)) or ANY_THEME_FILTER_LABEL
    subtheme_filter = _clean_text(st.session_state.get(INDICATOR_SELECTOR_SUBTHEME_FILTER_KEY)) or ANY_SUBTHEME_FILTER_LABEL
    indicator_filter = _clean_text(st.session_state.get(INDICATOR_SELECTOR_INDICATOR_FILTER_KEY)) or ANY_INDICATOR_FILTER_LABEL
    filtered_theme_nodes = _filter_hierarchy_for_selector(
        theme_nodes,
        theme_filter=theme_filter,
        subtheme_filter=subtheme_filter,
        indicator_filter=indicator_filter,
    )
    active_theme_label, active_topic_key = _ensure_indicator_selector_focus(filtered_theme_nodes)

    # State for the master-detail picker lives in session_state so the active
    # theme/topic and the search controls survive every rerun.
    _render_selection_toolbar(theme_nodes)
    st.markdown("<div style='margin-top: 1.2rem'></div>", unsafe_allow_html=True)

    # Pre-compute indicator panel state so the header row can show the
    # correct select-all / deselect-all state.
    (
        active_topic_node,
        visible_indicator_ids,
        visible_selected_count,
        filtered_core_catalog,
        filtered_advanced_catalog,
    ) = _compute_indicator_panel_state(
        filtered_theme_nodes, active_theme_label, active_topic_key,
    )

    # Compute header state needed by _render_selector_header_col
    active_theme_node, _ = _active_selector_nodes(
        filtered_theme_nodes, active_theme_label, active_topic_key,
    )

    theme_col, topic_col, indicator_col = st.columns(3, gap="small")
    with theme_col:
        with st.container(border=True, height=SETUP_SELECTOR_PANEL_HEIGHT):
            all_theme_selected = sum(int(n["selected_count"]) for n in filtered_theme_nodes)
            all_theme_total = sum(int(n["total_count"]) for n in filtered_theme_nodes)
            all_theme_ids = [
                iid for n in filtered_theme_nodes for iid in n["indicator_ids"]
            ]
            _render_selector_header_col(
                title="Themes",
                select_key="selector_theme_bulk_select_all",
                deselect_key="selector_theme_bulk_clear_all",
                select_disabled=all_theme_selected >= all_theme_total,
                deselect_disabled=all_theme_selected == 0,
                on_select=lambda: _apply_indicator_selection(all_theme_ids, True, valid_indicator_ids),
                on_deselect=lambda: _apply_indicator_selection(all_theme_ids, False, valid_indicator_ids),
                hide_actions=True,
            )
            _render_theme_list(filtered_theme_nodes, active_theme_label, valid_indicator_ids)
    with topic_col:
        with st.container(border=True, height=SETUP_SELECTOR_PANEL_HEIGHT):
            _render_selector_header_col(
                title="Topics",
                select_key=f"selector_topic_bulk_select_{_theme_widget_slug(active_theme_label)}",
                deselect_key=f"selector_topic_bulk_clear_{_theme_widget_slug(active_theme_label)}",
                select_disabled=active_theme_node is None or int(active_theme_node["selected_count"]) >= int(active_theme_node["total_count"]),
                deselect_disabled=active_theme_node is None or int(active_theme_node["selected_count"]) == 0,
                on_select=lambda: _apply_theme_selection(list(active_theme_node["indicator_ids"]), True, valid_indicator_ids),
                on_deselect=lambda: _apply_theme_selection(list(active_theme_node["indicator_ids"]), False, valid_indicator_ids),
            )
            _render_topic_list(
                filtered_theme_nodes,
                active_theme_label,
                active_topic_key,
                valid_indicator_ids,
            )
    with indicator_col:
        with st.container(border=True, height=SETUP_SELECTOR_PANEL_HEIGHT):
            _render_selector_header_col(
                title="Indicators",
                select_key=f"selector_indicator_bulk_select_{active_topic_key}",
                deselect_key=f"selector_indicator_bulk_clear_{active_topic_key}",
                select_disabled=active_topic_node is None or not visible_indicator_ids or visible_selected_count >= len(visible_indicator_ids),
                deselect_disabled=active_topic_node is None or not visible_indicator_ids or visible_selected_count == 0,
                on_select=lambda: _apply_indicator_selection(visible_indicator_ids, True, valid_indicator_ids),
                on_deselect=lambda: _apply_indicator_selection(visible_indicator_ids, False, valid_indicator_ids),
            )
            _render_indicator_panel(
                active_topic_node,
                filtered_core_catalog,
                filtered_advanced_catalog,
                valid_indicator_ids,
                show_advanced=bool(st.session_state.get(INDICATOR_SELECTOR_SHOW_ADVANCED_KEY, False)),
            )

    final_indicator_ids = _ordered_selected_indicator_ids(
        valid_indicator_ids,
        st.session_state.get(INDICATOR_SELECTION_KEY, []),
    )

    final_selected_set = set(final_indicator_ids)
    configured_categories = [
        str(theme_node["label"])
        for theme_node in theme_nodes
        if any(indicator_id in final_selected_set for indicator_id in theme_node["indicator_ids"])
    ]

    st.session_state[CATEGORY_SELECTION_KEY] = configured_categories
    return configured_categories, final_indicator_ids


def _render_comparison_configuration() -> list[str]:
    return _render_comparison_configuration_with_layout(compact=False)


def _apply_comparison_selection_from_widgets(
    option_keys: dict[str, str],
    available_options: list[str],
) -> None:
    st.session_state[COMPARISON_SELECTION_KEY] = [
        option
        for option in available_options
        if bool(st.session_state.get(option_keys[option], False))
    ]


def _render_comparison_configuration_with_layout(*, compact: bool) -> list[str]:
    available_options = _available_comparison_options()
    has_existing_selection = COMPARISON_SELECTION_KEY in st.session_state
    current_selection = [
        str(value)
        for value in st.session_state.get(COMPARISON_SELECTION_KEY, [])
        if str(value).strip() in set(available_options)
    ]
    if current_selection != st.session_state.get(COMPARISON_SELECTION_KEY, []):
        st.session_state[COMPARISON_SELECTION_KEY] = current_selection
    default_selected = (
        current_selection
        if has_existing_selection
        else [option for option in COMPARISON_OPTIONS if option in available_options]
    )

    if compact:
        option_keys = {
            option: f"configuration_comparison_scope_compact_{_theme_widget_slug(option)}"
            for option in available_options
        }
        for option, option_key in option_keys.items():
            st.session_state[option_key] = option in set(default_selected)
        option_cols = st.columns(max(len(available_options), 1), gap="small")
        for option_col, option in zip(option_cols, available_options, strict=False):
            with option_col:
                st.checkbox(
                    option,
                    key=option_keys[option],
                    on_change=_apply_comparison_selection_from_widgets,
                    args=(option_keys, available_options),
                )
        checked_ids = [
            option
            for option in available_options
            if bool(st.session_state.get(option_keys[option], False))
        ]
        st.session_state[COMPARISON_SELECTION_KEY] = checked_ids
        return checked_ids

    checked_ids = render_scrollable_multi_select_checkbox_list(
        options=[(option, option) for option in available_options],
        default_selected_ids=default_selected,
        widget_prefix="configuration_comparison_scope",
        height=116,
    )
    st.session_state[COMPARISON_SELECTION_KEY] = checked_ids
    return checked_ids


def _render_setup_review(
    reference_df: pd.DataFrame,
    configured_categories: list[str],
    configured_indicator_ids: list[str],
) -> None:
    current_ids = selected_ids()
    selected_comparisons = [
        str(value)
        for value in st.session_state.get(COMPARISON_SELECTION_KEY, [])
        if str(value).strip() in set(_available_comparison_options(current_ids))
    ]

    def _chip_markup(values: list[str], empty_label: str) -> str:
        items = values or [empty_label]
        return (
            "<div class='setup-chip-row'>"
            + "".join(f"<span class='setup-chip'>{item}</span>" for item in items)
            + "</div>"
        )

    left_col, right_col = st.columns([1.08, 0.92], gap="large")
    with left_col:
        st.markdown("<div class='setup-review-panel'>", unsafe_allow_html=True)
        st.markdown("<div class='setup-review-heading'>Area selected</div>", unsafe_allow_html=True)
        st.markdown(
            f"<p class='setup-review-text'>{selection_context_summary(reference_df, current_ids)}</p>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div class='setup-review-stat'>{len(current_ids):,}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<p class='setup-review-text'>Neighbourhoods are currently included in this view.</p>",
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    with right_col:
        st.markdown("<div class='setup-review-panel'>", unsafe_allow_html=True)
        st.markdown("<div class='setup-review-heading'>Included in explorer</div>", unsafe_allow_html=True)
        st.markdown(
            f"<p class='setup-review-text'><strong>{len(configured_indicator_ids):,}</strong> indicators across <strong>{len(configured_categories):,}</strong> themes are ready to explore.</p>",
            unsafe_allow_html=True,
        )
        st.markdown("<p class='setup-review-text' style='margin-top:0.7rem;'>Themes</p>", unsafe_allow_html=True)
        st.markdown(_chip_markup(configured_categories, "No themes selected"), unsafe_allow_html=True)
        st.markdown("<p class='setup-review-text' style='margin-top:0.85rem;'>Comparisons</p>", unsafe_allow_html=True)
        st.markdown(_chip_markup(selected_comparisons, "No comparisons selected"), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)


def _render_powerpoint_indicator_group_configuration(
    catalog_df: pd.DataFrame,
    category_labels: list[str],
    *,
    current_indicator_id: str,
) -> tuple[list[str], list[str]]:
    in_scope = _indicator_options_for_categories(catalog_df, category_labels)
    if in_scope.empty:
        st.info("Choose at least one theme to make indicators available in the PowerPoint report.")
        st.session_state["ppt_report_categories"] = []
        st.session_state["ppt_report_indicator_ids"] = []
        return [], []

    previous_categories = [
        label for label in st.session_state.get("ppt_report_categories", category_labels) if label in category_labels
    ]
    if not previous_categories:
        previous_categories = category_labels.copy()
    previous_category_set = set(previous_categories)

    valid_indicator_ids = set(in_scope["indicator_id"].astype(str).tolist())
    previous_indicator_ids = [
        str(value)
        for value in st.session_state.get("ppt_report_indicator_ids", [])
        if str(value) in valid_indicator_ids
    ]
    if not previous_indicator_ids:
        previous_indicator_ids = [
            str(value)
            for value in st.session_state.get(INDICATOR_SELECTION_KEY, [])
            if str(value) in valid_indicator_ids
        ] or ([str(current_indicator_id)] if str(current_indicator_id) in valid_indicator_ids else [])

    selected_categories: list[str] = []
    selected_indicator_ids: list[str] = []

    st.markdown("**Themes for the report**")
    st.caption("Select the themes and indicators you want to export.")

    for category_label in category_labels:
        category_df = in_scope[in_scope["top_level_category"] == category_label].copy()
        if category_df.empty:
            continue

        category_indicator_ids = category_df["indicator_id"].astype(str).tolist()
        category_indicator_set = set(category_indicator_ids)
        previously_selected_for_theme = [
            indicator_id for indicator_id in previous_indicator_ids if indicator_id in category_indicator_set
        ]
        widget_slug = f"ppt_{_theme_widget_slug(category_label)}"

        with st.container(border=True):
            header_col, count_col = st.columns([0.78, 0.22], gap="small")
            with header_col:
                include_theme = st.checkbox(
                    category_label,
                    value=category_label in previous_category_set,
                    key=f"include_theme_{widget_slug}",
                )
            with count_col:
                selected_count = (
                    len(category_indicator_ids)
                    if include_theme and category_label not in previous_category_set
                    else len(previously_selected_for_theme)
                    if include_theme
                    else 0
                )
                st.caption(f"{selected_count}/{len(category_indicator_ids)} indicators")

            if include_theme:
                selected_categories.append(category_label)

            with st.expander(f"{category_label} indicators", expanded=False):
                st.caption("Open this theme to choose the indicators you want in the report.")
                module_text = ", ".join(category_df["module_label"].dropna().astype(str).drop_duplicates().tolist())
                if module_text:
                    st.caption(f"Includes: {module_text}")
                if include_theme:
                    default_selected_ids = (
                        category_indicator_ids
                        if category_label not in previous_category_set
                        else previously_selected_for_theme or category_indicator_ids
                    )
                    checked_ids = render_scrollable_multi_select_checkbox_list(
                        options=[
                            (str(row.indicator_id), str(row.ui_title))
                            for row in category_df.itertuples(index=False)
                        ],
                        default_selected_ids=default_selected_ids,
                        widget_prefix=f"ppt_indicator_group_{widget_slug}",
                        height=min(260, 74 + 38 * len(category_indicator_ids)),
                    )
                    if not checked_ids:
                        checked_ids = category_indicator_ids
                    selected_indicator_ids.extend(checked_ids)

    ordered_selected_categories = [label for label in category_labels if label in set(selected_categories)]
    ordered_selected_indicator_ids = [
        indicator_id
        for indicator_id in in_scope["indicator_id"].astype(str).tolist()
        if indicator_id in set(selected_indicator_ids)
    ]

    st.session_state["ppt_report_categories"] = ordered_selected_categories
    st.session_state["ppt_report_indicator_ids"] = ordered_selected_indicator_ids
    st.caption(
        f"Themes: {len(ordered_selected_categories)} | Indicators: {len(ordered_selected_indicator_ids)}"
    )
    return ordered_selected_categories, ordered_selected_indicator_ids


def _render_powerpoint_slide_options() -> tuple[bool, bool, bool]:
    default_options = st.session_state.get("ppt_slide_options")
    if not isinstance(default_options, list):
        default_options = []
        if st.session_state.get("ppt_include_overview", True):
            default_options.append("overview")
        if st.session_state.get("ppt_include_detail_tables", True):
            default_options.append("detail_tables")
        if st.session_state.get("ppt_include_methodology", True):
            default_options.append("methodology")

    st.markdown("**Slides to include**")
    checked_ids = render_scrollable_multi_select_checkbox_list(
        options=PPT_SLIDE_OPTIONS,
        default_selected_ids=default_options,
        widget_prefix="ppt_slide_options",
        height=132,
    )
    st.session_state["ppt_slide_options"] = checked_ids
    include_overview = "overview" in checked_ids
    include_detail_tables = "detail_tables" in checked_ids
    include_methodology = "methodology" in checked_ids
    st.session_state["ppt_include_overview"] = include_overview
    st.session_state["ppt_include_detail_tables"] = include_detail_tables
    st.session_state["ppt_include_methodology"] = include_methodology
    return include_overview, include_detail_tables, include_methodology


def _ppt_visual_options(
    indicator_id: str,
    meta: dict[str, object],
    current_ids: list[str] | None = None,
) -> tuple[str, list[tuple[str, str]]]:
    default_view, compact_views, extra_views = _view_options(indicator_id, meta, current_ids=current_ids)

    if _gp_registered_population_requires_distribution_only(indicator_id, current_ids):
        # Hard-restricted: only ranked_distribution is valid for this selection
        ordered_views = _unique_views([default_view] + compact_views + extra_views)
    else:
        # PPT bypasses the profile-breakdown compact filter so slide authors can pick
        # comparison views (benchmark_lollipop, ranked_distribution) even for profile indicators.
        full_views = get_full_views(indicator_id) if current_ids else []
        if not full_views:
            full_view_text = _clean_text(meta.get("view_toggle_options_full"))
            if full_view_text:
                full_views = [item.strip() for item in full_view_text.split("|") if item.strip()]
            else:
                full_views = list(meta.get("available_view_list") or [])
        # default_view first, then full catalog set, then any explorer-only views as fallback
        ordered_views = _unique_views([default_view] + full_views + compact_views + extra_views)

    options = [(view, _view_label(view)) for view in ordered_views if view and view != "none"]
    if not options:
        options.append(("benchmark_lollipop", "Comparison chart"))

    option_values = [value for value, _ in options]
    default_option = default_view if default_view in option_values else option_values[0]
    return default_option, options


def _ppt_population_pyramid_comparator_options(
    indicator_id: str,
    *,
    current_ids: list[str],
    include_borough: bool,
    include_london: bool,
    meta: dict[str, object] | None = None,
) -> list[str]:
    period = _explorer_period_for_indicator(indicator_id)
    context = build_indicator_visual_context(
        indicator_id=indicator_id,
        period=period,
        current_ids=current_ids,
        include_borough=include_borough,
        include_london=include_london,
        meta=meta or indicator_metadata(indicator_id),
    )
    _, comparator_subjects = _population_pyramid_subject_options(context.get("composition_df", pd.DataFrame()))
    return comparator_subjects


def _render_powerpoint_visual_configuration(
    selected_indicator_ids: list[str],
    *,
    current_ids: list[str],
    include_borough: bool,
    include_london: bool,
) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    st.markdown("**Slide visuals**")
    detailed_mode = st.checkbox("Choose the visual for each indicator slide", key="ppt_use_detailed_visuals")
    if not detailed_mode or not selected_indicator_ids:
        return {}, {}

    st.caption("Select the visual you want on each slide.")
    overrides: dict[str, str] = {}
    config_overrides: dict[str, dict[str, str]] = {}
    with st.expander("Detailed visual choices", expanded=False):
        for indicator_id in selected_indicator_ids:
            meta = indicator_metadata(str(indicator_id))
            default_option, options = _ppt_visual_options(str(indicator_id), meta, current_ids=current_ids)
            option_values = [value for value, _ in options]
            option_labels = {value: label for value, label in options}
            choice = st.selectbox(
                str(meta.get("ui_title") or meta.get("title") or indicator_id),
                option_values,
                index=option_values.index(default_option),
                format_func=lambda value: option_labels.get(value, value),
                key=f"ppt_visual_choice_{indicator_id}",
            )
            overrides[str(indicator_id)] = str(choice)

            indicator_config: dict[str, str] = {}
            if choice == "choropleth_map":
                map_style_key = f"ppt_visual_map_style_{indicator_id}"
                map_style_label = st.radio(
                    "Map style",
                    options=["Hex map", "Neighbourhood map"],
                    index=0 if st.session_state.get(map_style_key, "Hex map") == "Hex map" else 1,
                    horizontal=True,
                    key=map_style_key,
                    label_visibility="collapsed",
                )
                indicator_config["map_style"] = "hex" if map_style_label == "Hex map" else "real"
            elif choice == "population_pyramid":
                comparator_subjects = _ppt_population_pyramid_comparator_options(
                    str(indicator_id),
                    current_ids=current_ids,
                    include_borough=include_borough,
                    include_london=include_london,
                    meta=meta,
                )
                if comparator_subjects:
                    comparator_key = f"ppt_visual_population_pyramid_comparator_{indicator_id}"
                    comparator_default = str(st.session_state.get(comparator_key) or comparator_subjects[0])
                    comparator_choice = st.selectbox(
                        "Population pyramid comparator",
                        comparator_subjects,
                        index=comparator_subjects.index(comparator_default) if comparator_default in comparator_subjects else 0,
                        key=comparator_key,
                    )
                    indicator_config["population_pyramid_comparator"] = str(comparator_choice)
            if indicator_config:
                config_overrides[str(indicator_id)] = indicator_config
    return overrides, config_overrides


def _render_headline_overview_cards(current_ids: list[str]) -> None:
    cards: list[dict[str, object]] = []
    for indicator_id in OVERVIEW_HEADLINE_IDS:
        try:
            meta = indicator_metadata(indicator_id)
        except KeyError:
            continue
        period = _explorer_period_for_indicator(indicator_id)
        bundle = comparison_bundle(indicator_id, period, current_ids)
        selection = bundle["selection"]
        if selection is None:
            continue
        cards.append(
            {
                "label": meta.get("ui_short_title") or meta["title"],
                "value": format_indicator_value(selection["value"], selection["unit"]),
                "caption": str(period),
            }
        )
    if cards:
        render_metric_cards(cards[:4])


def _comparison_metric_cards(context: dict[str, object]) -> list[dict[str, object]]:
    selection = context.get("selection")
    if selection is None:
        return []
    if _clean_text(context.get("indicator_id")) == "nomis_population_total":
        return []
    return build_summary_cards(context.get("comparator_context", {}))


def _preferred_bundle_indicator_and_view(
    indicator_id: str,
    subcategory_catalog: pd.DataFrame,
) -> tuple[str, str]:
    if subcategory_catalog.empty:
        return indicator_id, ""
    module_label = _clean_text(subcategory_catalog.iloc[0].get("module_label"))
    if module_label in SUPPRESSED_SUBCATEGORY_BUNDLE_LABELS:
        return indicator_id, ""

    for row in subcategory_catalog.to_dict(orient="records"):
        available_views = _row_available_views(row)
        if "population_pyramid" in available_views:
            return str(row.get("indicator_id") or indicator_id), "population_pyramid"

    bundle_view = get_bundle_view(indicator_id)
    if not bundle_view:
        bundle_values = [
            _clean_text(value)
            for value in subcategory_catalog["module_bundle_view"].dropna().tolist()
            if _clean_text(value)
        ]
        bundle_view = bundle_values[0] if bundle_values else ""
    return indicator_id, bundle_view


def _view_label(view_name: str) -> str:
    return humanise_enum(view_name, kind="visual") or "Chart view"


def _view_display_label(view_name: str, meta: dict[str, object]) -> str:
    if view_name == "choropleth_map" and _paired_map_companion_view(meta, view_name):
        return "Map + comparison"
    return _view_label(view_name)


def _clear_widget_state_if_invalid(widget_key: str, valid_values: list[str]) -> None:
    if widget_key not in st.session_state:
        return
    current_value = st.session_state.get(widget_key)
    if current_value is None:
        return
    if str(current_value) not in {str(value) for value in valid_values}:
        del st.session_state[widget_key]


def _render_more_toggle_button(
    *,
    state_key: str,
    button_key: str,
    closed_label: str,
    open_label: str,
    default_open: bool,
) -> bool:
    if state_key not in st.session_state:
        st.session_state[state_key] = bool(default_open)

    expanded = bool(st.session_state.get(state_key, False))
    if st.button(
        open_label if expanded else closed_label,
        key=button_key,
        type="secondary",
    ):
        expanded = not expanded
        st.session_state[state_key] = expanded
    return bool(st.session_state.get(state_key, expanded))


def _gp_registered_population_requires_distribution_only(
    indicator_id: str,
    current_ids: list[str] | None = None,
) -> bool:
    if indicator_id != "gp_registered_population_total":
        return False
    selected_set = {str(value).strip() for value in (current_ids or []) if str(value).strip()}
    if len(selected_set) <= 1:
        return False
    selection_descriptor = resolve_footprint_label(sorted(selected_set))
    return not (
        selection_descriptor.kind == "place"
        and selection_descriptor.item_count == 1
        and selection_descriptor.exact_boundary
    )


def _view_options(
    indicator_id: str,
    meta: dict[str, object],
    current_ids: list[str] | None = None,
    context: dict[str, object] | None = None,
) -> tuple[str, list[str], list[str]]:
    default_view = (
        _clean_text(meta.get("default_view"))
        or get_default_view(indicator_id)
        or _clean_text(meta.get("primary_visualisation"))
        or "benchmark_lollipop"
    )
    compact_views = _unique_views(
        [item.strip() for item in _clean_text(meta.get("view_toggle_options_compact")).split("|") if item.strip()]
        or get_compact_views(indicator_id)
    )
    full_views = _unique_views(
        [item.strip() for item in _clean_text(meta.get("view_toggle_options_full")).split("|") if item.strip()]
        or get_full_views(indicator_id)
    )
    map_view = _clean_text(meta.get("map_view_final")) or _clean_text(meta.get("map_view"))
    if map_view and map_view != "none":
        full_views = _unique_views(full_views + [map_view])
    if not compact_views:
        compact_views = _unique_views([default_view] + list(meta.get("available_view_list") or []))
    if is_profile_breakdown_indicator(meta):
        inferred_views = inferred_profile_breakdown_views(meta)
        compact_views = filter_profile_breakdown_views(meta, compact_views)
        full_views = filter_profile_breakdown_views(meta, full_views)
        if inferred_views:
            compact_views = _unique_views(inferred_views + compact_views) if compact_views else inferred_views.copy()
            full_views = _unique_views(inferred_views + full_views) if full_views else inferred_views.copy()
        default_candidates = filter_profile_breakdown_views(
            meta,
            [default_view] + compact_views + full_views + list(meta.get("available_view_list") or []),
        )
        if not default_candidates and inferred_views:
            default_candidates = inferred_views.copy()
        if "population_pyramid" in default_candidates:
            default_view = "population_pyramid"
        elif "grouped_bar" in default_candidates:
            default_view = "grouped_bar"
        elif "stacked_100_bar" in default_candidates:
            default_view = "stacked_100_bar"
        elif default_candidates:
            default_view = default_candidates[0]
    if default_view and default_view not in compact_views:
        compact_views.insert(0, default_view)
    if not full_views:
        full_views = compact_views.copy()
    if default_view and default_view not in full_views:
        full_views.insert(0, default_view)
    if _gp_registered_population_requires_distribution_only(indicator_id, current_ids):
        return "ranked_distribution", ["ranked_distribution"], []
    runtime_context = context
    if runtime_context is None and current_ids:
        runtime_context = build_indicator_visual_context(
            indicator_id=indicator_id,
            period=_explorer_period_for_indicator(indicator_id),
            current_ids=current_ids,
            include_borough=True,
            include_london=True,
            meta=meta,
            subcategory_catalog=pd.DataFrame(),
        )
    default_view = choose_default_view(
        default_view=default_view,
        compact_views=compact_views,
        full_views=full_views,
        context=runtime_context,
    )
    if default_view in full_views and default_view not in compact_views:
        compact_views = _unique_views([default_view] + compact_views)
    extra_views = [view for view in full_views if view not in compact_views and view != default_view]
    if len(extra_views) < 2:
        compact_views = _unique_views(compact_views + extra_views)
        extra_views = []
    return default_view, compact_views, extra_views


def _mark_spatial_perspective_user_set() -> None:
    st.session_state[SPATIAL_PERSPECTIVE_USER_SET_KEY] = True


def _sync_indicator_view_selection(selection_key: str, widget_key: str) -> None:
    selected_view = _clean_text(st.session_state.get(widget_key))
    if selected_view:
        st.session_state[selection_key] = selected_view


def _render_indicator_view_controls(
    indicator_id: str,
    meta: dict[str, object],
    current_ids: list[str],
    *,
    context: dict[str, object] | None = None,
) -> str:
    default_view, compact_views, extra_views = _view_options(
        indicator_id,
        meta,
        current_ids=current_ids,
        context=context,
    )
    if not compact_views:
        return default_view

    selection_key = f"indicator_selected_view_{indicator_id}"
    current_view = _clean_text(st.session_state.get(selection_key)) or default_view
    allowed_views = set(compact_views + extra_views)
    if current_view not in allowed_views:
        current_view = default_view

    primary_views = compact_views[:EXPLORER_PRIMARY_VIEW_LIMIT] if len(compact_views) > EXPLORER_PRIMARY_VIEW_LIMIT else compact_views[:]
    secondary_views = [view for view in compact_views if view not in primary_views]
    secondary_views.extend([view for view in extra_views if view not in secondary_views and view not in primary_views])
    primary_default = current_view if current_view in primary_views else primary_views[0]
    primary_widget_key = f"{selection_key}_primary"
    more_widget_key = f"{selection_key}_more"
    more_toggle_state_key = f"{selection_key}_more_open"
    more_toggle_button_key = f"{selection_key}_more_toggle"
    _clear_widget_state_if_invalid(primary_widget_key, primary_views)
    _clear_widget_state_if_invalid(more_widget_key, secondary_views)

    if len(primary_views) == 1 and not secondary_views:
        st.session_state[selection_key] = primary_views[0]
        return primary_views[0]

    st.markdown("<div class='explorer-control-label'>View</div>", unsafe_allow_html=True)
    primary_choice = primary_default
    if secondary_views:
        view_row_cols = st.columns([0.82, 0.18], gap="small")
        with view_row_cols[0]:
            primary_choice = st.pills(
                "View",
                options=primary_views,
                default=primary_default,
                format_func=lambda value: _view_display_label(str(value), meta),
                key=primary_widget_key,
                label_visibility="collapsed",
                width="content",
            )
            primary_choice = str(primary_choice or primary_default)
        with view_row_cols[1]:
            more_views_open = _render_more_toggle_button(
                state_key=more_toggle_state_key,
                button_key=more_toggle_button_key,
                closed_label=f"More views ({len(secondary_views)})",
                open_label=f"Hide more views ({len(secondary_views)})",
                default_open=current_view in secondary_views,
            )
    elif len(primary_views) == 1:
        primary_choice = primary_views[0]
        st.markdown(
            f"<div class='explorer-selection-note'>Primary view: {escape(_view_display_label(primary_choice, meta))}</div>",
            unsafe_allow_html=True,
        )
        more_views_open = False
    else:
        primary_choice = st.pills(
            "View",
            options=primary_views,
            default=primary_default,
            format_func=lambda value: _view_display_label(str(value), meta),
            key=primary_widget_key,
            label_visibility="collapsed",
            width="content",
        )
        primary_choice = str(primary_choice or primary_default)
        more_views_open = False

    if selection_key not in st.session_state:
        st.session_state[selection_key] = primary_choice

    selected_view = primary_choice
    if secondary_views:
        if more_views_open:
            more_choice = st.selectbox(
                "Browse more views",
                options=secondary_views,
                index=secondary_views.index(current_view) if current_view in secondary_views else None,
                format_func=lambda value: _view_display_label(str(value), meta),
                key=more_widget_key,
                label_visibility="collapsed",
                placeholder="Choose another view",
            )
            if more_choice:
                selected_view = str(more_choice)

    if not secondary_views:
        selected_view = primary_choice
    elif current_view in secondary_views and _clean_text(st.session_state.get(more_widget_key)) in secondary_views:
        selected_view = _clean_text(st.session_state.get(more_widget_key))
    elif current_view in primary_views and primary_choice in primary_views:
        selected_view = primary_choice
    elif _clean_text(st.session_state.get(selection_key)) in allowed_views:
        selected_view = _clean_text(st.session_state.get(selection_key))

    if selected_view not in allowed_views:
        selected_view = primary_choice
        st.session_state[selection_key] = selected_view
    else:
        st.session_state[selection_key] = selected_view
    return selected_view


def _count_context_note(context: dict[str, object]) -> str:
    selection = context.get("selection")
    if selection is None or str(selection.get("unit") or "") != "count":
        return ""
    borough_df = context.get("borough_benchmarks", pd.DataFrame())
    london_df = context.get("london_benchmark", pd.DataFrame())
    parts: list[str] = ["Use this count to understand scale rather than performance."]
    if isinstance(borough_df, pd.DataFrame) and len(borough_df) == 1:
        parts.append(
            f"Borough total: {format_indicator_value(borough_df.iloc[0]['value'], 'count')} for {borough_df.iloc[0]['benchmark_name']}."
        )
    elif isinstance(borough_df, pd.DataFrame) and len(borough_df) > 1:
        parts.append(
            "Borough totals range from "
            f"{format_indicator_value(borough_df['value'].min(), 'count')} to "
            f"{format_indicator_value(borough_df['value'].max(), 'count')} across the boroughs in scope."
        )
    if isinstance(london_df, pd.DataFrame) and not london_df.empty:
        parts.append(f"London total: {format_indicator_value(london_df.iloc[0]['value'], 'count')}.")
    indicator_id = _clean_text(context.get("indicator_id"))
    rate_indicator_id = indicator_id.replace("_count", "_rate_per_1000") if indicator_id.endswith("_count") else ""
    if rate_indicator_id:
        catalog = load_public_catalog_df()
        match = catalog[catalog["indicator_id"].astype(str) == rate_indicator_id]
        if not match.empty:
            parts.append(f"For clearer comparison, switch to {match.iloc[0]['ui_title']}.")
    return " ".join(parts)


def _paired_map_companion_view(meta: dict[str, object], selected_view: str) -> str | None:
    if selected_view != "choropleth_map":
        return None
    candidates = [
        _clean_text(meta.get("comparison_view")),
        _clean_text(meta.get("distribution_view")),
        _clean_text(meta.get("secondary_visualisation")),
    ]
    for candidate in candidates:
        if candidate and candidate not in {"none", "choropleth_map"}:
            return candidate
    return None


def _render_neighbourhood_values_table(
    detail_df: pd.DataFrame,
    *,
    indicator_id: str,
    period: str,
    unit: str | None,
    title: str,
) -> None:
    if detail_df.empty:
        return
    with st.expander("Neighbourhood values", expanded=False):
        display_detail_df = format_dataframe_for_display(
            detail_df[["neighbourhood_name", "borough_name", "value"]].sort_values(
                ["borough_name", "neighbourhood_name"]
            ),
            unit=unit,
            formatted_value_columns=["value"],
        )
        st.dataframe(display_detail_df, hide_index=True, use_container_width=True)
        render_download_button(
            detail_df,
            f"Download {title}",
            f"{indicator_id}_{period or 'current'}.csv",
        )


def _is_breakdown_metric(meta: dict[str, object], title: str) -> bool:
    if len(_sequence_from_meta(meta.get("breakdown_groups_json"))) > 1:
        return True
    if len(_sequence_from_meta(meta.get("numerator_fields"))) > 1:
        return True
    clean_title = _plain_english_indicator_label(title).lower()
    breakdown_tokens = (
        "age profile",
        "composition",
        "country of birth",
        "ethnicity",
        "identity",
        "passports held",
        "partnership status",
        "religion",
        "residential mobility",
        "second address",
        "sex split",
        "year of arrival",
    )
    return any(token in clean_title for token in breakdown_tokens)


def _indicator_definition_summary(
    indicator_id: str,
    meta: dict[str, object],
    title: str,
    current_ids: list[str],
    *,
    active_view: str | None = None,
) -> str:
    indicator_key = str(indicator_id)
    unit = _clean_text(meta.get("unit") or meta.get("unit_type")).lower()
    source_name = _clean_text(meta.get("source_name"))
    metric_kind = _clean_text(meta.get("qof_metric_kind")).lower()
    subject = _indicator_subject_phrase(meta, indicator_key, title)
    selection_descriptor = resolve_footprint_label(current_ids)
    selection_object = selection_descriptor.object_phrase
    selection_subject = selection_object
    selection_verb = "are" if selection_descriptor.is_plural else "is"
    profile_slice_label = active_profile_slice_label(meta, _clean_text(active_view))
    structure_views = {"grouped_bar", "stacked_100_bar", "population_pyramid", "table_support_only", "domain_tile_matrix"}
    resolved_view = (
        _clean_text(active_view)
        or _clean_text(meta.get("default_view"))
        or _clean_text(meta.get("primary_visualisation"))
    )

    if profile_slice_label:
        return (
            f"What this shows: the percentage of {denominator_population_phrase(meta)} in {selection_object} "
            f"who are in the {profile_slice_label} group."
        )

    if source_name == "NHS England Quality and Outcomes Framework":
        if metric_kind == "prevalence":
            condition = re.sub(r"\s+prevalence$", "", subject, flags=re.IGNORECASE).strip()
            return f"What this shows: the percentage of GP-registered patients on the QOF register for {condition} in {selection_object}."
        if metric_kind == "achievement":
            return f"What this shows: the percentage of eligible GP-registered patients meeting this QOF measure in {selection_object}."
        if metric_kind == "newly_diagnosed":
            return f"What this shows: the percentage of GP-registered patients with a newly recorded diagnosis for this QOF measure in {selection_object}."
        if metric_kind == "register":
            return f"What this shows: the percentage of GP-registered patients on the relevant QOF register in {selection_object}."

    if indicator_key == "imd_decile_median_lsoa":
        return f"What this shows: the typical deprivation decile across the smaller areas inside {selection_object}."

    if is_direct_value_breakdown_indicator(meta):
        breakdown_groups = breakdown_groups_from_meta(meta)
        if len(breakdown_groups) > 1:
            return (
                f"What this shows: the {subject} scores for {selection_object}, "
                "including the overall domain score and its component subdomains."
            )

    if (
        _is_breakdown_metric(meta, title)
        or is_profile_breakdown_indicator(meta)
        or bool(inferred_profile_breakdown_views(meta))
    ) and resolved_view in structure_views:
        breakdown_subject = _indicator_subject_phrase(meta, indicator_key, title, strip_breakdown_words=True)
        if breakdown_subject:
            return f"What this shows: how {selection_subject} {selection_verb} split by {breakdown_subject}."

    if unit == "count":
        if subject.lower().startswith("total "):
            return f"What this shows: the {subject} in {selection_object}."
        if subject:
            return f"What this shows: the total number of {subject} in {selection_object}."
        return f"What this shows: the total count for this measure in {selection_object}."

    if unit == "share":
        if subject:
            return f"What this shows: the percentage of {subject} in {selection_object}."
        return f"What this shows: the percentage for this measure in {selection_object}."

    if unit == "rate_per_1000":
        if subject:
            return f"What this shows: the rate per 1,000 residents for {subject} in {selection_object}."
        return f"What this shows: the rate per 1,000 residents for this measure in {selection_object}."

    if unit == "density_per_sq_km":
        if subject:
            return f"What this shows: the number of {subject} per square kilometre in {selection_object}."
        return f"What this shows: the density per square kilometre for this measure in {selection_object}."

    if unit == "currency_gbp":
        if subject:
            return f"What this shows: the value in pounds sterling for {subject} in {selection_object}."
        return f"What this shows: the value in pounds sterling for this measure in {selection_object}."

    if unit == "score":
        if subject:
            return f"What this shows: the score for {subject} in {selection_object}."
        return f"What this shows: the score for this measure in {selection_object}."

    if unit == "decile":
        return f"What this shows: the decile value for this measure across the smaller areas inside {selection_object}."

    clean_title = _plain_english_indicator_label(title)
    if not clean_title:
        return ""
    return f"What this shows: {clean_title} for {selection_object}."


def _is_qof_indicator(meta: dict[str, object]) -> bool:
    indicator_id = _clean_text(meta.get("indicator_id")) or ""
    source_key = _clean_text(meta.get("source_key")) or ""
    return indicator_id.startswith("qof_") or source_key.startswith("qof")


def _source_credit_html(meta: dict[str, object], period: str | None) -> str:
    source_name = _friendly_source_name(meta)
    source_url = _clean_text(meta.get("source_url")) or _clean_text(meta.get("docs_url"))
    metric_period = _metric_period_label(meta, period)
    last_refresh = format_period_label(_clean_text(meta.get("last_refresh_date")))
    source_label = (
        f"<a href=\"{escape(source_url)}\" target=\"_blank\" rel=\"noopener noreferrer\" "
        f"style=\"color:#7b8794; text-decoration:underline;\">{escape(source_name)}</a>"
        if source_url
        else escape(source_name)
    )
    suffix_parts = []
    if metric_period:
        suffix_parts.append(f"Data period {escape(metric_period)}")
    if last_refresh and last_refresh != "Not available":
        suffix_parts.append(f"Updated {escape(last_refresh)}")
    suffix = f" | {' | '.join(suffix_parts)}" if suffix_parts else ""
    qof_warning = ""
    if _is_qof_indicator(meta):
        qof_warning = (
            "<br><span style=\"color:#b45309;\">&#9888; Neighbourhood figures are modelled estimates "
            "disaggregated from GP practice data &mdash; "
            "<a href=\"/Methodology_and_Data_Coverage\" target=\"_self\" "
            "style=\"color:#b45309; text-decoration:underline;\">see methodology</a>"
            " for details</span>"
        )
    return (
        "<div style=\"margin-top:0.6rem; text-align:right; color:#7b8794; "
        "font-size:0.82rem; line-height:1.35;\">"
        f"Source: {source_label}{suffix}{qof_warning}"
        "</div>"
    )


def _render_source_credit(meta: dict[str, object], period: str | None) -> None:
    st.markdown(_source_credit_html(meta, period), unsafe_allow_html=True)


def _module_indicator_catalog(
    category_label: str,
    subcategory_label: str,
    *,
    include_hidden_exposure: bool = False,
) -> pd.DataFrame:
    catalog = load_catalog_df().copy()
    if catalog.empty:
        return catalog
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
    if not include_hidden_exposure and "ui_exposure_level" in catalog.columns:
        catalog = catalog[
            catalog["ui_exposure_level"].astype(str).replace("nan", "standard").str.lower() != "hidden"
        ].copy()
    catalog = catalog[
        (catalog["top_level_category"].astype(str) == str(category_label))
        & (catalog["module_label"].astype(str) == str(subcategory_label))
    ].copy()
    if catalog.empty:
        return catalog
    return _ordered_indicator_catalog_for_display(catalog)


def _bundle_capable_subcategory_catalog(category_label: str, subcategory_label: str) -> pd.DataFrame:
    return _module_indicator_catalog(category_label, subcategory_label)


def _composite_indicator_catalog(indicator_id: str) -> pd.DataFrame:
    spec = COMPOSITE_INDICATOR_GROUPS.get(str(indicator_id))
    if not spec:
        return pd.DataFrame()
    catalog = load_catalog_df().copy()
    if catalog.empty:
        return catalog
    indicator_ids = {str(value) for value in spec.get("indicator_ids", []) if str(value).strip()}
    if not indicator_ids:
        return pd.DataFrame()
    catalog = catalog[catalog["indicator_id"].astype(str).isin(indicator_ids)].copy()
    if catalog.empty:
        return catalog
    return _ordered_indicator_catalog_for_display(catalog)


def _ordered_indicator_catalog_for_display(catalog: pd.DataFrame) -> pd.DataFrame:
    if catalog.empty:
        return catalog
    ordered = catalog.copy()
    if ordered["indicator_id"].astype(str).str.startswith("qof_").all():
        metric_order = {
            "prevalence": 0,
            "register": 1,
            "achievement": 2,
            "points": 3,
            "points_raw": 4,
            "pcas": 5,
            "newly_diagnosed": 6,
        }
        ordered["qof_metric_sort"] = (
            ordered.get("qof_metric_kind", pd.Series("", index=ordered.index))
            .astype(str)
            .str.lower()
            .map(metric_order)
            .fillna(99)
        )
        ordered["qof_code_sort"] = ordered.get("qof_indicator_code", pd.Series("", index=ordered.index)).astype(str).fillna("")
        ordered = ordered.sort_values(
            ["qof_metric_sort", "qof_code_sort", "ui_title", "indicator_id"],
            kind="stable",
        )
        return ordered.drop(columns=["qof_metric_sort", "qof_code_sort"], errors="ignore").reset_index(drop=True)
    return ordered.sort_values(
        ["module_sort_order", "indicator_sort_order", "ui_exposure_level", "ui_title", "indicator_id"],
        kind="stable",
    ).reset_index(drop=True)


def _is_qof_module_catalog(catalog: pd.DataFrame) -> bool:
    return not catalog.empty and catalog["indicator_id"].astype(str).str.startswith("qof_").all()


def _qof_public_metric_catalog(catalog: pd.DataFrame) -> pd.DataFrame:
    if catalog.empty or "qof_metric_kind" not in catalog.columns:
        return catalog.copy()
    non_public_metric_kinds = {"points", "points_raw", "pcas"}
    return catalog[
        ~catalog["qof_metric_kind"].astype(str).fillna("").str.lower().isin(non_public_metric_kinds)
    ].copy()


def _qof_metric_catalog(catalog: pd.DataFrame, metric_kinds: set[str]) -> pd.DataFrame:
    if catalog.empty or "qof_metric_kind" not in catalog.columns:
        return pd.DataFrame()
    allowed_metric_kinds = {str(kind).lower() for kind in metric_kinds}
    subset = catalog[
        catalog["qof_metric_kind"].astype(str).fillna("").str.lower().isin(allowed_metric_kinds)
    ].copy()
    if subset.empty:
        return subset
    return _ordered_indicator_catalog_for_display(subset)


def _qof_advanced_indicator_label(row: pd.Series | dict[str, object]) -> str:
    indicator_id = _clean_text(row.get("indicator_id"))
    if indicator_id:
        return _indicator_display_title(dict(row), indicator_id)
    short_title = _clean_text(row.get("ui_short_title")) or _clean_text(row.get("short_title"))
    title = _clean_text(row.get("ui_title")) or _clean_text(row.get("title")) or _clean_text(row.get("indicator_id"))
    return short_title or title


def _qof_inline_advanced_module(advanced_catalog: pd.DataFrame) -> bool:
    if advanced_catalog.empty:
        return False
    module_label = _clean_text(advanced_catalog.iloc[0].get("module_label")).lower()
    return any(token in module_label for token in ("screen", "vaccination", "immunisation"))


def _render_qof_prevalence_group(
    *,
    prevalence_catalog: pd.DataFrame,
    full_module_catalog: pd.DataFrame,
    current_ids: list[str],
    include_borough: bool,
    include_london: bool,
) -> None:
    if prevalence_catalog.empty:
        return

    for index, row in enumerate(prevalence_catalog.to_dict(orient="records")):
        if index > 0:
            st.divider()
        _render_indicator_panel_body(
            indicator_id=str(row["indicator_id"]),
            current_ids=current_ids,
            include_borough=include_borough,
            include_london=include_london,
            subcategory_catalog=full_module_catalog,
        )


def _render_qof_advanced_group(
    *,
    advanced_catalog: pd.DataFrame,
    current_ids: list[str],
    include_borough: bool,
    include_london: bool,
) -> None:
    if advanced_catalog.empty:
        return

    advanced_catalog = _ordered_indicator_catalog_for_display(advanced_catalog)
    module_key = _clean_text(advanced_catalog.iloc[0].get("module_key")) or _clean_text(
        advanced_catalog.iloc[0].get("module_label")
    )
    indicator_options = advanced_catalog["indicator_id"].astype(str).tolist()
    label_lookup = {
        str(row["indicator_id"]): _qof_advanced_indicator_label(row)
        for row in advanced_catalog.to_dict(orient="records")
    }
    first_indicator_id = indicator_options[0]
    inline_module = _qof_inline_advanced_module(advanced_catalog)
    if inline_module:
        for index, indicator_id in enumerate(indicator_options):
            if index > 0:
                st.divider()
            _render_indicator_panel_body(
                indicator_id=str(indicator_id),
                current_ids=current_ids,
                include_borough=include_borough,
                include_london=include_london,
                subcategory_catalog=advanced_catalog,
            )
        return

    if len(indicator_options) > 1:
        overview_context = build_indicator_visual_context(
            indicator_id=first_indicator_id,
            period=_explorer_period_for_indicator(first_indicator_id),
            current_ids=current_ids,
            include_borough=include_borough,
            include_london=include_london,
            meta=indicator_metadata(first_indicator_id),
            subcategory_catalog=advanced_catalog,
        )
        render_indicator_view("domain_tile_matrix", overview_context)

    if len(indicator_options) > 1:
        selected_indicator_id = st.selectbox(
            "Advanced indicator",
            options=indicator_options,
            index=0,
            format_func=lambda value: label_lookup.get(str(value), str(value)),
            key=f"qof_advanced_indicator_{module_key}",
        )
    else:
        selected_indicator_id = first_indicator_id

    _render_indicator_panel_body(
        indicator_id=str(selected_indicator_id),
        current_ids=current_ids,
        include_borough=include_borough,
        include_london=include_london,
        subcategory_catalog=advanced_catalog,
    )


def _render_qof_subcategory_explorer_group(
    *,
    category_label: str,
    subcategory_label: str,
    subcategory_catalog: pd.DataFrame,
    current_ids: list[str],
    include_borough: bool,
    include_london: bool,
    use_nested_expander: bool,
) -> None:
    ordered_catalog = _ordered_indicator_catalog_for_display(_qof_public_metric_catalog(subcategory_catalog))
    if ordered_catalog.empty:
        return
    group_count = int(ordered_catalog["indicator_id"].nunique())
    bundle_catalog = ordered_catalog.copy()
    prevalence_catalog = _qof_metric_catalog(ordered_catalog, {"prevalence"})
    advanced_catalog = _qof_metric_catalog(ordered_catalog, {"achievement", "newly_diagnosed", "register"})
    has_tabbed_views = not prevalence_catalog.empty and should_render_advanced_section(prevalence_catalog, advanced_catalog)

    def _render_group_body() -> None:
        if prevalence_catalog.empty and advanced_catalog.empty:
            render_empty_state("No public QOF indicators are available in this topic yet.")
            return

        if not prevalence_catalog.empty and advanced_catalog.empty:
            _render_qof_prevalence_group(
                prevalence_catalog=prevalence_catalog,
                full_module_catalog=bundle_catalog,
                current_ids=current_ids,
                include_borough=include_borough,
                include_london=include_london,
            )
            return

        if prevalence_catalog.empty and advanced_catalog.empty:
            return

        if prevalence_catalog.empty:
            _render_qof_advanced_group(
                advanced_catalog=advanced_catalog,
                current_ids=current_ids,
                include_borough=include_borough,
                include_london=include_london,
            )
            return

        tab_labels: list[str] = []
        tab_renderers: list[tuple[str, pd.DataFrame]] = []
        if not prevalence_catalog.empty:
            tab_labels.append("Prevalence")
            tab_renderers.append(("Prevalence", prevalence_catalog))
        if has_tabbed_views:
            tab_labels.append("Advanced indicators")
            tab_renderers.append(("Advanced indicators", advanced_catalog))

        if not tab_renderers:
            _render_qof_prevalence_group(
                prevalence_catalog=prevalence_catalog,
                full_module_catalog=bundle_catalog,
                current_ids=current_ids,
                include_borough=include_borough,
                include_london=include_london,
            )
            return

        tabs = st.tabs(tab_labels)
        for tab, (tab_label, tab_catalog) in zip(tabs, tab_renderers):
            with tab:
                if tab_label == "Prevalence":
                    _render_qof_prevalence_group(
                        prevalence_catalog=tab_catalog,
                        full_module_catalog=bundle_catalog,
                        current_ids=current_ids,
                        include_borough=include_borough,
                        include_london=include_london,
                    )
                else:
                    _render_qof_advanced_group(
                        advanced_catalog=tab_catalog,
                        current_ids=current_ids,
                        include_borough=include_borough,
                        include_london=include_london,
                    )

    if use_nested_expander:
        with st.expander(f"{subcategory_label} ({group_count})", expanded=False):
            _render_group_body()
    else:
        _render_group_body()


def _render_subcategory_bundle(
    *,
    indicator_id: str,
    subcategory_catalog: pd.DataFrame,
    current_ids: list[str],
    include_borough: bool,
    include_london: bool,
) -> None:
    if subcategory_catalog.empty or subcategory_catalog["indicator_id"].nunique() <= 1:
        return

    bundle_indicator_id, bundle_view = _preferred_bundle_indicator_and_view(indicator_id, subcategory_catalog)
    if not should_render_module_overview(subcategory_catalog, bundle_view):
        return

    period = _explorer_period_for_indicator(bundle_indicator_id)
    with st.expander(f"{subcategory_catalog.iloc[0]['module_label']} overview", expanded=False):
        st.caption("This grouped view helps you scan the indicators in this topic before drilling into one chart.")
        context = build_indicator_visual_context(
            indicator_id=bundle_indicator_id,
            period=period,
            current_ids=current_ids,
            include_borough=include_borough,
            include_london=include_london,
            meta=indicator_metadata(bundle_indicator_id),
            subcategory_catalog=subcategory_catalog,
        )
        render_indicator_view(bundle_view, context)


def _render_indicator_single_panel_body(
    indicator_id: str,
    current_ids: list[str],
    include_borough: bool,
    include_london: bool,
    *,
    subcategory_catalog: pd.DataFrame,
    suppress_heading: bool = False,
) -> None:
    meta = indicator_metadata(indicator_id)
    period = _explorer_period_for_indicator(indicator_id)

    context = build_indicator_visual_context(
        indicator_id=indicator_id,
        period=period,
        current_ids=current_ids,
        include_borough=include_borough,
        include_london=include_london,
        meta=meta,
        subcategory_catalog=subcategory_catalog,
    )
    selected_view = _render_indicator_view_controls(indicator_id, meta, current_ids, context=context)
    title = _indicator_active_title(meta, indicator_id, selected_view)
    with st.container(border=True):
        if not suppress_heading:
            st.markdown(f"### {title}")
            panel_subtitle = _indicator_panel_subtitle(meta, period)
            if panel_subtitle:
                st.caption(panel_subtitle)
            active_slice_caption = _indicator_active_slice_caption(meta, selected_view)
            if active_slice_caption:
                st.caption(active_slice_caption)
            definition_summary = _indicator_definition_summary(
                indicator_id,
                meta,
                title,
                current_ids,
                active_view=selected_view,
            )
            if definition_summary:
                st.caption(definition_summary)

        selection = context["selection"]
        bundle = context["bundle"]
        selection_descriptor = resolve_footprint_label(current_ids)
        selection_label = selection_descriptor.label
        composition_df = context.get("composition_df", pd.DataFrame())
        is_structure_view = selected_view in {"stacked_100_bar", "grouped_bar", "population_pyramid"} and isinstance(
            composition_df, pd.DataFrame
        ) and not composition_df.empty
        is_group_bundle_view = selected_view in {"crime_mix_chart", "domain_tile_matrix"}

        card_rows = _comparison_metric_cards(context)
        if card_rows and selected_view not in {"kpi_card", "text_badges_or_indexed_note"} and not is_structure_view and not is_group_bundle_view:
            render_metric_cards(card_rows[:3])

        companion_view = _paired_map_companion_view(meta, selected_view)
        if companion_view:
            map_col, companion_col = st.columns([1.05, 0.95], gap="large")
            with map_col:
                render_indicator_view(selected_view, context)
            with companion_col:
                render_indicator_view(companion_view, context)
        else:
            render_indicator_view(selected_view, context)

        if selection is not None and not is_structure_view and not is_group_bundle_view:
            st.markdown(
                f"<div class='insight-note'>{indicator_summary(selection_label, selection, bundle['london_benchmark'], bundle['borough_benchmarks'], meta.get('unit') or meta.get('unit_type'), meta.get('neighbourhood_use_mode'), selection_is_plural=selection_descriptor.is_plural)}</div>",
                unsafe_allow_html=True,
            )

        count_note = _count_context_note(context) if not is_structure_view and not is_group_bundle_view else ""
        if count_note:
            st.caption(count_note)
        if not is_structure_view and not is_group_bundle_view:
            _render_neighbourhood_values_table(
                context["detail_df"],
                indicator_id=indicator_id,
                period=period,
                unit=selection["unit"] if selection is not None else str(meta.get("unit") or meta.get("unit_type") or ""),
                title=title,
            )
        _render_source_credit(meta, period)


def _render_composite_indicator_panel(
    indicator_id: str,
    current_ids: list[str],
    include_borough: bool,
    include_london: bool,
) -> None:
    composite_catalog = _composite_indicator_catalog(indicator_id)
    if composite_catalog.empty:
        _render_indicator_single_panel_body(
            indicator_id=indicator_id,
            current_ids=current_ids,
            include_borough=include_borough,
            include_london=include_london,
            subcategory_catalog=pd.DataFrame(),
        )
        return

    meta = indicator_metadata(indicator_id)
    period = _explorer_period_for_indicator(indicator_id)
    title = _indicator_display_title(meta, indicator_id)
    st.markdown(f"### {title}")
    panel_subtitle = _indicator_panel_subtitle(meta, period)
    if panel_subtitle:
        st.caption(panel_subtitle)
    composite_description = _clean_text(COMPOSITE_INDICATOR_GROUPS.get(indicator_id, {}).get("description"))
    if composite_description:
        st.caption(composite_description)

    overview_context = build_indicator_visual_context(
        indicator_id=indicator_id,
        period=period,
        current_ids=current_ids,
        include_borough=include_borough,
        include_london=include_london,
        meta=meta,
        subcategory_catalog=composite_catalog,
    )
    render_indicator_view("domain_tile_matrix", overview_context)

    indicator_options = composite_catalog["indicator_id"].astype(str).tolist()
    if len(indicator_options) > 1:
        selected_indicator_id = st.radio(
            "Measure",
            options=indicator_options,
            index=indicator_options.index(str(indicator_id)) if str(indicator_id) in indicator_options else 0,
            format_func=lambda value: _indicator_display_title(indicator_metadata(str(value)), str(value)),
            key=f"composite_indicator_measure_{indicator_id}",
            horizontal=True,
        )
    else:
        selected_indicator_id = indicator_options[0]

    _render_indicator_single_panel_body(
        indicator_id=str(selected_indicator_id),
        current_ids=current_ids,
        include_borough=include_borough,
        include_london=include_london,
        subcategory_catalog=composite_catalog,
        suppress_heading=True,
    )


def _render_indicator_panel_body(
    indicator_id: str,
    current_ids: list[str],
    include_borough: bool,
    include_london: bool,
    *,
    subcategory_catalog: pd.DataFrame,
) -> None:
    if str(indicator_id) in COMPOSITE_INDICATOR_GROUPS:
        _render_composite_indicator_panel(
            indicator_id=str(indicator_id),
            current_ids=current_ids,
            include_borough=include_borough,
            include_london=include_london,
        )
        return

    _render_indicator_single_panel_body(
        indicator_id=indicator_id,
        current_ids=current_ids,
        include_borough=include_borough,
        include_london=include_london,
        subcategory_catalog=subcategory_catalog,
    )


def _render_selected_indicator_explorer(
    *,
    category: str,
    subcategory: str,
    indicator_id: str,
    catalog_df: pd.DataFrame,
    current_ids: list[str],
    include_borough: bool,
    include_london: bool,
) -> None:
    subcategory_catalog = catalog_df[
        (catalog_df["top_level_category"].astype(str) == str(category))
        & (catalog_df["module_label"].astype(str) == str(subcategory))
    ].copy()
    bundle_catalog = _bundle_capable_subcategory_catalog(category, subcategory)
    if bundle_catalog.empty:
        bundle_catalog = subcategory_catalog.copy()
    if subcategory_catalog.empty:
        render_empty_state("No public indicators are available in this topic yet.")
        return

    module_description = _clean_text(subcategory_catalog.iloc[0].get("module_description"))
    with st.container(border=True):
        st.markdown("<div class='section-kicker'>Explorer</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='section-card-title'>{subcategory}</div>", unsafe_allow_html=True)
        helper_text = (
            module_description
            or "Choose an indicator below to see the default chart first, then switch to other views if you need more detail."
        )
        st.markdown(f"<div class='section-card-text'>{helper_text}</div>", unsafe_allow_html=True)
        _render_subcategory_bundle(
            indicator_id=indicator_id,
            subcategory_catalog=bundle_catalog,
            current_ids=current_ids,
            include_borough=include_borough,
            include_london=include_london,
        )
        _render_indicator_panel_body(
            indicator_id=indicator_id,
            current_ids=current_ids,
            include_borough=include_borough,
            include_london=include_london,
            subcategory_catalog=bundle_catalog,
        )


def _ordered_theme_labels(explorer_catalog: pd.DataFrame) -> list[str]:
    return _available_category_labels(explorer_catalog)


def _subcategory_groups_for_theme(theme_catalog: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    if theme_catalog.empty:
        return []
    ordered = theme_catalog.sort_values(
        ["module_sort_order", "module_label", "indicator_sort_order", "ui_title", "indicator_id"],
        kind="stable",
    ).copy()
    groups: list[tuple[str, pd.DataFrame]] = []
    for module_label, subset in ordered.groupby("module_label", dropna=False, sort=False):
        label = _clean_text(module_label) or _clean_text(subset.iloc[0].get("subcategory")) or "Indicators"
        groups.append((label, subset.reset_index(drop=True)))
    return groups


def _indicator_expander_label(row: pd.Series | dict[str, object]) -> str:
    title = _clean_text(row.get("ui_title")) or _clean_text(row.get("title")) or _clean_text(row.get("indicator_id"))
    short_title = _clean_text(row.get("ui_short_title")) or _clean_text(row.get("short_title"))
    indicator_id = _clean_text(row.get("indicator_id"))
    use_short_title = (
        short_title
        and short_title.lower() != title.lower()
        and (indicator_id.startswith("qof_") or len(title) > 56)
    )
    label = short_title if use_short_title else title
    exposure = _clean_text(row.get("ui_exposure_level")).lower()
    if exposure == "advanced":
        return f"{label} (Advanced)"
    return label


def _explorer_indicator_selector_key(category_label: str, subcategory_label: str) -> str:
    return f"explorer_indicator_{_theme_widget_slug(category_label)}_{_theme_widget_slug(subcategory_label)}"


def _explorer_topic_selector_key(theme_label: str) -> str:
    return f"explorer_topic_{_theme_widget_slug(theme_label)}"


def _theme_description_lookup() -> dict[str, str]:
    category_meta = category_frame()
    if category_meta.empty:
        return {}
    return {
        str(label): _clean_text(description)
        for label, description in zip(
            category_meta["label"].astype(str).tolist(),
            category_meta["description"].astype(str).fillna("").tolist(),
        )
        if _clean_text(label)
    }


def _indicator_tray_label(row: pd.Series | dict[str, object]) -> str:
    indicator_id = _clean_text(row.get("indicator_id"))
    title = _clean_text(row.get("ui_short_title")) or _clean_text(row.get("short_title"))
    if not title:
        title = _indicator_display_title(dict(row), indicator_id) if indicator_id else _clean_text(row.get("ui_title"))
    exposure = _clean_text(row.get("ui_exposure_level")).lower()
    if exposure == "advanced":
        return f"{title} (Advanced)"
    return title


def _indicator_tray_partition(topic_catalog: pd.DataFrame) -> tuple[list[str], list[str]]:
    ordered_ids = topic_catalog["indicator_id"].astype(str).tolist()
    if len(ordered_ids) <= 1:
        return ordered_ids, []
    advanced_mask = topic_catalog.get("ui_exposure_level", pd.Series("standard", index=topic_catalog.index)).astype(str).replace("nan", "standard").str.lower().eq("advanced")
    primary_ids = topic_catalog.loc[~advanced_mask, "indicator_id"].astype(str).tolist()
    if primary_ids:
        visible_ids = primary_ids[:EXPLORER_PRIMARY_INDICATOR_LIMIT]
        if not visible_ids:
            visible_ids = ordered_ids[:EXPLORER_PRIMARY_INDICATOR_LIMIT]
    else:
        visible_ids = ordered_ids[:EXPLORER_PRIMARY_INDICATOR_LIMIT]
    more_ids = [indicator_id for indicator_id in ordered_ids if indicator_id not in visible_ids]
    return visible_ids, more_ids


def _render_theme_section_header(
    *,
    theme_label: str,
    topic_count: int,
    indicator_count: int,
    description: str,
) -> None:
    badges = [
        f"<span class='explorer-shell-badge'>{topic_count} topic{'s' if topic_count != 1 else ''}</span>",
        f"<span class='explorer-shell-badge'>{indicator_count} indicator{'s' if indicator_count != 1 else ''}</span>",
    ]
    description_html = f"<div class='explorer-shell-copy'>{escape(description)}</div>" if description else ""
    st.markdown(
        (
            "<div class='explorer-theme-shell-header'>"
            "<div class='explorer-theme-shell-accent'></div>"
            "<div class='explorer-theme-shell-kicker'>Theme</div>"
            f"<div class='explorer-theme-shell-title'>{escape(theme_label)}</div>"
            f"{description_html}"
            f"<div class='explorer-shell-badge-row'>{''.join(badges)}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _render_topic_intro_block(subcategory_label: str, topic_catalog: pd.DataFrame) -> None:
    description = _clean_text(topic_catalog.iloc[0].get("module_description")) if not topic_catalog.empty else ""
    indicator_count = int(topic_catalog["indicator_id"].nunique()) if not topic_catalog.empty else 0
    advanced_count = int(
        topic_catalog.get("ui_exposure_level", pd.Series("standard", index=topic_catalog.index))
        .astype(str)
        .replace("nan", "standard")
        .str.lower()
        .eq("advanced")
        .sum()
    ) if not topic_catalog.empty else 0
    supporting_count = max(indicator_count - advanced_count, 0)
    badges = [
        f"<span class='explorer-shell-badge'>{indicator_count} indicator{'s' if indicator_count != 1 else ''}</span>",
    ]
    if supporting_count:
        badges.append(
            f"<span class='explorer-shell-badge explorer-shell-badge--soft'>{supporting_count} core/supporting</span>"
        )
    if advanced_count:
        badges.append(f"<span class='explorer-shell-badge explorer-shell-badge--soft'>{advanced_count} advanced</span>")
    description_html = (
        f"<div class='explorer-topic-intro-copy'>{escape(description)}</div>"
        if description
        else "<div class='explorer-topic-intro-copy'>Choose one indicator at a time to keep the Explorer focused and readable.</div>"
    )
    st.markdown(
        (
            "<div class='explorer-topic-intro'>"
            "<div class='explorer-topic-intro-kicker'>Topic</div>"
            f"<div class='explorer-topic-intro-title'>{escape(subcategory_label)}</div>"
            f"{description_html}"
            f"<div class='explorer-shell-badge-row'>{''.join(badges)}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _render_indicator_tray(
    *,
    theme_label: str,
    subcategory_label: str,
    topic_catalog: pd.DataFrame,
) -> str:
    indicator_rows = topic_catalog.to_dict(orient="records")
    indicator_ids = [str(row["indicator_id"]) for row in indicator_rows]
    if not indicator_ids:
        return ""
    selection_key = _explorer_indicator_selector_key(theme_label, subcategory_label)
    current_indicator_id = _clean_text(st.session_state.get(selection_key))
    if current_indicator_id not in indicator_ids:
        current_indicator_id = indicator_ids[0]
    label_lookup = {
        str(row["indicator_id"]): _indicator_tray_label(row)
        for row in indicator_rows
    }
    visible_ids, more_ids = _indicator_tray_partition(topic_catalog)
    visible_widget_key = f"{selection_key}_primary"
    more_widget_key = f"{selection_key}_more"
    more_toggle_state_key = f"{selection_key}_more_open"
    more_toggle_button_key = f"{selection_key}_more_toggle"
    _clear_widget_state_if_invalid(visible_widget_key, visible_ids)
    _clear_widget_state_if_invalid(more_widget_key, more_ids)

    st.markdown("<div class='explorer-control-label'>Indicator</div>", unsafe_allow_html=True)
    if len(indicator_ids) == 1:
        st.markdown(
            f"<div class='explorer-selection-note'>Showing: {escape(label_lookup[current_indicator_id])}</div>",
            unsafe_allow_html=True,
        )
        st.session_state[selection_key] = current_indicator_id
        return current_indicator_id

    selected_indicator_id = current_indicator_id
    if more_ids:
        indicator_row_cols = st.columns([0.82, 0.18], gap="small")
        with indicator_row_cols[0]:
            primary_choice = st.pills(
                "Indicator",
                options=visible_ids,
                default=current_indicator_id if current_indicator_id in visible_ids else None,
                format_func=lambda value: label_lookup.get(str(value), str(value)),
                key=visible_widget_key,
                label_visibility="collapsed",
                width="content",
            )
            if primary_choice:
                selected_indicator_id = str(primary_choice)
        with indicator_row_cols[1]:
            more_indicators_open = _render_more_toggle_button(
                state_key=more_toggle_state_key,
                button_key=more_toggle_button_key,
                closed_label=f"More indicators ({len(more_ids)})",
                open_label=f"Hide more indicators ({len(more_ids)})",
                default_open=current_indicator_id in more_ids,
            )
    else:
        primary_choice = st.pills(
            "Indicator",
            options=visible_ids,
            default=current_indicator_id if current_indicator_id in visible_ids else None,
            format_func=lambda value: label_lookup.get(str(value), str(value)),
            key=visible_widget_key,
            label_visibility="collapsed",
            width="content",
        )
        if primary_choice:
            selected_indicator_id = str(primary_choice)
        more_indicators_open = False

    if more_ids:
        advanced_in_more = sum(label_lookup[indicator_id].endswith("(Advanced)") for indicator_id in more_ids)
        supporting_in_more = len(more_ids) - advanced_in_more
        helper_parts = []
        if supporting_in_more:
            helper_parts.append(f"{supporting_in_more} supporting")
        if advanced_in_more:
            helper_parts.append(f"{advanced_in_more} advanced")
        helper_text = "Includes " + ", ".join(helper_parts) + "." if helper_parts else ""
        if more_indicators_open:
            if helper_text:
                st.caption(helper_text)
            more_choice = st.selectbox(
                "Browse more indicators",
                options=more_ids,
                index=more_ids.index(current_indicator_id) if current_indicator_id in more_ids else None,
                format_func=lambda value: label_lookup.get(str(value), str(value)),
                key=more_widget_key,
                label_visibility="collapsed",
                placeholder="Search supporting and advanced indicators",
            )
            if more_choice:
                selected_indicator_id = str(more_choice)

    st.session_state[selection_key] = selected_indicator_id
    if selected_indicator_id in more_ids:
        st.markdown(
            f"<div class='explorer-selection-note'>Selected from more indicators: {escape(label_lookup[selected_indicator_id])}</div>",
            unsafe_allow_html=True,
        )
    return selected_indicator_id


def _render_theme_explorer_shell(
    *,
    theme_label: str,
    theme_catalog: pd.DataFrame,
    current_ids: list[str],
    include_borough: bool,
    include_london: bool,
    description_lookup: dict[str, str],
) -> None:
    subcategory_groups = _subcategory_groups_for_theme(theme_catalog)
    if not subcategory_groups:
        return
    topic_lookup = {label: catalog for label, catalog in subcategory_groups}
    topic_labels = [label for label, _ in subcategory_groups]
    topic_count = len(topic_labels)
    description = _clean_text(description_lookup.get(theme_label))

    with st.container(border=True):
        _render_theme_section_header(
            theme_label=theme_label,
            topic_count=topic_count,
            indicator_count=int(theme_catalog["indicator_id"].nunique()),
            description=description,
        )

        selected_topic_label = topic_labels[0]
        if topic_count > 1:
            topic_widget_key = _explorer_topic_selector_key(theme_label)
            _clear_widget_state_if_invalid(topic_widget_key, topic_labels)
            st.markdown("<div class='explorer-control-label'>Topic</div>", unsafe_allow_html=True)
            topic_choice = st.pills(
                "Topic",
                options=topic_labels,
                default=_clean_text(st.session_state.get(topic_widget_key)) or topic_labels[0],
                key=topic_widget_key,
                label_visibility="collapsed",
                width="content",
            )
            selected_topic_label = str(topic_choice or topic_labels[0])

        selected_topic_catalog = _ordered_indicator_catalog_for_display(topic_lookup[selected_topic_label].copy())
        bundle_catalog = _bundle_capable_subcategory_catalog(theme_label, selected_topic_label)
        if bundle_catalog.empty:
            bundle_catalog = selected_topic_catalog.copy()

        selected_indicator_id = _render_indicator_tray(
            theme_label=theme_label,
            subcategory_label=selected_topic_label,
            topic_catalog=selected_topic_catalog,
        )
        _render_indicator_panel_body(
            indicator_id=selected_indicator_id,
            current_ids=current_ids,
            include_borough=include_borough,
            include_london=include_london,
            subcategory_catalog=bundle_catalog,
        )


def _render_subcategory_explorer_group(
    *,
    category_label: str,
    subcategory_label: str,
    subcategory_catalog: pd.DataFrame,
    current_ids: list[str],
    include_borough: bool,
    include_london: bool,
    use_nested_expander: bool,
) -> None:
    subcategory_catalog = _ordered_indicator_catalog_for_display(subcategory_catalog)
    if _is_qof_module_catalog(subcategory_catalog):
        _render_qof_subcategory_explorer_group(
            category_label=category_label,
            subcategory_label=subcategory_label,
            subcategory_catalog=subcategory_catalog,
            current_ids=current_ids,
            include_borough=include_borough,
            include_london=include_london,
            use_nested_expander=use_nested_expander,
        )
        return
    indicator_count = int(subcategory_catalog["indicator_id"].nunique())
    bundle_catalog = _bundle_capable_subcategory_catalog(category_label, subcategory_label)
    if bundle_catalog.empty:
        bundle_catalog = subcategory_catalog.copy()

    def _render_group_body() -> None:
        first_indicator_id = str(subcategory_catalog.iloc[0]["indicator_id"])
        _render_subcategory_bundle(
            indicator_id=first_indicator_id,
            subcategory_catalog=bundle_catalog,
            current_ids=current_ids,
            include_borough=include_borough,
            include_london=include_london,
        )
        if indicator_count == 1:
            _render_indicator_panel_body(
                indicator_id=first_indicator_id,
                current_ids=current_ids,
                include_borough=include_borough,
                include_london=include_london,
                subcategory_catalog=bundle_catalog,
            )
            return
        indicator_rows = subcategory_catalog.to_dict(orient="records")
        indicator_options = [str(row["indicator_id"]) for row in indicator_rows]
        indicator_labels = {
            str(row["indicator_id"]): _indicator_expander_label(row)
            for row in indicator_rows
        }
        selector_key = _explorer_indicator_selector_key(category_label, subcategory_label)
        selected_indicator_id = _clean_text(st.session_state.get(selector_key))
        if selected_indicator_id not in indicator_options:
            selected_indicator_id = indicator_options[0]
        selected_indicator_id = st.selectbox(
            "Indicator",
            indicator_options,
            index=indicator_options.index(selected_indicator_id),
            format_func=lambda value: indicator_labels.get(value, value),
            key=selector_key,
        )
        _render_indicator_panel_body(
            indicator_id=str(selected_indicator_id),
            current_ids=current_ids,
            include_borough=include_borough,
            include_london=include_london,
            subcategory_catalog=bundle_catalog,
        )

    if use_nested_expander:
        with st.expander(f"{subcategory_label} ({indicator_count})", expanded=False):
            _render_group_body()
    else:
        _render_group_body()


def _render_full_explorer_sections(
    *,
    explorer_catalog: pd.DataFrame,
    current_ids: list[str],
    include_borough: bool,
    include_london: bool,
) -> None:
    ordered_themes = _ordered_theme_labels(explorer_catalog)
    if not ordered_themes:
        render_empty_state("No public indicators are available in the current configuration.")
        return
    description_lookup = _theme_description_lookup()

    for theme_label in ordered_themes:
        theme_catalog = explorer_catalog[explorer_catalog["top_level_category"].astype(str) == str(theme_label)].copy()
        if theme_catalog.empty:
            continue
        theme_count = int(theme_catalog["indicator_id"].nunique())

        with st.expander(f"{theme_label} ({theme_count})", expanded=len(ordered_themes) == 1):
            _render_theme_explorer_shell(
                theme_label=theme_label,
                theme_catalog=theme_catalog,
                current_ids=current_ids,
                include_borough=include_borough,
                include_london=include_london,
                description_lookup=description_lookup,
            )


def _render_explorer_section_summary(explorer_catalog: pd.DataFrame) -> None:
    ordered_themes = _ordered_theme_labels(explorer_catalog)
    if not ordered_themes:
        st.caption("No sections are currently configured.")
        return
    st.caption("Open a theme to explore it.")
    chips = []
    for theme_label in ordered_themes:
        theme_catalog = explorer_catalog[explorer_catalog["top_level_category"].astype(str) == str(theme_label)].copy()
        count = int(theme_catalog["indicator_id"].nunique())
        chips.append(f"<span class='setup-chip'>{theme_label} ({count})</span>")
    st.markdown("<div class='setup-chip-row'>" + "".join(chips) + "</div>", unsafe_allow_html=True)


def _explorer_theme_filter_options(explorer_catalog: pd.DataFrame) -> list[str]:
    ordered_themes = _ordered_theme_labels(explorer_catalog)
    if not ordered_themes:
        return [ALL_EXPLORER_THEMES_LABEL]
    return [ALL_EXPLORER_THEMES_LABEL] + ordered_themes


def _filtered_explorer_catalog(
    explorer_catalog: pd.DataFrame,
    theme_filter: str | None = None,
) -> tuple[str, pd.DataFrame]:
    options = _explorer_theme_filter_options(explorer_catalog)
    current_filter = _clean_text(theme_filter) or _clean_text(st.session_state.get(EXPLORER_THEME_FILTER_KEY)) or ALL_EXPLORER_THEMES_LABEL
    if current_filter not in options:
        current_filter = ALL_EXPLORER_THEMES_LABEL
        st.session_state[EXPLORER_THEME_FILTER_KEY] = current_filter
    if current_filter == ALL_EXPLORER_THEMES_LABEL:
        return current_filter, explorer_catalog.copy()
    filtered = explorer_catalog[explorer_catalog["top_level_category"].astype(str) == str(current_filter)].copy()
    return current_filter, filtered


def render_configuration_page() -> None:
    set_page("Setup")
    inject_theme()
    ready = _data_readiness_guard()
    if ready is None:
        return
    reference_df, catalog_df = ready
    category_labels, configured_categories = _ensure_configuration_state(catalog_df)
    configured_indicator_ids = _ensure_indicator_configuration_state(catalog_df, category_labels)
    st.session_state[APP_SECTION_KEY] = "Setup"

    page_header(
        "Set up your neighbourhood view",
        "Choose the area, themes, and comparisons you want to visualise.",
    )
    _section_switcher("Setup", home_page=True)

    with st.container(border=True):
        _section_intro(
            "Footprint builder",
            "Choose the area you want to explore.",
            inline_heading=True,
        )
        control_bar_left, control_bar_right = st.columns([1.0, 1.0], gap="large")
        with control_bar_left:
            st.session_state.setdefault(SPATIAL_PERSPECTIVE_USER_SET_KEY, False)
            all_ids = sorted(reference_df["neighbourhood_id"].astype(str).unique().tolist())
            if not st.session_state.get(SPATIAL_PERSPECTIVE_USER_SET_KEY, False):
                if st.session_state.get(SPATIAL_PERSPECTIVE_KEY) not in SPATIAL_PERSPECTIVE_OPTIONS or st.session_state.get(SPATIAL_PERSPECTIVE_KEY) == "Region":
                    st.session_state[SPATIAL_PERSPECTIVE_KEY] = "Neighbourhood"
                if sorted(selected_ids()) == all_ids:
                    set_selected_ids([])
            if st.session_state.get(SPATIAL_PERSPECTIVE_KEY) not in SPATIAL_PERSPECTIVE_OPTIONS:
                st.session_state[SPATIAL_PERSPECTIVE_KEY] = "Neighbourhood"
            st.selectbox(
                "Spatial perspective",
                SPATIAL_PERSPECTIVE_OPTIONS,
                key=SPATIAL_PERSPECTIVE_KEY,
                on_change=_mark_spatial_perspective_user_set,
            )
        with control_bar_right:
            if st.session_state.get(MAP_MODE_KEY) not in MAP_INTERFACE_OPTIONS:
                st.session_state[MAP_MODE_KEY] = "Hex map"
            st.radio("Map mode", MAP_INTERFACE_OPTIONS, key=MAP_MODE_KEY, horizontal=True, label_visibility="collapsed")

        selector_col, map_col = st.columns([0.88, 1.72], gap="large")
        with selector_col:
            _render_setup_selector(reference_df)
        with map_col:
            _render_setup_map(str(st.session_state[MAP_MODE_KEY]))

    with st.container(border=True):
        step2_intro_col, step2_benchmark_col = st.columns([1.4, 0.9], gap="large")
        with step2_intro_col:
            _section_intro(
                "Select indicators",
                "Select the data you want to visualise.",
                inline_heading=True,
            )
        with step2_benchmark_col:
            _render_comparison_configuration_with_layout(compact=True)
        configured_categories, configured_indicator_ids = _render_indicator_group_configuration(catalog_df, category_labels)
        st.markdown(
            f"<div class='insight-note'>{selection_context_summary(reference_df, selected_ids())}</div>",
            unsafe_allow_html=True,
        )

    with st.container(border=True):
        _section_intro(
            "Current setup",
            "This shows what will appear in the Explorer and the report.",
            inline_heading=True,
        )
        _render_setup_review(reference_df, configured_categories, configured_indicator_ids)
        if st.button("Visualize data", type="primary", use_container_width=True):
            st.session_state[APP_SECTION_KEY] = "Explorer"
            st.switch_page(SECTION_TARGETS["Explorer"])


def render_explorer_page() -> None:
    set_page("Explorer")
    inject_theme()
    ready = _data_readiness_guard()
    if ready is None:
        return
    reference_df, catalog_df = ready
    _, configured_categories = _ensure_configuration_state(catalog_df)
    st.session_state[APP_SECTION_KEY] = "Explorer"

    current_ids = selected_ids()
    include_borough, include_london = _comparison_preferences(current_ids)
    explorer_catalog = catalog_df[catalog_df["top_level_category"].isin(configured_categories)].copy()
    configured_indicator_ids = [str(value) for value in st.session_state.get(INDICATOR_SELECTION_KEY, [])]
    explorer_catalog = explorer_catalog[
        explorer_catalog["indicator_id"].astype(str).isin(set(configured_indicator_ids))
    ].copy()
    theme_filter_options = _explorer_theme_filter_options(explorer_catalog)
    show_loading_overlay = bool(current_ids)
    if show_loading_overlay:
        render_loading_overlay(
            overlay_key="explorer",
            title="Loading the explorer",
            caption="Preparing maps, charts, and summaries for your selection.",
        )

    try:
        page_header(
            "Explorer",
            "Explore the indicators for the area you chose.",
            action_renderer=lambda: _render_powerpoint_header_panel(
                catalog_df=explorer_catalog,
                current_category_labels=configured_categories,
                current_indicator_id=str(st.session_state.get(INDICATOR_KEY, "")),
                current_period=str(st.session_state.get(PERIOD_KEY, "")),
                selected_ids_in_scope=current_ids,
                include_borough=include_borough,
                include_london=include_london,
            ),
        )
        _section_switcher("Explorer")

        if not current_ids:
            with st.container(border=True):
                _section_intro(
                    "No footprint selected",
                    "Go back to Setup to define a footprint before exploring indicators.",
                    kicker="Explorer",
                )
                if st.button("Go to setup", type="primary"):
                    st.session_state[APP_SECTION_KEY] = "Setup"
                    st.switch_page(SECTION_TARGETS["Setup"])
            return

        context_col, nav_col = st.columns([1.04, 0.96], gap="large")
        with context_col:
            with st.container(border=True):
                _section_intro(
                    "Current footprint",
                    "This keeps the current footprint in view while you explore the data below.",
                    kicker="Context",
                )
                st.markdown(
                    f"<div class='insight-note'>{selection_context_summary(reference_df, current_ids)}</div>",
                    unsafe_allow_html=True,
                )
                render_selection_map(
                    load_map_geography("hex"),
                    pd.DataFrame(columns=["neighbourhood_id", "value", "unit"]),
                    current_ids,
                    map_key="explorer_context_hex",
                    variant="hex",
                    overlay_geo_df=load_hex_icb_geography(),
                    height=360,
                )
                if st.button("Edit setup", use_container_width=True):
                    st.session_state[APP_SECTION_KEY] = "Setup"
                    st.switch_page(SECTION_TARGETS["Setup"])
        with nav_col:
            with st.container(border=True):
                _section_intro(
                    "Included sections",
                    "All of the sections you included in Setup are shown below. Open a theme to browse its indicators, and use nested topic dropdowns where a section has a lot of content.",
                    kicker="Explorer",
                )
                selected_theme_filter = st.selectbox(
                    "Filter by theme",
                    theme_filter_options,
                    key=EXPLORER_THEME_FILTER_KEY,
                )
                visible_theme_filter, visible_explorer_catalog = _filtered_explorer_catalog(explorer_catalog, selected_theme_filter)
                if visible_theme_filter != ALL_EXPLORER_THEMES_LABEL:
                    st.caption(f"Showing: {visible_theme_filter}")
                _render_explorer_section_summary(visible_explorer_catalog)

        with st.container(border=False):
            _render_full_explorer_sections(
                explorer_catalog=visible_explorer_catalog,
                current_ids=current_ids,
                include_borough=include_borough,
                include_london=include_london,
            )
    finally:
        if show_loading_overlay:
            dismiss_loading_overlay(overlay_key="explorer")


def render_methodology_page() -> None:
    set_page("Methodology & Data Coverage")
    inject_theme()
    st.session_state[APP_SECTION_KEY] = "Methodology & Data Coverage"
    page_header(
        "Methodology & Data Coverage",
        "This page explains where the data comes from, how neighbourhood figures are built, and what the main caveats are.",
    )
    _section_switcher("Methodology & Data Coverage")
    with st.container(border=True):
        _section_intro(
            "How the explorer works",
            "Use this page if you want to understand the data behind the tool, how comparisons work, and what the limits are.",
            kicker="Transparency",
        )
        from app.components.methodology_panel import render_methodology_panel

        render_methodology_panel()


def render_overview_page() -> None:
    render_guide_page()


def render_data_explorer_page() -> None:
    render_explorer_page()


def render_notes_page() -> None:
    render_methodology_page()


def render_topic_page(topic_name: str, page_title: str) -> None:
    render_explorer_page()


def render_compare_page() -> None:
    render_explorer_page()


def render_home_page() -> None:
    active_section = str(st.session_state.get(APP_SECTION_KEY, "Guide"))
    if active_section == "Setup":
        render_configuration_page()
        return
    render_guide_page()
