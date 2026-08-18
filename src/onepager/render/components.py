"""Page furniture: header band, stat tiles, chips, roster table, finding rows."""

from __future__ import annotations

from xml.sax.saxutils import escape

from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from ..config import BRAND_NAME, FOOTER_TAGLINE
from ..models import Citation, Finding, TeamAnalysis, TeamMember
from ..util.fitting import FitConfig, first_sentence
from . import theme as t


def esc(text: str) -> str:
    return escape(text or "")


def hx(color) -> str:
    """ReportLab inline markup needs a #rrggbb literal, not a bare hex string."""
    return "#" + color.hexval()[2:]


def _chip(label: str, fg, bg) -> str:
    """Inline pill. Non-breaking spaces keep the padding from collapsing at a wrap."""
    return (
        f'<font size="5.6" face="{t.FONT_BOLD}" color="{hx(fg)}" '
        f'backColor="{hx(bg)}">&nbsp;{escape(label)}&nbsp;</font>'
    )


def _outlined_chip(label: str, fg) -> str:
    return (
        f'<font size="5.6" face="{t.FONT_BOLD}" color="{hx(fg)}">'
        f"[{escape(label)}]</font>"
    )


def cite_markup(citations: list[Citation]) -> str:
    """Trailing superscript slide references, deduped and ordered."""
    if not citations:
        return ""
    slides = sorted({c.slide for c in citations if c.slide > 0})
    if not slides:
        return ""
    joined = ",".join(str(s) for s in slides)
    return (
        f'<super><font size="5" color="{hx(t.MUTED)}">'
        f"&nbsp;s.{joined}</font></super>"
    )


# --- paragraph styles ------------------------------------------------------------------


def styles(cfg: FitConfig) -> dict[str, ParagraphStyle]:
    size = cfg.body_size
    lead = size * t.LEADING_RATIO * cfg.spacing_scale
    return {
        "section": ParagraphStyle(
            "section",
            fontName=t.FONT_BOLD,
            fontSize=t.SECTION_SIZE,
            leading=t.SECTION_SIZE * 1.2,
            textColor=t.DARK_BLUE,
            spaceAfter=3 * cfg.spacing_scale,
            alignment=TA_LEFT,
        ),
        "body": ParagraphStyle(
            "body", fontName=t.FONT, fontSize=size, leading=lead, textColor=t.BODY
        ),
        "finding": ParagraphStyle(
            "finding",
            fontName=t.FONT,
            fontSize=size,
            leading=lead,
            textColor=t.BODY,
            spaceAfter=4 * cfg.spacing_scale,
        ),
        "gap": ParagraphStyle(
            "gap",
            fontName=t.FONT,
            fontSize=size,
            leading=lead,
            textColor=t.BODY,
            leftIndent=8,
            firstLineIndent=-8,
            spaceAfter=2 * cfg.spacing_scale,
        ),
        "cell": ParagraphStyle(
            "cell",
            fontName=t.FONT,
            fontSize=max(size - 0.5, 6.5),
            leading=max(size - 0.5, 6.5) * 1.18,
            textColor=t.BODY,
        ),
        "micro": ParagraphStyle(
            "micro",
            fontName=t.FONT,
            fontSize=t.MICRO_SIZE,
            leading=t.MICRO_SIZE * 1.2,
            textColor=t.MUTED,
        ),
        "dq": ParagraphStyle(
            "dq",
            fontName=t.FONT,
            fontSize=7.4,
            leading=8.8,
            textColor=t.BODY,
            leftIndent=10,
            firstLineIndent=-10,
        ),
    }


def _shrink_to_fit(c, text: str, width: float, font: str, start: float, floor: float) -> float:
    size = start
    while size > floor and c.stringWidth(text, font, size) > width:
        size -= 0.2
    return size


def _ellipsize(c, text: str, width: float, font: str, size: float) -> str:
    if c.stringWidth(text, font, size) <= width:
        return text
    trimmed = text
    while trimmed and c.stringWidth(trimmed + "...", font, size) > width:
        trimmed = trimmed[:-1]
    return trimmed.rstrip(" ,;:") + "..."


# --- canvas furniture --------------------------------------------------------------------


def draw_header(c, analysis: TeamAnalysis, deck_name: str, date_str: str) -> None:
    top, bottom = t.HEADER_TOP, t.HEADER_BOTTOM
    c.setFillColor(t.DARK_BLUE)
    c.rect(t.X0, bottom, 4, top - bottom, stroke=0, fill=1)

    text_x = t.X0 + 12
    c.setFillColor(t.DARK_BLUE)
    c.setFont(t.FONT_BOLD, t.TITLE_SIZE)
    c.drawString(text_x, top - 15, analysis.company_name[:52])

    c.setFillColor(t.MUTED)
    c.setFont(t.FONT_BOLD, 7.2)
    c.drawString(text_x, top - 25, "FOUNDER & TEAM ONE-PAGER")

    right_lines = [
        analysis.stage_and_raise or "Stage not stated in deck",
        analysis.sector or "Sector not stated in deck",
        f"{deck_name}  ·  {date_str}",
    ]
    c.setFillColor(t.MUTED)
    name_w = c.stringWidth(analysis.company_name[:52], t.FONT_BOLD, t.TITLE_SIZE)
    meta_w = t.CONTENT_W - 12 - name_w - 14
    for i, line in enumerate(right_lines):
        size = _shrink_to_fit(c, line, meta_w, t.FONT, 7.0, 5.4)
        c.setFont(t.FONT, size)
        c.drawRightString(t.X1, top - 12 - i * 9, _ellipsize(c, line, meta_w, t.FONT, size))

    # One-line business sits on its own baseline under the title block.
    style = ParagraphStyle(
        "hb", fontName=t.FONT, fontSize=8.5, leading=10, textColor=t.BODY
    )
    para = Paragraph(esc(analysis.one_line_business), style)
    w, h = para.wrap(t.CONTENT_W - 16, 24)
    para.drawOn(c, text_x, bottom + 5)

    c.setStrokeColor(t.RULE)
    c.setLineWidth(0.6)
    c.line(t.X0, bottom - 2, t.X1, bottom - 2)


def _tile(c, x: float, y: float, w: float, h: float, value: int, label: str, sub: str | None):
    fg, bg = t.band(value)
    c.setFillColor(bg)
    c.rect(x, y, w, h, stroke=0, fill=1)
    c.setStrokeColor(fg)
    c.setLineWidth(0.5)
    c.rect(x, y, w, h, stroke=1, fill=0)

    c.setFillColor(fg)
    c.setFont(t.FONT_BOLD, t.TILE_NUMBER_SIZE)
    c.drawCentredString(x + w / 2, y + h - 18, str(value))

    c.setFillColor(t.MUTED)
    c.setFont(t.FONT_BOLD, 5.6)
    c.drawCentredString(x + w / 2, y + h - 27, label.upper()[:26])

    # Thin value bar.
    bar_y = y + 9.5
    bar_w = w - 16
    c.setFillColor(t.WHITE)
    c.rect(x + 8, bar_y, bar_w, 3, stroke=0, fill=1)
    c.setFillColor(fg)
    c.rect(x + 8, bar_y, bar_w * (value / 100.0), 3, stroke=0, fill=1)

    if sub:
        c.setFillColor(fg)
        c.setFont(t.FONT_BOLD, 5.4)
        c.drawCentredString(x + w / 2, y + 3.5, sub[:26])


def draw_tiles(c, analysis: TeamAnalysis) -> None:
    s = analysis.scores
    tiles = [
        (analysis.team_score, "Team score /100", analysis.confidence_label),
        (s.founder_market_fit, "Founder-market fit", "weight 30"),
        (s.track_record, "Track record", "weight 20"),
        (s.team_completeness, "Team completeness", "weight 20"),
        (analysis.evidence_quality, "Evidence quality", "meta-score"),
    ]
    x = t.X0
    for value, label, sub in tiles:
        _tile(c, x, t.TILES_BOTTOM, t.TILE_W, t.TILES_H, value, label, sub)
        x += t.TILE_W + t.TILE_GAP


def draw_requirements(c, analysis: TeamAnalysis) -> None:
    y = t.CHIPS_BOTTOM
    c.setFillColor(t.MUTED)
    c.setFont(t.FONT_BOLD, 5.8)
    c.drawString(t.X0, y + t.CHIPS_H - 7, "WHAT THIS BUSINESS REQUIRES OF ANY TEAM")

    chip_h = 10.5
    row_gap = 2.0
    max_rows = 2
    labels = [item.strip() for item in analysis.what_this_business_requires]

    # Every requirement must stay readable: shrink the row font, then wrap to a second
    # row, and only ellipsize if a single label is still wider than the page.
    size, rows = 6.0, None
    while size >= 5.0:
        rows = _pack_rows(c, labels, size, t.CONTENT_W, max_rows)
        if rows is not None:
            break
        size -= 0.2
    if rows is None:
        size = 5.0
        labels = [_ellipsize(c, lab, t.CONTENT_W / 2.2, t.FONT_BOLD, size) for lab in labels]
        rows = _pack_rows(c, labels, size, t.CONTENT_W, max_rows) or [labels]

    c.setFont(t.FONT_BOLD, size)
    chip_y = y + (max_rows - len(rows)) * (chip_h + row_gap)
    for row in reversed(rows):  # draw bottom-up so a single row sits on the baseline
        x = t.X0
        for label in row:
            w = c.stringWidth(label, t.FONT_BOLD, size) + 10
            c.setFillColor(t.LIGHT_BLUE)
            c.roundRect(x, chip_y, w, chip_h, 2.5, stroke=0, fill=1)
            c.setFillColor(t.DARK_BLUE)
            c.drawString(x + 5, chip_y + (chip_h - size) / 2 + 0.6, label)
            x += w + 5
        chip_y += chip_h + row_gap


def _pack_rows(c, labels, size, width, max_rows):
    """Greedy row packing. Returns None if the labels need more than max_rows."""
    rows, current, used = [], [], 0.0
    for label in labels:
        w = c.stringWidth(label, t.FONT_BOLD, size) + 15
        if current and used + w > width:
            rows.append(current)
            current, used = [], 0.0
            if len(rows) == max_rows:
                return None
        if w > width:
            return None
        current.append(label)
        used += w
    if current:
        rows.append(current)
    return rows if len(rows) <= max_rows else None


def diligence_flowables(analysis: TeamAnalysis, sty: dict) -> list:
    out: list = []
    for i, q in enumerate(analysis.diligence_questions, start=1):
        out.append(
            Paragraph(
                f'<font face="{t.FONT_BOLD}" color="{hx(t.DARK_BLUE)}">{i}.</font>'
                f"&nbsp;&nbsp;{esc(q)}",
                sty["dq"],
            )
        )
    return out


def draw_diligence_band(c, top: float, height: float) -> None:
    c.setFillColor(t.LIGHT_BLUE)
    c.rect(t.X0, top - height, t.CONTENT_W, height, stroke=0, fill=1)
    c.setFillColor(t.DARK_BLUE)
    c.setFont(t.FONT_BOLD, 6.4)
    c.drawString(t.X0 + 8, top - 10, "DILIGENCE QUESTIONS FOR THE PARTNER MEETING")


def draw_footer(c, analysis: TeamAnalysis, date_str: str) -> None:
    c.setStrokeColor(t.RULE)
    c.setLineWidth(0.6)
    c.line(t.X0, t.FOOTER_RULE_Y, t.X1, t.FOOTER_RULE_Y)
    c.setFillColor(t.MUTED)
    c.setFont(t.FONT, 6.5)
    c.drawCentredString(
        t.PAGE_W / 2,
        t.FOOTER_LINE1_Y,
        f"{analysis.company_name} · Founder & Team One-Pager · Generated {date_str} · "
        f"{FOOTER_TAGLINE}",
    )
    c.setFont(t.FONT_BOLD, 6.5)
    c.setFillColor(t.DARK_BLUE)
    c.drawCentredString(t.PAGE_W / 2, t.FOOTER_LINE2_Y, f"Compiled by {BRAND_NAME}")


# --- column content ----------------------------------------------------------------------

_FT_MARK = {"yes": "FT", "no": "PT", "not stated": "?"}


def _member_cell(member: TeamMember, sty: dict) -> Paragraph:
    name = f'<font face="{t.FONT_BOLD}">{esc(member.name)}</font>'
    role = f" — {esc(member.role)}" if member.role else ""
    relevance = esc(member.relevance_to_business)
    cites = cite_markup(member.citations)
    if not member.citations:
        cites = f' {_outlined_chip("NOT IN DECK", t.MUTED)}'
    return Paragraph(
        f"{name}{role}<br/>"
        f'<font size="{max(sty["cell"].fontSize - 0.8, 6.0)}" '
        f'color="{hx(t.MUTED)}">{relevance}{cites}</font>',
        sty["cell"],
    )


def team_table(analysis: TeamAnalysis, cfg: FitConfig, sty: dict, width: float):
    """Roster table, founders first, capped by the fit config."""
    order = {"founder": 0, "unclear": 1, "employee": 2, "board": 3, "advisor": 4}
    members = sorted(analysis.team, key=lambda m: order.get(m.category, 9))
    members = members[: cfg.max_team_rows]
    if not members:
        return Paragraph(
            f'{_outlined_chip("NOT IN DECK", t.CRITICAL_FG)} '
            "The deck does not name any founder, employee, advisor, or board member. "
            "No roster could be assembled without inventing one.",
            sty["body"],
        )

    cat_w, ft_w = 42.0, 18.0
    name_w = width - cat_w - ft_w
    head = ParagraphStyle(
        "th", fontName=t.FONT_BOLD, fontSize=5.2, leading=6.2, textColor=t.MUTED
    )
    rows = [
        [
            Paragraph("NAME · ROLE · RELEVANCE TO THIS BUSINESS", head),
            Paragraph("CATEGORY", head),
            Paragraph("FT?", head),
        ]
    ]
    for m in members:
        fg, bg = t.CATEGORY_COLORS.get(m.category, t.CATEGORY_COLORS["unclear"])
        rows.append(
            [
                _member_cell(m, sty),
                Paragraph(_chip(t.CATEGORY_LABELS.get(m.category, "?"), fg, bg), sty["micro"]),
                Paragraph(
                    f'<font face="{t.FONT_BOLD}" size="6" '
                    f'color="{hx(t.MUTED if m.full_time != "yes" else t.POSITIVE_FG)}">'
                    f"{_FT_MARK.get(m.full_time, '?')}</font>",
                    sty["micro"],
                ),
            ]
        )
    table = Table(rows, colWidths=[name_w, cat_w, ft_w], hAlign="LEFT")
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5 * cfg.spacing_scale),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5 * cfg.spacing_scale),
        ("LINEBELOW", (0, 1), (-1, -2), 0.25, t.RULE),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, t.DARK_BLUE),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 1.5),
    ]
    for i in range(1, len(rows)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), t.ROW_TINT))
    table.setStyle(TableStyle(style))
    return table


def gaps_flowables(analysis: TeamAnalysis, sty: dict) -> list:
    if not analysis.composition_gaps:
        return [
            Paragraph(
                f'<font color="{hx(t.MUTED)}">'
                "No composition gaps identified against the stated requirements.</font>",
                sty["body"],
            )
        ]
    out = []
    for gap in analysis.composition_gaps[:5]:
        out.append(
            Paragraph(
                f'<font face="{t.FONT_BOLD}" color="{hx(t.CRITICAL_FG)}">▪</font>'
                f"&nbsp;&nbsp;{esc(gap)}",
                sty["gap"],
            )
        )
    return out


def claims_flowables(analysis: TeamAnalysis, sty: dict, limit: int = 4) -> list:
    """Deck assertions an investor should check elsewhere. This tool cannot check them."""
    if not analysis.unverifiable_claims:
        return []
    out = [
        Paragraph(
            f'<font color="{hx(t.MUTED)}" size="{max(sty["body"].fontSize - 1, 6.0)}">'
            "Stated in the deck, not verifiable from it. Check these against outside sources."
            "</font>",
            sty["body"],
        )
    ]
    for claim in analysis.unverifiable_claims[:limit]:
        out.append(
            Paragraph(
                f'<font face="{t.FONT_BOLD}" color="{hx(t.MED_BLUE)}">?</font>'
                f"&nbsp;&nbsp;{esc(claim)}",
                sty["gap"],
            )
        )
    return out


def finding_flowable(finding: Finding, cfg: FitConfig, sty: dict, positive: bool):
    detail = finding.detail
    if cfg.truncate_details:
        detail = first_sentence(detail)

    chips = ""
    if finding.severity and not positive:
        fg, bg = t.SEVERITY_COLORS.get(finding.severity, t.BAND_AMBER)
        chips += " " + _chip(finding.severity.upper(), fg, bg)
    if finding.is_absence:
        chips += " " + _outlined_chip("NOT IN DECK", t.MUTED)

    lead_color = hx(t.POSITIVE_FG if positive else t.DARK_BLUE)
    return Paragraph(
        f'<font face="{t.FONT_BOLD}" color="{lead_color}">{esc(finding.title)}</font>'
        f"{chips}<br/>{esc(detail)}{cite_markup(finding.citations)}",
        sty["finding"],
    )


def section_header(text: str, sty: dict):
    return Paragraph(text.upper(), sty["section"])


def spacer(height: float, cfg: FitConfig) -> Spacer:
    return Spacer(1, height * cfg.spacing_scale)
