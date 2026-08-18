"""TEN Capital palette, type scale, and page geometry."""

from __future__ import annotations

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter

# --- palette -------------------------------------------------------------------------

DARK_BLUE = HexColor("#1F3864")
MED_BLUE = HexColor("#2E75B6")
LIGHT_BLUE = HexColor("#D5E8F0")

CRITICAL_FG = HexColor("#C00000")
CRITICAL_BG = HexColor("#FFCCCC")
HIGH_FG = HexColor("#7F6000")
HIGH_BG = HexColor("#FFF2CC")
POSITIVE_FG = HexColor("#375623")
POSITIVE_BG = HexColor("#E2EFDA")

RULE = HexColor("#BFBFBF")
BODY = HexColor("#000000")
MUTED = HexColor("#595959")
WHITE = HexColor("#FFFFFF")
ROW_TINT = HexColor("#F2F6FA")

#: Score bands drive every tile fill and the confidence chip.
BAND_GREEN = (POSITIVE_FG, POSITIVE_BG)
BAND_AMBER = (HIGH_FG, HIGH_BG)
BAND_RED = (CRITICAL_FG, CRITICAL_BG)

SEVERITY_COLORS = {
    "critical": BAND_RED,
    "high": BAND_AMBER,
    "medium": BAND_GREEN,
}

CATEGORY_LABELS = {
    "founder": "FOUNDER",
    "employee": "EMPLOYEE",
    "advisor": "ADVISOR",
    "board": "BOARD",
    "unclear": "UNCLEAR",
}

CATEGORY_COLORS = {
    "founder": (DARK_BLUE, LIGHT_BLUE),
    "employee": (MUTED, HexColor("#EDEDED")),
    "advisor": (HIGH_FG, HIGH_BG),
    "board": (MED_BLUE, HexColor("#E6F0F8")),
    "unclear": (CRITICAL_FG, CRITICAL_BG),
}


def band(value: int) -> tuple:
    """Score band: >=70 green, 40-69 amber, <40 red."""
    if value >= 70:
        return BAND_GREEN
    if value >= 40:
        return BAND_AMBER
    return BAND_RED


# --- type ----------------------------------------------------------------------------

FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
FONT_ITALIC = "Helvetica-Oblique"

TITLE_SIZE = 16.0
SECTION_SIZE = 8.0
BODY_SIZE_BASE = 8.5
BODY_SIZE_MIN = 7.5
MICRO_SIZE = 6.0
TILE_NUMBER_SIZE = 17.0

LEADING_RATIO = 1.24

# --- geometry ------------------------------------------------------------------------

PAGE_W, PAGE_H = letter  # 612 x 792
MARGIN = 36.0

X0 = MARGIN
X1 = PAGE_W - MARGIN
CONTENT_W = X1 - X0  # 540

Y_TOP = PAGE_H - MARGIN  # 756
GAP = 8.0

HEADER_H = 54.0
HEADER_TOP = Y_TOP
HEADER_BOTTOM = HEADER_TOP - HEADER_H  # 702

TILES_TOP = HEADER_BOTTOM - GAP  # 694
TILES_H = 50.0
TILES_BOTTOM = TILES_TOP - TILES_H  # 644
TILE_GAP = 6.0
TILE_COUNT = 5
TILE_W = (CONTENT_W - TILE_GAP * (TILE_COUNT - 1)) / TILE_COUNT

CHIPS_TOP = TILES_BOTTOM - GAP  # 636
CHIPS_H = 30.0  # label line + up to two chip rows
CHIPS_BOTTOM = CHIPS_TOP - CHIPS_H  # 614

BODY_TOP = CHIPS_BOTTOM - GAP  # 606

FOOTER_RULE_Y = 58.0
FOOTER_LINE1_Y = 47.0
FOOTER_LINE2_Y = 37.0

DILIGENCE_BOTTOM = 68.0
DILIGENCE_H_MIN = 46.0
DILIGENCE_H_MAX = 78.0

GUTTER = 14.0
LEFT_W = round((CONTENT_W - GUTTER) * 0.46)  # 242
RIGHT_W = CONTENT_W - GUTTER - LEFT_W  # 284
LEFT_X = X0
RIGHT_X = X0 + LEFT_W + GUTTER
