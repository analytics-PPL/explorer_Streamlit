from __future__ import annotations

from html import escape
import re
import textwrap

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.components.colors import NHS_BLUE, PURPLE
from app.components.formatting import axis_label_for_unit, format_indicator_value, format_period_label, scale_value_for_display
from app.components.interface_semantics import (
    compare_values,
    detect_low_variance,
    format_comparison_narrative,
    should_use_horizontal_bars,
)
from app.components.layout import render_empty_state


PLOTLY_FONT_FAMILY = 'Inter, "Poppins", sans-serif'
PLOTLY_TEXT_COLOR = "#1a1f36"
PLOTLY_MUTED_TEXT_COLOR = "#4e5d78"
PLOTLY_GRID_COLOR = "rgba(100, 116, 139, 0.08)"
PLOTLY_ZERO_LINE_COLOR = "rgba(26, 31, 54, 0.18)"
TREND_RANGE_WINDOWS = (
    ("3 years", 3),
    ("5 years", 5),
    ("10 years", 10),
)
NUMERIC_AXIS_PADDING_RATIO = 0.12
NUMERIC_AXIS_HEADROOM_RATIO = 0.18
NUMERIC_AXIS_MIN_SPAN_RATIO = 0.04
NUMERIC_AXIS_MIN_SPAN_ABSOLUTE = 0.02
MAX_INLINE_SELECTION_COMPARISON_ROWS = 12


def _display_series_label(label: object, series_kind: object = "") -> str:
    clean_label = str(label or "").strip()
    if str(series_kind or "").strip() == "london" or clean_label == "London":
        return "London overall"
    return clean_label


def _comparison_chart_frame(
    selection_label: str,
    selection_value: float | int | None,
    london_df: pd.DataFrame,
    borough_df: pd.DataFrame,
    detail_df: pd.DataFrame | None = None,
    selection_kind: str | None = None,
    selection_exact_boundary: bool = False,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    inline_selected_rows = pd.DataFrame()
    if (
        isinstance(detail_df, pd.DataFrame)
        and not detail_df.empty
        and str(selection_kind or "").strip() == "neighbourhood"
        and not bool(selection_exact_boundary)
    ):
        detail = detail_df.copy()
        if "neighbourhood_id" in detail.columns:
            detail = detail.drop_duplicates(subset=["neighbourhood_id"], keep="first")
        label_column = "neighbourhood_name" if "neighbourhood_name" in detail.columns else ""
        if label_column:
            detail = detail[detail[label_column].astype(str).fillna("").str.strip().ne("")].copy()
        if 1 < len(detail) <= MAX_INLINE_SELECTION_COMPARISON_ROWS and "value" in detail.columns:
            inline_selected_rows = detail

    if not inline_selected_rows.empty:
        label_column = "neighbourhood_name" if "neighbourhood_name" in inline_selected_rows.columns else "neighbourhood_id"
        for row in inline_selected_rows.itertuples(index=False):
            rows.append(
                {
                    "label": str(getattr(row, label_column)),
                    "value": getattr(row, "value", None),
                    "series": "selection",
                }
            )
    else:
        rows.append({"label": selection_label, "value": selection_value, "series": "selection"})
    if not borough_df.empty:
        for row in borough_df.itertuples(index=False):
            rows.append({"label": str(row.benchmark_name), "value": row.value, "series": "borough"})
    if not london_df.empty:
        rows.append({"label": _display_series_label("London", "london"), "value": london_df.iloc[0]["value"], "series": "london"})
    return pd.DataFrame(rows)


def default_plotly_layout(**overrides) -> dict[str, object]:
    layout: dict[str, object] = {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": dict(family=PLOTLY_FONT_FAMILY, color=PLOTLY_TEXT_COLOR, size=13),
        "margin": dict(l=16, r=16, t=12, b=16),
        "hoverlabel": dict(
            bgcolor="white",
            bordercolor="#e2e8f0",
            font=dict(family=PLOTLY_FONT_FAMILY, size=13, color=PLOTLY_TEXT_COLOR),
        ),
    }
    layout.update(overrides)
    return layout


def default_plotly_axis(
    *,
    showgrid: bool,
    title: str | None = None,
    tickfont_size: int = 12,
    tickfont_color: str = PLOTLY_MUTED_TEXT_COLOR,
    **overrides,
) -> dict[str, object]:
    axis: dict[str, object] = {
        "showgrid": showgrid,
        "title": title,
        "tickfont": dict(
            family=PLOTLY_FONT_FAMILY,
            size=tickfont_size,
            color=tickfont_color,
        ),
    }
    if showgrid:
        axis["gridcolor"] = PLOTLY_GRID_COLOR
        axis["gridwidth"] = 0.5
    axis.update(overrides)
    return axis


def comfortable_numeric_axis_range(
    values: pd.Series | list[object],
    *,
    anchor_zero: bool = False,
) -> list[float] | None:
    numeric = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    if numeric.empty:
        return None

    min_value = float(numeric.min())
    max_value = float(numeric.max())
    span = max_value - min_value
    magnitude = max(abs(min_value), abs(max_value), 1.0)
    effective_span = max(span, magnitude * NUMERIC_AXIS_MIN_SPAN_RATIO, NUMERIC_AXIS_MIN_SPAN_ABSOLUTE)
    padding = effective_span * NUMERIC_AXIS_PADDING_RATIO
    headroom = effective_span * NUMERIC_AXIS_HEADROOM_RATIO

    if anchor_zero:
        if min_value >= 0:
            lower = 0.0
            upper = max_value + headroom
        elif max_value <= 0:
            lower = min_value - headroom
            upper = 0.0
        else:
            lower = min_value - padding
            upper = max_value + headroom
    else:
        lower = min_value - padding
        upper = max_value + headroom

    if lower == upper:
        lower -= NUMERIC_AXIS_MIN_SPAN_ABSOLUTE
        upper += NUMERIC_AXIS_MIN_SPAN_ABSOLUTE
    return [float(lower), float(upper)]


def default_numeric_y_axis(
    values: pd.Series | list[object],
    *,
    title: str | None = None,
    showgrid: bool = True,
    anchor_zero: bool = False,
    tickfont_size: int = 12,
    tickfont_color: str = PLOTLY_MUTED_TEXT_COLOR,
    **overrides,
) -> dict[str, object]:
    axis = default_plotly_axis(
        showgrid=showgrid,
        title=title,
        tickfont_size=tickfont_size,
        tickfont_color=tickfont_color,
        **overrides,
    )
    if "range" not in axis and "autorange" not in axis:
        axis_range = comfortable_numeric_axis_range(values, anchor_zero=anchor_zero)
        if axis_range is not None:
            axis["range"] = axis_range
    axis.pop("rangemode", None)
    return axis


def bar_marker_style(
    color: object,
    *,
    line_color: str = "rgba(255,255,255,0.85)",
    line_width: float = 1.1,
    opacity: float = 1.0,
) -> dict[str, object]:
    return {
        "color": color,
        "opacity": opacity,
        "line": dict(color=line_color, width=line_width),
        "cornerradius": 4,
    }


def scatter_marker_style(
    color: object,
    *,
    size: object = 7,
    opacity: float = 0.95,
) -> dict[str, object]:
    return {
        "color": color,
        "size": size,
        "opacity": opacity,
        "line": dict(color="#ffffff", width=1.5),
    }


def _plotly_chart(fig: go.Figure, *, chart_key: str | None = None) -> None:
    st.plotly_chart(
        fig,
        width="stretch",
        key=chart_key,
        config={
            "displayModeBar": False,
            "responsive": True,
            "displaylogo": False,
            "scrollZoom": False,
        },
    )


def _ordered_unique_periods(frame: pd.DataFrame) -> list[str]:
    if frame.empty or "period" not in frame.columns:
        return []
    return list(dict.fromkeys(frame["period"].dropna().astype(str).tolist()))


def infer_timeseries_granularity(
    periods: list[str] | pd.Series,
    *,
    period_type_hint: str | None = None,
) -> str:
    values = [str(value).strip() for value in periods if str(value).strip()]
    if not values:
        return "unknown"

    hint = str(period_type_hint or "").strip().lower()
    if hint == "monthly":
        return "monthly"
    if hint == "quarterly":
        return "quarterly"
    if hint in {"annual", "yearly"}:
        return "annual"

    if all(re.fullmatch(r"\d{4}-\d{2}", value) for value in values):
        return "monthly"
    if all(re.fullmatch(r"\d{4}-Q[1-4]", value) for value in values):
        return "quarterly"
    if all(re.fullmatch(r"\d{4}/\d{2}", value) for value in values):
        return "annual"
    if all(re.fullmatch(r"\d{4}", value) for value in values):
        return "annual"

    parsed = pd.to_datetime(pd.Series(values), errors="coerce")
    if parsed.notna().all():
        unique_months = parsed.dt.to_period("M").nunique()
        if unique_months == len(values) and len(values) > 1:
            return "monthly"
        return "annual"
    return "unknown"


def trend_range_options(
    frame: pd.DataFrame,
    *,
    period_type_hint: str | None = None,
) -> list[str]:
    periods = _ordered_unique_periods(frame)
    if len(periods) <= 1:
        return []

    periods_per_year = {
        "monthly": 12,
        "quarterly": 4,
        "annual": 1,
    }.get(infer_timeseries_granularity(periods, period_type_hint=period_type_hint))
    if periods_per_year is None:
        return ["Max"]

    options = [
        label
        for label, years in TREND_RANGE_WINDOWS
        if len(periods) > years * periods_per_year
    ]
    options.append("Max")
    return options


def filter_timeseries_to_range(
    frame: pd.DataFrame,
    range_label: str,
    *,
    period_type_hint: str | None = None,
) -> pd.DataFrame:
    if frame.empty:
        return frame
    selected_label = str(range_label or "Max").strip() or "Max"
    if selected_label == "Max":
        return frame.copy()

    years_match = re.fullmatch(r"(\d+)\s+years?", selected_label)
    if not years_match:
        return frame.copy()
    years = int(years_match.group(1))
    periods = _ordered_unique_periods(frame)
    periods_per_year = {
        "monthly": 12,
        "quarterly": 4,
        "annual": 1,
    }.get(infer_timeseries_granularity(periods, period_type_hint=period_type_hint))
    if periods_per_year is None:
        return frame.copy()

    keep_periods = set(periods[-years * periods_per_year :])
    if not keep_periods:
        return frame.copy()
    return frame[frame["period"].astype(str).isin(keep_periods)].copy()


def comparison_narrative(
    selection_label: str,
    selection_value: float | int | None,
    london_df: pd.DataFrame,
    borough_df: pd.DataFrame,
    unit: str | None,
    *,
    selection_is_plural: bool = False,
) -> str:
    return format_comparison_narrative(
        {
            "selection_label": selection_label,
            "selection_is_plural": selection_is_plural,
            "selection_value": selection_value,
            "unit": unit,
            "borough_df": borough_df,
            "london_df": london_df,
            "displayed_values": [
                selection_value,
                *(
                    pd.to_numeric(borough_df["value"], errors="coerce").dropna().tolist()
                    if isinstance(borough_df, pd.DataFrame) and "value" in borough_df.columns
                    else []
                ),
                *(
                    pd.to_numeric(london_df["value"], errors="coerce").dropna().tolist()
                    if isinstance(london_df, pd.DataFrame) and "value" in london_df.columns
                    else []
                ),
            ],
        }
    )


def render_metric_cards(cards: list[dict[str, object]]) -> None:
    if not cards:
        return
    cols = st.columns(len(cards))
    for col, card in zip(cols, cards, strict=False):
        with col:
            delta_text = str(card.get("delta", "") or "").strip()
            delta_markup = f"<div class='app-metric-delta'>{escape(delta_text)}</div>" if delta_text else ""
            st.markdown(
                (
                    "<div class='app-metric-card'>"
                    f"<div class='app-metric-label'>{escape(str(card.get('label', '')))}</div>"
                    f"<div class='app-metric-value'>{escape(str(card.get('value', '')))}</div>"
                    f"{delta_markup}"
                    f"<div class='app-metric-caption'>{escape(str(card.get('caption', '') or ''))}</div>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )


def render_comparison_chart(
    selection_label: str,
    selection_value: float | int | None,
    london_df: pd.DataFrame,
    borough_df: pd.DataFrame,
    unit: str | None = None,
    *,
    detail_df: pd.DataFrame | None = None,
    selection_kind: str | None = None,
    selection_exact_boundary: bool = False,
    chart_key: str | None = None,
) -> None:
    frame = _comparison_chart_frame(
        selection_label,
        selection_value,
        london_df,
        borough_df,
        detail_df=detail_df,
        selection_kind=selection_kind,
        selection_exact_boundary=selection_exact_boundary,
    )
    frame = frame[pd.to_numeric(frame["value"], errors="coerce").notna()].copy()
    if frame.empty:
        render_empty_state("No comparison data are available for this indicator.")
        return
    frame["formatted_value"] = frame["value"].apply(lambda value: format_indicator_value(value, unit))
    frame["display_value"] = frame["value"].apply(lambda value: scale_value_for_display(value, unit))
    palette = {
        "selection": PURPLE,
        "borough": NHS_BLUE,
        "london": "#41b6e6",
    }
    frame["marker_color"] = frame["series"].map(palette).fillna("#768692")
    comparison_count = len(frame)

    if detect_low_variance(frame["value"], unit):
        comparison_sentences: list[str] = []
        if not borough_df.empty and not london_df.empty:
            comparison_sentences.append("Values are effectively the same across the selected boroughs and London.")
        elif not london_df.empty:
            direction = compare_values(selection_value, london_df.iloc[0]["value"], unit)
            if direction == "same":
                comparison_sentences.append(f"{selection_label} is broadly in line with London overall.")
        elif not borough_df.empty:
            comparison_sentences.append("There is no meaningful variation across the relevant borough benchmarks.")
        if comparison_sentences:
            st.info(" ".join(comparison_sentences))
        st.dataframe(
            frame[["label", "formatted_value"]].rename(
                columns={"label": "Comparison unit", "formatted_value": "Value"}
            ),
            hide_index=True,
            width="stretch",
        )
        return

    if comparison_count >= 5 or should_use_horizontal_bars(frame["label"].tolist(), max_chars=14, item_threshold=4):
        chart = frame.sort_values(["display_value", "label"], ascending=[True, True]).reset_index(drop=True)
        chart["wrapped_label"] = chart["label"].map(lambda value: _wrap_axis_label(value, width=24))
        fig = go.Figure(
            data=[
                go.Bar(
                    x=chart["display_value"],
                    y=chart["wrapped_label"],
                    orientation="h",
                    marker=bar_marker_style(chart["marker_color"], line_width=1.2),
                    text=chart["formatted_value"],
                    customdata=chart["formatted_value"],
                    textposition="outside",
                    cliponaxis=False,
                    hovertemplate="%{y}<br>%{customdata}<extra></extra>",
                )
            ]
        )
        fig.update_layout(**default_plotly_layout(
            height=max(340, 140 + 56 * comparison_count),
            margin=dict(l=24, r=20, t=8, b=28),
            xaxis_title=axis_label_for_unit(unit),
            yaxis_title=None,
            showlegend=False,
            bargap=0.22,
        ))
        fig.update_yaxes(**default_plotly_axis(showgrid=False, tickfont_color=PLOTLY_TEXT_COLOR, tickfont_size=12))
        fig.update_xaxes(
            **default_numeric_y_axis(
                chart["display_value"],
                title=axis_label_for_unit(unit),
                anchor_zero=True,
                zeroline=True,
                zerolinecolor=PLOTLY_ZERO_LINE_COLOR,
            )
        )
    else:
        chart = frame.sort_values(["display_value", "label"], ascending=[True, True]).reset_index(drop=True)
        fig = go.Figure()
        for row in chart.itertuples(index=False):
            fig.add_shape(
                type="line",
                x0=0,
                x1=row.display_value,
                y0=row.label,
                y1=row.label,
                line=dict(color="rgba(79, 98, 120, 0.22)", width=3),
            )
        fig.add_trace(
            go.Scatter(
                y=chart["label"],
                x=chart["display_value"],
                mode="markers+text",
                marker=scatter_marker_style(chart["marker_color"], size=15, opacity=1.0),
                text=chart["formatted_value"],
                customdata=chart["formatted_value"],
                textposition="middle right",
                hovertemplate="%{y}<br>%{customdata}<extra></extra>",
                showlegend=False,
            )
        )
        fig.update_layout(**default_plotly_layout(
            height=max(280, 110 + 54 * len(frame)),
            margin=dict(l=20, r=72, t=8, b=20),
            yaxis_title=None,
            xaxis_title=axis_label_for_unit(unit),
            showlegend=False,
        ))
        fig.update_yaxes(**default_plotly_axis(showgrid=False, tickfont_size=13, tickfont_color=PLOTLY_TEXT_COLOR))
        fig.update_xaxes(
            **default_plotly_axis(
                showgrid=True,
                title=axis_label_for_unit(unit),
                zeroline=True,
                zerolinecolor=PLOTLY_ZERO_LINE_COLOR,
            )
        )
    _plotly_chart(fig, chart_key=chart_key)


def _wrap_axis_label(label: str, width: int = 16) -> str:
    text = str(label).strip()
    if not text:
        return ""
    return "<br>".join(textwrap.wrap(text, width=width)) or text


def render_ranked_distribution_chart(
    frame: pd.DataFrame,
    selected_ids: list[str] | set[str],
    unit: str | None,
    *,
    chart_key: str | None = None,
    rank_label: str = "Neighbourhood rank",
) -> None:
    if frame.empty:
        render_empty_state("No ranked distribution is available for this indicator.")
        return
    ranked = frame.copy()
    ranked["selected"] = ranked["neighbourhood_id"].astype(str).isin({str(value) for value in selected_ids})
    ranked["rank_order"] = range(1, len(ranked) + 1)
    ranked["marker_color"] = ranked["selected"].map({True: "#005eb8", False: "#c8bfd6"})
    ranked["marker_size"] = ranked["selected"].map({True: 10, False: 6})
    ranked["formatted_value"] = ranked["value"].apply(lambda value: format_indicator_value(value, unit))
    ranked["display_value"] = ranked["value"].apply(lambda value: scale_value_for_display(value, unit))

    fig = go.Figure(
        data=[
            go.Scatter(
                x=ranked["rank_order"],
                y=ranked["display_value"],
                mode="markers",
                marker=scatter_marker_style(ranked["marker_color"], size=ranked["marker_size"], opacity=0.92),
                text=ranked["neighbourhood_name"],
                customdata=ranked["formatted_value"],
                hovertemplate="%{text}<br>%{customdata}<extra></extra>",
            )
        ]
    )
    selected_rows = ranked[ranked["selected"]].copy().reset_index(drop=True)
    annotated_rows = selected_rows.head(4)
    for index, row in annotated_rows.iterrows():
        fig.add_annotation(
            x=row["rank_order"],
            y=row["display_value"],
            text=f"{row['neighbourhood_name']}<br>{row['formatted_value']}",
            showarrow=True,
            arrowhead=0,
            arrowcolor="#005eb8",
            arrowwidth=1.4,
            ax=34 if index % 2 == 0 else -34,
            ay=-42 if index % 2 == 0 else 42,
            bgcolor="rgba(255,255,255,0.96)",
            bordercolor="#005eb8",
            borderwidth=1,
            font=dict(family=PLOTLY_FONT_FAMILY, size=11, color=PLOTLY_TEXT_COLOR),
            align="left",
        )
    if len(selected_rows) > len(annotated_rows):
        st.caption(f"{len(selected_rows) - len(annotated_rows)} additional selected areas are highlighted without direct labels to keep the chart readable.")
    fig.update_layout(**default_plotly_layout(
        height=max(420, 320 + 24 * len(selected_rows)),
        margin=dict(l=20, r=72, t=18, b=32),
        xaxis_title=rank_label,
        yaxis_title=axis_label_for_unit(unit),
    ))
    fig.update_xaxes(**default_plotly_axis(showgrid=False))
    fig.update_yaxes(**default_numeric_y_axis(ranked["display_value"], title=axis_label_for_unit(unit)))
    _plotly_chart(fig, chart_key=chart_key)


def render_timeseries_chart(
    frame: pd.DataFrame,
    unit: str | None,
    *,
    rolling_average: bool = False,
    max_periods: int | None = None,
    period_type_hint: str | None = None,
    chart_key: str | None = None,
) -> None:
    if frame.empty:
        render_empty_state("No time series are available for this indicator.")
        return
    chart = frame.copy()
    chart["period_dt"] = pd.to_datetime(chart["period"], errors="coerce")
    chart = chart.sort_values(["period_dt", "series", "period"]).reset_index(drop=True)
    if max_periods:
        period_order = [value for value in chart["period"].drop_duplicates().tolist()]
        if len(period_order) > max_periods:
            allowed = set(period_order[-max_periods:])
            chart = chart[chart["period"].isin(allowed)].copy()
    chart["display_period"] = chart["period"].map(format_period_label)
    chart["formatted_value"] = chart["value"].apply(lambda value: format_indicator_value(value, unit))
    chart["display_value"] = chart["value"].apply(lambda value: scale_value_for_display(value, unit))
    granularity = infer_timeseries_granularity(chart["period"].astype(str).tolist(), period_type_hint=period_type_hint)
    rolling_label = "3-month average" if granularity == "monthly" else "3-quarter average" if granularity == "quarterly" else "3-period average"
    palette = {
        "selection": PURPLE,
        "london": NHS_BLUE,
        "borough": "#9aa8b6",
    }
    series_order = list(dict.fromkeys(chart["series"].astype(str).tolist()))
    prominent_series = []
    if any(chart["series_kind"].astype(str) == "selection"):
        prominent_series.extend(chart.loc[chart["series_kind"].astype(str) == "selection", "series"].astype(str).drop_duplicates().tolist())
    if any(chart["series_kind"].astype(str) == "london"):
        prominent_series.extend(chart.loc[chart["series_kind"].astype(str) == "london", "series"].astype(str).drop_duplicates().tolist())
    prominent_series = list(
        dict.fromkeys(
            _display_series_label(series_name, "london" if str(series_name) in {"London", "London overall"} else "")
            for series_name in prominent_series
        )
    )
    end_values = (
        chart.sort_values(["series", "period_dt", "period"])
        .groupby("series", dropna=False)["display_value"]
        .last()
        .to_dict()
    )
    prominent_end_values = [float(end_values.get(series, 0.0)) for series in prominent_series if series in end_values]
    use_direct_end_labels = len(prominent_end_values) <= 1 or not detect_low_variance(prominent_end_values, unit)
    fig = go.Figure()
    for series_name, subset in chart.groupby("series", sort=False):
        subset = subset.copy().reset_index(drop=True)
        raw_series_label = str(series_name)
        series_kind = str(subset["series_kind"].iloc[0]) if "series_kind" in subset.columns else ""
        series_label = _display_series_label(raw_series_label, series_kind)
        is_selection_series = (
            series_kind == "selection"
            or raw_series_label not in {"London", "London overall", "Average place", "Average neighbourhood"}
            and "borough" not in raw_series_label.lower()
        )
        is_borough_series = (
            series_kind == "borough"
            or "borough" in raw_series_label.lower()
            or "average place" in raw_series_label.lower()
            or "average neighbourhood" in raw_series_label.lower()
        )
        is_prominent = series_label in prominent_series or is_selection_series
        if is_selection_series:
            color = palette["selection"]
        elif series_kind == "london" or raw_series_label in {"London", "London overall"}:
            color = palette["london"]
        elif is_borough_series:
            color = palette["borough"]
        else:
            color = "#7b8794"
        label_text = [""] * len(subset)
        if label_text and use_direct_end_labels and (is_selection_series or series_kind == "london"):
            label_text[-1] = series_label
        if is_selection_series:
            fig.add_trace(
                go.Scatter(
                    x=subset["display_period"],
                    y=subset["display_value"],
                    mode="lines",
                    fill="tozeroy",
                    fillcolor="rgba(83, 35, 128, 0.06)",
                    line=dict(width=0),
                    hoverinfo="skip",
                    showlegend=False,
                )
            )
        fig.add_trace(
            go.Scatter(
                x=subset["display_period"],
                y=subset["display_value"],
                mode="lines+markers+text" if is_prominent else "lines",
                name=series_label,
                line=dict(
                    color=color,
                    width=3 if is_selection_series else 2.2 if series_kind == "london" else 1.2,
                    dash="solid" if is_prominent else "dot",
                ),
                marker=scatter_marker_style(color, size=7 if is_selection_series else 6 if series_kind == "london" else 0, opacity=1.0 if is_prominent else 0.55),
                text=label_text,
                textposition="middle right",
                customdata=subset["formatted_value"],
                hovertemplate=f"{series_label}<br>%{{x}}<br>%{{customdata}}<extra></extra>",
                showlegend=not use_direct_end_labels and (is_prominent or not is_borough_series),
                opacity=1.0 if is_prominent else 0.5,
            )
        )
        if rolling_average and is_selection_series and len(subset) >= 3:
            rolling = subset.copy()
            rolling["rolling_value"] = rolling["display_value"].rolling(window=3, min_periods=3).mean()
            fig.add_trace(
                go.Scatter(
                    x=rolling["display_period"],
                    y=rolling["rolling_value"],
                    mode="lines",
                    name=f"{series_label} ({rolling_label})",
                    line=dict(color="#6b3a9e", width=2, dash="dash"),
                    hovertemplate=f"{series_label} ({rolling_label})<br>%{{x}}<br>%{{y:.1f}}<extra></extra>",
                    showlegend=False,
                )
            )
    fig.update_layout(**default_plotly_layout(
        height=340,
        margin=dict(l=20, r=120 if use_direct_end_labels else 20, t=10, b=46 if not use_direct_end_labels else 20),
        yaxis_title=axis_label_for_unit(unit),
        xaxis_title=None,
        showlegend=not use_direct_end_labels,
        legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="left", x=0),
    ))
    fig.update_xaxes(**default_plotly_axis(showgrid=False))
    fig.update_yaxes(**default_numeric_y_axis(chart["display_value"], title=axis_label_for_unit(unit)))
    _plotly_chart(fig, chart_key=chart_key)


def render_distribution_band(summary: dict[str, object], unit: str | None, *, chart_key: str | None = None) -> None:
    low = summary.get("summary_min")
    mid = summary.get("summary_median")
    high = summary.get("summary_max")
    if any(pd.isna(value) for value in [low, mid, high]):
        render_empty_state("No distribution band is available for this indicator.")
        return
    low_display = scale_value_for_display(low, unit)
    mid_display = scale_value_for_display(mid, unit)
    high_display = scale_value_for_display(high, unit)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=[low_display, high_display],
            y=["Selected footprint", "Selected footprint"],
            mode="lines",
            line=dict(color="#b8a4d0", width=8),
            hoverinfo="skip",
            showlegend=False,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[mid_display],
            y=["Selected footprint"],
            mode="markers",
            marker=scatter_marker_style("#005eb8", size=14, opacity=1.0),
            text=[format_indicator_value(mid, unit)],
            hovertemplate="Median: %{text}<extra></extra>",
            showlegend=False,
        )
    )
    fig.update_layout(**default_plotly_layout(
        height=180,
        margin=dict(l=20, r=20, t=10, b=20),
        xaxis_title=axis_label_for_unit(unit),
        yaxis_title=None,
    ))
    fig.update_xaxes(**default_plotly_axis(showgrid=True, title=axis_label_for_unit(unit)))
    fig.update_yaxes(**default_plotly_axis(showgrid=False, tickfont_color=PLOTLY_TEXT_COLOR))
    _plotly_chart(fig, chart_key=chart_key)


def render_download_button(df: pd.DataFrame, label: str, filename: str) -> None:
    payload = df.to_csv(index=False).encode("utf-8")
    size_kb = max(1, round(len(payload) / 1024))
    st.download_button(
        f"{label} (CSV, {size_kb} KB)",
        payload,
        file_name=filename,
        mime="text/csv",
    )
