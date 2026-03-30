"""Pure display helper functions shared across page view modules.

These functions handle text cleaning, formatting, title resolution,
and metadata interpretation. They do not import streamlit.
"""

from __future__ import annotations

import ast
import csv
import json
import re
from functools import lru_cache

import pandas as pd

from app.components.formatting import format_period_label
from neighbourhood_explorer.paths import ROOT_DIR


# ── Friendly name lookups ──

_GENERIC_PERIOD_LABELS = {"snapshot", "annual", "quarterly", "monthly"}

_FRIENDLY_SOURCE_NAMES = {
    "Department for Transport Road Traffic Statistics API": "Department for Transport road traffic data",
    "Environment Agency Flood Monitoring API": "Environment Agency flood area data",
    "Indices of Deprivation 2025": "English Indices of Deprivation data",
    "London Datastore CKAN API": "London Datastore data",
    "NHS England Patients Registered at a GP Practice": "NHS GP registration data",
    "NHS England Quality and Outcomes Framework": "NHS Quality and Outcomes Framework data",
    "NaPTAN / NPTG API": "National public transport stops and stations data",
    "Nomis API": "Census data",
    "ONS Census 2021": "Census data",
    "ONS API": "Office for National Statistics data",
    "TfL Unified API": "Transport for London data",
    "data.police.uk street-level crime": "Police recorded crime data",
    "OHID Fingertips API": "OHID public health data",
}

_DISPLAY_TITLE_OVERRIDES = {
    "ea_flood_area_overlap_share": "Area covered by flood areas",
    "imd_score": "Deprivation score",
    "imd_decile_median_lsoa": "Typical neighbourhood deprivation decile",
    "nomis_recent_arrivals_share": "Length of residence in the UK",
    "nomis_main_language_not_english_share": "Main language and English proficiency",
    "nomis_households_without_english_main_language_share": "Household language",
    "nomis_households_with_multiple_main_languages_share": "Household language diversity",
    "nomis_overcrowded_household_share": "Bedroom occupancy",
    "nomis_room_overcrowding_share": "Room occupancy",
    "naptan_public_transport_access_node_count": "Public transport stops and stations",
    "naptan_access_node_density": "Public transport stops and stations density",
    "naptan_bus_access_node_count": "Bus stops",
    "naptan_rail_and_tube_node_count": "Rail and Tube stations",
    "tfl_cycle_docking_station_count": "Cycle hire docking stations",
    "tfl_cycle_docking_station_density": "Cycle hire docking station density",
    "tfl_cycle_dock_capacity_total": "Cycle hire dock capacity",
    "tfl_cycle_dock_capacity_density": "Cycle hire dock capacity density",
}

_DESCRIPTION_SUBJECT_OVERRIDES = {
    "ea_flood_area_overlap_share": "neighbourhood area covered by Environment Agency flood areas",
    "imd_score": "overall deprivation",
    "income_deprivation_rate": "people affected by income deprivation",
    "employment_deprivation_rate": "working-age people affected by employment deprivation",
    "london_datastore_fuel_poverty": "households in fuel poverty",
    "naptan_public_transport_access_node_count": "public transport stops and stations",
    "naptan_access_node_density": "public transport stops and stations",
    "naptan_bus_access_node_count": "bus stops",
    "naptan_rail_and_tube_node_count": "rail and Tube stations",
    "tfl_cycle_docking_station_count": "cycle hire docking stations",
    "tfl_cycle_docking_station_density": "cycle hire docking stations",
    "tfl_cycle_dock_capacity_total": "cycle hire dock capacity",
    "tfl_cycle_dock_capacity_density": "cycle hire dock capacity",
}

STRUCTURE_LED_VIEWS = {
    "stacked_100_bar",
    "grouped_bar",
    "population_pyramid",
    "crime_mix_chart",
    "domain_tile_matrix",
}


# ── Text utilities ──


def clean_text(value: object) -> str:
    """Convert value to string and strip whitespace. Returns '' for None/NaN."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def truncate_text(value: object, *, max_chars: int = 120) -> str:
    """Truncate text to max_chars with ellipsis if needed."""
    text = clean_text(value)
    if len(text) <= max_chars:
        return text
    truncated = text[: max_chars - 1].rsplit(" ", 1)[0]
    return f"{truncated or text[: max_chars - 1]}..."


def normalise_search_text(value: object) -> str:
    """Normalise text for search matching (lowercase, whitespace collapsed)."""
    return re.sub(r"\s+", " ", clean_text(value)).strip().casefold()


def theme_widget_slug(label: str) -> str:
    """Convert a theme label into a valid widget key slug."""
    return (
        str(label)
        .lower()
        .replace("&", "and")
        .replace("/", "_")
        .replace(" ", "_")
        .replace(",", "")
    )


def safe_filename(text: str) -> str:
    """Sanitize a string to be a safe filename."""
    return re.sub(r"[^a-zA-Z0-9_\-]+", "_", str(text).strip()).strip("_").lower() or "report"


def sentence_case_phrase(text: str) -> str:
    """Convert 'Title case' to 'title case' if applicable."""
    if len(text) > 1 and text[0].isupper() and text[1].islower():
        return text[0].lower() + text[1:]
    return text


def sequence_from_meta(value: object) -> list[str]:
    """Parse various formats into a list of strings from metadata."""
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = clean_text(value)
    if not text:
        return []
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(text)
        except Exception:
            continue
        if isinstance(parsed, (list, tuple, set)):
            return [str(item).strip() for item in parsed if str(item).strip()]
    if ";" in text:
        return [item.strip() for item in text.split(";") if item.strip()]
    return [text]


def normalised_field_set(value: object) -> set[str]:
    """Normalise a set of field names from metadata."""
    return {
        clean_text(item)
        for item in sequence_from_meta(value)
        if clean_text(item)
    }


# ── Source and period helpers ──


def friendly_source_name(meta: dict[str, object]) -> str:
    """Convert source name to friendly display version."""
    source_name = clean_text(meta.get("source_name"))
    return _FRIENDLY_SOURCE_NAMES.get(source_name, source_name or "Public data")


def metric_period_label(meta: dict[str, object], period: str | None) -> str:
    """Generate formatted period label from metadata candidates."""
    period_candidates = [
        clean_text(period),
        clean_text(meta.get("latest_period_available")),
        clean_text(meta.get("source_period")),
        clean_text(meta.get("time_coverage")),
    ]
    for candidate in period_candidates:
        if candidate and candidate.lower() not in _GENERIC_PERIOD_LABELS:
            return format_period_label(candidate)
    last_refresh = clean_text(meta.get("last_refresh_date"))
    if last_refresh:
        return format_period_label(last_refresh)
    for candidate in period_candidates:
        if candidate:
            return format_period_label(candidate)
    return ""


def indicator_source_summary(meta: dict[str, object], period: str | None) -> str:
    """Generate source and data period summary line."""
    source_name = friendly_source_name(meta)
    period_label = metric_period_label(meta, period)
    if period_label:
        return f"Source: {source_name} | Data period: {period_label}"
    return f"Source: {source_name}"


def indicator_history_range_label(meta: dict[str, object]) -> str:
    """Generate label showing available history range."""
    earliest = clean_text(meta.get("earliest_available_period"))
    latest = clean_text(meta.get("latest_available_period"))
    if not earliest or not latest or earliest == latest:
        return ""
    period_count = pd.to_numeric(pd.Series([meta.get("timeseries_period_count")]), errors="coerce").iloc[0]
    if not pd.isna(period_count) and float(period_count) <= 1:
        return ""
    return f"History available: {format_period_label(earliest)} to {format_period_label(latest)}"


def indicator_panel_subtitle(meta: dict[str, object], period: str | None) -> str:
    """Generate subtitle with data period, history range, source geography."""
    period_label = metric_period_label(meta, period)
    geography = clean_text(meta.get("source_geography") or meta.get("geography_level") or meta.get("geography_type"))
    parts: list[str] = []
    if period_label:
        parts.append(f"Data period: {period_label}")
    history_range = indicator_history_range_label(meta)
    if history_range:
        parts.append(history_range)
    if geography:
        parts.append(f"Source geography: {geography}")
    return " | ".join(parts)


# ── Label / title helpers ──


def plain_english_indicator_label(text: object) -> str:
    """Clean and normalise indicator label text."""
    label = clean_text(text).rstrip(".")
    if not label:
        return ""
    label = re.sub(r"\s+profile$", "", label, flags=re.IGNORECASE)
    label = re.sub(r"\s+", " ", label).strip()
    return label


def plain_english_clinical_text(text: str) -> str:
    """Expand medical abbreviations in clinical text."""
    cleaned = text.replace("≤", "at or below ").replace(">=", "at or above ").replace("<=", "at or below ")
    replacements = [
        (r"\bACE inhibitor or ARB\b", "ACE inhibitor or angiotensin receptor blocker"),
        (r"\bARB\b", "angiotensin receptor blocker"),
        (r"\bCOPD\b", "chronic obstructive pulmonary disease"),
        (r"\bCHD\b", "coronary heart disease"),
        (r"\bTIA\b", "transient ischaemic attack"),
        (r"\bstroke/TIA\b", "stroke or transient ischaemic attack"),
        (r"\bBMI\b", "body mass index (BMI)"),
        (r"\bHbA1c\b", "long-term blood sugar (HbA1c)"),
        (r"\bDTaP\b", "diphtheria, tetanus and whooping cough (DTaP)"),
        (r"\bMMR\b", "measles, mumps and rubella (MMR)"),
        (r"\bCHA2DS2-VASc score\b", "the CHA2DS2-VASc stroke risk score"),
        (r"\becho\b", "echocardiogram"),
        (r"\bBP\b", "Blood pressure"),
        (r"\bAF\b", "Atrial fibrillation"),
    ]
    for pattern, replacement in replacements:
        cleaned = re.sub(pattern, replacement, cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


@lru_cache(maxsize=1)
def qof_guidance_lookup() -> dict[str, str]:
    """Load cached QOF guidance CSV for clinical text expansion."""
    path = ROOT_DIR / "QOF Guidance.csv"
    if not path.exists():
        return {}
    lookup: dict[str, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        for row in reader:
            if not row:
                continue
            cell = clean_text(row[0])
            if not cell:
                continue
            parts = [part.strip() for part in cell.split(",", 2)]
            if len(parts) != 3:
                continue
            _, code, description = parts
            if code and description:
                lookup[code.upper()] = plain_english_clinical_text(description)
    return lookup


def qof_display_title(meta: dict[str, object], raw_title: str) -> str:
    """Generate display title for QOF indicator with clinical expansion."""
    metric_kind = clean_text(meta.get("qof_metric_kind")).lower()
    code = clean_text(meta.get("qof_indicator_code")).upper()
    lookup = qof_guidance_lookup()
    if metric_kind in {"achievement"} and code and code in lookup:
        return lookup[code]
    cleaned = re.sub(r"\s*\(QOF\)$", "", raw_title, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*\([A-Z]{2,}\d+[A-Z0-9]*\)$", "", cleaned)
    if metric_kind == "newly_diagnosed":
        cleaned = re.sub(r"\s+share$", "", cleaned, flags=re.IGNORECASE)
    return plain_english_clinical_text(cleaned)


def indicator_display_title(meta: dict[str, object], indicator_id: str) -> str:
    """Generate display title for indicator, handling QOF and overrides."""
    from app.components.interface_semantics import (
        is_profile_breakdown_indicator,
        profile_breakdown_title_override,
    )

    raw_title = clean_text(meta.get("ui_title")) or clean_text(meta.get("title")) or str(indicator_id)
    if str(indicator_id).startswith("qof_"):
        raw_title = qof_display_title(meta, raw_title)
    title_source = (
        _DISPLAY_TITLE_OVERRIDES.get(str(indicator_id))
        or (profile_breakdown_title_override(meta) if is_profile_breakdown_indicator(meta) else "")
        or raw_title
    )
    title = plain_english_indicator_label(title_source)
    if title and title[0].islower():
        title = title[0].upper() + title[1:]
    return title


# ── Breakdown / profile helpers ──


def breakdown_groups_from_meta(meta: dict[str, object]) -> list[dict[str, object]]:
    """Parse breakdown groups JSON from metadata."""
    raw_value = meta.get("breakdown_groups_json")
    if isinstance(raw_value, list):
        return [item for item in raw_value if isinstance(item, dict)]
    text = clean_text(raw_value)
    if not text:
        return []
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(text)
        except Exception:
            continue
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
    return []


def profile_primary_slice_label(meta: dict[str, object]) -> str:
    """Get label of primary breakdown group from metadata."""
    groups = breakdown_groups_from_meta(meta)
    if not groups:
        return ""
    numerator_fields = normalised_field_set(meta.get("numerator_fields"))
    if numerator_fields:
        for group in groups:
            group_fields = normalised_field_set(group.get("fields"))
            if group_fields and numerator_fields == group_fields:
                return clean_text(group.get("label"))
        for group in groups:
            group_fields = normalised_field_set(group.get("fields"))
            if group_fields and numerator_fields.issubset(group_fields):
                return clean_text(group.get("label"))
    return clean_text(groups[0].get("label"))


def denominator_population_phrase(meta: dict[str, object]) -> str:
    """Derive population phrase (residents, households, etc.) from metadata."""
    denominator_text = clean_text(meta.get("denominator_field")).lower()
    if "aged 16 years and over" in denominator_text or "aged 16+" in denominator_text:
        return "residents aged 16+"
    if "household" in denominator_text:
        return "households"
    if "usual residents" in denominator_text or "total residents" in denominator_text:
        return "residents"
    return "people"


def active_profile_slice_label(meta: dict[str, object], selected_view: str) -> str:
    """Get label of active profile slice for selected view."""
    if not clean_text(selected_view):
        return ""
    if clean_text(meta.get("unit")).lower() != "share":
        return ""
    if selected_view in STRUCTURE_LED_VIEWS:
        return ""
    return profile_primary_slice_label(meta)


def indicator_active_title(meta: dict[str, object], indicator_id: str, selected_view: str) -> str:
    """Generate title including profile breakdown slice if applicable."""
    base_title = indicator_display_title(meta, indicator_id)
    slice_label = active_profile_slice_label(meta, selected_view)
    if not slice_label:
        return base_title
    return f"{base_title}: {slice_label}"


def indicator_active_slice_caption(meta: dict[str, object], selected_view: str) -> str:
    """Generate caption explaining active profile breakdown slice."""
    slice_label = active_profile_slice_label(meta, selected_view)
    if not slice_label:
        return ""
    return f"Currently showing the share of {denominator_population_phrase(meta)} in: {slice_label}."


def indicator_subject_phrase(
    meta: dict[str, object],
    indicator_id: str,
    title: str,
    *,
    strip_breakdown_words: bool = False,
) -> str:
    """Extract subject noun phrase from indicator title/metadata."""
    indicator_key = str(indicator_id)
    if indicator_key in _DESCRIPTION_SUBJECT_OVERRIDES:
        return _DESCRIPTION_SUBJECT_OVERRIDES[indicator_key]
    subject = sentence_case_phrase(plain_english_indicator_label(title))
    if strip_breakdown_words:
        subject = re.sub(r"^(share of|proportion of|percentage of|rate of)\s+", "", subject, flags=re.IGNORECASE)
    return subject


# ── View helpers ──


def unique_views(values: list[str]) -> list[str]:
    """Remove duplicates and 'none' from a list of view names."""
    ordered: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item or item == "none" or item in ordered:
            continue
        ordered.append(item)
    return ordered


def row_available_views(row: pd.Series | dict[str, object]) -> list[str]:
    """Extract all available views from a catalog row."""
    compact_views = clean_text(row.get("view_toggle_options_compact"))
    full_views = clean_text(row.get("view_toggle_options_full"))
    raw_views = [
        clean_text(row.get("default_view")),
        clean_text(row.get("primary_visualisation")),
        clean_text(row.get("secondary_visualisation")),
    ]
    raw_views.extend([item.strip() for item in compact_views.split("|") if item.strip()])
    raw_views.extend([item.strip() for item in full_views.split("|") if item.strip()])
    return unique_views(raw_views)
