"""Centralised color palette for the London Neighbourhood Explorer.

Import from here instead of hardcoding hex values across chart, map,
and template modules.
"""

from __future__ import annotations

# ── Primary brand ──
PURPLE = "#532380"
PURPLE_LIGHT = "#6b3a9e"
PURPLE_DARK = "#2a1245"
PURPLE_MUTED = "#c8bfd6"

# ── NHS / public sector ──
NHS_BLUE = "#005eb8"
NHS_DARK_BLUE = "#003087"

# ── Semantic ──
SUCCESS = "#007f3b"
CAUTION = "#d4351c"

# ── Chart palettes ──
COMPARISON_PALETTE = {
    "selection": PURPLE,
    "borough": NHS_BLUE,
    "london": NHS_BLUE,
}

CATEGORY_PALETTE = [
    PURPLE,
    NHS_BLUE,
    SUCCESS,
    "#c2410c",
    "#7c3aed",
    "#0f766e",
    "#be185d",
    "#ca8a04",
]

# ── Map colors ──
MAP_SELECTED_FILL = PURPLE
MAP_SELECTED_BORDER = PURPLE_DARK
MAP_UNSELECTED_FILL = "#CBD5E1"
