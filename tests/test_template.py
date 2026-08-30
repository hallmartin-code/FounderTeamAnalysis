"""The blank template must stay valid, structural, and free of any company data."""

from __future__ import annotations

import re
from pathlib import Path

import pymupdf
import pytest
from typer.testing import CliRunner

from onepager.cli import app
from onepager.config import ExitCode
from onepager.models import TeamAnalysis
from onepager.render import render
from onepager.template import blank_analysis

runner = CliRunner()

#: Names of the sample companies used anywhere in this repo's fixtures and sample decks.
FORBIDDEN = ("Northwind", "AccuBreath", "Verdant", "Halcyon", "Okonkwo", "Mendes")


def _text(pdf: Path) -> str:
    doc = pymupdf.open(pdf)
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def _rendered(tmp_path: Path) -> Path:
    out = tmp_path / "template.pdf"
    render(blank_analysis(), out, "[DECK FILENAME]")
    return out


# --- it is a real, valid document ---------------------------------------------------------


def test_blank_analysis_satisfies_the_full_schema() -> None:
    """A template that could not validate would not be a template of anything."""
    blank = blank_analysis()
    assert isinstance(blank, TeamAnalysis)
    assert TeamAnalysis.model_validate_json(blank.model_dump_json()) == blank


def test_template_renders_to_exactly_one_page(tmp_path: Path) -> None:
    assert pymupdf.open(_rendered(tmp_path)).page_count == 1


def test_template_honours_the_traceability_invariant() -> None:
    blank = blank_analysis()
    for finding in [*blank.strengths, *blank.weaknesses]:
        assert finding.citations or finding.is_absence
    for member in blank.team:
        assert member.citations or member.full_time == "not stated"


# --- it carries no company data ------------------------------------------------------------


@pytest.mark.parametrize("name", FORBIDDEN)
def test_no_sample_company_name_survives_in_the_template(name: str, tmp_path: Path) -> None:
    assert name.lower() not in _text(_rendered(tmp_path)).lower()
    assert name.lower() not in blank_analysis().model_dump_json().lower()


def test_every_free_text_field_is_a_bracketed_placeholder() -> None:
    blank = blank_analysis()
    bracketed = [
        blank.company_name,
        blank.one_line_business,
        blank.stage_and_raise,
        blank.sector,
        *blank.what_this_business_requires,
        *blank.composition_gaps,
        *blank.diligence_questions,
        *blank.unverifiable_claims,
        *[m.name for m in blank.team],
        *[f.title for f in [*blank.strengths, *blank.weaknesses]],
    ]
    for value in bracketed:
        assert value.startswith("["), f"{value!r} is not a placeholder"
        assert value.endswith("]"), f"{value!r} is not a placeholder"


def test_scores_are_zeroed_so_nothing_reads_as_a_result() -> None:
    blank = blank_analysis()
    assert blank.team_score == 0
    assert blank.evidence_quality == 0
    assert all(getattr(blank.scores, f) == 0 for f in type(blank.scores).model_fields)


# --- it exhibits every render state ---------------------------------------------------------


def test_template_shows_all_five_member_categories(tmp_path: Path) -> None:
    text = _text(_rendered(tmp_path))
    for badge in ("FOUNDER", "EMPLOYEE", "BOARD", "ADVISOR", "UNCLEAR"):
        assert badge in text


def test_template_shows_all_three_severities(tmp_path: Path) -> None:
    text = _text(_rendered(tmp_path))
    for chip in ("CRITICAL", "HIGH", "MEDIUM"):
        assert chip in text


def test_template_shows_both_cited_and_absence_findings(tmp_path: Path) -> None:
    blank = blank_analysis()
    assert any(f.is_absence for f in blank.weaknesses)
    assert any(not f.is_absence and f.citations for f in blank.weaknesses)
    assert "NOT IN DECK" in _text(_rendered(tmp_path))


def test_template_demonstrates_the_citation_superscript(tmp_path: Path) -> None:
    """The trailing s.N marker is a format element; the template has to show it."""
    assert re.search(r"s\.\d", _text(_rendered(tmp_path)))


def test_template_shows_the_low_confidence_banner(tmp_path: Path) -> None:
    text = _text(_rendered(tmp_path)).replace("\n", " ")
    assert "LOW CONFIDENCE" in text
    assert "does not contain enough team information" in text


def test_template_shows_every_named_zone(tmp_path: Path) -> None:
    text = _text(_rendered(tmp_path))
    for zone in (
        "FOUNDER & TEAM ONE-PAGER",
        "WHAT THIS BUSINESS REQUIRES OF ANY TEAM",
        "TEAM AT A GLANCE",
        "COMPOSITION GAPS",
        "CLAIMS TO VERIFY",
        "STRENGTHS",
        "WEAKNESSES",
        "DILIGENCE QUESTIONS FOR THE PARTNER MEETING",
        "Compiled by TEN Capital Network",
    ):
        assert zone in text, f"missing zone: {zone}"


# --- the CLI command --------------------------------------------------------------------------


def test_template_command_writes_pdf_and_json(tmp_path: Path, no_api_client) -> None:
    pdf, js = tmp_path / "t.pdf", tmp_path / "t.json"
    result = runner.invoke(app, ["template", "-o", str(pdf), "--json", str(js)])
    assert result.exit_code == ExitCode.OK, result.output
    assert pymupdf.open(pdf).page_count == 1
    assert TeamAnalysis.model_validate_json(js.read_text(encoding="utf-8"))
    no_api_client.assert_not_called()


def test_template_command_creates_missing_directories(tmp_path: Path) -> None:
    pdf = tmp_path / "nested" / "deep" / "t.pdf"
    assert runner.invoke(app, ["template", "-o", str(pdf)]).exit_code == ExitCode.OK
    assert pdf.exists()


def test_committed_template_matches_the_current_renderer(tmp_path: Path) -> None:
    """docs/onepager_template.pdf is generated, not hand-maintained. Keep it in step.

    Generation dates are normalised out: the committed artifact carries the date it was
    built, and comparing that would fail on every day but one.
    """
    committed = Path(__file__).parents[1] / "docs" / "onepager_template.pdf"
    if not committed.exists():
        pytest.skip("docs template not generated in this checkout")
    undated = lambda t: re.sub(r"\d{2} \w{3} \d{4}", "<DATE>", t)  # noqa: E731
    assert undated(_text(committed)) == undated(_text(_rendered(tmp_path)))
