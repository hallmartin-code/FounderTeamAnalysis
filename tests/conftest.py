"""Shared fixtures. Everything here is synthesized, so the suite needs no real deck."""

from __future__ import annotations

from pathlib import Path

import pytest
from pptx import Presentation
from pptx.util import Inches, Pt
from reportlab.pdfgen import canvas as rlcanvas

from onepager.models import Citation, Finding, TeamAnalysis, TeamMember

from .factories import _cite, make_analysis

# --- synthetic decks ---------------------------------------------------------------------

_FILLER = (
    "Cold-storage warehouses run at minus twenty degrees, which is why labour turnover "
    "sits at ninety percent annually and why every operator we spoke to has an unfilled "
    "headcount problem they cannot recruit their way out of. "
)


@pytest.fixture
def text_pdf(tmp_path: Path) -> Path:
    """A text-based PDF, dense enough that the vision path should not trigger."""
    path = tmp_path / "text_deck.pdf"
    c = rlcanvas.Canvas(str(path))
    pages = [
        ("Northwind Robotics", "Autonomous forklifts for cold-storage warehouses. " + _FILLER),
        ("The Problem", "Labour turnover is 90% annually. Injuries cost $2B. " + _FILLER),
        (
            "Our Team",
            "Dana Okonkwo, CEO and co-founder. Ten years at Amazon Robotics. "
            "Rafi Mendes, CTO and co-founder. PhD robotics, Carnegie Mellon. "
            "Advisor: Lin Zhao, former VP Ops at Americold. " + _FILLER,
        ),
        ("The Ask", "Raising $4M seed at a $16M cap. $1.2M committed. " + _FILLER),
    ]
    for title, body in pages:
        c.setFont("Helvetica-Bold", 18)
        c.drawString(72, 720, title)
        c.setFont("Helvetica", 11)
        text = c.beginText(72, 690)
        for chunk in _wrap(body, 78):
            text.textLine(chunk)
        c.drawText(text)
        c.showPage()
    c.save()
    return path


@pytest.fixture
def image_only_pdf(tmp_path: Path) -> Path:
    """A PDF with drawn shapes and no extractable text, i.e. a scan stand-in."""
    path = tmp_path / "scanned_deck.pdf"
    c = rlcanvas.Canvas(str(path))
    for i in range(3):
        c.rect(72, 400 + i * 10, 400, 200, stroke=1, fill=0)
        c.circle(300, 300, 60, stroke=1, fill=0)
        c.showPage()
    c.save()
    return path


@pytest.fixture
def pptx_deck(tmp_path: Path) -> Path:
    """A PPTX exercising the group-shape walk, a table, and speaker notes."""
    path = tmp_path / "deck.pptx"
    prs = Presentation()
    blank = prs.slide_layouts[6]

    s1 = prs.slides.add_slide(blank)
    box = s1.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(2))
    box.text_frame.text = "Northwind Robotics"
    box.text_frame.add_paragraph().text = _FILLER

    s2 = prs.slides.add_slide(blank)
    tbl = s2.shapes.add_table(2, 2, Inches(1), Inches(1), Inches(6), Inches(2)).table
    tbl.cell(0, 0).text = "Founder"
    tbl.cell(0, 1).text = "Background"
    tbl.cell(1, 0).text = "Dana Okonkwo"
    tbl.cell(1, 1).text = "Ten years at Amazon Robotics leading fulfilment automation"
    s2.notes_slide.notes_text_frame.text = (
        "Dana is full-time; Rafi joins after close. " + _FILLER
    )

    s3 = prs.slides.add_slide(blank)
    grouped = []
    for i in range(2):
        shape = s3.shapes.add_textbox(Inches(1 + i * 3), Inches(1), Inches(2.5), Inches(1.5))
        shape.text_frame.text = f"Leadership member {i}: {_FILLER}"
        shape.text_frame.paragraphs[0].runs[0].font.size = Pt(14)
        grouped.append(shape)
    s3.shapes.add_group_shape(grouped)

    prs.save(str(path))
    return path


@pytest.fixture
def corrupt_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.4\nthis is not actually a pdf body\n")
    return path


def _wrap(text: str, width: int) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


# --- analyses ------------------------------------------------------------------------------


@pytest.fixture
def analysis() -> TeamAnalysis:
    return make_analysis()


@pytest.fixture
def oversized_analysis() -> TeamAnalysis:
    """Deliberately too much content for one page, to exercise every ladder rung."""
    long_detail = (
        "This finding carries the maximum permitted detail length so that the fit loop has "
        "to work for its living, and it deliberately runs across several lines of the "
        "right-hand column before it finally reaches its full two hundred and eighty."
    )
    return make_analysis(
        one_line_business="A very long single-line business description that runs on. " * 2,
        team=[
            TeamMember(
                name=f"Person Number {i} With A Long Name",
                role="Chief Something Officer and co-founder",
                category="founder" if i < 3 else "advisor",
                stated_background="A stated background of considerable length" * 2,
                full_time="yes",
                relevance_to_business=(
                    "A long explanation of why this person matters to this particular "
                    "business, running well past a single line of the roster column."
                ),
                citations=_cite(i + 1),
            )
            for i in range(1, 9)
        ],
        strengths=[
            Finding(
                title=f"Strength number {i} with a long title",
                detail=long_detail,
                citations=_cite(i),
            )
            for i in range(1, 6)
        ],
        weaknesses=[
            Finding(
                title=f"Weakness number {i} with a long title",
                detail=long_detail,
                severity="critical",
                citations=_cite(i),
            )
            for i in range(1, 6)
        ],
        composition_gaps=[f"A missing role number {i} described at length" for i in range(1, 6)],
        diligence_questions=[
            "A deliberately long diligence question that wraps onto more than one line "
            f"because it keeps going and going and going, number {i}?"
            for i in range(1, 4)
        ],
        unverifiable_claims=[
            f"An unverifiable claim of some considerable length, number {i}" for i in range(6)
        ],
    )


@pytest.fixture
def empty_team_analysis() -> TeamAnalysis:
    """A deck with no team information at all: empty roster, absence findings, low evidence."""
    return make_analysis(
        team=[],
        strengths=[
            Finding(
                title=f"Strength {i}",
                detail="The deck makes a substantiated product claim.",
                citations=[Citation(slide=2, quote="90% turnover annually")],
            )
            for i in range(1, 4)
        ],
        weaknesses=[
            Finding(
                title=f"No team information {i}",
                detail="The deck names no founder, employee, advisor, or board member.",
                severity="critical",
                citations=[],
                is_absence=True,
            )
            for i in range(1, 6)
        ],
        composition_gaps=["Entire roster undisclosed"],
        evidence_quality=12,
        unverifiable_claims=[],
    )


@pytest.fixture
def no_api_client(mocker):
    """Fails loudly if a supposedly offline code path constructs an API client."""
    return mocker.patch(
        "onepager.cli.AnalysisClient",
        side_effect=AssertionError("the API must not be called on this path"),
    )
