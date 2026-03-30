from __future__ import annotations

from dataclasses import dataclass, field

from pptx.dml.color import RGBColor
from pptx.util import Inches


def rgb(red: int, green: int, blue: int) -> RGBColor:
    return RGBColor(red, green, blue)


@dataclass(frozen=True)
class PptLayoutStandards:
    grid_gap: int = Inches(0.14)
    section_gap: int = Inches(0.18)
    title_min_font: int = 16
    title_max_font: int = 24
    body_min_font: int = 9
    body_max_font: int = 12
    caption_min_font: int = 8
    caption_max_font: int = 10
    max_title_lines: int = 3
    max_subtitle_lines: int = 2
    footer_band_height: int = Inches(0.44)
    footer_note_width_ratio: float = 0.72
    kpi_row_height: int = Inches(0.94)
    kpi_row_height_compact: int = Inches(0.82)
    visual_min_height: int = Inches(2.2)
    visual_max_height: int = Inches(4.5)
    map_min_height: int = Inches(3.35)
    map_min_width: int = Inches(4.8)
    map_reserved_width: int = Inches(0.24)
    map_reserved_height: int = Inches(0.74)
    map_fill_warn_threshold: float = 0.42
    strong_visual_fill_threshold: float = 0.78
    trend_min_height: int = Inches(3.75)
    trend_dense_series_threshold: int = 4
    trend_compact_legend_chars: int = 18
    trend_warn_series_threshold: int = 5
    comparison_dense_row_threshold: int = 5
    comparison_warn_row_threshold: int = 7
    comparison_label_soft_chars: int = 28
    comparison_label_hard_chars: int = 40
    narrative_min_height: int = Inches(0.68)
    narrative_max_height: int = Inches(1.35)
    panel_inner_padding: int = Inches(0.12)
    visual_padding: int = Inches(0.16)
    min_kpi_card_width: int = Inches(2.45)
    max_kpi_card_width: int = Inches(4.2)
    max_footer_note_chars: int = 160
    max_note_chars: int = 220
    max_display_title_chars: int = 110
    fullness_warn_threshold: float = 0.62


@dataclass(frozen=True)
class PptTheme:
    slide_width: int = Inches(13.333)
    slide_height: int = Inches(7.5)
    margin_x: int = Inches(0.48)
    margin_y: int = Inches(0.38)
    gutter: int = Inches(0.2)
    font_family: str = "Poppins"
    font_family_bold: str = "Poppins SemiBold"
    text: RGBColor = rgb(33, 43, 50)
    muted: RGBColor = rgb(76, 98, 114)
    navy: RGBColor = rgb(83, 35, 128)
    blue: RGBColor = rgb(0, 94, 184)
    teal: RGBColor = rgb(65, 182, 230)
    orange: RGBColor = rgb(0, 94, 184)
    gold: RGBColor = rgb(107, 58, 158)
    green: RGBColor = rgb(0, 127, 59)
    red: RGBColor = rgb(212, 53, 28)
    line: RGBColor = rgb(224, 214, 236)
    soft_line: RGBColor = rgb(240, 236, 244)
    background: RGBColor = rgb(248, 248, 250)
    surface: RGBColor = rgb(255, 255, 255)
    surface_alt: RGBColor = rgb(245, 242, 248)
    surface_tint: RGBColor = rgb(240, 236, 244)
    layout: PptLayoutStandards = field(default_factory=PptLayoutStandards)
    category_colours: dict[str, RGBColor] = field(
        default_factory=lambda: {
            "Population & Demography": rgb(83, 35, 128),
            "Health & Wellbeing": rgb(0, 94, 184),
            "Social Factors & Wider Determinants": rgb(107, 58, 158),
            "Safety & Crime": rgb(212, 53, 28),
            "Environment & Access": rgb(0, 127, 59),
        }
    )

    def category_accent(self, category: str | None) -> RGBColor:
        if not category:
            return self.blue
        return self.category_colours.get(str(category), self.blue)


THEME = PptTheme()
