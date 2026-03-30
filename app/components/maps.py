from __future__ import annotations

import json
from typing import Iterable

import folium
import geopandas as gpd
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from branca.colormap import linear
from shapely.geometry import Point
from streamlit_folium import st_folium

from app.components.formatting import format_indicator_value, system_name
from app.components.layout import render_empty_state


def _map_click_to_neighbourhood(geo_df: gpd.GeoDataFrame, lat: float, lng: float) -> str | None:
    point = Point(float(lng), float(lat))
    match = geo_df[geo_df.geometry.intersects(point)]
    if match.empty:
        return None
    return str(match.iloc[0]["neighbourhood_id"])


def _hex_fill_colors(display: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    colored = display.copy()
    values = pd.to_numeric(colored["value"], errors="coerce").dropna()
    colormap = linear.PuBu_09.scale(float(values.min()), float(values.max())) if not values.empty else None
    default_fill = "#e0d6ec"
    colored["fill_color"] = [
        colormap(float(value)) if colormap is not None and pd.notna(value) else default_fill
        for value in colored["value"]
    ]
    return colored


def render_hex_selection_map(
    geo_df: gpd.GeoDataFrame,
    value_frame: pd.DataFrame,
    selected_ids: Iterable[str],
    map_key: str,
    overlay_geo_df: gpd.GeoDataFrame | None = None,
    height: int = 620,
) -> None:
    selected_set = {str(value) for value in selected_ids}
    display = geo_df.merge(value_frame[["neighbourhood_id", "value", "unit"]], on="neighbourhood_id", how="left")
    display = _hex_fill_colors(display)
    display["selected"] = display["neighbourhood_id"].astype(str).isin(selected_set)
    display["system_name"] = display["icb_code"].map(system_name)
    display["display_value"] = [
        format_indicator_value(row.value, row.unit)
        for row in display[["value", "unit"]].itertuples(index=False)
    ]

    if display.empty:
        render_empty_state("No hex geometry available.", icon="🗺️")
        return

    bounds = display.total_bounds.tolist()
    map_bounds = [[bounds[1], bounds[0]], [bounds[3], bounds[2]]]

    neighbourhood_geojson = json.loads(display.to_json())
    overlay_geojson = json.loads(overlay_geo_df.to_json()) if overlay_geo_df is not None and not overlay_geo_df.empty else None
    map_height = max(320, int(height))
    inner_map_height = max(280, int(map_height) - 20)
    map_id = f"hex_map_{abs(hash(map_key))}"

    html_block = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
      <style>
        :root {{
          background: transparent !important;
        }}
        html, body {{
          margin: 0;
          padding: 0;
          background: transparent !important;
          overflow: hidden;
        }}
        #{map_id} {{
          width: 100%;
          height: {inner_map_height}px;
          border: none;
          border-radius: 14px;
          background: transparent !important;
        }}
        .leaflet-container,
        .leaflet-pane,
        .leaflet-map-pane,
        .leaflet-tile-pane,
        .leaflet-overlay-pane,
        .leaflet-shadow-pane,
        .leaflet-marker-pane,
        .leaflet-tooltip-pane,
        .leaflet-control-container,
        svg,
        canvas {{
          background: transparent !important;
        }}
        .leaflet-tooltip {{
          font-family: Inter, Poppins, sans-serif;
          font-size: 13px;
          padding: 8px 12px;
          border-radius: 8px;
          border: 1px solid rgba(83, 35, 128, 0.12);
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
          backdrop-filter: blur(8px);
          background: rgba(255, 255, 255, 0.95);
          color: #1a1f36;
        }}
      </style>
    </head>
    <body>
      <div id="{map_id}"></div>
      <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
      <script>
        const neighbourhoods = {json.dumps(neighbourhood_geojson)};
        const overlay = {json.dumps(overlay_geojson)};
        const bounds = {json.dumps(map_bounds)};
        const mapEl = document.getElementById("{map_id}");
        let map = null;

        function canRenderMap() {{
          return !!mapEl && mapEl.clientWidth > 0 && mapEl.clientHeight > 0;
        }}

        function renderTooltipHtml(properties) {{
          const p = properties || {{}};
          return (
            "<strong>" + String(p.neighbourhood_name || "") + "</strong><br/>" +
            "Borough: " + String(p.borough_name || "") + "<br/>" +
            "System: " + String(p.system_name || p.icb_code || "") + "<br/>" +
            "Value: " + String(p.display_value || "No data")
          );
        }}

        function ensureMapReady() {{
          try {{
            if (typeof L === "undefined") {{
              return false;
            }}
            if (!canRenderMap()) {{
              return false;
            }}

            if (!map) {{
              map = L.map("{map_id}", {{
                zoomControl: false,
                attributionControl: false,
                dragging: false,
                scrollWheelZoom: false,
                doubleClickZoom: false,
                boxZoom: false,
                keyboard: false,
                touchZoom: false,
              }});

              L.geoJSON(neighbourhoods, {{
                style: function(feature) {{
                  const p = feature.properties || {{}};
                  const selected = Boolean(p.selected);
                  return {{
                    color: selected ? "#2a1245" : "#532380",
                    weight: selected ? 2.2 : 0.4,
                    opacity: selected ? 0.98 : 0.5,
                    fillColor: selected ? "#532380" : (p.fill_color || "#CBD5E1"),
                    fillOpacity: selected ? 0.92 : 0.62
                  }};
                }},
                onEachFeature: function(feature, layer) {{
                  layer.bindTooltip(renderTooltipHtml(feature.properties), {{ sticky: true }});
                }}
              }}).addTo(map);

              if (overlay) {{
                L.geoJSON(overlay, {{
                  style: function() {{
                    return {{
                      color: "#2a1245",
                      weight: 2.2,
                      opacity: 0.95,
                      fill: false
                    }};
                  }}
                }}).addTo(map);
              }}
            }}

            map.invalidateSize(true);
            map.fitBounds(bounds, {{ padding: [16, 16] }});
            return true;
          }} catch (err) {{
            return false;
          }}
        }}

        function waitForVisibleMap(attempt) {{
          if (ensureMapReady()) {{
            return;
          }}
          if (attempt < 80) {{
            setTimeout(function() {{
              waitForVisibleMap(attempt + 1);
            }}, 100);
          }}
        }}

        waitForVisibleMap(0);
        window.addEventListener("resize", function() {{
          ensureMapReady();
        }});
        document.addEventListener("visibilitychange", function() {{
          if (document.visibilityState === "visible") {{
            ensureMapReady();
          }}
        }});
        if (typeof ResizeObserver !== "undefined" && mapEl) {{
          const resizeObserver = new ResizeObserver(function() {{
            ensureMapReady();
          }});
          resizeObserver.observe(mapEl);
        }}
      </script>
    </body>
    </html>
    """
    components.html(html_block, height=map_height)


def render_selection_map(
    geo_df: gpd.GeoDataFrame,
    value_frame: pd.DataFrame,
    selected_ids: Iterable[str],
    map_key: str,
    variant: str = "real",
    overlay_geo_df: gpd.GeoDataFrame | None = None,
    height: int = 620,
) -> str | None:
    if variant == "hex":
        render_hex_selection_map(
            geo_df=geo_df,
            value_frame=value_frame,
            selected_ids=selected_ids,
            map_key=map_key,
            overlay_geo_df=overlay_geo_df,
            height=height,
        )
        return None

    selected_set = {str(value) for value in selected_ids}
    display = geo_df.merge(value_frame[["neighbourhood_id", "value", "unit"]], on="neighbourhood_id", how="left")
    display = display.copy()

    center = [51.5074, -0.1278]
    tiles = "CartoDB Voyager"
    fmap = folium.Map(location=center, zoom_start=9, tiles=tiles)
    values = pd.to_numeric(display["value"], errors="coerce").dropna()
    colormap = linear.PuBu_09.scale(float(values.min()), float(values.max())) if not values.empty else None

    def style_function(feature):
        props = feature["properties"]
        value = props.get("value")
        selected = str(props.get("neighbourhood_id")) in selected_set
        fill_color = "#e0d6ec"
        if value is not None and colormap is not None:
            fill_color = colormap(float(value))
        return {
            "fillColor": "#6b3a9e" if selected else fill_color,
            "color": "#2a1245" if selected else "#9070b8",
            "weight": 2.2 if selected else 0.5,
            "opacity": 0.98 if selected else 0.55,
            "fillOpacity": 0.92 if selected else 0.62,
        }

    tooltip_fields = ["neighbourhood_name", "borough_name", "icb_code", "display_value"]
    tooltip_aliases = ["Neighbourhood", "Borough", "System", "Value"]
    tooltip_style = (
        "background-color: rgba(255, 255, 255, 0.95);"
        "border: 1px solid rgba(83, 35, 128, 0.12);"
        "border-radius: 8px;"
        "box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);"
        "font-family: Inter, Poppins, sans-serif;"
        "font-size: 13px;"
        "padding: 8px 12px;"
        "color: #1a1f36;"
    )
    feature_data = display.copy()
    feature_data["icb_code"] = feature_data["icb_code"].map(system_name)
    feature_data["display_value"] = [
        format_indicator_value(row.value, row.unit) for row in feature_data[["value", "unit"]].itertuples(index=False)
    ]
    folium.GeoJson(
        feature_data.to_json(),
        name="Neighbourhoods",
        style_function=style_function,
        highlight_function=(lambda _: {"weight": 2.8, "fillOpacity": 0.95}),
        tooltip=folium.GeoJsonTooltip(fields=tooltip_fields, aliases=tooltip_aliases, sticky=True, style=tooltip_style),
    ).add_to(fmap)

    if overlay_geo_df is not None and not overlay_geo_df.empty:
        overlay_name_col = "name" if "name" in overlay_geo_df.columns else overlay_geo_df.columns[0]
        folium.GeoJson(
            overlay_geo_df.to_json(),
            name="Overlay boundaries",
            style_function=lambda _: {
                "color": "#2a1245",
                "weight": 2.2 if variant == "hex" else 1.4,
                "opacity": 0.95,
                "fillOpacity": 0.0,
            },
            tooltip=folium.GeoJsonTooltip(fields=[overlay_name_col], aliases=["System"], sticky=True, style=tooltip_style),
        ).add_to(fmap)

    if selected_set:
        selected_geo = display[display["neighbourhood_id"].astype(str).isin(selected_set)]
        if not selected_geo.empty:
            bounds = selected_geo.total_bounds
            fmap.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])

    st_map = st_folium(fmap, width=None, height=height, key=map_key, returned_objects=["last_clicked"])
    clicked = st_map.get("last_clicked") if isinstance(st_map, dict) else None
    if not clicked:
        return None

    click_signature = f"{clicked.get('lat'):.6f}_{clicked.get('lng'):.6f}"
    last_signature_key = f"{map_key}_last_click_signature"
    if st.session_state.get(last_signature_key) == click_signature:
        return None
    st.session_state[last_signature_key] = click_signature
    return _map_click_to_neighbourhood(display, clicked["lat"], clicked["lng"])
