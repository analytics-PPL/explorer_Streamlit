from __future__ import annotations

import pandas as pd


_DUPLICATE_KEY_COLUMNS = [
    "title",
    "source_period",
    "source_geography",
    "geography_version",
    "unit",
    "aggregation_method",
    "benchmark_method",
]

_SOURCE_PREFERENCE = {
    "Nomis API": 0,
    "NHS England Patients Registered at a GP Practice": 1,
    "Department for Transport Road Traffic Statistics API": 1,
    "Environment Agency Flood Monitoring API": 1,
    "London Datastore CKAN API": 1,
    "NaPTAN / NPTG API": 1,
    "TfL Unified API": 1,
    "data.police.uk street-level crime": 1,
    "Indices of Deprivation 2025": 1,
    "ONS Census 2021": 2,
}

_EXPOSURE_PREFERENCE = {
    "core": 0,
    "standard": 1,
    "advanced": 2,
    "hidden": 3,
}

_DISPLAY_PREFERENCE = {
    "public": 0,
    "hidden_for_now": 1,
}


def drop_overlapping_catalog_metrics(catalog: pd.DataFrame) -> pd.DataFrame:
    if catalog.empty:
        return catalog

    available_key_columns = [column for column in _DUPLICATE_KEY_COLUMNS if column in catalog.columns]
    if not available_key_columns:
        return catalog

    deduped = catalog.copy()
    for column in available_key_columns:
        deduped[column] = deduped[column].astype(str).fillna("").str.strip()

    source_series = deduped["source_name"] if "source_name" in deduped.columns else pd.Series("", index=deduped.index)
    display_series = deduped["display_status"] if "display_status" in deduped.columns else pd.Series("", index=deduped.index)
    exposure_series = deduped["ui_exposure_level"] if "ui_exposure_level" in deduped.columns else pd.Series("", index=deduped.index)

    deduped["_source_preference"] = source_series.map(lambda value: _SOURCE_PREFERENCE.get(str(value), 9))
    deduped["_display_preference"] = display_series.map(
        lambda value: _DISPLAY_PREFERENCE.get(str(value).strip().lower(), 2)
    )
    deduped["_exposure_preference"] = exposure_series.map(
        lambda value: _EXPOSURE_PREFERENCE.get(str(value).strip().lower(), 4)
    )

    sort_columns = [
        column
        for column in [
            "_source_preference",
            "_display_preference",
            "_exposure_preference",
            "indicator_id",
        ]
        if column in deduped.columns
    ]

    deduped = deduped.sort_values(sort_columns).drop_duplicates(subset=available_key_columns, keep="first")
    return deduped.drop(
        columns=["_source_preference", "_display_preference", "_exposure_preference"],
        errors="ignore",
    )
