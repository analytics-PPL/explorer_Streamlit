from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from neighbourhood_explorer.ppt import (
    build_powerpoint_report as _build_powerpoint_report,
    generate_powerpoint_review_assets as _generate_powerpoint_review_assets,
    review_assets_available as _review_assets_available,
)


def powerpoint_available() -> bool:
    try:
        import pptx  # noqa: F401
    except ImportError:
        return False
    return True


def powerpoint_review_assets_available() -> bool:
    return _review_assets_available()


def build_powerpoint_report(
    *,
    selected_ids: list[str] | Iterable[str],
    indicator_ids: list[str],
    current_indicator_id: str,
    current_period: str,
    include_borough: bool,
    include_london: bool,
    include_overview_slide: bool = True,
    include_detail_tables: bool = True,
    include_methodology_slide: bool = True,
    report_title: str | None = None,
    configured_topics: list[str] | None = None,
    indicator_visual_overrides: dict[str, str] | None = None,
    indicator_visual_config_overrides: dict[str, dict[str, str]] | None = None,
) -> bytes:
    return _build_powerpoint_report(
        selected_ids=selected_ids,
        indicator_ids=indicator_ids,
        current_indicator_id=current_indicator_id,
        current_period=current_period,
        include_borough=include_borough,
        include_london=include_london,
        include_overview_slide=include_overview_slide,
        include_detail_tables=include_detail_tables,
        include_methodology_slide=include_methodology_slide,
        report_title=report_title,
        configured_topics=configured_topics,
        indicator_visual_overrides=indicator_visual_overrides,
        indicator_visual_config_overrides=indicator_visual_config_overrides,
    )


def generate_powerpoint_review_assets(
    *,
    output_dir: str | Path,
    pptx_bytes: bytes | None = None,
    pptx_path: str | Path | None = None,
    deck_name: str = "neighbourhood_report",
    thumbnail_size: int = 2048,
    contact_sheet_columns: int = 3,
):
    return _generate_powerpoint_review_assets(
        output_dir=output_dir,
        pptx_bytes=pptx_bytes,
        pptx_path=pptx_path,
        deck_name=deck_name,
        thumbnail_size=thumbnail_size,
        contact_sheet_columns=contact_sheet_columns,
    )
