# London Neighbourhood Public Data Explorer

This folder is the complete working area for the London Neighbourhood Explorer app. If you are running, editing, testing, or rebuilding the explorer, start here.

This repo contains two connected products:

- a public-facing Streamlit explorer for custom London neighbourhood geographies
- a Python API discovery toolkit for assessing future public-data sources

The explorer’s core reporting geography is a custom London neighbourhood, built from the canonical static `LSOA 2021 -> neighbourhood` crosswalk in `london_maps/`.

## Start Here If You Are Maintaining Data

The quickest colleague-facing references are now:

- `data/metadata/indicator_manifest.csv`
- `data/metadata/source_manifest.csv`
- `data/metadata/api_refresh_manifest.csv`
- `data/metadata/tool_data_file_manifest.csv`

Supporting docs:

- `docs/data_architecture_and_api_reference.md`
- `docs/api_refresh_and_automation_guide.md`
- `docs/api_interaction_reference.md`

## App overview

The public app now has a coherent three-part structure:

- `Home.py`: Setup
- `app/pages/0_Explorer.py`: Explorer
- `app/pages/1_Methodology_and_Data_Coverage.py`: Methodology & Data Coverage

The product journey is:

1. define a footprint in `Setup`
2. carry that configuration into `Explorer`
3. inspect methodology, coverage, and caveats in `Methodology & Data Coverage`

## Current data scope

Current processed scope in the app:

- 141 neighbourhoods
- 33 borough comparator names
- 5 ICB groupings: `NCL`, `NEL`, `NWL`, `SEL`, `SWL`
- 51 public Explorer indicators
- current public themes:
  - Population & Demographics
  - Poverty & Deprivation
  - Health & Wellbeing
  - Housing, Work & Living Conditions
  - Safety & Crime

Current public sources:

- ONS Census 2021
- Indices of Deprivation 2025
- `data.police.uk` street-level crime
- NHS England Patients Registered at a GP Practice
- Nomis API
- NaPTAN / NPTG API
- TfL Unified API
- Department for Transport Road Traffic Statistics API
- Environment Agency Flood Monitoring API
- London Datastore CKAN API

The canonical live source-input area is `london_maps/data_for_app/`. Files not in current runtime use should live outside that folder, for example in `data/archive/`.

## Canonical geography rule

- integration geography: `LSOA 2021`
- reporting geography: `neighbourhood`
- stable neighbourhood key: `neighbourhood_id`
- canonical crosswalk: `london_maps/crosswalk_lsoa21_to_neighbourhood.csv`

## Product architecture

### App shell

- `app/Home.py`: public setup entrypoint
- `app/pages/0_Explorer.py`: main explorer surface
- `app/pages/1_Methodology_and_Data_Coverage.py`: transparency and coverage page

### UI components

- `app/components/page_views.py`: top-level page controllers
- `app/components/category_nav.py`: category navigation and indicator search
- `app/components/map_panel.py`: persistent explorer map context
- `app/components/chart_registry.py`: primary and secondary visual selection
- `app/components/charts.py`: reusable chart templates
- `app/components/methodology_panel.py`: methodology and coverage surface
- `app/components/narrative_summaries.py`: rule-based plain-English summaries
- `app/components/selection.py`: shared selection state
- `app/components/maps.py`: real-map and hex-map rendering
- `assets/`: app-local logos and shared hex-geometry assets

### Shared data layer

- `neighbourhood_explorer/data_access.py`: processed-data access, benchmark bundles, map values, catalogue loading
- `neighbourhood_explorer/aggregation.py`: safe aggregation rules
- `neighbourhood_explorer/catalog.py`: unified indicator catalogue enrichment
- `neighbourhood_explorer/config.py`: configuration loaders
- `neighbourhood_explorer/paths.py`: canonical project paths

## Indicator catalogue architecture

The app is now catalogue-driven rather than UI-hardcoded.

The unified indicator catalogue combines:

- the manually curated source indicators in `config/indicators.yml`
- public category and module structure from `catalog/categories.yml`
- visualisation defaults and overrides from `catalog/visualisations.yml`
- Fingertips curation rules from `catalog/fingertips_curated.yml`
- the app-facing visual contract in `london_maps/data_for_app/indicator_visualisation_guidance_final.csv`

Each indicator row carries metadata used by the app, including:

- category and module placement
- metric family
- unit type
- aggregation policy
- neighbourhood use mode
- benchmark mode
- period type
- map eligibility
- comparison eligibility
- trend eligibility
- primary and secondary visualisation templates
- methodology summary
- refresh date

Processed catalogue output:

- `data/processed/indicator_catalog.parquet`

## Category system

The public explorer is category-led and now reads its navigation structure from the visualisation contract CSV at `london_maps/data_for_app/indicator_visualisation_guidance_final.csv`.

Key fields used in the app:

- `category_final`
- `subcategory_final`
- `ui_exposure_level`

The public UI shows `core` and `standard` indicators by default, with `advanced` behind an explicit toggle. `hidden` indicators stay out of the default public flow.

## Visualisation system

Chart selection is now contract-driven through:

- `london_maps/data_for_app/indicator_visualisation_guidance_final.csv`
- `catalog/indicator_visualisation_registry.py`
- `app/components/chart_template_registry.py`
- `app/components/chart_templates.py`

Key contract fields used at render time:

- `default_view`
- `primary_visual_final`
- `secondary_visual_final`
- `view_toggle_options_compact`
- `view_toggle_options_full`
- `comparison_view`
- `trend_view`
- `map_view_final`
- `distribution_view`
- `composition_view`
- `module_bundle_view`

Current template coverage includes:

- benchmark lollipop / comparison views
- trend lines with optional rolling average
- ranked distribution and ranked strip views
- KPI cards
- choropleth maps
- sorted bars
- distribution bands
- domain tile matrices
- crime mix views
- grouped/table fallback views

This means new indicators can usually be added or reclassified by editing the CSV contract instead of rewriting explorer page logic.

## Fingertips integration strategy

Fingertips is handled as a metadata-first expansion path.

Relevant files:

- `etl/fingertips_discovery.py`
- `etl/fingertips_normalise.py`
- `etl/fetch_fingertips.py`
- `catalog/fingertips_curated.yml`
- `data/processed/fingertips_discovery.parquet`
- `data/processed/fingertips_indicator_metadata.parquet`
- `data/processed/fingertips_catalog.parquet`

The intended flow is:

1. discover and cache profiles / area types / indicator metadata
2. normalise cached metadata into processed parquet tables
3. classify indicators into user-facing categories and suitability modes
4. rebuild the unified indicator catalogue

Important distinction in the model:

- `direct_neighbourhood_candidate`
- `neighbourhood_estimate_with_caveats`
- `benchmark_only`
- `hidden_for_now`
- `not_recommended`

The public UI should only surface indicators that are understandable and methodologically defensible.

## How to add indicators

### Add a non-Fingertips indicator

1. Add the source indicator metadata to `config/indicators.yml`.
2. If needed, create or refresh the source ingest step first, for example `python3 etl/fetch_gp_registrations.py`.
3. Assign the indicator to a public category and module in `catalog/categories.yml` or in the visualisation guidance CSV.
4. Add or update its row in `london_maps/data_for_app/indicator_visualisation_guidance_final.csv`.
5. Rebuild the processed data and indicator catalogue.

### Extend the API candidate universe

Run:

```bash
python3 etl/build_next_wave_extension.py
```

This refreshes:

- additional API discovery outputs
- the curated next-wave indicator menu
- the critique notes for those candidate indicators
- the canonical visualisation guidance CSV
- the maintained source inventory in `london_maps/data_for_app/`

### Add or curate Fingertips indicators

1. Run the Fingertips discovery and normalisation scripts.
2. Review cached metadata and update `catalog/fingertips_curated.yml`.
3. Rebuild `data/processed/indicator_catalog.parquet`.
4. Only surface indicators publicly once their geography and aggregation mode are clear.

## Run the ETL

From the repo root:

```bash
python3 etl/fetch_gp_registrations.py
python3 etl/inspect_sources.py
python3 etl/standardise_sources.py
python3 etl/aggregate_to_neighbourhoods.py
python3 etl/build_benchmarks.py
python3 etl/build_indicator_catalog.py
```

For a repeatable one-command refresh of the live API-backed data, use:

```bash
python3 etl/refresh_data.py --with-tests
```

Full maintenance notes are in:

- `docs/api_refresh_and_automation_guide.md`

Optional Fingertips steps:

```bash
python3 etl/fingertips_discovery.py
python3 etl/fingertips_normalise.py
python3 etl/fetch_fingertips.py
```

Key processed outputs:

- `data/source_inventory.csv`
- `data/source_inventory.md`
- `london_maps/data_for_app/indicator_source_inventory.csv`
- `london_maps/data_for_app/indicator_source_inventory.md`
- `data/processed/lsoa_indicator_values.parquet`
- `data/processed/neighbourhood_indicator_values.parquet`
- `data/processed/borough_benchmarks.parquet`
- `data/processed/london_benchmarks.parquet`
- `data/processed/neighbourhood_reference.parquet`
- `data/processed/neighbourhood_boundaries.geojson`
- `data/processed/neighbourhood_hex.geojson`
- `data/processed/indicator_catalog.parquet`

## Run the app

```bash
streamlit run app/Home.py
```

The app starts in `Setup`, where users can:

- choose a footprint using the `Region / System / Place / Neighbourhood` pattern
- use the checklist selector and direct neighbourhood search
- switch between hex, real, or split-map reference views
- choose which public themes to carry into the explorer
- decide whether borough and/or London comparisons should appear

The `Explorer` then:

- keeps the footprint visible
- uses category-led navigation
- retains persistent map context
- groups indicators into coherent modules
- uses tailored visuals by metric family
- supports PowerPoint export from the configured scope

The `Methodology & Data Coverage` page explains:

- geography rules
- aggregation policies
- benchmark logic
- source coverage
- indicator coverage
- Fingertips scaffolding

## Install

```bash
python3 -m pip install -r requirements.txt
```

If the plain `streamlit` command ever points at the wrong interpreter on a machine, `python3 -m streamlit run app/Home.py` is still a safe fallback.

## API discovery toolkit

The discovery toolkit does not build the app UI. It inspects a curated set of official UK public APIs and writes a single primary report:

- `outputs/api_discovery_report.md`

Run it with:

```bash
python3 etl/discover_public_apis.py
```

Secondary outputs:

- `outputs/api_source_assessment.csv`
- `outputs/api_candidate_datasets.csv`
- `outputs/api_discovery_snapshot.json`

## Indicator menu toolkit

The indicator-menu step sits after source discovery. It turns the source-level API assessment into a decision-ready shortlist of actual indicator candidates, with geography notes, use modes, aggregation suggestions, and recommended visuals.

Primary outputs:

- `outputs/api_indicator_menu.md`
- `outputs/api_indicator_menu.csv`

Supporting outputs:

- `outputs/api_indicator_menu.parquet`
- `outputs/fingertips_indicator_catalogue.csv`
- `outputs/nomis_indicator_catalogue.csv`
- `outputs/london_datastore_curated_candidates.csv`
- `outputs/indicator_visualisation_recommendations.csv`

Run it with:

```bash
python3 etl/build_indicator_menu.py
```

## Full indicator universe

The full-indicator-universe step merges:

- every indicator already live in the app from static/local files
- the full harvested Fingertips indicator catalogue
- the curated non-Fingertips API candidate menu
- the source-level API assessment and candidate dataset-family notes

Primary outputs:

- `outputs/full_indicator_universe.md`
- `outputs/full_indicator_universe.csv`

Supporting output:

- `outputs/full_indicator_universe.parquet`

Run it with:

```bash
python3 etl/build_full_indicator_universe.py
```

## Current limitations

- police stop-and-search is inventoried but not yet included in the neighbourhood explorer
- some deprivation indicators remain display-only by design because they are non-additive
- Fingertips scaffolding is in place, but public surfacing should remain curated rather than automatic
- Some catalogued sources, including Fingertips, London Air, EPC and selected London Datastore datasets, still require further geography or methodology review before public inclusion

## Validation

Current test command:

```bash
python3 -m pytest tests -q
```

See `METHODOLOGY.md` for the detailed geography and aggregation logic.
