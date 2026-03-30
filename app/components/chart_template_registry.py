from __future__ import annotations

from collections.abc import Callable

from app.components import chart_templates


TEMPLATE_RENDERERS: dict[str, Callable[[dict[str, object]], None]] = {
    "benchmark_lollipop": chart_templates.render_benchmark_lollipop,
    "benchmark_only_compare": chart_templates.render_benchmark_only_compare,
    "lollipop_compare": chart_templates.render_lollipop_compare,
    "trend_line_with_rolling_average": chart_templates.render_trend_line_with_rolling_average,
    "trend_line": chart_templates.render_trend_line,
    "kpi_card": chart_templates.render_kpi_card,
    "stacked_100_bar": chart_templates.render_stacked_100_bar,
    "grouped_bar": chart_templates.render_grouped_bar,
    "population_pyramid": chart_templates.render_population_pyramid,
    "distribution_band": chart_templates.render_distribution_band_template,
    "ranked_strip": chart_templates.render_ranked_strip,
    "ranked_distribution": chart_templates.render_ranked_distribution,
    "sorted_bar": chart_templates.render_sorted_bar,
    "choropleth_map": chart_templates.render_choropleth_map,
    "crime_mix_chart": chart_templates.render_crime_mix_chart,
    "domain_tile_matrix": chart_templates.render_domain_tile_matrix,
    "table_support_only": chart_templates.render_table_support_only,
    "text_badges_or_indexed_note": chart_templates.render_text_badges_or_indexed_note,
}


def available_template_names() -> list[str]:
    return sorted(TEMPLATE_RENDERERS)


def get_template_renderer(template_name: str) -> Callable[[dict[str, object]], None]:
    key = str(template_name).strip()
    if key not in TEMPLATE_RENDERERS:
        raise KeyError(f"No chart template renderer registered for: {template_name}")
    return TEMPLATE_RENDERERS[key]


def render_template(template_name: str, context: dict[str, object]) -> None:
    get_template_renderer(template_name)(context)

