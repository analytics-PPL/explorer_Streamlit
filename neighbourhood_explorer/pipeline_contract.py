from __future__ import annotations

from functools import lru_cache
import hashlib
import json
import re
from pathlib import Path

import pandas as pd

from neighbourhood_explorer.config import load_source_hierarchy_config, load_sources_config
from neighbourhood_explorer.paths import (
    LSOA_INDICATOR_VALUES_PATH,
    NEIGHBOURHOOD_INDICATOR_VALUES_PATH,
    ROOT_DIR,
)


TIME_METADATA_COLUMNS = [
    "earliest_available_period",
    "latest_available_period",
    "update_frequency",
    "time_series_status",
    "time_series_complete",
    "time_series_completeness_flag",
    "available_period_count",
    "processed_period_count",
    "version_selected",
]


def _coalesce_contract_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if frame.empty:
        return frame
    adjusted = frame.copy()
    for column in columns:
        candidates = [
            candidate
            for candidate in [column, f"{column}_x", f"{column}_y"]
            if candidate in adjusted.columns
        ]
        if not candidates:
            continue
        combined = adjusted[candidates].bfill(axis=1).iloc[:, 0]
        adjusted[column] = combined
        drop_candidates = [candidate for candidate in candidates if candidate != column]
        if drop_candidates:
            adjusted = adjusted.drop(columns=drop_candidates)
    return adjusted


def _parse_listish(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, list):
            return [str(item).strip() for item in loaded if str(item).strip()]
    if "; " in text:
        return [item.strip() for item in text.split("; ") if item.strip()]
    if "|" in text:
        return [item.strip() for item in text.split("|") if item.strip()]
    return [text]


def _field_list(indicator: dict[str, object], singular_key: str, plural_key: str) -> list[str]:
    values = _parse_listish(indicator.get(plural_key))
    if values:
        return values
    return _parse_listish(indicator.get(singular_key))


def _canonical_field_name(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"\s*;\s*measures:\s*value\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text.casefold()


def _normalise_title(value: object) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def _table_code_from_source_key(source_key: object) -> str:
    text = str(source_key or "").strip()
    match = re.search(r"(ts\d+[a-z]?)", text, flags=re.IGNORECASE)
    return match.group(1).lower() if match else ""


def _breakdown_field_list(indicator: dict[str, object]) -> list[str]:
    raw = indicator.get("breakdown_groups_json")
    if raw is None:
        return []
    try:
        loaded = raw if isinstance(raw, list) else json.loads(str(raw))
    except json.JSONDecodeError:
        return []
    if not isinstance(loaded, list):
        return []
    fields: list[str] = []
    for item in loaded:
        if not isinstance(item, dict):
            continue
        for field in item.get("fields", []) or []:
            candidate = str(field).strip()
            if candidate:
                fields.append(candidate)
    return fields


def _source_field_signature(indicator: dict[str, object]) -> str:
    fields = (
        _field_list(indicator, "numerator_field", "numerator_fields")
        + _field_list(indicator, "denominator_field", "denominator_fields")
        + _field_list(indicator, "value_field", "value_fields")
        + _breakdown_field_list(indicator)
    )
    canonical_fields = sorted({field for field in (_canonical_field_name(value) for value in fields) if field})
    return "|".join(canonical_fields)


def infer_metric_domain(indicator: dict[str, object]) -> str:
    source_name = str(indicator.get("source_name") or "").strip()
    topic = str(indicator.get("topic") or indicator.get("top_level_category") or "").strip().lower()

    if source_name == "Nomis API" or source_name == "ONS Census 2021":
        return "demographics_census"
    if source_name == "NHS England Patients Registered at a GP Practice":
        return "gp_registrations"
    if source_name == "NHS England Quality and Outcomes Framework":
        return "primary_care_qof"
    if source_name == "data.police.uk street-level crime":
        return "crime"
    if source_name == "Indices of Deprivation 2025":
        return "deprivation"
    if source_name == "London Datastore CKAN API":
        return "housing_market"
    if source_name in {"NaPTAN / NPTG API", "TfL Unified API"}:
        return "transport_access"
    if source_name == "Department for Transport Road Traffic Statistics API":
        return "road_traffic"
    if source_name == "Environment Agency Flood Monitoring API":
        return "environment_flood"
    if "fingertips" in source_name.lower():
        return "public_health_benchmark"
    if "population" in topic or "demographic" in topic:
        return "demographics_census"
    return "other"


def _domain_rule(domain_key: str) -> dict[str, object]:
    hierarchy = load_source_hierarchy_config().get("domains", {})
    return dict(hierarchy.get(domain_key, hierarchy.get("other", {})))


def _matching_nomis_census_source_key(source_key: str) -> str:
    table_code = _table_code_from_source_key(source_key)
    if not table_code:
        return ""
    candidate = f"nomis_c2021{table_code}_api"
    return candidate if candidate in load_sources_config().get("sources", {}) else ""


def _candidate_source_keys(indicator: dict[str, object]) -> list[str]:
    configured_source_key = str(indicator.get("configured_source_key") or indicator.get("source_key") or "").strip()
    candidates: list[str] = []
    if configured_source_key:
        candidates.append(configured_source_key)
    nomis_candidate = _matching_nomis_census_source_key(configured_source_key)
    if nomis_candidate and nomis_candidate not in candidates:
        candidates.append(nomis_candidate)
    resolved_source_key = str(indicator.get("resolved_source_key") or indicator.get("source_key") or "").strip()
    if resolved_source_key and resolved_source_key not in candidates:
        candidates.append(resolved_source_key)
    return candidates


def resolve_indicator_definition(indicator: dict[str, object]) -> dict[str, object]:
    resolved = dict(indicator)
    sources_cfg = load_sources_config().get("sources", {})

    configured_source_key = str(indicator.get("configured_source_key") or indicator.get("source_key") or "").strip()
    configured_source_name = str(indicator.get("configured_source_name") or indicator.get("source_name") or "").strip()
    configured_source_path = str(
        indicator.get("configured_source_file_or_api") or indicator.get("source_file_or_api") or ""
    ).strip()

    resolved["configured_source_key"] = configured_source_key
    resolved["configured_source_name"] = configured_source_name
    resolved["configured_source_file_or_api"] = configured_source_path

    resolved_source_key = configured_source_key
    resolved_source_name = configured_source_name
    resolved_source_path = configured_source_path
    resolution_reason = "Configured source retained."

    nomis_candidate = _matching_nomis_census_source_key(configured_source_key)
    if configured_source_name == "ONS Census 2021" and nomis_candidate:
        candidate_cfg = sources_cfg[nomis_candidate]
        resolved_source_key = nomis_candidate
        resolved_source_name = str(candidate_cfg.get("source_name") or configured_source_name)
        resolved_source_path = str(candidate_cfg.get("path") or configured_source_path)
        resolution_reason = (
            f"Equivalent Nomis API table {nomis_candidate} is available; prefer Nomis for the production Census ingestion path."
        )

    resolved["source_key"] = resolved_source_key
    resolved["source_name"] = resolved_source_name
    if resolved_source_path:
        resolved["source_file_or_api"] = resolved_source_path
    resolved["resolved_source_key"] = resolved_source_key
    resolved["resolved_source_name"] = resolved_source_name
    resolved["resolved_source_file_or_api"] = resolved_source_path
    resolved["source_resolution_reason"] = resolution_reason
    resolved["source_dataset"] = resolved_source_key or configured_source_key
    resolved["resolved_source_changed"] = bool(
        resolved_source_key and configured_source_key and resolved_source_key != configured_source_key
    )

    metric_domain = infer_metric_domain(resolved)
    domain_rule = _domain_rule(metric_domain)
    resolved["metric_domain"] = metric_domain
    resolved["source_priority"] = "primary"
    resolved["fallback_source"] = str(domain_rule.get("fallback_source") or "").strip()
    resolved["benchmark_source"] = str(domain_rule.get("benchmark_source") or "").strip()
    resolved["deprecated_sources"] = "|".join(_parse_listish(domain_rule.get("deprecated_sources")))
    resolved["last_updated"] = str(resolved.get("last_refresh_date") or "").strip()

    signature = _source_field_signature(resolved)
    signature_seed = "||".join(
        [
            infer_metric_domain(resolved),
            _table_code_from_source_key(resolved_source_key) or _normalise_title(resolved.get("title")),
            str(resolved.get("unit") or resolved.get("unit_type") or "").strip().lower(),
            str(resolved.get("aggregation_method") or resolved.get("aggregation_policy") or "").strip().lower(),
            signature,
        ]
    )
    resolved["duplicate_group_id"] = f"dup_{hashlib.sha1(signature_seed.encode('utf-8')).hexdigest()[:12]}"
    resolved["source_field_signature"] = signature
    resolved["duplicate_candidate_sources"] = "|".join(_candidate_source_keys(resolved))
    return resolved


def apply_pipeline_contract(catalog_df: pd.DataFrame) -> pd.DataFrame:
    if catalog_df.empty:
        return catalog_df

    base_catalog = _coalesce_contract_columns(catalog_df, TIME_METADATA_COLUMNS)
    rows = [resolve_indicator_definition(row) for row in base_catalog.to_dict(orient="records")]
    adjusted = pd.DataFrame(rows)
    if adjusted.empty:
        return adjusted

    grouped = adjusted.groupby("duplicate_group_id")["indicator_id"].agg(list).to_dict()
    for index, row in adjusted.iterrows():
        duplicate_indicator_ids = [
            value for value in grouped.get(str(row.get("duplicate_group_id") or ""), [])
            if str(value) != str(row.get("indicator_id") or "")
        ]
        adjusted.at[index, "duplicate_candidates"] = "|".join(duplicate_indicator_ids)

    time_metadata = build_time_series_metadata(adjusted)
    merge_columns = ["indicator_id", *TIME_METADATA_COLUMNS]
    drop_candidates = [
        column_name
        for column_name in adjusted.columns
        if column_name in TIME_METADATA_COLUMNS or any(column_name == f"{base}_x" or column_name == f"{base}_y" for base in TIME_METADATA_COLUMNS)
    ]
    if drop_candidates:
        adjusted = adjusted.drop(columns=drop_candidates)
    adjusted = adjusted.merge(time_metadata[merge_columns], on="indicator_id", how="left")
    return _coalesce_contract_columns(adjusted, TIME_METADATA_COLUMNS)


def _period_sort_key(value: object) -> tuple[int, object]:
    text = str(value).strip()
    if not text:
        return (99, text)
    if re.fullmatch(r"\d{4}-\d{2}", text):
        year, month = text.split("-")
        return (0, int(year), int(month))
    if re.fullmatch(r"\d{4}-Q[1-4]", text):
        year, quarter = text.split("-Q")
        return (1, int(year), int(quarter))
    if re.fullmatch(r"\d{4}/\d{2}", text):
        return (2, int(text[:4]), int(text[-2:]))
    if re.fullmatch(r"\d{4}", text):
        return (3, int(text))
    parsed = pd.to_datetime(text, errors="coerce")
    if not pd.isna(parsed):
        return (4, parsed.toordinal())
    return (98, text)


def _sort_period_values(values: list[object]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()}, key=_period_sort_key)


@lru_cache(maxsize=None)
def _source_periods(source_key: str, configured_period: str) -> tuple[str, ...]:
    sources_cfg = load_sources_config().get("sources", {})
    source_cfg = sources_cfg.get(str(source_key), {})
    source_type = str(source_cfg.get("source_type") or "").strip()
    source_path = ROOT_DIR / str(source_cfg.get("path") or "")

    if source_type == "police_street_monthly" and source_path.exists() and source_path.is_dir():
        values = [path.name for path in source_path.iterdir() if path.is_dir()]
        return tuple(_sort_period_values(values))

    if not source_path.exists() or source_path.is_dir():
        return tuple(_sort_period_values([configured_period]))

    if source_path.suffix.lower() != ".csv":
        return tuple(_sort_period_values([configured_period]))

    try:
        header = pd.read_csv(source_path, nrows=0)
    except (OSError, pd.errors.ParserError, ValueError):
        return tuple(_sort_period_values([configured_period]))

    period_column = next(
        (
            column
            for column in ["period", "date", "Month", "month"]
            if column in header.columns
        ),
        "",
    )
    if not period_column:
        return tuple(_sort_period_values([configured_period]))

    try:
        periods = pd.read_csv(source_path, usecols=[period_column])[period_column].dropna().astype(str).tolist()
    except (OSError, pd.errors.ParserError, ValueError):
        return tuple(_sort_period_values([configured_period]))
    ordered = _sort_period_values(periods)
    if ordered:
        return tuple(ordered)
    return tuple(_sort_period_values([configured_period]))


@lru_cache(maxsize=1)
def _load_processed_periods() -> tuple[pd.DataFrame, pd.DataFrame]:
    lsoa = pd.read_parquet(LSOA_INDICATOR_VALUES_PATH) if LSOA_INDICATOR_VALUES_PATH.exists() else pd.DataFrame()
    neighbourhood = (
        pd.read_parquet(NEIGHBOURHOOD_INDICATOR_VALUES_PATH)
        if NEIGHBOURHOOD_INDICATOR_VALUES_PATH.exists()
        else pd.DataFrame()
    )
    return lsoa, neighbourhood


def _infer_update_frequency(periods: list[str], configured_period: object) -> str:
    configured = str(configured_period or "").strip().lower()
    if "quarter" in configured:
        return "quarterly"
    if "month" in configured:
        return "monthly"
    if "annual" in configured or re.fullmatch(r"\d{4}", str(configured_period or "").strip()):
        return "annual"
    if len(periods) <= 1:
        return "snapshot"
    if periods and all(re.fullmatch(r"\d{4}-\d{2}", value) for value in periods):
        return "monthly"
    if periods and all(re.fullmatch(r"\d{4}-Q[1-4]", value) for value in periods):
        return "quarterly"
    if periods and all(re.fullmatch(r"\d{4}", value) for value in periods):
        return "annual"
    return configured or "unknown"


def build_time_series_metadata(catalog_df: pd.DataFrame) -> pd.DataFrame:
    if catalog_df.empty:
        return pd.DataFrame(
            columns=[
                "indicator_id",
                *TIME_METADATA_COLUMNS,
            ]
        )

    lsoa_values, _ = _load_processed_periods()
    processed_lookup: dict[str, list[str]] = {}
    if not lsoa_values.empty:
        processed_lookup = {
            str(indicator_id): _sort_period_values(group["period"].dropna().astype(str).tolist())
            for indicator_id, group in lsoa_values.groupby("indicator_id", dropna=False)
        }

    rows: list[dict[str, object]] = []
    for indicator in catalog_df.to_dict(orient="records"):
        indicator_id = str(indicator.get("indicator_id") or "").strip()
        source_key = str(indicator.get("source_key") or "").strip()
        source_period = str(indicator.get("source_period") or "").strip()
        available_periods = list(_source_periods(source_key, source_period))
        processed_periods = processed_lookup.get(indicator_id, [])
        update_frequency = _infer_update_frequency(available_periods, source_period)

        if len(available_periods) <= 1:
            status = "snapshot_only"
        elif not processed_periods:
            status = "partial"
        elif processed_periods == available_periods:
            status = "full"
        elif set(processed_periods).issubset(set(available_periods)):
            source_first = available_periods[0]
            source_last = available_periods[-1]
            processed_first = processed_periods[0]
            processed_last = processed_periods[-1]
            status = "truncated" if processed_first != source_first or processed_last != source_last else "partial"
        else:
            status = "partial"

        time_series_complete = status in {"full", "snapshot_only"}
        rows.append(
            {
                "indicator_id": indicator_id,
                "earliest_available_period": available_periods[0] if available_periods else source_period,
                "latest_available_period": available_periods[-1] if available_periods else source_period,
                "update_frequency": update_frequency,
                "time_series_status": status,
                "time_series_complete": bool(time_series_complete),
                "time_series_completeness_flag": "complete" if time_series_complete else status,
                "available_period_count": int(len(available_periods)),
                "processed_period_count": int(len(processed_periods)),
                "version_selected": available_periods[-1] if available_periods else source_period,
            }
        )

    return pd.DataFrame(rows)


def build_pipeline_indicator_mapping(catalog_df: pd.DataFrame) -> pd.DataFrame:
    contracted = apply_pipeline_contract(catalog_df)
    rows: list[dict[str, object]] = []
    for indicator in contracted.to_dict(orient="records"):
        source_fields = _field_list(indicator, "numerator_field", "numerator_fields")
        source_fields += _field_list(indicator, "denominator_field", "denominator_fields")
        source_fields += _field_list(indicator, "value_field", "value_fields")
        source_fields += _breakdown_field_list(indicator)
        dependencies = []
        denominator_values = _field_list(indicator, "denominator_field", "denominator_fields")
        for dependency in denominator_values:
            if dependency == "population_total":
                dependencies.append("population_total")
        transformation_steps = " -> ".join(
            [
                f"fetch:{indicator.get('source_key') or indicator.get('configured_source_key') or 'manual'}",
                "etl/standardise_sources.py",
                "etl/aggregate_to_neighbourhoods.py",
                "etl/build_benchmarks.py",
                "etl/build_indicator_catalog.py",
            ]
        )
        rows.append(
            {
                "indicator_id": indicator.get("indicator_id"),
                "indicator_name": indicator.get("title") or indicator.get("ui_title"),
                "source_name": indicator.get("source_name"),
                "source_dataset": indicator.get("source_dataset"),
                "source_fields": " | ".join(sorted(dict.fromkeys(source_fields))),
                "geography_level": indicator.get("source_geography") or indicator.get("geography_level"),
                "time_coverage": (
                    f"{indicator.get('earliest_available_period')} to {indicator.get('latest_available_period')}"
                    if indicator.get("available_period_count", 0) not in {0, 1}
                    else indicator.get("latest_available_period") or indicator.get("source_period")
                ),
                "latest_period_available": indicator.get("latest_available_period") or indicator.get("source_period"),
                "transformation_steps": transformation_steps,
                "aggregation_method": indicator.get("aggregation_method") or indicator.get("aggregation_policy"),
                "dependencies": " | ".join(sorted(dict.fromkeys(dependencies))),
                "duplicate_candidates": indicator.get("duplicate_candidate_sources") or indicator.get("duplicate_candidates") or "",
                "version_conflicts": "",
                "time_series_status": indicator.get("time_series_status"),
                "source_priority": indicator.get("source_priority"),
                "duplicate_group_id": indicator.get("duplicate_group_id"),
                "version_selected": indicator.get("version_selected"),
                "time_series_complete": indicator.get("time_series_complete"),
                "neighbourhood_use_mode": indicator.get("neighbourhood_use_mode"),
                "caveats": indicator.get("caveats"),
                "last_updated": indicator.get("last_updated"),
                "configured_source_name": indicator.get("configured_source_name"),
                "configured_source_key": indicator.get("configured_source_key"),
                "resolved_source_name": indicator.get("resolved_source_name"),
                "resolved_source_key": indicator.get("resolved_source_key"),
                "source_resolution_reason": indicator.get("source_resolution_reason"),
            }
        )
    return pd.DataFrame(rows).sort_values(["source_name", "indicator_name", "indicator_id"]).reset_index(drop=True)


def build_pipeline_source_conflicts(catalog_df: pd.DataFrame) -> pd.DataFrame:
    contracted = apply_pipeline_contract(catalog_df)
    rows: list[dict[str, object]] = []
    seen_keys: set[tuple[str, str, str]] = set()

    for indicator in contracted.to_dict(orient="records"):
        configured_source_key = str(indicator.get("configured_source_key") or "").strip()
        resolved_source_key = str(indicator.get("resolved_source_key") or "").strip()
        if not configured_source_key or configured_source_key == resolved_source_key:
            continue
        key = (str(indicator.get("indicator_id") or ""), configured_source_key, resolved_source_key)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        rows.append(
            {
                "indicator_id": indicator.get("indicator_id"),
                "indicator_name": indicator.get("title") or indicator.get("ui_title"),
                "configured_source": indicator.get("configured_source_name"),
                "configured_source_key": configured_source_key,
                "resolved_primary_source": indicator.get("resolved_source_name"),
                "resolved_source_key": resolved_source_key,
                "relationship_class": "exact duplicate",
                "resolution": "keep primary source",
                "reasoning": indicator.get("source_resolution_reason"),
                "version_conflicts": "",
                "time_coverage_difference": "",
                "duplicate_group_id": indicator.get("duplicate_group_id"),
            }
        )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(["indicator_name", "indicator_id"]).reset_index(drop=True)


def build_source_hierarchy_frame() -> pd.DataFrame:
    hierarchy = load_source_hierarchy_config().get("domains", {})
    rows = []
    for domain_key, values in hierarchy.items():
        rows.append(
            {
                "metric_domain": domain_key,
                "primary_source": values.get("primary_source", ""),
                "fallback_source": values.get("fallback_source", ""),
                "benchmark_source": values.get("benchmark_source", ""),
                "deprecated_sources": " | ".join(_parse_listish(values.get("deprecated_sources"))),
                "notes": values.get("notes", ""),
            }
        )
    return pd.DataFrame(rows).sort_values("metric_domain").reset_index(drop=True)


def run_pipeline_validation(catalog_df: pd.DataFrame) -> pd.DataFrame:
    contracted = apply_pipeline_contract(catalog_df)
    issues: list[dict[str, object]] = []

    duplicate_indicator_ids = contracted["indicator_id"][contracted["indicator_id"].astype(str).duplicated(keep=False)]
    for indicator_id in sorted(set(duplicate_indicator_ids.astype(str).tolist())):
        issues.append({"check": "duplicate_indicator_id", "severity": "error", "detail": indicator_id})

    for row in contracted.to_dict(orient="records"):
        indicator_id = str(row.get("indicator_id") or "")
        if not str(row.get("source_key") or "").strip():
            issues.append({"check": "missing_source_key", "severity": "error", "detail": indicator_id})
        if str(row.get("unit") or "").strip() in {"share", "rate_per_1000"}:
            denominator_fields = _field_list(row, "denominator_field", "denominator_fields")
            if not denominator_fields:
                issues.append({"check": "missing_denominator", "severity": "error", "detail": indicator_id})
        if not bool(row.get("time_series_complete", True)) and str(row.get("time_series_status")) == "truncated":
            issues.append({"check": "truncated_time_series", "severity": "warning", "detail": indicator_id})

    return pd.DataFrame(issues)
