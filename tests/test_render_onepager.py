from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pymupdf
import pytest

from onepager.models import TeamAnalysis
from onepager.render import plan, render
from onepager.render.onepager import RenderError
from onepager.util.fitting import BASE_CONFIG

FIXED_DATE = date(2026, 3, 4)


def _render(analysis: TeamAnalysis, tmp_path: Path, name: str = "out.pdf"):
    out = tmp_path / name
    report = render(analysis, out, "deck.pdf", generated=FIXED_DATE)
    return out, report


def _text(pdf: Path) -> str:
    doc = pymupdf.open(pdf)
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def _page_count(pdf: Path) -> int:
    doc = pymupdf.open(pdf)
    try:
        return doc.page_count
    finally:
        doc.close()


# --- the non-negotiable ------------------------------------------------------------------


def test_output_is_exactly_one_page(analysis: TeamAnalysis, tmp_path: Path) -> None:
    out, _ = _render(analysis, tmp_path)
    assert _page_count(out) == 1


def test_oversized_analysis_is_still_exactly_one_page(
    oversized_analysis: TeamAnalysis, tmp_path: Path
) -> None:
    out, report = _render(oversized_analysis, tmp_path)
    assert _page_count(out) == 1
    assert report.degraded is True


def test_empty_team_analysis_is_still_exactly_one_page(
    empty_team_analysis: TeamAnalysis, tmp_path: Path
) -> None:
    out, _ = _render(empty_team_analysis, tmp_path)
    assert _page_count(out) == 1


def test_oversized_analysis_fires_a_warning_naming_what_was_dropped(
    oversized_analysis: TeamAnalysis, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="onepager"):
        _render(oversized_analysis, tmp_path)
    messages = [r.getMessage() for r in caplog.records]
    assert messages, "degradation must be reported, not silent"
    assert any("one-page fit" in m for m in messages)
    assert any("font" in m or "trimmed" in m or "truncated" in m for m in messages)


def test_the_fit_loop_actually_degrades_for_oversized_content(
    oversized_analysis: TeamAnalysis,
) -> None:
    result, _ = plan(oversized_analysis)
    assert result.config != BASE_CONFIG
    assert result.dropped


def test_a_modest_analysis_needs_no_content_loss(analysis: TeamAnalysis) -> None:
    result, _ = plan(analysis)
    assert result.config.max_strengths == 5
    assert result.config.max_weaknesses == 5
    assert result.overflowed is False


# --- content -------------------------------------------------------------------------------


def test_page_carries_the_headline_facts(analysis: TeamAnalysis, tmp_path: Path) -> None:
    out, _ = _render(analysis, tmp_path)
    text = _text(out)
    assert "Northwind Robotics" in text
    assert "FOUNDER & TEAM ONE-PAGER" in text
    assert str(analysis.team_score) in text
    assert "STRENGTHS" in text and "WEAKNESSES" in text
    assert "DILIGENCE QUESTIONS FOR THE PARTNER MEETING" in text
    assert "Compiled by TEN Capital Network" in text
    assert "04 Mar 2026" in text


def test_absence_findings_are_flagged_as_a_deck_gap(
    analysis: TeamAnalysis, tmp_path: Path
) -> None:
    out, _ = _render(analysis, tmp_path)
    assert "NOT IN DECK" in _text(out)


def test_severity_chips_are_rendered(analysis: TeamAnalysis, tmp_path: Path) -> None:
    text = _text(_render(analysis, tmp_path)[0])
    assert "CRITICAL" in text
    assert "HIGH" in text


def test_requirements_are_all_rendered(analysis: TeamAnalysis, tmp_path: Path) -> None:
    text = _text(_render(analysis, tmp_path)[0]).replace("\n", " ")
    for requirement in analysis.what_this_business_requires:
        assert requirement in text


def test_unverifiable_claims_reach_the_page(analysis: TeamAnalysis, tmp_path: Path) -> None:
    text = _text(_render(analysis, tmp_path)[0])
    assert "CLAIMS TO VERIFY" in text


# --- the confidence gate --------------------------------------------------------------------


def test_low_evidence_renders_a_low_confidence_band(
    empty_team_analysis: TeamAnalysis, tmp_path: Path
) -> None:
    out, _ = _render(empty_team_analysis, tmp_path)
    text = _text(out).replace("\n", " ")
    assert "LOW CONFIDENCE" in text
    assert "does not contain enough team information" in text


def test_sufficient_evidence_renders_no_low_confidence_band(
    analysis: TeamAnalysis, tmp_path: Path
) -> None:
    text = _text(_render(analysis, tmp_path)[0])
    assert "LOW CONFIDENCE" not in text


def test_empty_roster_says_so_rather_than_inventing_a_team(
    empty_team_analysis: TeamAnalysis, tmp_path: Path
) -> None:
    text = _text(_render(empty_team_analysis, tmp_path)[0]).replace("\n", " ")
    assert "does not name any founder" in text


# --- determinism and failure ------------------------------------------------------------------


def test_same_analysis_renders_byte_identical(analysis: TeamAnalysis, tmp_path: Path) -> None:
    a, _ = _render(analysis, tmp_path, "a.pdf")
    b, _ = _render(analysis, tmp_path, "b.pdf")
    assert a.read_bytes() == b.read_bytes()


def test_output_directory_is_created(analysis: TeamAnalysis, tmp_path: Path) -> None:
    out = tmp_path / "nested" / "deeper" / "out.pdf"
    render(analysis, out, "deck.pdf", generated=FIXED_DATE)
    assert out.exists()


def test_unwritable_target_raises_render_error(analysis: TeamAnalysis, tmp_path: Path) -> None:
    target = tmp_path / "dir_not_file"
    target.mkdir()
    with pytest.raises(RenderError):
        render(analysis, target, "deck.pdf", generated=FIXED_DATE)


def test_overflow_beyond_the_ladder_still_yields_one_page(
    oversized_analysis: TeamAnalysis,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With every degradation removed, content that cannot fit is dropped, never spilled."""
    from onepager.util import fitting

    monkeypatch.setattr(fitting, "LADDER", (BASE_CONFIG,))
    with caplog.at_level(logging.WARNING, logger="onepager"):
        out, report = _render(oversized_analysis, tmp_path, "overflow.pdf")

    assert _page_count(out) == 1
    assert report.overflowed is True
    assert report.truncated
    messages = [r.getMessage() for r in caplog.records]
    assert any("rather than spilling to page 2" in m for m in messages)
