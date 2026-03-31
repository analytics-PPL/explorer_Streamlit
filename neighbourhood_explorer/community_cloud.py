from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import shutil
from pathlib import Path

import pandas as pd

from neighbourhood_explorer.config import load_sources_config
from neighbourhood_explorer.paths import ROOT_DIR


APP_RUNTIME_DIRECTORIES = (
    ".streamlit",
    "app",
    "assets",
    "catalog",
    "config",
    "data/metadata",
    "neighbourhood_explorer",
)
APP_RUNTIME_FILES = (
    "METHODOLOGY.md",
    "QOF Guidance.csv",
    "README.md",
    "requirements.txt",
    "runtime.txt",
    "data/processed/borough_benchmarks.parquet",
    "data/processed/indicator_catalog.parquet",
    "data/processed/london_benchmarks.parquet",
    "data/processed/neighbourhood_boundaries.geojson",
    "data/processed/neighbourhood_hex.geojson",
    "data/processed/neighbourhood_indicator_values.parquet",
    "data/processed/neighbourhood_reference.parquet",
    "london_maps/crosswalk_lsoa21_to_neighbourhood.csv",
    "london_maps/crosswalk_lsoa21_to_neighbourhood_dq.json",
    "london_maps/data_for_app/indicator_source_inventory.csv",
    "london_maps/data_for_app/indicator_source_inventory.md",
    "london_maps/data_for_app/indicator_visualisation_guidance_final.csv",
    "london_maps/data_for_app/QOF/qof_indicator_catalog.csv",
)
IMD_SOURCE_KEYS = {"imd_2025"}
IMD_BREAKDOWN_VALUE_FIELDS = {
    "Education, Skills and Training Score",
    "Barriers to Housing and Services Score",
    "Living Environment Score",
}


@dataclass(frozen=True)
class BundleManifest:
    directories: tuple[str, ...]
    files: tuple[str, ...]

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "directories": list(self.directories),
            "files": list(self.files),
        }


def _catalog_frame(root_dir: Path) -> pd.DataFrame:
    catalog_path = root_dir / "data" / "processed" / "indicator_catalog.parquet"
    if not catalog_path.exists():
        return pd.DataFrame()
    return pd.read_parquet(catalog_path)


def _breakdown_runtime_source_keys(root_dir: Path) -> set[str]:
    catalog_df = _catalog_frame(root_dir)
    if catalog_df.empty or "source_key" not in catalog_df.columns:
        return set(IMD_SOURCE_KEYS)

    keys: set[str] = set()
    if "breakdown_groups_json" in catalog_df.columns:
        has_breakdown = catalog_df["breakdown_groups_json"].astype(str).fillna("").str.strip().ne("")
        keys.update(
            source_key
            for source_key in catalog_df.loc[has_breakdown, "source_key"].astype(str).str.strip().tolist()
            if source_key
        )

    if "value_field" in catalog_df.columns:
        needs_imd_source = catalog_df["value_field"].astype(str).fillna("").isin(IMD_BREAKDOWN_VALUE_FIELDS)
        keys.update(
            source_key
            for source_key in catalog_df.loc[needs_imd_source, "source_key"].astype(str).str.strip().tolist()
            if source_key
        )

    keys.update(IMD_SOURCE_KEYS)
    return keys


def _runtime_source_files(root_dir: Path) -> set[str]:
    source_files: set[str] = set()
    sources_cfg = load_sources_config().get("sources", {})
    for source_key in sorted(_breakdown_runtime_source_keys(root_dir)):
        source_cfg = sources_cfg.get(source_key, {})
        relative_path = str(source_cfg.get("path") or "").strip()
        if not relative_path:
            continue
        candidate = root_dir / relative_path
        if candidate.exists() and candidate.is_file():
            source_files.add(candidate.relative_to(root_dir).as_posix())
    return source_files


def build_runtime_bundle_manifest(root_dir: Path | None = None) -> BundleManifest:
    resolved_root = (root_dir or ROOT_DIR).resolve()

    directories = tuple(
        relative_path
        for relative_path in APP_RUNTIME_DIRECTORIES
        if (resolved_root / relative_path).exists()
    )
    files = set(
        relative_path
        for relative_path in APP_RUNTIME_FILES
        if (resolved_root / relative_path).exists()
    )
    files.update(_runtime_source_files(resolved_root))

    return BundleManifest(
        directories=directories,
        files=tuple(sorted(files)),
    )


def _copy_path(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True)
        return
    shutil.copy2(source, destination)


def export_runtime_bundle(output_dir: Path, root_dir: Path | None = None, force: bool = False) -> dict[str, object]:
    resolved_root = (root_dir or ROOT_DIR).resolve()
    resolved_output = output_dir.resolve()

    if resolved_output.exists():
        if not force:
            raise FileExistsError(f"{resolved_output} already exists. Use force=True to replace it.")
        shutil.rmtree(resolved_output)

    manifest = build_runtime_bundle_manifest(resolved_root)

    for relative_dir in manifest.directories:
        source = resolved_root / relative_dir
        destination = resolved_output / relative_dir
        _copy_path(source, destination)

    for relative_file in manifest.files:
        source = resolved_root / relative_file
        destination = resolved_output / relative_file
        _copy_path(source, destination)

    included_paths = [resolved_output / relative_dir for relative_dir in manifest.directories]
    included_paths.extend(resolved_output / relative_file for relative_file in manifest.files)
    total_bytes = sum(path.stat().st_size for path in resolved_output.rglob("*") if path.is_file())

    export_summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_root": str(resolved_root),
        "output_dir": str(resolved_output),
        "directory_count": len(manifest.directories),
        "file_count": len(manifest.files),
        "bundle_size_mb": round(total_bytes / 1024 / 1024, 1),
        **manifest.to_dict(),
    }
    (resolved_output / "community_cloud_bundle_manifest.json").write_text(
        json.dumps(export_summary, indent=2),
        encoding="utf-8",
    )
    return export_summary
