from __future__ import annotations

from functools import lru_cache

import pandas as pd
import streamlit as st

from app.components.formatting import format_dataframe_for_display
from neighbourhood_explorer.catalog import category_frame
from neighbourhood_explorer.data_access import load_catalog_df, load_neighbourhood_reference, load_public_catalog_df
from neighbourhood_explorer.paths import (
    FINGERTIPS_DISCOVERY_PATH,
    INDICATOR_SOURCE_INVENTORY_CSV_PATH,
    INDICATOR_VISUALISATION_GUIDANCE_PATH,
)


@lru_cache(maxsize=1)
def _load_guidance_inventory() -> pd.DataFrame:
    if not INDICATOR_VISUALISATION_GUIDANCE_PATH.exists():
        return pd.DataFrame()
    return pd.read_csv(INDICATOR_VISUALISATION_GUIDANCE_PATH)


@lru_cache(maxsize=1)
def _load_source_inventory() -> pd.DataFrame:
    if not INDICATOR_SOURCE_INVENTORY_CSV_PATH.exists():
        return pd.DataFrame()
    return pd.read_csv(INDICATOR_SOURCE_INVENTORY_CSV_PATH)


def _parse_bool(value: object) -> bool:
    if pd.isna(value):
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _indicator_universe_status(
    frame: pd.DataFrame,
    public_indicator_ids: set[str] | None = None,
    catalog_indicator_ids: set[str] | None = None,
) -> pd.DataFrame:
    if frame.empty:
        return frame
    enriched = frame.copy()
    live_mask = enriched["currently_in_app"].map(_parse_bool)
    hidden_mask = enriched["ui_exposure_level"].astype(str).str.strip().str.lower().eq("hidden")
    public_indicator_ids = public_indicator_ids or set()
    catalog_indicator_ids = catalog_indicator_ids or set()
    public_live_mask = enriched["indicator_id"].astype(str).isin(public_indicator_ids)
    catalog_live_mask = enriched["indicator_id"].astype(str).isin(catalog_indicator_ids)
    enriched["app_status"] = "Specified only"
    enriched.loc[public_live_mask, "app_status"] = "Live in app"
    enriched.loc[hidden_mask & catalog_live_mask & ~public_live_mask, "app_status"] = "Hidden from public navigation"
    enriched.loc[live_mask & catalog_live_mask & ~hidden_mask & ~public_live_mask, "app_status"] = "Live in app"
    return enriched


def _universe_summary(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    return (
        frame.groupby(["app_status", "source_name"], dropna=False)["indicator_id"]
        .nunique()
        .reset_index(name="indicator_count")
        .sort_values(["app_status", "indicator_count", "source_name"], ascending=[True, False, True])
        .reset_index(drop=True)
    )


def _source_inventory_summary(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    return (
        frame.groupby(["current_status", "current_app_usage"], dropna=False)["source_name"]
        .nunique()
        .reset_index(name="source_count")
        .sort_values(["current_status", "source_count"], ascending=[True, False])
        .reset_index(drop=True)
    )


def _coverage_by_category(catalog_df: pd.DataFrame) -> pd.DataFrame:
    if catalog_df.empty:
        return pd.DataFrame()
    grouped = (
        catalog_df.groupby(["top_level_category", "neighbourhood_use_mode"], dropna=False)["indicator_id"]
        .nunique()
        .reset_index(name="indicator_count")
        .sort_values(["top_level_category", "neighbourhood_use_mode"])
        .reset_index(drop=True)
    )
    return grouped


def _source_summary(catalog_df: pd.DataFrame) -> pd.DataFrame:
    if catalog_df.empty:
        return pd.DataFrame()
    summary = (
        catalog_df.groupby(["source_name", "source_geography", "period_type"], dropna=False)["indicator_id"]
        .nunique()
        .reset_index(name="indicator_count")
        .sort_values(["indicator_count", "source_name"], ascending=[False, True])
        .reset_index(drop=True)
    )
    return summary


def _aggregation_summary(catalog_df: pd.DataFrame) -> pd.DataFrame:
    if catalog_df.empty:
        return pd.DataFrame()
    return (
        catalog_df.groupby(["aggregation_policy", "unit_type"], dropna=False)["indicator_id"]
        .nunique()
        .reset_index(name="indicator_count")
        .sort_values(["indicator_count", "aggregation_policy"], ascending=[False, True])
        .reset_index(drop=True)
    )


def _order_indicator_rows_by_catalog(frame: pd.DataFrame, catalog_df: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "indicator_id" not in frame.columns or catalog_df.empty or "indicator_id" not in catalog_df.columns:
        return frame

    order_lookup = {
        str(indicator_id): index
        for index, indicator_id in enumerate(catalog_df["indicator_id"].astype(str).tolist())
    }
    ordered = frame.copy()
    ordered["_catalog_order"] = ordered["indicator_id"].astype(str).map(order_lookup)
    ordered["_catalog_missing"] = ordered["_catalog_order"].isna()
    ordered["_original_order"] = range(len(ordered))
    ordered = ordered.sort_values(
        ["_catalog_missing", "_catalog_order", "_original_order"],
        ascending=[True, True, True],
        na_position="last",
    ).drop(columns=["_catalog_order", "_catalog_missing", "_original_order"])
    return ordered.reset_index(drop=True)


def render_methodology_panel() -> None:
    catalog_df = load_public_catalog_df()
    full_catalog_df = load_catalog_df()
    reference_df = load_neighbourhood_reference()
    categories_df = category_frame()
    guidance_df = _indicator_universe_status(
        _load_guidance_inventory(),
        public_indicator_ids=set(catalog_df["indicator_id"].astype(str)),
        catalog_indicator_ids=set(full_catalog_df["indicator_id"].astype(str)),
    )
    source_inventory_df = _load_source_inventory()

    tabs = st.tabs(["Methodology", "Indicator inventory", "Source inventory"])

    with tabs[0]:
        summary_cards = st.columns(4)
        card_values = [
            ("Neighbourhoods", f"{reference_df['neighbourhood_id'].nunique():,}", "Custom London neighbourhoods in scope"),
            ("Borough comparators", f"{reference_df['borough_code'].nunique():,}", "Comparator names preserved for careful benchmark logic"),
            ("Live indicators", f"{catalog_df['indicator_id'].nunique():,}", "Indicators currently available in the Explorer"),
            ("Themes", f"{categories_df['category_key'].nunique():,}", "Public-facing navigation categories"),
        ]
        for col, (label, value, caption) in zip(summary_cards, card_values, strict=False):
            with col:
                st.metric(label, value)
                st.caption(caption)

        st.markdown("### Geography and benchmark logic")
        st.markdown(
            """
            - Reporting geography is the custom London neighbourhood.
            - Integration geography is LSOA 2021, using the canonical static LSOA 2021 to neighbourhood crosswalk.
            - Selections can span one or several neighbourhoods, exact place boundaries, exact system boundaries, or the London region.
            - London is always treated as a real aggregate benchmark.
            - Borough comparison is careful by design: if a selection spans multiple boroughs, the app shows each relevant borough separately instead of fabricating one combined borough benchmark.
            """
        )

        st.markdown("### Aggregation policies")
        st.markdown(
            """
            - Counts are added across the selected footprint.
            - Percentages are rebuilt from summed counts and denominators.
            - Rates are rebuilt from summed numerators and denominators.
            - Weighted averages are used only where that is methodologically defensible.
            - Ranks, deciles, and similar measures are shown as descriptive summaries rather than fake combined figures.
            """
        )

        coverage_left, coverage_right = st.columns([1.05, 0.95], gap="large")
        with coverage_left:
            st.markdown("### Indicator coverage by category")
            coverage_df = _coverage_by_category(catalog_df)
            st.dataframe(
                format_dataframe_for_display(
                    coverage_df,
                    value_map={"neighbourhood_use_mode": "use_mode"},
                ),
                hide_index=True,
                width="stretch",
            )

            st.markdown("### Source coverage")
            st.dataframe(
                format_dataframe_for_display(
                    _source_summary(catalog_df),
                    value_map={"period_type": "label"},
                ),
                hide_index=True,
                width="stretch",
            )
        with coverage_right:
            st.markdown("### Aggregation coverage")
            st.dataframe(
                format_dataframe_for_display(
                    _aggregation_summary(catalog_df),
                    value_map={"aggregation_policy": "aggregation", "unit_type": "unit"},
                ),
                hide_index=True,
                width="stretch",
            )

            st.markdown("### Category design")
            if not categories_df.empty:
                st.dataframe(
                    categories_df[["label", "description", "sort_order"]].rename(columns={"label": "Category", "description": "Description", "sort_order": "Order"}),
                    hide_index=True,
                    width="stretch",
                )

        st.markdown("### Neighbourhood estimate versus benchmark context")
        st.markdown(
            """
            The catalogue explicitly distinguishes between:

            - direct neighbourhood estimates
            - neighbourhood estimates with caveats
            - benchmark-only context indicators

            This distinction drives chart choice, map eligibility, comparison behaviour, and methodology copy in the explorer.
            """
        )

        st.markdown("### Fingertips expansion scaffolding")
        if FINGERTIPS_DISCOVERY_PATH.exists():
            try:
                discovery = pd.read_parquet(FINGERTIPS_DISCOVERY_PATH)
                st.caption(f"Cached Fingertips discovery rows available: {len(discovery):,}")
            except Exception:
                st.caption("A Fingertips discovery cache exists, but it could not be read in this session.")
        else:
            st.caption("No local Fingertips discovery cache is present yet. Run the Fingertips discovery scripts to populate it.")
        st.markdown(
            """
            Fingertips ingestion is designed as a metadata-first pipeline:

            - discovery and caching of profiles, area types, and indicator metadata
            - normalised metadata tables
            - curation rules that map raw source structures into user-facing categories
            - suitability flags that distinguish direct neighbourhood estimates, benchmark-only context, and hidden or deferred indicators

            This keeps future expansion configuration-driven rather than hard-coded into the app surface.
            """
        )

        st.markdown("### QOF indicators: GP practice to LSOA to neighbourhood conversion")
        st.markdown(
            """
            Quality and Outcomes Framework (QOF) data is published at GP practice level. To
            produce neighbourhood-level estimates, this project applies a disaggregation method
            developed by the **House of Commons Library** and implemented in R by
            **Dr Alex Gibson, Senior Research Fellow, Peninsula Medical School**.

            The method works as follows:

            1. **Practice-to-LSOA registrations** — each GP practice's registered list is
               disaggregated to LSOA 2021 geography using NHS Digital patient registration data,
               which records the number of patients registered at each practice who live in each LSOA.
            2. **Age-structure adjustment** — Census 2021 age structure within each LSOA is used
               to weight the registration shares, so that age-sensitive QOF indicators are
               disaggregated in a way that reflects the local demographic profile.
            3. **LSOA to neighbourhood aggregation** — LSOA-level estimates are then summed or
               reweighted to the custom London neighbourhood geography using the canonical
               LSOA 2021 → neighbourhood crosswalk.

            **These are modelled estimates, not directly measured neighbourhood values.**
            The allocation inherits the assumptions of the registration-weighting method and will
            not perfectly reflect within-practice variation across LSOAs. Users should treat QOF
            neighbourhood figures as approximate indicators of relative variation, not precise counts.

            **Method credit:**
            - House of Commons Library — original GP-to-LSOA allocation method
            - Dr Alex Gibson, Senior Research Fellow, Peninsula Medical School — R implementation
              ([github.com/houseofcommonslibrary/local-health-data-from-QOF](https://github.com/houseofcommonslibrary/local-health-data-from-QOF/blob/main/gp-lsoa.R))
            """
        )

        st.markdown("### Live indicator coverage index")
        display_cols = [
            "ui_title",
            "source_name",
            "source_period",
            "last_refresh_date",
            "source_geography",
        ]
        existing_cols = [col for col in display_cols if col in catalog_df.columns]
        st.dataframe(
            format_dataframe_for_display(
                catalog_df[existing_cols],
                value_map={},
            ),
            hide_index=True,
            width="stretch",
        )

    with tabs[1]:
        if guidance_df.empty:
            st.info("No indicator universe file is available in this session.")
        else:
            inventory_cols = [
                "indicator_id",
                "ui_title",
                "source_name",
                "category_final",
                "subcategory_final",
                "app_status",
                "ui_exposure_level",
                "use_mode",
                "neighbourhood_suitability",
                "geography_level",
                "period_type",
                "default_view",
                "primary_visual_final",
                "secondary_visual_final",
            ]
            existing_cols = [col for col in inventory_cols if col in guidance_df.columns]
            live_df = guidance_df[guidance_df["app_status"] != "Specified only"] if "app_status" in guidance_df.columns else guidance_df
            live_df = _order_indicator_rows_by_catalog(live_df, full_catalog_df)
            st.dataframe(
                format_dataframe_for_display(
                    live_df[existing_cols],
                    value_map={
                        "ui_exposure_level": "label",
                        "use_mode": "use_mode",
                        "default_view": "visual",
                        "primary_visual_final": "visual",
                        "secondary_visual_final": "visual",
                    },
                ),
                hide_index=True,
                width="stretch",
                height=620,
            )
            st.download_button(
                "Download full indicator universe",
                data=live_df.to_csv(index=False).encode("utf-8"),
                file_name="indicator_visualisation_guidance_final.csv",
                mime="text/csv",
                width="stretch",
            )

    with tabs[2]:
        if source_inventory_df.empty:
            st.info("No source inventory file is available in this session.")
        else:
            display_cols = [
                "source_name",
                "source_group",
                "source_type",
                "current_status",
                "refresh_mode",
                "api_or_download",
                "geography_base",
                "typical_periodicity",
                "current_app_usage",
            ]
            existing_cols = [col for col in display_cols if col in source_inventory_df.columns]
            st.dataframe(
                format_dataframe_for_display(
                    source_inventory_df[existing_cols],
                    value_map={"current_status": "label"},
                ),
                hide_index=True,
                width="stretch",
                height=420,
            )
            st.download_button(
                "Download source inventory",
                data=source_inventory_df.to_csv(index=False).encode("utf-8"),
                file_name="indicator_source_inventory.csv",
                mime="text/csv",
                width="stretch",
            )
