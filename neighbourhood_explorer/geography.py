from __future__ import annotations

import pandas as pd

from neighbourhood_explorer.paths import (
    CROSSWALK_PATH,
    HEX_GEOJSON_PATH,
    NEIGHBOURHOOD_BOUNDARIES_GEOJSON_PATH,
    NEIGHBOURHOOD_HEX_GEOJSON_PATH,
    NEIGHBOURHOOD_REFERENCE_PATH,
    NEIGHBOURHOOD_SHAPEFILE_PATH,
    ensure_runtime_dirs,
)


def load_crosswalk() -> pd.DataFrame:
    df = pd.read_csv(CROSSWALK_PATH)
    if df["lsoa21cd"].duplicated().any():
        raise ValueError("Canonical crosswalk contains duplicated lsoa21cd values.")
    return df


def build_neighbourhood_reference(population_lookup: pd.DataFrame | None = None) -> pd.DataFrame:
    crosswalk = load_crosswalk()
    neighbourhoods = (
        crosswalk.groupby("neighbourhood_id", as_index=False)
        .agg(
            neighbourhood_name=("neighbourhood_name", "first"),
            icb_code=("icb_code", "first"),
            borough_name=("borough_name", lambda values: "; ".join(sorted(pd.Series(values).dropna().astype(str).unique()))),
            borough_code=("borough_code", lambda values: "; ".join(sorted(pd.Series(values).dropna().astype(str).unique()))),
            borough_count=("borough_name", "nunique"),
        )
        .sort_values(["icb_code", "neighbourhood_name"])
        .reset_index(drop=True)
    )

    if population_lookup is not None and not population_lookup.empty:
        population_frame = (
            crosswalk[["lsoa21cd", "neighbourhood_id"]]
            .merge(population_lookup[["lsoa21cd", "value"]], on="lsoa21cd", how="left")
            .groupby("neighbourhood_id", as_index=False)["value"]
            .sum()
            .rename(columns={"value": "population"})
        )
        neighbourhoods = neighbourhoods.merge(population_frame, on="neighbourhood_id", how="left")
    else:
        neighbourhoods["population"] = pd.NA

    return neighbourhoods


def export_geography_assets(population_lookup: pd.DataFrame | None = None) -> pd.DataFrame:
    import geopandas as gpd

    ensure_runtime_dirs()
    reference = build_neighbourhood_reference(population_lookup=population_lookup)
    shape_lookup = (
        load_crosswalk()[
            [
                "neighbourhood_id",
                "neighbourhood_name",
                "borough_name",
                "borough_code",
                "icb_code",
            ]
        ]
        .drop_duplicates()
        .reset_index(drop=True)
    ).merge(reference[["neighbourhood_id", "population"]], on="neighbourhood_id", how="left")

    boundaries = gpd.read_file(NEIGHBOURHOOD_SHAPEFILE_PATH)
    boundaries = boundaries.dropna(subset=["nghbrhd", "borough", "ICB"]).copy()
    boundaries = boundaries.merge(
        shape_lookup,
        left_on=["nghbrhd", "borough", "ICB"],
        right_on=["neighbourhood_name", "borough_name", "icb_code"],
        how="left",
    )
    if boundaries["neighbourhood_id"].isna().any():
        unmatched = boundaries.loc[boundaries["neighbourhood_id"].isna(), ["nghbrhd", "borough", "ICB"]]
        raise ValueError(f"Could not match all real boundaries to canonical neighbourhood IDs: {unmatched.to_dict('records')}")
    boundaries = boundaries[
        ["neighbourhood_id", "neighbourhood_name", "borough_name", "borough_code", "icb_code", "population", "geometry"]
    ].sort_values(["icb_code", "borough_name", "neighbourhood_name"])
    boundaries.to_file(NEIGHBOURHOOD_BOUNDARIES_GEOJSON_PATH, driver="GeoJSON")

    hex_gdf = gpd.read_file(HEX_GEOJSON_PATH).rename(
        columns={"name": "neighbourhood_name", "icb_name": "icb_code", "population": "hex_population"}
    )
    hex_gdf = hex_gdf.merge(shape_lookup, on=["neighbourhood_name", "borough_name", "icb_code"], how="left")
    if hex_gdf["neighbourhood_id"].isna().any():
        missing = hex_gdf.loc[hex_gdf["neighbourhood_id"].isna(), ["neighbourhood_name", "borough_name", "icb_code"]]
        raise ValueError(f"Could not match all hex features to canonical neighbourhood IDs: {missing.to_dict('records')}")
    hex_gdf = hex_gdf[
        ["neighbourhood_id", "neighbourhood_name", "borough_name", "borough_code", "icb_code", "population", "hex_population", "geometry"]
    ].sort_values(["icb_code", "borough_name", "neighbourhood_name"])
    hex_gdf.to_file(NEIGHBOURHOOD_HEX_GEOJSON_PATH, driver="GeoJSON")

    reference.to_parquet(NEIGHBOURHOOD_REFERENCE_PATH, index=False)
    return reference
