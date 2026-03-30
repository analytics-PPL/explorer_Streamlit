# Methodology

## Geography

### Canonical mapping

- The app uses `london_maps/crosswalk_lsoa21_to_neighbourhood.csv` as the canonical `LSOA 2021 -> neighbourhood` mapping.
- Each London `LSOA21` appears exactly once in that crosswalk.
- The stable neighbourhood key is `neighbourhood_id`.
- Borough and ICB assignments come directly from the canonical crosswalk.

### Real and hex geometry

- Real neighbourhood boundaries come from `london_maps/maps/shape_files/neighbourhoods_shapefile.shp`.
- Hex geometry comes from the app-local asset at `assets/geojson/neighbourhoods_hex.geojson`.
- Both geometry layers are matched back onto the canonical neighbourhood IDs before being written to `data/processed/`.

## Source handling

### Census 2021

- Only LSOA extracts are used for the first app build.
- Category-count tables are aggregated by summing counts across the selected neighbourhoods.
- Shares are recomputed from summed numerators and denominators rather than by averaging percentages.

### IMD / IoD 2025

- The app uses the `File_7_IoD2025_All_Ranks_Scores_Deciles_Population_Denominators.csv` file.
- Score-based indicators use weighted aggregation where that is defensible.
- Rate-style indicators such as Income, Employment, IDACI, and IDAOPI are recomputed from derived numerators and denominators.
- Ranks and deciles are not aggregated into fake composite scores. They are treated as display-only summaries.

### Police

- The app uses monthly `data.police.uk` street crime files for:
  - Metropolitan Police
  - City of London Police
- Records are filtered to London LSOAs found in the canonical crosswalk.
- Crime counts are additive.
- Crime rates are recomputed using the Census 2021 resident population denominator.
- Police outcomes are inventoried but not currently surfaced in the first public app.
- Stop-and-search is inventoried but not included in the first neighbourhood aggregation outputs.

## Aggregation methods

The app uses a metadata-driven aggregation system with these explicit methods:

- `sum_counts`
  - Sum raw counts.
- `recompute_rate_from_numerator_denominator`
  - Sum numerator and denominator, then recompute the rate.
- `recompute_share_from_category_counts`
  - Sum numerator category counts and denominator totals, then recompute the share.
- `population_weighted_mean`
  - Use a population-weighted average where the source is a valid score-based measure.
- `area_weighted_mean`
  - Implemented for future use; not used in the first indicator set.
- `non_additive_display_only`
  - Show a distribution-style summary and do not claim the result is an additive aggregate.

## Benchmark logic

### London benchmark

- Defined as all London neighbourhoods aggregated together.
- For counts and rate-style indicators, this is a real aggregate.
- For display-only non-additive indicators, the app shows a summary rather than a fake combined rank or decile.

### Borough benchmark

- For a single-neighbourhood selection, the borough benchmark is the parent borough aggregate.
- For multiple neighbourhoods in the same borough, the borough benchmark is still that parent borough aggregate.
- For multiple neighbourhoods spanning more than one borough, the app does not fabricate a single combined borough comparator.
- Instead, it shows each relevant borough benchmark separately.

## Fingertips

- `etl/fetch_fingertips.py` discovers and caches official Fingertips metadata from `https://fingertips.phe.org.uk/api`.
- Raw downloads are cached under `data/cache/fingertips/`.
- Fingertips data are not automatically shown in the explorer unless the downloaded geography can be cleanly normalised to neighbourhoods using files already present in the repo.

## Validation

The delivered tests cover:

- crosswalk uniqueness and completeness
- aggregation semantics for counts, shares, rates, and non-additive summaries
- benchmark logic for rate recomputation and cross-borough selections
- indicator catalog structure

The ETL also writes:

- `data/source_inventory.csv`
- `data/source_inventory.md`
- `london_maps/data_for_app/indicator_source_inventory.csv`
- `london_maps/data_for_app/indicator_source_inventory.md`

so the actual source-file footprint and inferred schema assumptions are documented from the files present in the repo.
