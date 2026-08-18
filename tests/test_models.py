from __future__ import annotations

import pytest
from pydantic import ValidationError

from onepager.config import SCORE_WEIGHTS
from onepager.models import (
    Citation,
    Finding,
    TeamAnalysis,
    TeamMember,
    TeamScores,
    sorted_weaknesses,
)

from .factories import make_analysis

# --- scoring --------------------------------------------------------------------------


def test_weights_sum_to_one_hundred() -> None:
    assert sum(SCORE_WEIGHTS.values()) == 100


def test_team_score_is_the_documented_weighted_sum() -> None:
    scores = TeamScores(
        founder_market_fit=80,
        founder_product_fit=60,
        track_record=40,
        team_completeness=20,
        commitment_structure=100,
    )
    expected = (80 * 30 + 60 * 20 + 40 * 20 + 20 * 20 + 100 * 10) / 100
    assert scores.team_score == round(expected) == 58


def test_team_score_is_computed_not_supplied() -> None:
    """The model has no way to hand us a total; it is derived from the components."""
    assert "team_score" not in TeamAnalysis.model_fields
    assert "team_score" not in TeamScores.model_fields


@pytest.mark.parametrize("value", [0, 100])
def test_subscores_accept_the_full_range(value: int) -> None:
    TeamScores(
        founder_market_fit=value,
        founder_product_fit=value,
        track_record=value,
        team_completeness=value,
        commitment_structure=value,
    )


@pytest.mark.parametrize("value", [-1, 101])
def test_subscores_reject_out_of_range(value: int) -> None:
    with pytest.raises(ValidationError):
        TeamScores(
            founder_market_fit=value,
            founder_product_fit=50,
            track_record=50,
            team_completeness=50,
            commitment_structure=50,
        )


# --- confidence gate -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("evidence", "low", "label"),
    [
        (0, True, "LOW CONFIDENCE"),
        (39, True, "LOW CONFIDENCE"),
        (40, False, "SCORED ON DECK EVIDENCE"),
    ],
)
def test_low_confidence_gate(evidence: int, low: bool, label: str) -> None:
    analysis = make_analysis(evidence_quality=evidence)
    assert analysis.low_confidence is low
    assert analysis.confidence_label == label


# --- the traceability invariant --------------------------------------------------------


def test_uncited_finding_that_is_not_an_absence_is_rejected() -> None:
    with pytest.raises(ValidationError, match="is_absence"):
        make_analysis(
            strengths=[
                Finding(title="Unsourced praise", detail="No slide backs this up.", citations=[])
            ]
            + [
                Finding(title=f"S{i}", detail="ok", citations=[Citation(slide=1, quote="q")])
                for i in range(4)
            ]
        )


def test_uncited_finding_marked_as_absence_is_accepted() -> None:
    analysis = make_analysis(
        weaknesses=[
            Finding(
                title="No CTO named",
                detail="The deck does not name a technical lead.",
                severity="high",
                citations=[],
                is_absence=True,
            )
        ]
        * 3
    )
    assert all(f.is_absence for f in analysis.weaknesses)


def test_uncited_person_with_a_claimed_full_time_status_is_rejected() -> None:
    with pytest.raises(ValidationError, match="traceable to a slide"):
        make_analysis(
            team=[
                TeamMember(
                    name="Ghost Founder",
                    role="CEO",
                    category="founder",
                    full_time="yes",
                    relevance_to_business="Invented from nowhere.",
                    citations=[],
                )
            ]
        )


def test_uncited_person_is_allowed_when_the_deck_is_silent() -> None:
    analysis = make_analysis()
    advisor = next(m for m in analysis.team if m.category == "advisor")
    assert advisor.citations == []
    assert advisor.full_time == "not stated"


def test_acceptance_invariant_holds_for_every_finding_and_member() -> None:
    """Each Finding/TeamMember has >=1 citation, or is_absence / full_time='not stated'."""
    analysis = make_analysis()
    for finding in [*analysis.strengths, *analysis.weaknesses]:
        assert finding.citations or finding.is_absence
    for member in analysis.team:
        assert member.citations or member.full_time == "not stated"


# --- shape rules -----------------------------------------------------------------------


def test_empty_roster_is_valid() -> None:
    analysis = make_analysis(team=[])
    assert analysis.team == []
    assert analysis.founders == []


def test_strengths_never_carry_a_severity() -> None:
    analysis = make_analysis()
    assert all(f.severity is None for f in analysis.strengths)


def test_weaknesses_always_carry_a_severity() -> None:
    analysis = make_analysis(
        weaknesses=[
            Finding(title=f"W{i}", detail="d", severity=None, citations=[], is_absence=True)
            for i in range(3)
        ]
    )
    assert all(f.severity == "medium" for f in analysis.weaknesses)


def test_weaknesses_sort_critical_first() -> None:
    analysis = make_analysis()
    order = [f.severity for f in sorted_weaknesses(analysis)]
    assert order == ["critical", "high", "high", "medium", "medium"]


def test_exactly_three_diligence_questions_are_required() -> None:
    with pytest.raises(ValidationError):
        make_analysis(diligence_questions=["only one"])


def test_findings_below_three_are_rejected() -> None:
    with pytest.raises(ValidationError):
        make_analysis(
            strengths=[
                Finding(title="S", detail="d", citations=[Citation(slide=1, quote="q")])
            ]
        )


def test_requirement_chips_are_length_capped() -> None:
    with pytest.raises(ValidationError):
        make_analysis(what_this_business_requires=["x" * 200, "b", "c"])


def test_round_trips_through_json_unchanged(analysis: TeamAnalysis) -> None:
    restored = TeamAnalysis.model_validate_json(analysis.model_dump_json())
    assert restored == analysis
    assert restored.team_score == analysis.team_score
