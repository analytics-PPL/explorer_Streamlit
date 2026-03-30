from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


SYSTEM_NAME_BY_CODE = {
    "NCL": "North Central London",
    "NEL": "North East London",
    "NWL": "North West London",
    "SEL": "South East London",
    "SWL": "South West London",
}


@dataclass(frozen=True)
class FootprintLabel:
    kind: str
    label: str
    item_count: int
    exact_boundary: bool
    is_plural: bool

    @property
    def object_phrase(self) -> str:
        if self.kind == "region":
            return "London"
        if self.label.startswith("Selected "):
            return f"the {self.label.lower()}"
        return self.label


def selection_label(
    selected_ids: list[str] | list[int] | set[str] | set[int],
    reference_df: pd.DataFrame | None = None,
) -> str:
    return resolve_footprint_label(selected_ids, reference_df).label


def selection_object_phrase(
    selected_ids: list[str] | list[int] | set[str] | set[int],
    reference_df: pd.DataFrame | None = None,
) -> str:
    return resolve_footprint_label(selected_ids, reference_df).object_phrase


def resolve_footprint_label(
    selected_ids: list[str] | list[int] | set[str] | set[int],
    reference_df: pd.DataFrame | None = None,
) -> FootprintLabel:
    selected_set = {str(value).strip() for value in selected_ids if str(value).strip()}
    if not selected_set:
        return FootprintLabel(kind="neighbourhood", label="Selected neighbourhoods", item_count=0, exact_boundary=False, is_plural=True)

    reference = _reference_frame(reference_df)
    if reference.empty:
        if len(selected_set) == 1:
            return FootprintLabel(kind="neighbourhood", label="Selected neighbourhood", item_count=1, exact_boundary=False, is_plural=False)
        return FootprintLabel(kind="neighbourhood", label="Selected neighbourhoods", item_count=len(selected_set), exact_boundary=False, is_plural=True)

    reference = reference.copy()
    reference["neighbourhood_id"] = reference["neighbourhood_id"].astype(str)
    selected_meta = reference[reference["neighbourhood_id"].isin(selected_set)].copy()
    if selected_meta.empty:
        if len(selected_set) == 1:
            return FootprintLabel(kind="neighbourhood", label="Selected neighbourhood", item_count=1, exact_boundary=False, is_plural=False)
        return FootprintLabel(kind="neighbourhood", label="Selected neighbourhoods", item_count=len(selected_set), exact_boundary=False, is_plural=True)

    all_neighbourhood_ids = set(reference["neighbourhood_id"].astype(str))
    if selected_set == all_neighbourhood_ids:
        return FootprintLabel(kind="region", label="London", item_count=1, exact_boundary=True, is_plural=False)

    system_groups = _system_groups(reference)
    selected_system_codes = sorted(
        code for code, neighbourhood_ids in system_groups.items() if neighbourhood_ids and neighbourhood_ids.issubset(selected_set)
    )
    if selected_system_codes:
        system_union = set().union(*(system_groups[code] for code in selected_system_codes))
        if system_union == selected_set:
            if len(selected_system_codes) == 1:
                label = _system_name(selected_system_codes[0])
                return FootprintLabel(kind="system", label=label, item_count=1, exact_boundary=True, is_plural=False)
            return FootprintLabel(kind="system", label="Selected Systems", item_count=len(selected_system_codes), exact_boundary=True, is_plural=True)

    place_groups = _place_groups(reference)
    selected_place_codes = sorted(
        code for code, data in place_groups.items() if data["ids"] and data["ids"].issubset(selected_set)
    )
    if selected_place_codes:
        place_union = set().union(*(place_groups[code]["ids"] for code in selected_place_codes))
        if place_union == selected_set:
            place_names = sorted(place_groups[code]["name"] for code in selected_place_codes if place_groups[code]["name"])
            if len(place_names) == 1:
                return FootprintLabel(kind="place", label=place_names[0], item_count=1, exact_boundary=True, is_plural=False)
            if len(place_names) == 2:
                return FootprintLabel(kind="place", label=f"{place_names[0]} and {place_names[1]}", item_count=2, exact_boundary=True, is_plural=True)
            return FootprintLabel(kind="place", label="Selected Places", item_count=len(place_names), exact_boundary=True, is_plural=True)

    neighbourhood_names = sorted(selected_meta["neighbourhood_name"].dropna().astype(str).unique().tolist())
    if len(neighbourhood_names) == 1:
        return FootprintLabel(kind="neighbourhood", label=neighbourhood_names[0], item_count=1, exact_boundary=False, is_plural=False)
    return FootprintLabel(kind="neighbourhood", label="Selected neighbourhoods", item_count=len(neighbourhood_names), exact_boundary=False, is_plural=True)


def _reference_frame(reference_df: pd.DataFrame | None) -> pd.DataFrame:
    if isinstance(reference_df, pd.DataFrame):
        return reference_df
    from neighbourhood_explorer.data_access import load_neighbourhood_reference

    return load_neighbourhood_reference()


def _system_name(code: object) -> str:
    value = str(code).strip()
    return SYSTEM_NAME_BY_CODE.get(value, value)


def _split_multi_value(value: object) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    return [item.strip() for item in str(value).split(";") if item.strip()]


def _system_groups(reference_df: pd.DataFrame) -> dict[str, set[str]]:
    groups: dict[str, set[str]] = {}
    if "icb_code" not in reference_df.columns:
        return groups
    valid = reference_df.dropna(subset=["icb_code"]).copy()
    valid["icb_code"] = valid["icb_code"].astype(str)
    for code, group in valid.groupby("icb_code"):
        groups[str(code)] = set(group["neighbourhood_id"].astype(str))
    return groups


def _place_groups(reference_df: pd.DataFrame) -> dict[str, dict[str, object]]:
    groups: dict[str, dict[str, object]] = {}
    if "borough_code" not in reference_df.columns or "borough_name" not in reference_df.columns:
        return groups
    for row in reference_df[["neighbourhood_id", "borough_code", "borough_name"]].drop_duplicates().itertuples(index=False):
        codes = _split_multi_value(row.borough_code)
        names = _split_multi_value(row.borough_name)
        if not codes and not names:
            continue
        code_name_pairs = zip(codes, names, strict=False) if len(codes) == len(names) else ((code, names[0] if names else "") for code in codes)
        for code, name in code_name_pairs:
            clean_code = str(code).strip()
            clean_name = str(name).strip()
            if not clean_code and not clean_name:
                continue
            key = clean_code or clean_name
            groups.setdefault(key, {"name": clean_name or clean_code, "ids": set()})
            groups[key]["ids"].add(str(row.neighbourhood_id))
            if clean_name:
                groups[key]["name"] = clean_name
    return groups
