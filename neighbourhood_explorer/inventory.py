from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from neighbourhood_explorer.paths import DATA_FOR_APP_DIR


def _infer_census_geography(file_name: str) -> tuple[str, str]:
    geography_key = file_name.split("-")[-1].replace(".csv", "")
    geography_key = geography_key.rstrip(".")
    geography_lookup = {
        "ctry": ("Country", "2021"),
        "rgn": ("Region", "2021"),
        "utla": ("Upper Tier Local Authority", "2021"),
        "ulta": ("Upper Tier Local Authority", "2021"),
        "ltla": ("Lower Tier Local Authority", "2021"),
        "llta": ("Lower Tier Local Authority", "2021"),
        "lsoa": ("LSOA", "2021"),
        "msoa": ("MSOA", "2021"),
        "oa": ("OA", "2021"),
    }
    return geography_lookup.get(geography_key, (geography_key.upper(), "unknown"))


def _classify_numeric_measures(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    numeric_cols = [col for col in df.columns if pd.api.types.is_numeric_dtype(df[col])]
    category_cols = [col for col in numeric_cols if col not in {"date"}]
    return numeric_cols, category_cols


def inspect_source_file(path: Path) -> dict[str, Any]:
    rel = path.relative_to(DATA_FOR_APP_DIR).as_posix()
    row: dict[str, Any] = {
        "file_path": rel,
        "file_name": path.name,
        "source_name": "",
        "topic": "",
        "file_type": path.suffix.lower().lstrip("."),
        "geography_level": "",
        "geography_version": "",
        "time_period": "",
        "key_columns": "",
        "numeric_columns": "",
        "possible_numerator_columns": "",
        "possible_denominator_columns": "",
        "aggregation_class": "",
        "notes": "",
        "row_count_estimate": pd.NA,
        "is_lsoa_compatible": False,
    }

    if path.name == ".DS_Store":
        row["source_name"] = "Ignored system file"
        row["notes"] = "macOS Finder metadata"
        return row

    if "Census" in rel and path.suffix.lower() == ".txt":
        row["source_name"] = "ONS Census 2021 metadata"
        row["topic"] = path.parent.parent.name.upper()
        row["geography_level"] = "Metadata"
        row["geography_version"] = "2021"
        row["time_period"] = "2021"
        row["notes"] = "ONS metadata text file supplied alongside the Census table extracts."
        return row

    if "Census" in rel and path.suffix.lower() == ".csv":
        row["source_name"] = "ONS Census 2021"
        geography_level, geography_version = _infer_census_geography(path.name)
        row["geography_level"] = geography_level
        row["geography_version"] = geography_version
        row["time_period"] = "2021"
        row["is_lsoa_compatible"] = geography_level == "LSOA"
        if path.stat().st_size == 0:
            row["topic"] = path.parent.name.upper()
            row["notes"] = "Empty CSV file."
            return row
        sample = pd.read_csv(path, nrows=5)
        numeric_cols, category_cols = _classify_numeric_measures(sample)
        row["topic"] = category_cols[0].split(":")[0] if category_cols else path.parent.name.upper()
        row["key_columns"] = ", ".join(col for col in sample.columns if "geography" in str(col).lower() or col == "date")
        row["numeric_columns"] = ", ".join(numeric_cols)
        totals = [col for col in category_cols if "total" in str(col).lower()]
        row["possible_denominator_columns"] = ", ".join(totals[:3])
        row["possible_numerator_columns"] = ", ".join([col for col in category_cols if col not in totals][:3])
        row["aggregation_class"] = "additive_category_counts"
        row["notes"] = "Category counts suitable for neighbourhood aggregation via summed numerators/denominators."
        return row

    if path.name == "File_7_IoD2025_All_Ranks_Scores_Deciles_Population_Denominators.csv":
        sample = pd.read_csv(path, nrows=5)
        numeric_cols, _ = _classify_numeric_measures(sample)
        row.update(
            {
                "source_name": "Indices of Deprivation 2025",
                "topic": "Deprivation",
                "geography_level": "LSOA",
                "geography_version": "2021",
                "time_period": "2025 release; denominators mid-2022",
                "key_columns": "LSOA code (2021), Local Authority District code (2024)",
                "numeric_columns": ", ".join(numeric_cols),
                "possible_denominator_columns": ", ".join(
                    [
                        "Total population: mid 2022",
                        "Dependent Children aged 0-15: mid 2022",
                        "Older population aged 60 and over: mid 2022",
                        "Working age population 18-66 (for use with Employment Deprivation Domain): mid 2022",
                    ]
                ),
                "possible_numerator_columns": "Derived from rate columns when applicable",
                "aggregation_class": "mixed_scores_rates_ranks",
                "notes": "Scores and rate fields can be weighted; ranks/deciles are non-additive display-only.",
                "is_lsoa_compatible": True,
            }
        )
        return row

    if path.suffix.lower() == ".csv" and (rel.startswith("Police/") or "/Police/" in rel):
        sample = pd.read_csv(path, nrows=5)
        row["source_name"] = "data.police.uk"
        row["topic"] = "Safety / Crime"
        row["time_period"] = path.parent.name
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            row["row_count_estimate"] = sum(1 for _ in fh) - 1
        if path.name.endswith("-street.csv"):
            row["geography_level"] = "Crime event with LSOA code"
            row["geography_version"] = "LSOA version not labelled; London rows crosswalk to LSOA 2021 in practice"
            row["key_columns"] = "Crime ID, Month, LSOA code, Crime type"
            row["numeric_columns"] = "Longitude, Latitude"
            row["aggregation_class"] = "event_counts"
            row["is_lsoa_compatible"] = True
            row["notes"] = "Use LSOA code and filter to canonical London crosswalk."
        elif path.name.endswith("-outcomes.csv"):
            row["geography_level"] = "Crime outcome event with LSOA code"
            row["geography_version"] = "LSOA version not labelled; London rows crosswalk to LSOA 2021 in practice"
            row["key_columns"] = "Crime ID, Month, LSOA code, Outcome type"
            row["numeric_columns"] = "Longitude, Latitude"
            row["aggregation_class"] = "event_counts"
            row["is_lsoa_compatible"] = True
            row["notes"] = "Can be linked by Crime ID or aggregated separately by LSOA."
        else:
            row["geography_level"] = "Point event"
            row["geography_version"] = "not area-coded"
            row["key_columns"] = "Date, Type, Latitude, Longitude"
            row["numeric_columns"] = "Latitude, Longitude"
            row["aggregation_class"] = "event_counts"
            row["is_lsoa_compatible"] = False
            row["notes"] = "Requires point-in-polygon join to neighbourhood geometry; not used in the first aggregated explorer."
        return row

    row["source_name"] = "Unclassified"
    row["notes"] = "Not included in automated inventory heuristics."
    return row


def build_source_inventory() -> pd.DataFrame:
    rows = [inspect_source_file(path) for path in sorted(DATA_FOR_APP_DIR.rglob("*")) if path.is_file()]
    return pd.DataFrame(rows)
