"""The single-page layout engine.

Exactly one page is structural, not aspirational: this module draws onto one canvas and
calls `showPage` once. The fit loop exists so that the page is *complete*, not merely
singular — anything it has to sacrifice is reported to the caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from reportlab.pdfgen import canvas as rlcanvas
from reportlab.platypus import Frame

from ..models import TeamAnalysis, sorted_weaknesses
from ..util.fitting import Column, FitConfig, FitResult, find_fit, measure
from ..util.logging import get_logger
from . import components as comp
from . import theme as t

_log = get_logger()

LOW_CONF_BANNER_H = 12.0


class RenderError(Exception):
    """Raised when the one-pager cannot be written at all (exit code 6)."""


@dataclass
class RenderReport:
    output: Path
    config: FitConfig
    dropped: list[str] = field(default_factory=list)
    overflowed: bool = False
    truncated: dict[str, float] = field(default_factory=dict)

    @property
    def degraded(self) -> bool:
        return bool(self.dropped) or self.overflowed


def _diligence_height(analysis: TeamAnalysis, cfg: FitConfig) -> float:
    sty = comp.styles(cfg)
    body = measure(comp.diligence_flowables(analysis, sty), t.CONTENT_W - 20)
    return min(max(body + 18.0, t.DILIGENCE_H_MIN), t.DILIGENCE_H_MAX)


def _build_columns(
    analysis: TeamAnalysis, cfg: FitConfig, body_top: float, body_bottom: float
) -> dict[str, Column]:
    sty = comp.styles(cfg)
    avail = body_top - body_bottom

    left: list = [comp.section_header("Team at a glance", sty)]
    left.append(comp.team_table(analysis, cfg, sty, t.LEFT_W))
    left.append(comp.spacer(9, cfg))
    left.append(comp.section_header("Composition gaps", sty))
    left.extend(comp.gaps_flowables(analysis, sty))
    claims = comp.claims_flowables(analysis, sty)
    if claims:
        left.append(comp.spacer(9, cfg))
        left.append(comp.section_header("Claims to verify", sty))
        left.extend(claims)

    right: list = [comp.section_header("Strengths", sty)]
    for f in analysis.strengths[: cfg.max_strengths]:
        right.append(comp.finding_flowable(f, cfg, sty, positive=True))
    right.append(comp.spacer(5, cfg))
    right.append(comp.section_header("Weaknesses", sty))
    for f in sorted_weaknesses(analysis)[: cfg.max_weaknesses]:
        right.append(comp.finding_flowable(f, cfg, sty, positive=False))

    return {
        "left": Column("left", left, t.LEFT_W, avail),
        "right": Column("right", right, t.RIGHT_W, avail),
    }


def body_top_for(analysis: TeamAnalysis) -> float:
    """The low-confidence banner eats into the body; reserve its strip up front."""
    return t.BODY_TOP - (LOW_CONF_BANNER_H + 4 if analysis.low_confidence else 0)


def plan(analysis: TeamAnalysis) -> tuple[FitResult, float]:
    """Run the fit loop without drawing. Exposed so tests can assert on degradation."""
    dili_h = _diligence_height(analysis, FitConfig())
    body_bottom = t.DILIGENCE_BOTTOM + dili_h + t.GAP
    body_top = body_top_for(analysis)
    result = find_fit(lambda cfg: _build_columns(analysis, cfg, body_top, body_bottom))
    return result, dili_h


def render(
    analysis: TeamAnalysis,
    output: Path,
    deck_name: str,
    generated: date | None = None,
) -> RenderReport:
    generated = generated or date.today()
    date_str = generated.strftime("%d %b %Y")

    try:
        result, dili_h = plan(analysis)
        body_bottom = t.DILIGENCE_BOTTOM + dili_h + t.GAP
        body_top = body_top_for(analysis)

        output.parent.mkdir(parents=True, exist_ok=True)
        # invariant=1 strips the creation timestamp and random doc ID, so the same
        # analysis renders byte-identical on every run (--json / --from-json audits).
        c = rlcanvas.Canvas(str(output), pagesize=(t.PAGE_W, t.PAGE_H), invariant=1)
        c.setTitle(f"{analysis.company_name} — Founder & Team One-Pager")
        c.setAuthor("TEN Capital Network")
        c.setSubject("Founder and team assessment generated from the submitted pitch deck")

        comp.draw_header(c, analysis, deck_name, date_str)
        comp.draw_tiles(c, analysis)
        comp.draw_requirements(c, analysis)

        if analysis.low_confidence:
            _draw_low_confidence_banner(c, analysis)

        truncated: dict[str, float] = {}
        for name, geom_x in (("left", t.LEFT_X), ("right", t.RIGHT_X)):
            col = result.columns[name]
            frame = Frame(
                geom_x,
                body_bottom,
                col.width,
                body_top - body_bottom,
                leftPadding=0,
                rightPadding=0,
                topPadding=0,
                bottomPadding=0,
                showBoundary=0,
            )
            remaining = list(col.flowables)
            frame.addFromList(remaining, c)
            if remaining:
                truncated[name] = col.overflow

        dili_top = t.DILIGENCE_BOTTOM + dili_h
        comp.draw_diligence_band(c, dili_top, dili_h)
        dili_frame = Frame(
            t.X0 + 8,
            t.DILIGENCE_BOTTOM + 3,
            t.CONTENT_W - 20,
            dili_h - 16,
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )
        dili_frame.addFromList(comp.diligence_flowables(analysis, comp.styles(result.config)), c)

        comp.draw_footer(c, analysis, date_str)

        c.showPage()  # the only one
        c.save()
    except RenderError:
        raise
    except Exception as exc:
        raise RenderError(f"could not write {output}: {type(exc).__name__}: {exc}") from exc

    report = RenderReport(
        output=output,
        config=result.config,
        dropped=result.dropped,
        overflowed=result.overflowed,
        truncated=truncated,
    )
    _warn(report)
    return report


def _draw_low_confidence_banner(c, analysis: TeamAnalysis) -> None:
    """A confident number on a thin deck is the worst failure mode; say so loudly."""
    top = t.CHIPS_BOTTOM - 2
    c.setFillColor(t.CRITICAL_BG)
    c.rect(t.X0, top - LOW_CONF_BANNER_H, t.CONTENT_W, LOW_CONF_BANNER_H, stroke=0, fill=1)
    c.setFillColor(t.CRITICAL_FG)
    c.setFont(t.FONT_BOLD, 6.2)
    c.drawString(
        t.X0 + 5,
        top - 8.5,
        f"LOW CONFIDENCE — evidence quality {analysis.evidence_quality}/100. "
        "This deck does not contain enough team information to score reliably; "
        "treat the scores above as provisional.",
    )


def _warn(report: RenderReport) -> None:
    for note in report.dropped:
        _log.warning("one-page fit: %s", note)
    if report.overflowed:
        cols = ", ".join(f"{k} by {v:.0f}pt" for k, v in report.truncated.items()) or "unknown"
        _log.warning(
            "one-page fit: content still exceeded the page after every degradation step "
            "(%s); the overflowing items were dropped rather than spilling to page 2",
            cols,
        )
