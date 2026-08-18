"""Analysis factories shared by the test modules."""

from __future__ import annotations

from onepager.models import Citation, Finding, TeamAnalysis, TeamMember, TeamScores


def _cite(slide: int = 3) -> list[Citation]:
    return [Citation(slide=slide, quote="Dana Okonkwo, CEO and co-founder")]


def make_analysis(**overrides) -> TeamAnalysis:
    base = dict(
        company_name="Northwind Robotics",
        one_line_business="Autonomous forklifts for cold-storage warehouses.",
        stage_and_raise="Seed · $4M · $16M cap",
        sector="Industrial robotics",
        what_this_business_requires=[
            "Warehouse automation deployment experience",
            "Robotics and perception engineering depth",
            "Enterprise logistics sales",
        ],
        team=[
            TeamMember(
                name="Dana Okonkwo",
                role="CEO and co-founder",
                category="founder",
                stated_background="Ten years at Amazon Robotics",
                full_time="yes",
                relevance_to_business="Owns the customer relationship this business depends on.",
                citations=_cite(),
            ),
            TeamMember(
                name="Lin Zhao",
                role="Advisor",
                category="advisor",
                stated_background=None,
                full_time="not stated",
                relevance_to_business="Named as an advisor with no stated engagement terms.",
                citations=[],
            ),
        ],
        strengths=[
            Finding(
                title=f"Strength {i}",
                detail="The deck states a directly relevant prior role. It matters here.",
                citations=_cite(),
            )
            for i in range(1, 6)
        ],
        weaknesses=[
            Finding(
                title=f"Weakness {i}",
                detail="No commercial lead is named anywhere in the deck. That is a gap.",
                severity=sev,
                citations=[],
                is_absence=True,
            )
            for i, sev in enumerate(["critical", "high", "high", "medium", "medium"], start=1)
        ],
        composition_gaps=["No VP Sales", "No regulatory owner"],
        diligence_questions=[
            "Who owns enterprise sales, and have they closed a six-figure logistics contract?",
            "Is Rafi full-time at close, and what is his vesting schedule?",
            "What are Lin Zhao's engagement terms and time commitment?",
        ],
        scores=TeamScores(
            founder_market_fit=70,
            founder_product_fit=60,
            track_record=50,
            team_completeness=40,
            commitment_structure=55,
        ),
        evidence_quality=65,
        unverifiable_claims=["Ten years at Amazon Robotics", "PhD robotics, Carnegie Mellon"],
    )
    base.update(overrides)
    return TeamAnalysis(**base)
