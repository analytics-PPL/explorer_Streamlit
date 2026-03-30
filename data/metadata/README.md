# Tool Metadata

This folder is the colleague-facing metadata layer for the London Neighbourhood Explorer.

These files are the quickest way to understand what the app is using, how indicators are configured, and how the live sources are refreshed.

## Canonical manifests

- `indicator_manifest.csv`
  - one row per live processed indicator
  - includes theme, source, last refresh date, aggregation, and chart choices
- `source_manifest.csv`
  - one row per documented source
  - includes current status, live usage, configured paths, refresh script, and documentation links
- `api_refresh_manifest.csv`
  - one row per source with the update command and the post-refresh rebuild steps
- `tool_data_file_manifest.csv`
  - one row per app-relevant file path across source inputs, processed outputs, configuration, and metadata

## How this folder is updated

Run:

```bash
python3 etl/build_tool_metadata.py
```

Or run the full refresh:

```bash
python3 etl/refresh_data.py --with-tests
```

That rebuilds these manifests after the source data and processed outputs are refreshed.

For detailed source-by-source API interaction notes, use:

- `docs/api_interaction_reference.md`

## What not to treat as canonical

- `outputs/`
  - useful research, discovery, and one-off assessment outputs
  - not required for the public app runtime
- `data/archive/`
  - files intentionally kept out of the live app source area
  - not loaded by the public app
