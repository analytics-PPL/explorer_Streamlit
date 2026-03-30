from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from neighbourhood_explorer.paths import (
    CATEGORIES_CONFIG_PATH,
    FINGERTIPS_CURATION_CONFIG_PATH,
    INDICATORS_CONFIG_PATH,
    QOF_INDICATOR_CATALOG_PATH,
    SOURCE_HIERARCHY_CONFIG_PATH,
    SOURCES_CONFIG_PATH,
    VISUALISATIONS_CONFIG_PATH,
)


def _parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if value == "":
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    lower = value.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    return value


def _load_simple_yaml(path: Path) -> Any:
    lines = path.read_text(encoding="utf-8").splitlines()
    cleaned = [line.rstrip("\n") for line in lines if line.strip() and not line.lstrip().startswith("#")]
    if not cleaned:
        return {}

    if path.name == "indicators.yml":
        root: dict[str, Any] = {}
        current_list_key: str | None = None
        current_item: dict[str, Any] | None = None
        current_nested_list_key: str | None = None
        for line in cleaned:
            indent = len(line) - len(line.lstrip(" "))
            stripped = line.strip()
            if indent == 0 and stripped.endswith(":"):
                current_list_key = stripped[:-1]
                root[current_list_key] = []
                continue
            if indent == 2 and stripped.startswith("- "):
                current_item = {}
                root[current_list_key].append(current_item)
                current_nested_list_key = None
                payload = stripped[2:]
                if ":" in payload:
                    key, value = payload.split(":", 1)
                    current_item[key.strip()] = _parse_scalar(value)
                continue
            if indent == 4 and current_item is not None:
                if stripped.endswith(":") and ": " not in stripped:
                    current_nested_list_key = stripped[:-1]
                    current_item[current_nested_list_key] = []
                else:
                    key, value = stripped.split(":", 1)
                    current_item[key.strip()] = _parse_scalar(value)
                    current_nested_list_key = None
                continue
            if indent == 6 and stripped.startswith("- ") and current_item is not None and current_nested_list_key is not None:
                current_item[current_nested_list_key].append(_parse_scalar(stripped[2:]))
        return root

    if path.name == "sources.yml":
        root: dict[str, Any] = {}
        current_top_key: str | None = None
        current_mapping_key: str | None = None
        current_nested_list_key: str | None = None
        for line in cleaned:
            indent = len(line) - len(line.lstrip(" "))
            stripped = line.strip()
            if indent == 0 and stripped.endswith(":"):
                current_top_key = stripped[:-1]
                root[current_top_key] = {}
                continue
            if indent == 2 and stripped.endswith(":"):
                current_mapping_key = stripped[:-1]
                root[current_top_key][current_mapping_key] = {}
                current_nested_list_key = None
                continue
            if indent == 4 and current_mapping_key is not None:
                if stripped.endswith(":") and ": " not in stripped:
                    current_nested_list_key = stripped[:-1]
                    root[current_top_key][current_mapping_key][current_nested_list_key] = []
                else:
                    key, value = stripped.split(":", 1)
                    root[current_top_key][current_mapping_key][key.strip()] = _parse_scalar(value)
                    current_nested_list_key = None
                continue
            if indent == 6 and stripped.startswith("- ") and current_nested_list_key is not None and current_mapping_key is not None:
                root[current_top_key][current_mapping_key][current_nested_list_key].append(_parse_scalar(stripped[2:]))
        return root

    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_yaml(path) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)
    except yaml.YAMLError:
        return _load_simple_yaml(Path(path))


def _load_generated_indicator_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    if frame.empty:
        return []
    frame = frame.replace("", None)
    if "review_required" in frame.columns:
        frame["review_required"] = frame["review_required"].map(lambda value: str(value).strip().lower() == "true")
    return frame.to_dict(orient="records")


@lru_cache(maxsize=1)
def load_sources_config() -> dict[str, Any]:
    return _load_yaml(SOURCES_CONFIG_PATH) or {}


@lru_cache(maxsize=1)
def load_source_hierarchy_config() -> dict[str, Any]:
    return _load_yaml(SOURCE_HIERARCHY_CONFIG_PATH) or {}


@lru_cache(maxsize=1)
def load_indicator_catalog() -> list[dict[str, Any]]:
    data = _load_yaml(INDICATORS_CONFIG_PATH) or {}
    indicators = data.get("indicators", [])
    if not isinstance(indicators, list):
        raise ValueError("config/indicators.yml must contain an 'indicators' list.")
    generated = _load_generated_indicator_rows(QOF_INDICATOR_CATALOG_PATH)
    return indicators + generated


@lru_cache(maxsize=1)
def load_categories_config() -> dict[str, Any]:
    return _load_yaml(CATEGORIES_CONFIG_PATH) or {}


@lru_cache(maxsize=1)
def load_visualisations_config() -> dict[str, Any]:
    return _load_yaml(VISUALISATIONS_CONFIG_PATH) or {}


@lru_cache(maxsize=1)
def load_fingertips_curation_config() -> dict[str, Any]:
    return _load_yaml(FINGERTIPS_CURATION_CONFIG_PATH) or {}
