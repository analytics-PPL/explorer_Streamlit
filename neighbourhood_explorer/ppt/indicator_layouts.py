from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

from pptx.util import Inches

from .style_tokens import PptTheme, THEME


@dataclass(frozen=True)
class Box:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def area(self) -> int:
        return max(0, self.width) * max(0, self.height)

    def inset(self, padding: int) -> Box:
        safe_padding = max(0, padding)
        return Box(
            self.left + safe_padding,
            self.top + safe_padding,
            max(0, self.width - safe_padding * 2),
            max(0, self.height - safe_padding * 2),
        )


@dataclass(frozen=True)
class TextBlockSpec:
    text: str
    min_font_size: int
    max_font_size: int
    max_lines: int
    allow_truncation: bool = True
    priority: str = "body"


@dataclass
class IndicatorSlideContent:
    slide_id: str
    title: str
    display_title: str
    full_title: str
    subtitle: str
    visual_type: str
    visual_is_weak: bool
    primary_note: str
    secondary_note: str
    footer_note: str
    footer_meta: str
    kpi_cards: list[dict[str, Any]]
    has_borough_benchmark: bool
    has_london_benchmark: bool
    visual_aspect_ratio: float | None = None

    @property
    def title_length(self) -> int:
        return len(self.display_title or self.title)

    @property
    def subtitle_length(self) -> int:
        return len(self.subtitle)

    @property
    def primary_length(self) -> int:
        return len(self.primary_note)

    @property
    def secondary_length(self) -> int:
        return len(self.secondary_note)

    @property
    def footer_length(self) -> int:
        return len(self.footer_note)

    @property
    def kpi_count(self) -> int:
        return len(self.kpi_cards)


@dataclass
class LayoutPlan:
    variant: str
    title_box: Box
    subtitle_box: Box
    kpi_boxes: list[Box]
    visual_box: Box
    primary_narrative_box: Box | None
    secondary_narrative_box: Box | None
    merged_narrative_box: Box | None
    footer_band_box: Box
    footer_note_box: Box
    footer_meta_box: Box
    title_spec: TextBlockSpec
    subtitle_spec: TextBlockSpec
    primary_spec: TextBlockSpec | None
    secondary_spec: TextBlockSpec | None
    merged_spec: TextBlockSpec | None
    footer_spec: TextBlockSpec
    footer_meta_spec: TextBlockSpec
    debug: dict[str, Any] = field(default_factory=dict)

    def occupied_boxes(self) -> list[tuple[str, Box]]:
        boxes: list[tuple[str, Box]] = [
            ("title", self.title_box),
            ("subtitle", self.subtitle_box),
            ("visual", self.visual_box),
            ("footer_band", self.footer_band_box),
            ("footer_note", self.footer_note_box),
            ("footer_meta", self.footer_meta_box),
        ]
        boxes.extend((f"kpi_{index}", box) for index, box in enumerate(self.kpi_boxes))
        if self.primary_narrative_box is not None:
            boxes.append(("primary_narrative", self.primary_narrative_box))
        if self.secondary_narrative_box is not None:
            boxes.append(("secondary_narrative", self.secondary_narrative_box))
        if self.merged_narrative_box is not None:
            boxes.append(("merged_narrative", self.merged_narrative_box))
        return boxes


@dataclass
class ValidationResult:
    slide_id: str
    warnings: list[str] = field(default_factory=list)
    fullness_score: float = 1.0

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)


def choose_indicator_layout(
    content: IndicatorSlideContent,
    theme: PptTheme = THEME,
    *,
    force_variant: str | None = None,
) -> LayoutPlan:
    standards = theme.layout
    inner_width = theme.slide_width - 2 * theme.margin_x
    header_heavy = content.title_length > 84 or content.subtitle_length > 90
    long_narrative = max(content.primary_length, content.secondary_length) > 165 or (content.primary_length + content.secondary_length) > 265
    long_footer = content.footer_length > standards.max_footer_note_chars
    sparse_comparison = (
        content.visual_type == "comparison"
        and content.kpi_count <= 1
        and not content.has_borough_benchmark
        and not content.has_london_benchmark
    )
    narrative_heavy = header_heavy or long_narrative or long_footer or (content.visual_is_weak and content.visual_type == "comparison")

    variant = "comparison"
    if force_variant:
        variant = force_variant
    elif content.visual_type == "map":
        variant = "map"
    elif content.visual_type == "trend":
        variant = "trend"
    elif narrative_heavy or sparse_comparison:
        variant = "narrative_heavy"

    title_height = Inches(0.56)
    subtitle_height = Inches(0.26)
    if variant == "narrative_heavy":
        title_height = Inches(0.82)
        subtitle_height = Inches(0.42)
    elif header_heavy:
        title_height = Inches(0.7)
        subtitle_height = Inches(0.34)
    elif variant == "trend" and content.subtitle_length > 78:
        title_height = Inches(0.66)
        subtitle_height = Inches(0.36)

    title_box = Box(theme.margin_x, Inches(0.74), Inches(9.3), title_height)
    subtitle_box = Box(theme.margin_x, title_box.bottom + Inches(0.04), Inches(10.0), subtitle_height)

    kpi_top = subtitle_box.bottom + standards.section_gap
    kpi_height = standards.kpi_row_height_compact if variant in {"trend", "narrative_heavy"} else standards.kpi_row_height
    kpi_boxes = _kpi_boxes(content.kpi_count, kpi_top, kpi_height, theme)

    footer_band_box = Box(
        theme.margin_x,
        theme.slide_height - standards.footer_band_height - Inches(0.22),
        inner_width,
        standards.footer_band_height,
    )
    footer_note_width = int(inner_width * standards.footer_note_width_ratio)
    footer_note_box = Box(theme.margin_x, footer_band_box.top + Inches(0.02), footer_note_width, footer_band_box.height)
    footer_meta_box = Box(
        footer_note_box.right + standards.grid_gap,
        footer_band_box.top + Inches(0.02),
        max(0, inner_width - footer_note_width - standards.grid_gap),
        footer_band_box.height,
    )

    body_top = kpi_top + kpi_height + standards.section_gap
    body_height = max(standards.visual_min_height, footer_band_box.top - body_top - standards.section_gap)

    visual_height = min(standards.visual_max_height, max(standards.visual_min_height, int(body_height * 0.62)))
    primary_box: Box | None = None
    secondary_box: Box | None = None
    merged_box: Box | None = None

    if variant == "map":
        map_ratio = content.visual_aspect_ratio or 1.93
        visual_height = min(standards.visual_max_height, max(standards.map_min_height, body_height))
        effective_map_height = max(standards.visual_min_height, visual_height - standards.map_reserved_height)
        desired_width = int(effective_map_height * map_ratio + standards.map_reserved_width + standards.grid_gap)
        visual_width = min(inner_width, max(standards.map_min_width, desired_width))
        visual_left = int(theme.margin_x + max(0, (inner_width - visual_width) / 2))
        visual_box = Box(visual_left, body_top, visual_width, visual_height)
    elif variant == "trend":
        visual_height = min(standards.visual_max_height, max(standards.visual_min_height, body_height))
        visual_box = Box(theme.margin_x, body_top, inner_width, max(standards.visual_min_height, visual_height))
    elif variant == "narrative_heavy":
        visual_height = min(standards.visual_max_height, max(standards.visual_min_height, body_height))
        visual_box = Box(theme.margin_x, body_top, inner_width, max(standards.visual_min_height, visual_height))
    else:
        visual_box = Box(
            theme.margin_x,
            body_top,
            inner_width,
            max(standards.visual_min_height, min(standards.visual_max_height, body_height)),
        )

    title_spec = TextBlockSpec(
        text=content.display_title or content.title,
        min_font_size=theme.layout.title_min_font,
        max_font_size=theme.layout.title_max_font,
        max_lines=theme.layout.max_title_lines,
        allow_truncation=True,
        priority="title",
    )
    subtitle_spec = TextBlockSpec(
        text=content.subtitle,
        min_font_size=theme.layout.caption_min_font,
        max_font_size=11,
        max_lines=theme.layout.max_subtitle_lines,
        allow_truncation=True,
        priority="subtitle",
    )
    primary_spec = None if primary_box is None else TextBlockSpec(
        text=content.primary_note,
        min_font_size=theme.layout.body_min_font,
        max_font_size=theme.layout.body_max_font,
        max_lines=5 if variant in {"map", "comparison"} else 6,
        allow_truncation=False,
    )
    secondary_spec = None if secondary_box is None else TextBlockSpec(
        text=content.secondary_note,
        min_font_size=theme.layout.body_min_font,
        max_font_size=theme.layout.body_max_font,
        max_lines=5 if variant in {"map", "comparison"} else 6,
        allow_truncation=False,
    )
    merged_text = f"{content.primary_note} {content.secondary_note}".strip()
    merged_spec = None if merged_box is None else TextBlockSpec(
        text=merged_text,
        min_font_size=theme.layout.body_min_font,
        max_font_size=theme.layout.body_max_font,
        max_lines=7 if variant == "narrative_heavy" else 6,
        allow_truncation=False,
    )
    footer_spec = TextBlockSpec(
        text=content.footer_note,
        min_font_size=theme.layout.caption_min_font,
        max_font_size=theme.layout.caption_max_font,
        max_lines=2,
        allow_truncation=True,
        priority="footer",
    )
    footer_meta_spec = TextBlockSpec(
        text=content.footer_meta,
        min_font_size=theme.layout.caption_min_font,
        max_font_size=theme.layout.caption_max_font,
        max_lines=2,
        allow_truncation=True,
        priority="footer",
    )

    return LayoutPlan(
        variant=variant,
        title_box=title_box,
        subtitle_box=subtitle_box,
        kpi_boxes=kpi_boxes,
        visual_box=visual_box,
        primary_narrative_box=primary_box,
        secondary_narrative_box=secondary_box,
        merged_narrative_box=merged_box,
        footer_band_box=footer_band_box,
        footer_note_box=footer_note_box,
        footer_meta_box=footer_meta_box,
        title_spec=title_spec,
        subtitle_spec=subtitle_spec,
        primary_spec=primary_spec,
        secondary_spec=secondary_spec,
        merged_spec=merged_spec,
        footer_spec=footer_spec,
        footer_meta_spec=footer_meta_spec,
        debug={
            "title_length": content.title_length,
            "subtitle_length": content.subtitle_length,
            "header_heavy": header_heavy,
            "primary_length": content.primary_length,
            "secondary_length": content.secondary_length,
            "footer_length": content.footer_length,
            "visual_type": content.visual_type,
            "visual_is_weak": content.visual_is_weak,
            "kpi_count": content.kpi_count,
            "has_borough_benchmark": content.has_borough_benchmark,
            "has_london_benchmark": content.has_london_benchmark,
            "sparse_comparison": sparse_comparison,
            "forced_variant": force_variant or "",
        },
    )


def score_slide_fullness(plan: LayoutPlan, theme: PptTheme = THEME) -> float:
    available = (theme.slide_width - 2 * theme.margin_x) * (theme.slide_height - Inches(0.9))
    occupied = sum(box.area for _, box in plan.occupied_boxes())
    if available <= 0:
        return 1.0
    return min(1.0, occupied / available)


def validate_slide_layout(
    content: IndicatorSlideContent,
    plan: LayoutPlan,
    *,
    text_results: dict[str, Any] | None = None,
    visual_placement: Any | None = None,
    theme: PptTheme = THEME,
) -> ValidationResult:
    result = ValidationResult(slide_id=content.slide_id)
    result.fullness_score = score_slide_fullness(plan, theme=theme)
    available_text_results = text_results or {}

    for name, box in plan.occupied_boxes():
        if box.left < 0 or box.top < 0 or box.right > theme.slide_width or box.bottom > theme.slide_height:
            result.add_warning(f"{name} exceeds slide bounds.")

    expected_text_regions = {
        "title": plan.title_box,
        "subtitle": plan.subtitle_box,
        "footer_note": plan.footer_note_box,
        "footer_meta": plan.footer_meta_box,
    }
    if plan.primary_narrative_box is not None:
        expected_text_regions["primary_narrative"] = plan.primary_narrative_box
    if plan.secondary_narrative_box is not None:
        expected_text_regions["secondary_narrative"] = plan.secondary_narrative_box
    if plan.merged_narrative_box is not None:
        expected_text_regions["merged_narrative"] = plan.merged_narrative_box
    for key in expected_text_regions:
        if key not in available_text_results:
            result.add_warning(f"{key} content was not rendered for the chosen layout.")
    for index, _ in enumerate(plan.kpi_boxes):
        if not any(key.startswith(f"kpi_{index}_") for key in available_text_results):
            result.add_warning(f"kpi_{index} content was not rendered for the chosen layout.")

    overlap_candidates = [(name, box) for name, box in plan.occupied_boxes() if name not in {"footer_band"}]
    for (left_name, left_box), (right_name, right_box) in combinations(overlap_candidates, 2):
        if left_name.startswith("kpi_") and right_name.startswith("kpi_"):
            continue
        if _boxes_overlap(left_box, right_box):
            result.add_warning(f"{left_name} overlaps {right_name}.")

    for name, fit in available_text_results.items():
        if bool(getattr(fit, "overflow", False)):
            result.add_warning(f"{name} is estimated to overflow its box.")
        if int(getattr(fit, "font_size_pt", theme.layout.body_min_font)) < theme.layout.caption_min_font:
            result.add_warning(f"{name} fell below the minimum readable size.")
        if name == "title" and int(getattr(fit, "line_count", 0)) > theme.layout.max_title_lines:
            result.add_warning("Title exceeds the maximum line count.")

    fill_ratio = None
    visual_debug = {}
    if visual_placement is None:
        result.add_warning("Visual content was not rendered for the chosen layout.")
    if visual_placement is not None:
        box = getattr(visual_placement, "box", None) or getattr(visual_placement, "visual_box", None)
        if box is not None and (box.left < 0 or box.top < 0 or box.right > theme.slide_width or box.bottom > theme.slide_height):
            result.add_warning("Visual placement exceeds slide bounds.")
        if getattr(visual_placement, "distorted", False):
            result.add_warning("Visual aspect ratio was distorted.")
        fill_ratio = getattr(visual_placement, "rendered_content_ratio", None)
        visual_debug = getattr(visual_placement, "debug", {}) or {}
        if fill_ratio is None and box is not None and plan.visual_box.area > 0:
            fill_ratio = box.area / plan.visual_box.area
        if content.visual_type == "map" and fill_ratio is not None and fill_ratio < theme.layout.map_fill_warn_threshold:
            result.add_warning("Map content uses too little of the available frame.")

    relaxed_fullness = (
        fill_ratio is not None
        and fill_ratio >= theme.layout.strong_visual_fill_threshold
        and content.visual_type in {"map", "trend"}
    )
    if result.fullness_score < theme.layout.fullness_warn_threshold and not relaxed_fullness:
        result.add_warning(f"Slide fullness score is low ({result.fullness_score:.2f}).")

    if (
        content.visual_type == "comparison"
        and content.kpi_count <= 1
        and not content.has_borough_benchmark
        and not content.has_london_benchmark
        and getattr(visual_placement, "fallback_used", "") != "context_strip"
    ):
        result.add_warning("Comparison slide has limited benchmark context and may feel sparse.")
    if content.visual_type == "comparison":
        row_count = int(visual_debug.get("row_count", 0) or 0)
        row_spacing_inches = float(visual_debug.get("row_spacing_inches", 0.0) or 0.0)
        label_compacted = bool(visual_debug.get("label_compacted", False))
        if (
            row_count >= theme.layout.comparison_warn_row_threshold
            and row_spacing_inches < 0.34
            and not label_compacted
        ):
            result.add_warning("Comparison visual is dense and may need more label compaction.")
    if (
        content.visual_type == "trend"
        and content.visual_is_weak
        and (
            fill_ratio is None
            or fill_ratio < theme.layout.strong_visual_fill_threshold
            or result.fullness_score < theme.layout.fullness_warn_threshold
        )
    ):
        result.add_warning("Trend chart has limited time points and should be reviewed for visual density.")
    if content.visual_type == "trend":
        visible_series_count = int(visual_debug.get("visible_series_count", 0) or 0)
        max_series_label_chars = int(visual_debug.get("max_series_label_chars", 0) or 0)
        legend_compacted = bool(visual_debug.get("legend_compacted", False))
        if (
            visible_series_count >= theme.layout.trend_warn_series_threshold
            and max_series_label_chars > theme.layout.trend_compact_legend_chars
            and not legend_compacted
        ):
            result.add_warning("Trend legend is likely to feel crowded.")

    if content.visual_is_weak and plan.variant not in {"narrative_heavy", "trend"}:
        result.add_warning("Weak visual content did not trigger a visual-priority fallback layout.")
    return result


def _kpi_boxes(count: int, top: int, height: int, theme: PptTheme) -> list[Box]:
    if count <= 0:
        return []
    available_width = theme.slide_width - 2 * theme.margin_x
    gap = theme.layout.grid_gap
    desired_width = (available_width - gap * (count - 1)) / count
    card_width = int(min(theme.layout.max_kpi_card_width, max(theme.layout.min_kpi_card_width, desired_width)))
    total_width = card_width * count + gap * (count - 1)
    left = int(theme.margin_x + max(0, (available_width - total_width) / 2))
    return [
        Box(left + index * (card_width + gap), top, card_width, height)
        for index in range(count)
    ]


def _split_narrative_boxes(
    *,
    top: int,
    width: int,
    height: int,
    primary_length: int,
    secondary_length: int,
    theme: PptTheme,
) -> tuple[Box, Box]:
    gap = theme.layout.grid_gap
    total = max(1, primary_length + secondary_length)
    primary_share = min(0.62, max(0.38, primary_length / total))
    primary_width = int((width - gap) * primary_share)
    secondary_width = max(0, width - gap - primary_width)
    return (
        Box(theme.margin_x, top, primary_width, height),
        Box(theme.margin_x + primary_width + gap, top, secondary_width, height),
    )


def _boxes_overlap(left: Box, right: Box) -> bool:
    return not (
        left.right <= right.left
        or right.right <= left.left
        or left.bottom <= right.top
        or right.bottom <= left.top
    )
