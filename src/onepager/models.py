"""The I/O contract. Everything the model returns and the renderer consumes lives here."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

from .config import LOW_CONFIDENCE_THRESHOLD, SCORE_WEIGHTS

Requirement = Annotated[str, StringConstraints(max_length=70)]
"""A capability label short enough to render as a chip."""

Severity = Literal["critical", "high", "medium"]
MemberCategory = Literal["founder", "employee", "advisor", "board", "unclear"]
FullTime = Literal["yes", "no", "not stated"]


class Citation(BaseModel):
    slide: int = Field(ge=0, description="1-based slide number the quote came from.")
    quote: str = Field(max_length=200, description="Short verbatim excerpt from that slide.")


class TeamMember(BaseModel):
    name: str
    role: str | None = None
    category: MemberCategory
    stated_background: str | None = Field(
        default=None, description="Background exactly as stated in the deck. Never inferred."
    )
    full_time: FullTime
    relevance_to_business: str = Field(
        description="One line: why this person matters for this specific business."
    )
    citations: list[Citation] = Field(default_factory=list)


class Finding(BaseModel):
    title: str = Field(max_length=70, description="Bold lead-in, no trailing period.")
    detail: str = Field(max_length=280, description="One or two sentences of substance.")
    severity: Severity | None = Field(
        default=None, description="Weaknesses only; leave null for strengths."
    )
    citations: list[Citation] = Field(default_factory=list)
    is_absence: bool = Field(
        default=False, description="True when the finding is that the deck does not say."
    )


class TeamScores(BaseModel):
    founder_market_fit: int = Field(ge=0, le=100)
    founder_product_fit: int = Field(ge=0, le=100)
    track_record: int = Field(ge=0, le=100)
    team_completeness: int = Field(ge=0, le=100)
    commitment_structure: int = Field(ge=0, le=100)

    @property
    def team_score(self) -> int:
        """Weighted 0-100 composite. Computed here, never taken from the model."""
        total = sum(getattr(self, k) * w for k, w in SCORE_WEIGHTS.items())
        return round(total / sum(SCORE_WEIGHTS.values()))


class TeamAnalysis(BaseModel):
    company_name: str
    one_line_business: str = Field(max_length=160)
    stage_and_raise: str | None = None
    sector: str | None = None
    what_this_business_requires: list[Requirement] = Field(
        min_length=3,
        max_length=5,
        description=(
            "Capabilities this business demands of any team. Short noun phrases of at "
            "most eight words - these render as chips, not sentences."
        ),
    )
    team: list[TeamMember] = Field(default_factory=list)
    strengths: list[Finding] = Field(min_length=3, max_length=5)
    weaknesses: list[Finding] = Field(min_length=3, max_length=5)
    composition_gaps: list[str] = Field(default_factory=list)
    diligence_questions: list[str] = Field(min_length=3, max_length=3)
    scores: TeamScores
    evidence_quality: int = Field(ge=0, le=100)
    unverifiable_claims: list[str] = Field(default_factory=list)

    # --- derived, never supplied by the model ----------------------------------------

    @property
    def team_score(self) -> int:
        return self.scores.team_score

    @property
    def low_confidence(self) -> bool:
        return self.evidence_quality < LOW_CONFIDENCE_THRESHOLD

    @property
    def confidence_label(self) -> str:
        return "LOW CONFIDENCE" if self.low_confidence else "SCORED ON DECK EVIDENCE"

    @property
    def founders(self) -> list[TeamMember]:
        return [m for m in self.team if m.category == "founder"]

    # --- invariants -------------------------------------------------------------------

    @field_validator("strengths")
    @classmethod
    def _strengths_have_no_severity(cls, v: list[Finding]) -> list[Finding]:
        for f in v:
            f.severity = None
        return v

    @field_validator("weaknesses")
    @classmethod
    def _weaknesses_have_severity(cls, v: list[Finding]) -> list[Finding]:
        for f in v:
            if f.severity is None:
                f.severity = "medium"
        return v

    @model_validator(mode="after")
    def _every_claim_is_traceable(self) -> TeamAnalysis:
        """Nothing asserted about a person may float free of the deck.

        A finding is admissible if it cites a slide or is explicitly an absence claim.
        A team member is admissible if they are cited or their full-time status is unknown
        (i.e. we are already signalling that the deck is thin on them).
        """
        for kind, findings in (("strength", self.strengths), ("weakness", self.weaknesses)):
            for f in findings:
                if not f.citations and not f.is_absence:
                    raise ValueError(
                        f"{kind} {f.title!r} has no citation and is not marked is_absence. "
                        "Every claim must carry a slide + quote, or be declared an absence."
                    )
        for m in self.team:
            if not m.citations and m.full_time != "not stated":
                raise ValueError(
                    f"team member {m.name!r} has no citation. People named in the "
                    "one-pager must be traceable to a slide."
                )
        return self


def sorted_weaknesses(analysis: TeamAnalysis) -> list[Finding]:
    """Weaknesses ranked critical -> high -> medium, stable within a band."""
    order = {"critical": 0, "high": 1, "medium": 2}
    return sorted(analysis.weaknesses, key=lambda f: order.get(f.severity or "medium", 3))
