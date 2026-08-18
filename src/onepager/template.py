"""The blank document template.

`blank_analysis()` is a fully-placeholdered `TeamAnalysis`: no company, no findings, no
scores — only the structure. Rendering it through the ordinary renderer produces the
canonical one-pager template, which is why the template can never drift from what the app
actually emits. It also exercises every conditional zone at once (all five member
categories, all three severities, both cited and absence findings, and the low-confidence
banner) so the template shows every state the layout can enter.
"""

from __future__ import annotations

from .models import Citation, Finding, TeamAnalysis, TeamMember, TeamScores

PLACEHOLDER_SLIDE = 1
"""Slide number on every template citation.

It exists so the template demonstrates the trailing-superscript citation format
(rendered as "s.1"). It is a format marker, not a reference to any real slide.
"""

_QUOTE = "[VERBATIM QUOTE FROM THE CITED SLIDE, MAX 200 CHARS]"


def _cite() -> list[Citation]:
    return [Citation(slide=PLACEHOLDER_SLIDE, quote=_QUOTE)]


def blank_analysis() -> TeamAnalysis:
    """A TeamAnalysis containing only field placeholders and structural markers."""
    return TeamAnalysis(
        company_name="[COMPANY NAME]",
        one_line_business=(
            "[ONE-LINE DESCRIPTION OF WHAT THIS BUSINESS DOES, MAX 160 CHARACTERS]"
        ),
        stage_and_raise="[STAGE · ROUND SIZE · INSTRUMENT · CAP OR VALUATION]",
        sector="[SECTOR / SUB-SECTOR]",
        what_this_business_requires=[
            "[REQUIRED CAPABILITY 1 — SHORT LABEL, MAX 8 WORDS]",
            "[REQUIRED CAPABILITY 2]",
            "[REQUIRED CAPABILITY 3]",
            "[REQUIRED CAPABILITY 4 — OPTIONAL]",
            "[REQUIRED CAPABILITY 5 — OPTIONAL]",
        ],
        team=[
            TeamMember(
                name="[PERSON NAME]",
                role="[ROLE AS STATED IN DECK]",
                category="founder",
                stated_background="[BACKGROUND EXACTLY AS STATED IN THE DECK]",
                full_time="yes",
                relevance_to_business=(
                    "[ONE LINE: WHY THIS PERSON MATTERS FOR THIS SPECIFIC BUSINESS]"
                ),
                citations=_cite(),
            ),
            TeamMember(
                name="[PERSON NAME]",
                role="[ROLE AS STATED IN DECK]",
                category="employee",
                stated_background="[BACKGROUND EXACTLY AS STATED IN THE DECK]",
                full_time="no",
                relevance_to_business="[ONE LINE OF RELEVANCE TO THIS BUSINESS]",
                citations=_cite(),
            ),
            TeamMember(
                name="[PERSON NAME]",
                role="[ROLE AS STATED IN DECK]",
                category="board",
                stated_background=None,
                full_time="not stated",
                relevance_to_business="[ONE LINE OF RELEVANCE TO THIS BUSINESS]",
                citations=_cite(),
            ),
            TeamMember(
                name="[PERSON NAME]",
                role="[ROLE AS STATED IN DECK]",
                category="advisor",
                stated_background=None,
                full_time="not stated",
                relevance_to_business="[ONE LINE OF RELEVANCE TO THIS BUSINESS]",
                citations=[],
            ),
            TeamMember(
                name="[PERSON NAME]",
                role="[ROLE AS STATED IN DECK]",
                category="unclear",
                stated_background=None,
                full_time="not stated",
                relevance_to_business="[ONE LINE OF RELEVANCE TO THIS BUSINESS]",
                citations=_cite(),
            ),
        ],
        strengths=[
            Finding(
                title=f"[STRENGTH {i} — BOLD LEAD-IN, MAX 70 CHARS]",
                detail=(
                    "[ONE OR TWO SENTENCES OF SUBSTANCE, MAX 280 CHARACTERS. EVERY CLAIM "
                    "ABOUT A PERSON CARRIES A SLIDE NUMBER AND A VERBATIM QUOTE.]"
                ),
                citations=_cite(),
            )
            for i in range(1, 6)
        ],
        weaknesses=[
            Finding(
                title=f"[WEAKNESS {i} — BOLD LEAD-IN, MAX 70 CHARS]",
                detail=(
                    "[ONE OR TWO SENTENCES OF SUBSTANCE, MAX 280 CHARACTERS. RANKED BY "
                    "SEVERITY: CRITICAL, THEN HIGH, THEN MEDIUM.]"
                ),
                severity=severity,
                citations=[] if is_absence else _cite(),
                is_absence=is_absence,
            )
            for i, (severity, is_absence) in enumerate(
                [
                    ("critical", False),
                    ("critical", True),
                    ("high", False),
                    ("high", True),
                    ("medium", False),
                ],
                start=1,
            )
        ],
        composition_gaps=[
            f"[ROLE {i} THIS BUSINESS NEEDS THAT THE ROSTER DOES NOT COVER]" for i in range(1, 6)
        ],
        diligence_questions=[
            f"[DILIGENCE QUESTION {i} — SHARP, ANSWERABLE IN A PARTNER MEETING, "
            "TARGETING A GAP IDENTIFIED ABOVE]"
            for i in range(1, 4)
        ],
        scores=TeamScores(
            founder_market_fit=0,
            founder_product_fit=0,
            track_record=0,
            team_completeness=0,
            commitment_structure=0,
        ),
        evidence_quality=0,
        unverifiable_claims=[
            f"[CLAIM {i} THE DECK ASSERTS THAT AN INVESTOR MUST CHECK ELSEWHERE]"
            for i in range(1, 5)
        ],
    )
