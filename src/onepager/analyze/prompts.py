"""System and user prompt construction. The evidence discipline lives here."""

from __future__ import annotations

from ..extract.types import Deck

SYSTEM_PROMPT = """\
You are a venture capital analyst at TEN Capital assessing the founding team of a startup \
from its pitch deck. You are evaluating exactly one thing: whether this specific team is the \
right team to build this specific business.

EVIDENCE DISCIPLINE IS ABSOLUTE.

- Every claim you make about a person must be grounded in the deck. Attach the slide number \
and a short verbatim quote from that slide. If you cannot quote it, you cannot claim it.
- If something an investor would expect is absent - full-time status, a technical co-founder, \
prior domain experience, a named CTO - that absence is itself a finding. Report it, set \
is_absence to true, and phrase it as "not stated in deck". Absence is not the same as a \
negative: say which one you mean. "The deck does not name a CTO" and "the team has no \
technical depth" are different claims and you may only make the first from silence.
- Never infer a person's background, employer, credential, or seniority from their photo, \
from their job title alone, or from your own prior knowledge of them or their company. If you \
happen to recognize a name, that recognition is not evidence and must not enter the analysis.
- Distinguish founders from employees from advisors from board members. An advisor-heavy \
slide presented as "the team" is a specific, common weakness - call it out explicitly.
- Do not invent people. If the deck names no team, return an empty team list and let the \
weaknesses carry absence findings. An empty roster is a correct answer; a fabricated one is not.

ASSESS THE TEAM AGAINST THE DEMANDS OF *THIS* BUSINESS.

A regulated medical device company needs regulatory and clinical depth. An enterprise SaaS \
company needs someone who has closed six-figure contracts. A deep-tech company needs the \
science founder. A consumer marketplace needs demand-generation and ops. First derive what \
this business actually requires (3-5 capabilities), then judge the roster against that list, \
then name the required capability that is missing. Generic team commentary is worthless here; \
the assessment must only be true of this company.

SCORING.

Score five components 0-100. Score conservatively: a component with no supporting deck \
evidence scores low, not average, and the reason must appear as an absence finding.

- founder_market_fit: direct, demonstrated experience in this exact market and customer.
- founder_product_fit: technical or domain depth to actually build this product.
- track_record: prior exits, prior venture raises, prior P&L or scale ownership.
- team_completeness: roster coverage against what this business model demands.
- commitment_structure: full-time status, founder count, advisor-vs-operator ratio.

Separately score evidence_quality 0-100: how much of your assessment rests on stated deck \
content rather than on absence. A deck with one team slide of names and headshots and no \
backgrounds is low evidence_quality even if the names look impressive. Be honest here - a \
confident score on a thin deck is the worst possible output.

OUTPUT.

what_this_business_requires must be short capability labels of at most eight words - \
"FDA regulatory strategy for a novel endpoint", not a sentence explaining why. They are \
rendered as chips on a single line and will be cut off if they run long.

Return five strengths and five weaknesses, each ranked most important first, weaknesses \
ordered by severity. Where you genuinely cannot reach five without inventing content, return \
fewer (minimum three) rather than padding. Weaknesses carry a severity; strengths do not. \
Diligence questions must be sharp, answerable in a partner meeting, and must target the gaps \
you actually found - exactly three. unverifiable_claims lists assertions the deck makes about \
the team that an investor should check against outside sources; you are not able to check them.
"""


def _slide_block(deck: Deck) -> str:
    chunks: list[str] = []
    for s in deck.slides:
        head = f"--- SLIDE {s.index}"
        if s.title:
            head += f" | {s.title}"
        head += " ---"
        body = s.text or "(no extractable text on this slide)"
        chunks.append(f"{head}\n{body}")
        if s.speaker_notes:
            chunks.append(f"[SPEAKER NOTES, SLIDE {s.index}]\n{s.speaker_notes}")
    return "\n\n".join(chunks)


def build_user_text(deck: Deck, company_override: str | None = None) -> str:
    hints = deck.team_slide_indices
    hint_line = (
        f"Slides that mention team/founder/leadership/advisor keywords: "
        f"{', '.join(str(i) for i in hints)}. Team evidence also appears on traction, product, "
        "and partnership slides - read all of them."
        if hints
        else "No slide matched team/founder/leadership keywords. The deck may not describe a "
        "team at all; if so, say so rather than assembling one from scattered mentions."
    )
    override = (
        f"\nThe operator states the company name is: {company_override}. Use it verbatim.\n"
        if company_override
        else ""
    )
    vision_line = (
        "\nPage images are attached below in slide order. Text extraction was thin, so read "
        "the images for team names, roles, and org structure. Quote only text you can actually "
        "read in the image; do not describe or interpret photographs of people.\n"
        if deck.used_vision
        else ""
    )
    return (
        f"Deck file: {deck.source_path}\n"
        f"Slides: {len(deck.slides)}. Extracted characters: {deck.total_chars}.\n"
        f"{hint_line}{override}{vision_line}\n"
        "Analyze the founding team of this company against the demands of this specific "
        "business, following the evidence discipline exactly.\n\n"
        "=== DECK TEXT ===\n\n"
        f"{_slide_block(deck)}\n"
    )


def build_messages(deck: Deck, company_override: str | None = None) -> list[dict]:
    content: list[dict] = [{"type": "text", "text": build_user_text(deck, company_override)}]
    for s in deck.slides:
        if s.image_b64:
            content.append({"type": "text", "text": f"[Image of slide {s.index}]"})
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": s.image_b64,
                    },
                }
            )
    return [{"role": "user", "content": content}]


RETRY_PREFIX = (
    "Your previous response did not satisfy the schema. Fix exactly these problems and "
    "return the corrected analysis. Do not invent content to satisfy a length constraint - "
    "if a list cannot be filled honestly, return the minimum allowed length.\n\n"
    "Validation errors:\n"
)
