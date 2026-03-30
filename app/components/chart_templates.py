from __future__ import annotations

from itertools import count
import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.components.colors import CATEGORY_PALETTE, NHS_BLUE, PURPLE, PURPLE_MUTED, SUCCESS
from app.components.charts import (
    PLOTLY_FONT_FAMILY,
    PLOTLY_TEXT_COLOR,
    bar_marker_style,
    default_numeric_y_axis,
    default_plotly_axis,
    default_plotly_layout,
    filter_timeseries_to_range,
    format_indicator_value,
    render_comparison_chart,
    render_distribution_band,
    render_metric_cards,
    render_ranked_distribution_chart,
    render_timeseries_chart,
    scatter_marker_style,
    trend_range_options,
)
from app.components.formatting import axis_label_for_unit, scale_value_for_display
from app.components.interface_semantics import (
    build_summary_cards,
    composition_view_prefers_grouped_bar,
    grouped_summary_card,
    is_profile_breakdown_indicator,
    should_use_horizontal_bars,
)
from app.components.layout import render_empty_state
from app.components.maps import render_selection_map
from neighbourhood_explorer.data_access import load_hex_icb_geography, load_map_geography


_CHART_RENDER_COUNTER = count()
def _context_chart_key(context: dict[str, object], suffix: str) -> str:
    indicator_id = str(context.get("indicator_id") or "indicator")
    period = str(context.get("period") or "period")
    current_ids = "_".join(sorted(str(value) for value in context.get("current_ids", [])[:6]))
    if not current_ids:
        current_ids = "none"
    render_instance = next(_CHART_RENDER_COUNTER)
    return f"{indicator_id}_{period}_{suffix}_{current_ids}_{render_instance}"


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


def _trend_range_state_key(context: dict[str, object], suffix: str) -> str:
    indicator_id = str(context.get("indicator_id") or "indicator")
    return f"{indicator_id}_{suffix}_trend_range"


def _selected_trend_frame(
    context: dict[str, object],
    *,
    suffix: str,
) -> tuple[pd.DataFrame, str]:
    frame = context.get("timeseries_df", pd.DataFrame())
    period_type_hint = str(context.get("meta", {}).get("period_type") or "").strip()
    options = trend_range_options(frame, period_type_hint=period_type_hint)
    if not options:
        return frame, "Max"

    default_option = "Max" if "Max" in options else options[-1]
    state_key = _trend_range_state_key(context, suffix)
    current_value = str(st.session_state.get(state_key) or default_option)
    if current_value not in options:
        current_value = default_option
    if len(options) > 1:
        st.markdown("**Time range**")
        selected_option = st.radio(
            "Time range",
            options=options,
            index=options.index(current_value),
            horizontal=True,
            key=state_key,
            label_visibility="collapsed",
        )
    else:
        selected_option = current_value
    return (
        filter_timeseries_to_range(frame, selected_option, period_type_hint=period_type_hint),
        selected_option,
    )


def _benchmark_style(context: dict[str, object]) -> str:
    meta = context.get("meta", {})
    return str(meta.get("benchmark_style") or "").strip()


def _joined_label(values: list[str]) -> str:
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return f"{', '.join(values[:-1])} and {values[-1]}"

def _comparison_card_rows(context: dict[str, object]) -> list[dict[str, object]]:
    selection = context.get("selection")
    if selection is None:
        return []
    unit = selection.get("unit")
    benchmark_style = _benchmark_style(context)
    rows = build_summary_cards(context.get("comparator_context", {}))
    if unit == "count" and benchmark_style == "de_emphasise_totals_show_rate_if_available":
        return rows
    return rows


def render_benchmark_lollipop(context: dict[str, object]) -> None:
    selection = context.get("selection")
    if selection is None:
        render_empty_state("No selected footprint data are available for this indicator.")
        return
    render_comparison_chart(
        str(context.get("selection_label") or "Selected footprint"),
        selection.get("value"),
        context.get("london_benchmark", pd.DataFrame()),
        context.get("borough_benchmarks", pd.DataFrame()),
        selection.get("unit"),
        detail_df=context.get("detail_df", pd.DataFrame()),
        selection_kind=str(context.get("selection_kind") or ""),
        selection_exact_boundary=bool(context.get("selection_exact_boundary", False)),
        chart_key=_context_chart_key(context, "benchmark_lollipop"),
    )


def render_benchmark_only_compare(context: dict[str, object]) -> None:
    render_benchmark_lollipop(context)


def render_lollipop_compare(context: dict[str, object]) -> None:
    render_benchmark_lollipop(context)


def render_trend_line(context: dict[str, object]) -> None:
    frame, _ = _selected_trend_frame(context, suffix="trend_line")
    selection = context.get("selection")
    unit = selection.get("unit") if isinstance(selection, dict) else context.get("unit")
    render_timeseries_chart(
        frame,
        unit,
        rolling_average=False,
        period_type_hint=str(context.get("meta", {}).get("period_type") or "").strip(),
        chart_key=_context_chart_key(context, "trend_line"),
    )


def render_trend_line_with_rolling_average(context: dict[str, object]) -> None:
    frame, _ = _selected_trend_frame(context, suffix="trend_line_with_rolling_average")
    selection = context.get("selection")
    unit = selection.get("unit") if isinstance(selection, dict) else context.get("unit")
    render_timeseries_chart(
        frame,
        unit,
        rolling_average=True,
        period_type_hint=str(context.get("meta", {}).get("period_type") or "").strip(),
        chart_key=_context_chart_key(context, "trend_line_with_rolling_average"),
    )


def render_kpi_card(context: dict[str, object]) -> None:
    rows = _comparison_card_rows(context)
    if not rows:
        render_empty_state("No selected footprint data are available for this indicator.")
        return
    render_metric_cards(rows[:3])


def render_distribution_band_template(context: dict[str, object]) -> None:
    selection = context.get("selection")
    if selection is None:
        render_empty_state("No footprint summary is available for this indicator.")
        return
    render_distribution_band(
        selection,
        selection.get("unit"),
        chart_key=_context_chart_key(context, "distribution_band"),
    )


def _place_distribution_toggle(context: dict[str, object], suffix: str) -> tuple[pd.DataFrame, list[str], bool]:
    """Return (active_frame, active_ids, is_place_view) based on a place/neighbourhood toggle.

    When the selection exactly constitutes one or more complete places (boroughs)
    and a place-level ranked frame is available, this renders a toggle so the
    user can switch between neighbourhood-level and place-level distributions.
    Returns ``is_place_view=False`` when the toggle is not applicable.
    """
    neighbourhood_frame = context.get("ranked_df", pd.DataFrame())
    place_frame = context.get("place_ranked_df", pd.DataFrame())
    selection_kind = str(context.get("selection_kind", ""))
    current_ids = list(context.get("current_ids", []))

    if selection_kind != "place" or place_frame.empty:
        return neighbourhood_frame, current_ids, False

    place_codes = list(context.get("place_selected_codes", set()))
    toggle_key = _context_chart_key(context, f"dist_toggle_{suffix}")
    choice = st.radio(
        "Distribution level",
        options=["By neighbourhood", "By place"],
        horizontal=True,
        key=toggle_key,
        label_visibility="collapsed",
    )
    if choice == "By place":
        return place_frame, place_codes, True
    return neighbourhood_frame, current_ids, False


def render_ranked_distribution(context: dict[str, object]) -> None:
    active_frame, active_ids, is_place_view = _place_distribution_toggle(context, "ranked")
    selection = context.get("selection")
    unit = selection.get("unit") if isinstance(selection, dict) else context.get("unit")
    rank_label = "Place rank" if is_place_view else "Neighbourhood rank"
    render_ranked_distribution_chart(
        active_frame,
        active_ids,
        unit,
        chart_key=_context_chart_key(context, "ranked_distribution"),
        rank_label=rank_label,
    )


def render_ranked_strip(context: dict[str, object]) -> None:
    active_frame, active_ids, is_place_view = _place_distribution_toggle(context, "strip")
    selection = context.get("selection")
    if active_frame.empty or selection is None:
        render_empty_state("No London-wide ranked strip is available for this indicator.")
        return
    active_id_set = {str(v) for v in active_ids}
    strip_label = "London places" if is_place_view else "London neighbourhoods"
    chart = active_frame.copy()
    chart["selected"] = chart["neighbourhood_id"].astype(str).isin(active_id_set)
    chart["display_value"] = chart["value"].map(lambda value: scale_value_for_display(value, selection.get("unit")))
    chart["color"] = chart["selected"].map({True: PURPLE, False: PURPLE_MUTED})
    chart["size"] = chart["selected"].map({True: 11, False: 6})

    fig = go.Figure(
        data=[
            go.Scatter(
                x=chart["display_value"],
                y=[strip_label] * len(chart),
                mode="markers",
                marker=scatter_marker_style(chart["color"], size=chart["size"], opacity=0.88),
                text=chart["neighbourhood_name"],
                customdata=chart["value"].map(lambda value: format_indicator_value(value, selection.get("unit"))),
                hovertemplate="%{text}<br>%{customdata}<extra></extra>",
                showlegend=False,
            )
        ]
    )
    fig.update_layout(**default_plotly_layout(
        height=140,
        margin=dict(l=20, r=20, t=10, b=20),
        xaxis_title=axis_label_for_unit(selection.get("unit")),
        yaxis_title=None,
    ))
    fig.update_yaxes(**default_plotly_axis(showgrid=False, tickfont_color=PLOTLY_TEXT_COLOR))
    fig.update_xaxes(**default_plotly_axis(showgrid=True, title=axis_label_for_unit(selection.get("unit"))))
    _plotly_chart(fig, chart_key=_context_chart_key(context, "ranked_strip"))


def render_sorted_bar(context: dict[str, object]) -> None:
    detail_df = context.get("detail_df", pd.DataFrame())
    selection = context.get("selection")
    unit = selection.get("unit") if isinstance(selection, dict) else context.get("unit")
    if detail_df.empty:
        render_empty_state("No selected footprint values are available for this view.")
        return
    chart = detail_df.copy().sort_values(["value", "neighbourhood_name"], ascending=[False, True]).head(12)
    chart["display_value"] = chart["value"].map(lambda value: scale_value_for_display(value, unit))
    chart["formatted_value"] = chart["value"].map(lambda value: format_indicator_value(value, unit))

    chart["wrapped_label"] = chart["neighbourhood_name"].map(lambda value: value if len(str(value)) <= 24 else f"{str(value)[:24]}…")
    fig = go.Figure(
        data=[
            go.Bar(
                x=chart["display_value"],
                y=chart["wrapped_label"],
                orientation="h",
                marker=bar_marker_style(PURPLE),
                text=chart["formatted_value"],
                textposition="outside",
                cliponaxis=False,
                hovertemplate="%{y}<br>%{text}<extra></extra>",
            )
        ]
    )
    fig.update_layout(**default_plotly_layout(
        height=max(320, 140 + len(chart) * 28),
        margin=dict(l=20, r=20, t=12, b=24),
        xaxis_title=axis_label_for_unit(unit),
        yaxis_title=None,
        showlegend=False,
    ))
    fig.update_yaxes(**default_plotly_axis(showgrid=False, tickfont_size=11, tickfont_color=PLOTLY_TEXT_COLOR))
    fig.update_xaxes(**default_numeric_y_axis(chart["display_value"], title=axis_label_for_unit(unit), anchor_zero=True))
    _plotly_chart(fig, chart_key=_context_chart_key(context, "sorted_bar"))


def render_choropleth_map(context: dict[str, object]) -> None:
    map_values = context.get("map_values", pd.DataFrame())
    if map_values.empty:
        render_empty_state("No map values are available for this indicator.", icon="🗺️")
        return
    map_mode_key = f"indicator_map_mode_{context['indicator_id']}_{context['period']}"
    st.radio("Map style", ["Hex map", "Neighbourhood map"], key=map_mode_key, horizontal=True, label_visibility="collapsed")
    map_mode = str(st.session_state.get(map_mode_key, "Hex map"))
    variant = "hex" if map_mode == "Hex map" else "real"
    render_selection_map(
        load_map_geography("hex" if variant == "hex" else "real"),
        map_values,
        context.get("current_ids", []),
        map_key=f"indicator_map_{context['indicator_id']}_{context['period']}",
        variant=variant,
        overlay_geo_df=load_hex_icb_geography() if variant == "hex" else None,
        height=420,
    )


def _composition_frame(context: dict[str, object]) -> pd.DataFrame:
    frame = context.get("composition_df", pd.DataFrame())
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    chart = frame.copy()
    if "share" in chart.columns:
        chart["share_pct"] = pd.to_numeric(chart["share"], errors="coerce") * 100.0
        chart["formatted_share"] = chart["share"].map(lambda value: format_indicator_value(value, "share"))
        chart["plot_value"] = chart["share_pct"]
        chart["formatted_plot_value"] = chart["formatted_share"]
        chart["axis_title"] = "Share (%)"
        chart["composition_measure"] = "share"
        return chart

    unit = ""
    if "unit" in chart.columns and not chart["unit"].dropna().empty:
        unit = str(chart["unit"].dropna().astype(str).iloc[0]).strip()
    if not unit:
        unit = str(context.get("unit") or "").strip()
    chart["plot_value"] = pd.to_numeric(chart.get("value"), errors="coerce").map(
        lambda value: scale_value_for_display(value, unit) if pd.notna(value) else value
    )
    chart["formatted_plot_value"] = pd.to_numeric(chart.get("value"), errors="coerce").map(
        lambda value: format_indicator_value(value, unit) if pd.notna(value) else ""
    )
    chart["axis_title"] = axis_label_for_unit(unit) or "Value"
    chart["composition_measure"] = "value"
    return chart


def _population_pyramid_subject_options(composition_df: pd.DataFrame) -> tuple[str, list[str]]:
    if composition_df.empty:
        return "", []
    subject_order = list(dict.fromkeys(composition_df.sort_values("subject_order")["subject"].astype(str).tolist()))
    if "subject_kind" in composition_df.columns:
        selection_subject = next(
            (
                str(row.subject)
                for row in composition_df.sort_values("subject_order")[["subject", "subject_kind"]].drop_duplicates().itertuples(index=False)
                if str(row.subject_kind) == "selection"
            ),
            subject_order[0] if subject_order else "",
        )
    else:
        selection_subject = subject_order[0] if subject_order else ""
    comparator_subjects = [subject for subject in subject_order if subject and subject != selection_subject]
    return selection_subject, comparator_subjects


def render_table_support_only(context: dict[str, object]) -> None:
    composition_df = _composition_frame(context)
    if not composition_df.empty:
        display = (
            composition_df.pivot(index="category", columns="subject", values="formatted_plot_value")
            .reset_index()
            .rename(columns={"category": "Category"})
        )
        st.dataframe(display, hide_index=True, width="stretch")
        return

    detail_df = context.get("detail_df", pd.DataFrame())
    if detail_df.empty:
        render_empty_state("No selected footprint values are available for this view.")
        return
    unit = context.get("unit")
    display = detail_df[["neighbourhood_name", "borough_name", "value"]].copy()
    display["value"] = display["value"].map(lambda value: format_indicator_value(value, unit))
    display = display.rename(
        columns={
            "neighbourhood_name": "Neighbourhood",
            "borough_name": "Place",
            "value": "Value",
        }
    )
    st.dataframe(display, hide_index=True, width="stretch")


def render_text_badges_or_indexed_note(context: dict[str, object]) -> None:
    rows = _comparison_card_rows(context)
    if rows:
        render_metric_cards(rows[:3])
    selection = context.get("selection")
    if selection is None:
        return
    ranked_df = context.get("ranked_df", pd.DataFrame())
    if ranked_df.empty:
        st.caption("This view summarises the selected footprint value using simple cards and notes.")
        return
    ranked_df = ranked_df.copy().reset_index(drop=True)
    ranked_df["rank_order"] = range(1, len(ranked_df) + 1)
    match = ranked_df[ranked_df["neighbourhood_id"].astype(str).isin({str(value) for value in context.get("current_ids", [])})]
    if match.empty:
        st.caption("This view summarises the selected footprint value using simple cards and notes.")
        return
    best_rank = int(match["rank_order"].min())
    selection_label = str(context.get("selection_label") or "Selected footprint")
    selection_verb = "sit" if bool(context.get("selection_is_plural")) else "sits"
    st.info(f"{selection_label} {selection_verb} around rank {best_rank} among London neighbourhood values for this indicator.")


def render_crime_mix_chart(context: dict[str, object]) -> None:
    subcategory_catalog = context.get("subcategory_catalog", pd.DataFrame())
    period = context.get("period")
    current_ids = context.get("current_ids", [])
    if subcategory_catalog.empty or len(subcategory_catalog) <= 1:
        render_empty_state("A crime mix view is not available for this indicator yet.")
        return

    rows: list[dict[str, object]] = []
    for row in subcategory_catalog.itertuples(index=False):
        if str(row.indicator_id) == str(context.get("indicator_id")) and "all_crimes" in str(row.indicator_id):
            continue
        bundle = context["comparison_loader"](str(row.indicator_id), str(period), current_ids)
        selection = bundle["selection"]
        if selection is None:
            continue
        rows.append(
            {
                "label": str(row.ui_title),
                "value": scale_value_for_display(selection["value"], selection["unit"]),
                "formatted": format_indicator_value(selection["value"], selection["unit"]),
            }
        )
    if not rows:
        render_empty_state("A crime mix view is not available for this indicator yet.")
        return

    chart = pd.DataFrame(rows).sort_values("value", ascending=False)
    fig = go.Figure(
        data=[
            go.Bar(
                x=chart["value"],
                y=chart["label"].map(lambda value: value if len(str(value)) <= 28 else f"{str(value)[:28]}…"),
                orientation="h",
                marker=bar_marker_style(PURPLE, line_width=1.0),
                text=chart["formatted"],
                textposition="outside",
                cliponaxis=False,
                hovertemplate="%{y}<br>%{text}<extra></extra>",
            )
        ]
    )
    fig.update_layout(**default_plotly_layout(
        height=max(320, 130 + len(chart) * 28),
        margin=dict(l=20, r=20, t=12, b=24),
        yaxis_title=None,
        xaxis_title=axis_label_for_unit(context.get("unit")),
        showlegend=False,
    ))
    fig.update_yaxes(**default_plotly_axis(showgrid=False, tickfont_size=11, tickfont_color=PLOTLY_TEXT_COLOR))
    fig.update_xaxes(**default_numeric_y_axis(chart["value"], title=axis_label_for_unit(context.get("unit")), anchor_zero=True))
    _plotly_chart(fig, chart_key=_context_chart_key(context, "crime_mix_chart"))


def render_domain_tile_matrix(context: dict[str, object]) -> None:
    subcategory_catalog = context.get("subcategory_catalog", pd.DataFrame())
    period = context.get("period")
    current_ids = context.get("current_ids", [])
    comparison_loader = context["comparison_loader"]
    if subcategory_catalog.empty:
        render_empty_state("A grouped summary is not available for this subcategory.")
        return
    cards: list[dict[str, object]] = []
    for row in subcategory_catalog.itertuples(index=False):
        row_dict = row._asdict()
        label = str(row.ui_short_title or row.ui_title)
        if is_profile_breakdown_indicator(row_dict):
            cards.append(grouped_summary_card(row_dict, label=label, selection_value=None, unit=str(row_dict.get("unit") or "")))
            continue
        bundle = comparison_loader(str(row.indicator_id), str(period), current_ids)
        selection = bundle["selection"]
        if selection is None:
            continue
        cards.append(grouped_summary_card(row_dict, label=label, selection_value=selection["value"], unit=selection["unit"]))
    if not cards:
        render_empty_state("A grouped summary is not available for this subcategory.")
        return
    for start in range(0, len(cards), 4):
        render_metric_cards(cards[start : start + 4])


def render_grouped_bar(context: dict[str, object]) -> None:
    composition_df = _composition_frame(context)
    if composition_df.empty:
        render_empty_state("This grouped view needs category breakdown data that is not currently available for this indicator.")
        return

    subject_order = list(dict.fromkeys(composition_df.sort_values("subject_order")["subject"].tolist()))
    category_order = list(dict.fromkeys(composition_df.sort_values("category_order")["category"].tolist()))
    subject_kind_map = {}
    if "subject_kind" in composition_df.columns:
        subject_kind_map = {
            str(row.subject): str(row.subject_kind)
            for row in composition_df[["subject", "subject_kind"]].drop_duplicates().itertuples(index=False)
        }
    fallback_colors = CATEGORY_PALETTE[:6]
    use_horizontal = should_use_horizontal_bars(category_order, max_chars=16, item_threshold=5)
    axis_title = str(composition_df["axis_title"].iloc[0]) if "axis_title" in composition_df.columns and not composition_df.empty else "Value"

    fig = go.Figure()
    for index, subject in enumerate(subject_order):
        subject_df = composition_df[composition_df["subject"] == subject].copy()
        subject_df["category"] = pd.Categorical(subject_df["category"], categories=category_order, ordered=True)
        subject_df = subject_df.sort_values("category")
        subject_kind = subject_kind_map.get(str(subject), "")
        if subject_kind == "selection":
            color = PURPLE
        elif subject_kind == "london":
            color = "#005eb8"
        else:
            color = fallback_colors[index % len(fallback_colors)]
        fig.add_trace(
            go.Bar(
                x=subject_df["plot_value"] if use_horizontal else subject_df["category"],
                y=subject_df["category"] if use_horizontal else subject_df["plot_value"],
                orientation="h" if use_horizontal else "v",
                name=subject,
                marker=bar_marker_style(color, line_width=1.0),
                text=subject_df["formatted_plot_value"],
                textposition="outside",
                cliponaxis=False,
                hovertemplate=("%{y}<br>%{fullData.name}: %{text}<extra></extra>" if use_horizontal else "%{x}<br>%{fullData.name}: %{text}<extra></extra>"),
            )
        )

    legend_rows = max(1, math.ceil(len(subject_order) / 5))
    layout = default_plotly_layout(
        barmode="group",
        height=max(360, 150 + len(category_order) * (34 if use_horizontal else 0)),
        margin=dict(l=20, r=20, t=12, b=72 + legend_rows * 22),
        xaxis_title=axis_title if use_horizontal else None,
        yaxis_title=None if use_horizontal else axis_title,
        legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="left", x=0),
    )
    fig.update_layout(**layout)
    if use_horizontal:
        fig.update_yaxes(**default_plotly_axis(showgrid=False, tickfont_size=11, tickfont_color=PLOTLY_TEXT_COLOR))
        fig.update_xaxes(**default_numeric_y_axis(composition_df["plot_value"], title=axis_title, anchor_zero=True))
    else:
        fig.update_xaxes(**default_plotly_axis(showgrid=False, tickfont_size=11, tickfont_color=PLOTLY_TEXT_COLOR))
        fig.update_yaxes(**default_numeric_y_axis(composition_df["plot_value"], title=axis_title, anchor_zero=True))
    _plotly_chart(fig, chart_key=_context_chart_key(context, "grouped_bar"))


def render_stacked_100_bar(context: dict[str, object]) -> None:
    composition_df = _composition_frame(context)
    if composition_df.empty:
        render_empty_state("This structure view needs category breakdown data that is not currently available for this indicator.")
        return
    if "composition_measure" in composition_df.columns and str(composition_df["composition_measure"].iloc[0]) != "share":
        render_grouped_bar(context)
        return

    subject_order = list(dict.fromkeys(composition_df.sort_values("subject_order")["subject"].tolist()))
    category_order = list(dict.fromkeys(composition_df.sort_values("category_order")["category"].tolist()))
    palette = list(CATEGORY_PALETTE)
    category_colors = {category: palette[index % len(palette)] for index, category in enumerate(category_order)}

    fig = go.Figure()
    for category in category_order:
        category_df = composition_df[composition_df["category"] == category].copy()
        category_df["subject"] = pd.Categorical(category_df["subject"], categories=subject_order, ordered=True)
        category_df = category_df.sort_values("subject")
        fig.add_trace(
            go.Bar(
                y=category_df["subject"],
                x=category_df["share_pct"],
                name=category,
                orientation="h",
                marker=bar_marker_style(category_colors[category]),
                text=category_df["formatted_share"].where(category_df["share_pct"] >= 10, ""),
                textposition="inside",
                insidetextanchor="middle",
                hovertemplate="%{y}<br>" + category + ": %{text}<extra></extra>",
            )
        )

    legend_rows = max(1, math.ceil(len(category_order) / 4))
    layout = default_plotly_layout(
        barmode="stack",
        height=max(220, 120 + len(subject_order) * 72),
        margin=dict(l=20, r=20, t=12, b=54 + legend_rows * 22),
        xaxis_title="Share (%)",
        yaxis_title=None,
        legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="left", x=0),
    )
    fig.update_layout(**layout)
    fig.update_xaxes(**default_plotly_axis(showgrid=True, title="Share (%)", range=[0, 100]))
    fig.update_yaxes(**default_plotly_axis(showgrid=False, tickfont_color=PLOTLY_TEXT_COLOR))
    _plotly_chart(fig, chart_key=_context_chart_key(context, "stacked_100_bar"))


def render_population_pyramid(context: dict[str, object]) -> None:
    composition_df = _composition_frame(context)
    if composition_df.empty:
        render_empty_state("This population pyramid view needs category breakdown data that is not currently available for this indicator.")
        return
    if "composition_measure" in composition_df.columns and str(composition_df["composition_measure"].iloc[0]) != "share":
        render_grouped_bar(context)
        return

    selection_subject, comparator_subjects = _population_pyramid_subject_options(composition_df)
    if not selection_subject or not comparator_subjects:
        st.caption("Add one benchmark to compare the age profile as a population pyramid.")
        render_stacked_100_bar(context)
        return

    comparator_subject = comparator_subjects[0]
    chart_col = None
    if len(comparator_subjects) > 1:
        chart_col, control_col = st.columns([0.8, 0.2], gap="large")
        with control_col:
            st.markdown("**Comparator**")
            comparator_subject = st.radio(
                "Population pyramid comparator",
                options=comparator_subjects,
                index=0,
                key=_context_chart_key(context, "population_pyramid_comparator"),
                label_visibility="collapsed",
            )

    category_order = list(dict.fromkeys(composition_df.sort_values("category_order")["category"].astype(str).tolist()))
    selected_df = (
        composition_df[composition_df["subject"] == selection_subject][["category", "category_order", "share_pct", "formatted_share"]]
        .rename(columns={"share_pct": "selected_share_pct", "formatted_share": "selected_formatted"})
        .copy()
    )
    comparator_df = (
        composition_df[composition_df["subject"] == comparator_subject][["category", "category_order", "share_pct", "formatted_share"]]
        .rename(columns={"share_pct": "comparator_share_pct", "formatted_share": "comparator_formatted"})
        .copy()
    )
    chart = (
        selected_df.merge(comparator_df, on=["category", "category_order"], how="outer")
        .fillna(
            {
                "selected_share_pct": 0.0,
                "selected_formatted": format_indicator_value(0, "share"),
                "comparator_share_pct": 0.0,
                "comparator_formatted": format_indicator_value(0, "share"),
            }
        )
        .sort_values("category_order", ascending=False)
        .copy()
    )
    chart["selected_value"] = -chart["selected_share_pct"]

    max_share = max(
        float(chart["selected_share_pct"].max()),
        float(chart["comparator_share_pct"].max()),
        1.0,
    )
    axis_limit = max(5, int(math.ceil(max_share / 5.0) * 5))
    tick_step = 2 if axis_limit <= 10 else 5
    tickvals = list(range(-axis_limit, axis_limit + tick_step, tick_step))
    ticktext = [f"{abs(value)}" for value in tickvals]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=chart["category"],
            x=chart["selected_value"],
            orientation="h",
            marker=bar_marker_style(PURPLE, line_width=0.9),
            customdata=chart["selected_formatted"],
            hovertemplate="%{y}<br>" + selection_subject + ": %{customdata}<extra></extra>",
            showlegend=False,
        )
    )
    fig.add_trace(
        go.Bar(
            y=chart["category"],
            x=chart["comparator_share_pct"],
            orientation="h",
            marker=bar_marker_style("#005eb8", line_width=0.9),
            customdata=chart["comparator_formatted"],
            hovertemplate="%{y}<br>" + comparator_subject + ": %{customdata}<extra></extra>",
            showlegend=False,
        )
    )

    fig.update_layout(**default_plotly_layout(
        barmode="relative",
        height=max(460, 140 + len(chart) * 28),
        margin=dict(l=28, r=28, t=36, b=30),
        xaxis_title="Share (%)",
        yaxis_title=None,
    ))
    fig.update_xaxes(
        **default_plotly_axis(
            showgrid=True,
            title="Share (%)",
            range=[-axis_limit, axis_limit],
            tickvals=tickvals,
            ticktext=ticktext,
            zeroline=True,
            zerolinecolor="rgba(20, 32, 51, 0.35)",
            zerolinewidth=1.1,
        )
    )
    fig.update_yaxes(
        **default_plotly_axis(
            showgrid=False,
            tickfont_size=11,
            tickfont_color=PLOTLY_TEXT_COLOR,
            categoryorder="array",
            categoryarray=list(chart["category"]),
        )
    )
    fig.add_annotation(
        x=-axis_limit * 0.62,
        y=1.05,
        xref="x",
        yref="paper",
        text=selection_subject,
        showarrow=False,
        font=dict(family=PLOTLY_FONT_FAMILY, size=12, color=PURPLE),
    )
    fig.add_annotation(
        x=axis_limit * 0.62,
        y=1.05,
        xref="x",
        yref="paper",
        text=comparator_subject,
        showarrow=False,
        font=dict(family=PLOTLY_FONT_FAMILY, size=12, color="#005eb8"),
    )
    if chart_col is None:
        _plotly_chart(fig, chart_key=_context_chart_key(context, "population_pyramid"))
    else:
        with chart_col:
            _plotly_chart(fig, chart_key=_context_chart_key(context, "population_pyramid"))
