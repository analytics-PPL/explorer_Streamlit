from __future__ import annotations

import math
import re
from datetime import date

import pandas as pd

from neighbourhood_explorer.footprints import selection_label as footprint_selection_label


_WHITESPACE_RE = re.compile(r"\s+")


def clean_text(text: object) -> str:
    if text is None:
        return ""
    value = str(text).strip()
    if not value:
        return ""
    return _WHITESPACE_RE.sub(" ", value)


def pluralise(count: int, singular: str, plural: str | None = None) -> str:
    word = singular if count == 1 else (plural or f"{singular}s")
    return f"{count} {word}"


def truncate_text(text: object, max_chars: int) -> str:
    value = clean_text(text)
    if len(value) <= max_chars:
        return value
    clipped = value[: max_chars - 1].rsplit(" ", 1)[0].strip()
    return (clipped or value[: max_chars - 1]).rstrip(",;:") + "..."


def first_sentence(text: object, max_chars: int = 120) -> str:
    value = clean_text(text)
    if not value:
        return ""
    for separator in [". ", "; ", ": "]:
        if separator in value:
            value = value.split(separator, 1)[0]
            break
    return truncate_text(value.rstrip(".") + ".", max_chars)


def dynamic_title_size(text: object, *, base: int = 24, floor: int = 18) -> int:
    length = len(clean_text(text))
    if length <= 48:
        return base
    if length <= 72:
        return max(base - 2, floor)
    if length <= 96:
        return max(base - 4, floor)
    return floor


def shorten_display_title(title: object, module_name: object = "", source_name: object = "", *, max_chars: int = 110) -> str:
    value = clean_text(title)
    module = clean_text(module_name)
    source = clean_text(source_name)
    if module:
        for prefix in [f"{module}: ", f"{module} - ", f"{module} | "]:
            if value.lower().startswith(prefix.lower()):
                value = value[len(prefix):].strip()
                break
    replacements = {
        "Proportion of ": "Share of ",
        "Percentage of ": "Share of ",
        " per 1,000 residents": " per 1,000",
        " annual review with control and action plan": " annual review and action plan",
        " objective tests recorded around ": " objective tests around ",
        " quality-assured ": " QA ",
    }
    for source_text, target_text in replacements.items():
        value = re.sub(re.escape(source_text), target_text, value, flags=re.IGNORECASE)
    if source and value.lower().startswith(source.lower()):
        value = value[len(source):].lstrip(" :-|")
    return truncate_text(value, max_chars)


def format_indicator_value(value: float | int | None, unit: str | None) -> str:
    if value is None or pd.isna(value):
        return "No data"
    if unit == "count":
        return f"{int(round(float(value))):,}"
    if unit == "share":
        return f"{float(value) * 100:.1f}%"
    if unit == "rate_per_1000":
        return f"{float(value) * 1000:.1f} per 1,000"
    if unit == "density_per_sq_km":
        return f"{float(value):.2f} per sq km"
    if unit == "score":
        return f"{float(value):.2f}"
    if unit == "decile":
        return f"{float(value):.1f}"
    return f"{float(value):.2f}"


def scale_for_chart(value: float | int | None, unit: str | None) -> float | None:
    if value is None or pd.isna(value):
        return None
    raw = float(value)
    if unit == "share":
        return raw * 100.0
    if unit == "rate_per_1000":
        return raw * 1000.0
    return raw


def chart_number_format(unit: str | None) -> str:
    if unit == "count":
        return "#,##0"
    if unit in {"share", "rate_per_1000", "density_per_sq_km"}:
        return "0.0"
    if unit == "decile":
        return "0.0"
    return "0.00"


def friendly_period(period: object) -> str:
    value = clean_text(period)
    if not value:
        return "Latest"
    try:
        if re.fullmatch(r"\d{4}-\d{2}", value):
            return pd.to_datetime(value).strftime("%b %Y")
    except Exception:
        return value
    return value


def short_aggregation_label(method: object) -> str:
    mapping = {
        "sum_counts": "Counts summed across contributing LSOAs.",
        "recompute_share_from_category_counts": "Share recomputed from summed counts.",
        "recompute_rate_from_numerator_denominator": "Rate recomputed from summed numerator and denominator.",
        "weighted_mean": "Weighted average across contributing areas.",
        "population_weighted_mean": "Population-weighted mean across contributing LSOAs.",
        "area_weighted_mean": "Area-weighted mean across contributing areas.",
        "non_additive_display_only": "Display-only neighbourhood summary.",
    }
    return mapping.get(clean_text(method), "Aggregated using the configured neighbourhood method.")


def short_caveat(meta: dict[str, object]) -> str:
    caveat = first_sentence(meta.get("caveats"), max_chars=120)
    if caveat:
        return caveat
    use_mode = clean_text(meta.get("neighbourhood_use_mode"))
    if use_mode == "neighbourhood_estimate_with_caveats":
        return "Use as a descriptive neighbourhood summary rather than a precise additive statistic."
    return "Public data shown using the app's current benchmark settings."


def short_source_label(meta: dict[str, object], period: object) -> str:
    source = clean_text(meta.get("source_name")) or "Public data"
    geography = clean_text(meta.get("source_geography"))
    if geography:
        return f"{source} | {friendly_period(period)} | {geography}"
    return f"{source} | {friendly_period(period)}"


def full_footer_method_note(meta: dict[str, object]) -> str:
    method = short_aggregation_label(meta.get("aggregation_method"))
    caveat = short_caveat(meta)
    return clean_text(f"{method} {caveat}")


def footer_method_note(meta: dict[str, object]) -> str:
    return truncate_text(full_footer_method_note(meta), 170)


def compress_note_text(text: object, *, max_chars: int = 220) -> str:
    value = clean_text(text)
    if not value:
        return ""
    parts = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", value) if segment.strip()]
    deduped: list[str] = []
    seen: set[str] = set()
    for part in parts:
        normalised = re.sub(r"\W+", "", part).lower()
        if normalised in seen:
            continue
        seen.add(normalised)
        deduped.append(part)
    value = " ".join(deduped)
    value = re.sub(r"\b(selected footprint is|this slide focuses on)\b", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value).strip(" ,;:")
    if not value:
        return ""
    return truncate_text(value, max_chars)


def merge_narrative_text(primary: object, secondary: object, *, max_chars: int = 320) -> str:
    primary_text = compress_note_text(primary, max_chars=max_chars)
    secondary_text = compress_note_text(secondary, max_chars=max_chars)
    if not primary_text:
        return secondary_text
    if not secondary_text:
        return primary_text
    if primary_text.lower() in secondary_text.lower():
        return secondary_text
    if secondary_text.lower() in primary_text.lower():
        return primary_text
    return truncate_text(f"{primary_text} {secondary_text}", max_chars)


def selection_label(selected_ids: list[str]) -> str:
    return footprint_selection_label(selected_ids)


def selection_scope_summary(selected_meta: pd.DataFrame) -> str:
    neighbourhood_count = int(selected_meta["neighbourhood_id"].nunique()) if not selected_meta.empty else 0
    borough_count = _borough_count(selected_meta)
    icb_count = int(selected_meta["icb_code"].dropna().astype(str).nunique()) if "icb_code" in selected_meta.columns else 0
    parts = [pluralise(neighbourhood_count, "neighbourhood")]
    if borough_count:
        parts.append(pluralise(borough_count, "borough"))
    if icb_count:
        parts.append(pluralise(icb_count, "system"))
    return " across ".join([parts[0], ", ".join(parts[1:])]) if len(parts) > 1 else parts[0]


def neighbourhood_name_summary(selected_meta: pd.DataFrame, *, max_items: int = 6) -> str:
    names = selected_meta["neighbourhood_name"].dropna().astype(str).tolist() if not selected_meta.empty else []
    if len(names) <= max_items:
        return ", ".join(names)
    shown = ", ".join(names[:max_items])
    remaining = len(names) - max_items
    return f"{shown}, and {remaining} more"


def neighbourhood_bullet_rows(selected_meta: pd.DataFrame, *, max_rows: int = 8) -> list[str]:
    if selected_meta.empty:
        return []
    rows = [
        f"{row.neighbourhood_name} ({row.borough_name})"
        for row in selected_meta.sort_values(["borough_name", "neighbourhood_name"]).head(max_rows).itertuples(index=False)
    ]
    extra = int(selected_meta["neighbourhood_id"].nunique()) - len(rows)
    if extra > 0:
        rows.append(f"... plus {extra} more neighbourhoods")
    return rows


def contents_examples(titles: list[str], *, max_examples: int = 3) -> str:
    if not titles:
        return "No indicators selected."
    short = [truncate_text(title, 42) for title in titles[:max_examples]]
    if len(titles) > max_examples:
        short.append(f"+{len(titles) - max_examples} more")
    return " | ".join(short)


def comparison_summary_text(
    selection_value: float | int | None,
    benchmark_rows: pd.DataFrame,
    unit: str | None,
    *,
    has_borough_range: bool = False,
) -> str:
    if selection_value is None or pd.isna(selection_value):
        return "No comparison values are available for this indicator."
    notes: list[str] = []
    borough_rows = benchmark_rows[benchmark_rows["kind"] == "borough"] if not benchmark_rows.empty and "kind" in benchmark_rows.columns else pd.DataFrame()
    london_rows = benchmark_rows[benchmark_rows["kind"] == "london"] if not benchmark_rows.empty and "kind" in benchmark_rows.columns else pd.DataFrame()
    if len(borough_rows) == 1:
        borough_value = borough_rows.iloc[0]["value"]
        borough_name = clean_text(borough_rows.iloc[0]["label"])
        direction = compare_direction(selection_value, borough_value)
        notes.append(f"{direction} {borough_name} ({format_indicator_value(borough_value, unit)})")
    elif has_borough_range and not borough_rows.empty:
        notes.append(
            f"within the selected borough range ({format_indicator_value(borough_rows['value'].min(), unit)} to {format_indicator_value(borough_rows['value'].max(), unit)})"
        )
    if not london_rows.empty:
        london_value = london_rows.iloc[0]["value"]
        notes.append(f"{compare_direction(selection_value, london_value)} London ({format_indicator_value(london_value, unit)})")
    if not notes:
        return "This slide focuses on the selected footprint without additional benchmark context."
    prefix = "Selected footprint is " if len(notes) == 1 else "Selected footprint is "
    return prefix + " and ".join(notes) + "."


def compare_direction(left: float | int | None, right: float | int | None) -> str:
    if left is None or right is None or pd.isna(left) or pd.isna(right):
        return "in line with"
    if math.isclose(float(left), float(right), rel_tol=1e-9, abs_tol=1e-9):
        return "in line with"
    return "above" if float(left) > float(right) else "below"


def percentile_note(distribution: pd.DataFrame, value: float | int | None) -> str:
    if value is None or pd.isna(value) or distribution.empty:
        return "No London-wide neighbourhood distribution is available for this indicator."
    values = pd.to_numeric(distribution["value"], errors="coerce").dropna()
    if values.empty:
        return "No London-wide neighbourhood distribution is available for this indicator."
    lower_share = (values < float(value)).mean()
    percentile = int(round(lower_share * 100))
    return f"The selected footprint is higher than roughly {percentile}% of London neighbourhood values in this dataset."


def recent_change_note(series: pd.DataFrame, unit: str | None) -> str:
    if series.empty or "series" not in series.columns:
        return "No recent trend summary is available."
    if "series_kind" in series.columns:
        selected = series[series["series_kind"].astype(str) == "selection"].copy()
    else:
        selected = series[series["series"] == selection_label([])].copy()
    if len(selected) < 2:
        return "No recent trend summary is available."
    selected = selected.reset_index(drop=True)
    latest = float(selected.iloc[-1]["value"])
    prior_index = max(0, len(selected) - 13)
    prior = float(selected.iloc[prior_index]["value"])
    direction = "higher" if latest > prior else "lower" if latest < prior else "similar to"
    return (
        f"Latest month is {direction} {friendly_period(selected.iloc[prior_index]['period'])} "
        f"({format_indicator_value(prior, unit)})."
    )


def report_date_label() -> str:
    return date.today().strftime("%d %b %Y")


def _borough_count(selected_meta: pd.DataFrame) -> int:
    if selected_meta.empty or "borough_name" not in selected_meta.columns:
        return 0
    boroughs: set[str] = set()
    for raw in selected_meta["borough_name"].dropna().astype(str):
        boroughs.update(item.strip() for item in raw.split(";") if item.strip())
    return len(boroughs)
