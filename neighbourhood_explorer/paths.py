from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
LONDON_MAPS_DIR = ROOT_DIR / "london_maps"
DATA_FOR_APP_DIR = LONDON_MAPS_DIR / "data_for_app"
ASSETS_DIR = ROOT_DIR / "assets"
LOGOS_DIR = ASSETS_DIR / "logos"
HEX_GEOJSON_DIR = ASSETS_DIR / "geojson"
CONFIG_DIR = ROOT_DIR / "config"
CATALOG_DIR = ROOT_DIR / "catalog"
DATA_DIR = ROOT_DIR / "data"
PROCESSED_DIR = DATA_DIR / "processed"
CACHE_DIR = DATA_DIR / "cache"
METADATA_DIR = DATA_DIR / "metadata"
ARCHIVE_DIR = DATA_DIR / "archive"
FINGERTIPS_CACHE_DIR = CACHE_DIR / "fingertips"
APP_DIR = ROOT_DIR / "app"
TESTS_DIR = ROOT_DIR / "tests"

CROSSWALK_PATH = LONDON_MAPS_DIR / "crosswalk_lsoa21_to_neighbourhood.csv"
CROSSWALK_DQ_PATH = LONDON_MAPS_DIR / "crosswalk_lsoa21_to_neighbourhood_dq.json"
NEIGHBOURHOOD_SHAPEFILE_PATH = LONDON_MAPS_DIR / "maps" / "shape_files" / "neighbourhoods_shapefile.shp"
NEIGHBOURHOOD_SUMMARY_PATH = LONDON_MAPS_DIR / "maps" / "shape_files" / "neighbourhoods_summary.xlsx"
HEX_GEOJSON_PATH = HEX_GEOJSON_DIR / "neighbourhoods_hex.geojson"
HEX_ICB_GEOJSON_PATH = HEX_GEOJSON_DIR / "icbs_hex.geojson"
HEX_BOROUGH_GEOJSON_PATH = HEX_GEOJSON_DIR / "boroughs_hex.geojson"

SOURCE_INVENTORY_CSV_PATH = DATA_DIR / "source_inventory.csv"
SOURCE_INVENTORY_MD_PATH = DATA_DIR / "source_inventory.md"
INDICATOR_MANIFEST_CSV_PATH = METADATA_DIR / "indicator_manifest.csv"
SOURCE_MANIFEST_CSV_PATH = METADATA_DIR / "source_manifest.csv"
API_REFRESH_MANIFEST_CSV_PATH = METADATA_DIR / "api_refresh_manifest.csv"
TOOL_DATA_FILE_MANIFEST_CSV_PATH = METADATA_DIR / "tool_data_file_manifest.csv"

NEIGHBOURHOOD_REFERENCE_PATH = PROCESSED_DIR / "neighbourhood_reference.parquet"
NEIGHBOURHOOD_BOUNDARIES_GEOJSON_PATH = PROCESSED_DIR / "neighbourhood_boundaries.geojson"
NEIGHBOURHOOD_HEX_GEOJSON_PATH = PROCESSED_DIR / "neighbourhood_hex.geojson"
LSOA_INDICATOR_VALUES_PATH = PROCESSED_DIR / "lsoa_indicator_values.parquet"
NEIGHBOURHOOD_INDICATOR_VALUES_PATH = PROCESSED_DIR / "neighbourhood_indicator_values.parquet"
BOROUGH_BENCHMARKS_PATH = PROCESSED_DIR / "borough_benchmarks.parquet"
LONDON_BENCHMARKS_PATH = PROCESSED_DIR / "london_benchmarks.parquet"
INDICATOR_CATALOG_EXPORT_PATH = PROCESSED_DIR / "indicator_catalog.parquet"
FINGERTIPS_DISCOVERY_PATH = PROCESSED_DIR / "fingertips_discovery.parquet"
FINGERTIPS_PROFILES_PATH = PROCESSED_DIR / "fingertips_profiles.parquet"
FINGERTIPS_AREA_TYPES_PATH = PROCESSED_DIR / "fingertips_area_types.parquet"
FINGERTIPS_METADATA_PATH = PROCESSED_DIR / "fingertips_indicator_metadata.parquet"
FINGERTIPS_CATALOG_PATH = PROCESSED_DIR / "fingertips_catalog.parquet"

SOURCES_CONFIG_PATH = CONFIG_DIR / "sources.yml"
SOURCE_HIERARCHY_CONFIG_PATH = CONFIG_DIR / "source_hierarchy.yml"
INDICATORS_CONFIG_PATH = CONFIG_DIR / "indicators.yml"
CATEGORIES_CONFIG_PATH = CATALOG_DIR / "categories.yml"
VISUALISATIONS_CONFIG_PATH = CATALOG_DIR / "visualisations.yml"
FINGERTIPS_CURATION_CONFIG_PATH = CATALOG_DIR / "fingertips_curated.yml"
INDICATOR_VISUALISATION_GUIDANCE_PATH = DATA_FOR_APP_DIR / "indicator_visualisation_guidance_final.csv"
INDICATOR_SOURCE_INVENTORY_CSV_PATH = DATA_FOR_APP_DIR / "indicator_source_inventory.csv"
INDICATOR_SOURCE_INVENTORY_MD_PATH = DATA_FOR_APP_DIR / "indicator_source_inventory.md"
QOF_DIR = DATA_FOR_APP_DIR / "QOF"
QOF_RAW_DIR = QOF_DIR / "raw"
QOF_LSOA_LONG_PATH = QOF_DIR / "qof_lsoa_long.csv"
QOF_INDICATOR_CATALOG_PATH = QOF_DIR / "qof_indicator_catalog.csv"
QOF_BUILD_NOTES_PATH = QOF_DIR / "qof_build_notes.md"


def ensure_runtime_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    FINGERTIPS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)


def project_path(*parts: str) -> Path:
    return ROOT_DIR.joinpath(*parts)
