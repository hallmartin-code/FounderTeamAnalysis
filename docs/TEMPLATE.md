# Founder & Team One-Pager — Document Structure Template

The canonical structure of every document this app generates. No company data appears
anywhere in this template or in the files it describes.

| Artifact | What it is |
|---|---|
| [`onepager_template.pdf`](onepager_template.pdf) | The rendered blank template — the page structure itself |
| [`onepager_template.png`](onepager_template.png) | Preview image of the same |
| [`onepager_template.json`](onepager_template.json) | The blank data contract, field-for-field |
| `src/onepager/template.py` | `blank_analysis()` — the single source of both |

Regenerate all of them with:

```bash
onepager template -o docs/onepager_template.pdf --json docs/onepager_template.json
```

The template is rendered through the **same layout engine** as a real analysis, so it cannot
drift from what the app actually produces. It is not a mock-up.

---

## Page specification

| Property | Value |
|---|---|
| Page size | US Letter portrait, 612 × 792 pt |
| Margins | 36 pt all sides |
| Page count | **Exactly 1**, structurally guaranteed |
| Base font | Helvetica; body 8.5 pt, degrading to 8.0 / 7.5 pt to fit |
| Body columns | Left 242 pt (46%) · gutter 14 pt · right 284 pt (54%) |

### Palette

| Role | Hex | Used for |
|---|---|---|
| Dark blue | `#1F3864` | Company name, section headers, finding lead-ins, accent bar |
| Medium blue | `#2E75B6` | Board badge, claims-to-verify marker |
| Light blue | `#D5E8F0` | Requirement chips, diligence band, founder badge |
| Critical | `#C00000` on `#FFCCCC` | Critical severity, composition-gap markers, low-confidence banner |
| High | `#7F6000` on `#FFF2CC` | High severity, advisor badge |
| Medium / positive | `#375623` on `#E2EFDA` | Medium severity, strength lead-ins, green score band |
| Rule | `#BFBFBF` | Horizontal rules, table row lines |
| Body / muted | `#000000` / `#595959` | Body text / secondary text |

---

## Zone map, top to bottom

### 1 — Header band (54 pt)

| Element | Field | Format |
|---|---|---|
| Company name | `company_name` | 16 pt bold, dark blue, left |
| Document label | *(fixed)* | `FOUNDER & TEAM ONE-PAGER`, 7.2 pt bold |
| Stage / raise | `stage_and_raise` | Right-aligned, 7 pt, auto-shrinks to 5.4 pt then ellipsizes |
| Sector | `sector` | Right-aligned, line 2 |
| Provenance | *(runtime)* | `<deck filename> · <generation date>`, right-aligned, line 3 |
| Business line | `one_line_business` | 8.5 pt, full width, below the title block |

A 4 pt dark-blue vertical accent bar runs the full band height at the left margin; a rule
closes the band.

### 2 — Stat tile row (50 pt, five tiles)

Each tile: large number, uppercase label, thin proportional value bar, sub-caption. Tile fill
follows the score band — **≥70 green · 40–69 amber · <40 red**.

| # | Tile | Field | Sub-caption |
|---|---|---|---|
| 1 | Team score /100 | *computed* from `scores` | Confidence label |
| 2 | Founder–market fit | `scores.founder_market_fit` | `weight 30` |
| 3 | Track record | `scores.track_record` | `weight 20` |
| 4 | Team completeness | `scores.team_completeness` | `weight 20` |
| 5 | Evidence quality | `evidence_quality` | `meta-score` |

The team score is a weighted composite computed in code, never supplied by the model:

```
team_score = (founder_market_fit×30 + founder_product_fit×20 + track_record×20
              + team_completeness×20 + commitment_structure×10) / 100
```

`founder_product_fit` and `commitment_structure` carry weight but have no tile of their own;
they appear in the JSON and in the composite.

### 3 — Requirement chips (30 pt)

Label `WHAT THIS BUSINESS REQUIRES OF ANY TEAM`, then `what_this_business_requires` as 3–5
rounded chips. The row auto-shrinks 6.0 → 5.0 pt and wraps to a second row so every chip
stays visible; only a single chip wider than half the page is ever ellipsized.

### 4 — Low-confidence banner (12 pt) · **conditional**

Rendered **only when `evidence_quality < 40`**. Full-width red band stating the evidence
score and that the deck does not contain enough team information to score reliably. When
present it reserves its own strip, shifting the body columns down; it never overlaps them.

The template renders with `evidence_quality = 0`, so this zone is visible. A document scoring
40 or above omits it entirely and the tile sub-caption reads `SCORED ON DECK EVIDENCE`
instead of `LOW CONFIDENCE`.

### 5 — Left column (46%)

**`TEAM AT A GLANCE`** — table with a header row (`NAME · ROLE · RELEVANCE TO THIS BUSINESS`
/ `CATEGORY` / `FT?`), up to 6 member rows, alternating row tint.

Each row carries: bold `name` — `role`, then `relevance_to_business` in muted text with a
trailing slide citation, plus two badge columns.

| Field | Rendering |
|---|---|
| `category` | Badge: `FOUNDER` · `EMPLOYEE` · `BOARD` · `ADVISOR` · `UNCLEAR`, each with its own colour |
| `full_time` | `FT` (yes, green) · `PT` (no) · `?` (not stated) |
| `citations` | Trailing superscript `s.N` (comma-joined when several) |
| *no citations* | Outlined `[NOT IN DECK]` chip instead of a superscript |

Rows sort **founder → unclear → employee → board → advisor**, so principals lead and
advisors trail. When the fit loop trims the roster it trims from the bottom, keeping founders.

**`COMPOSITION GAPS`** — `composition_gaps`, up to 5, each with a red square marker. If the
list is empty the section states that no gaps were identified.

**`CLAIMS TO VERIFY`** — `unverifiable_claims`, up to 4, each with a blue `?` marker, under a
muted standing caption: *"Stated in the deck, not verifiable from it. Check these against
outside sources."* The whole section is omitted when the list is empty.

### 6 — Right column (54%)

**`STRENGTHS`** — 3–5 `Finding` rows, ranked most important first.
**`WEAKNESSES`** — 3–5 `Finding` rows, ranked critical → high → medium.

Each finding row:

```
<bold title>  [severity chip]  [NOT IN DECK chip]
<detail text><superscript slide citation>
```

| Field | Rendering |
|---|---|
| `title` | Bold lead-in, max 70 chars. Green for strengths, dark blue for weaknesses |
| `detail` | 1–2 sentences, max 280 chars. Truncated to the first sentence under fit pressure |
| `severity` | Chip: `CRITICAL` red · `HIGH` amber · `MEDIUM` green. **Weaknesses only** |
| `is_absence` | Outlined `[NOT IN DECK]` chip — distinguishes a gap in the *deck* from a gap in the *team* |
| `citations` | Trailing superscript `s.N` |

### 7 — Diligence questions band (46–78 pt, height fits content)

Light-blue full-width band. Label `DILIGENCE QUESTIONS FOR THE PARTNER MEETING`, then
**exactly three** numbered questions from `diligence_questions`.

### 8 — Footer

Rule, then two centred lines:

```
<Company> · Founder & Team One-Pager · Generated <date> · Analysis grounded in the
submitted deck; unverified claims flagged
Compiled by TEN Capital Network
```

---

## Data contract

Field-by-field, as enforced by `src/onepager/models.py`.

### `TeamAnalysis` (root)

| Field | Type | Constraint | Rendered in |
|---|---|---|---|
| `company_name` | string | required | Header, footer |
| `one_line_business` | string | ≤ 160 chars | Header |
| `stage_and_raise` | string \| null | — | Header right |
| `sector` | string \| null | — | Header right |
| `what_this_business_requires` | string[] | 3–5 items, ≤ 70 chars each | Zone 3 |
| `team` | TeamMember[] | may be **empty** | Zone 5 |
| `strengths` | Finding[] | 3–5 items | Zone 6 |
| `weaknesses` | Finding[] | 3–5 items | Zone 6 |
| `composition_gaps` | string[] | first 5 shown | Zone 5 |
| `diligence_questions` | string[] | **exactly 3** | Zone 7 |
| `scores` | TeamScores | — | Zone 2 |
| `evidence_quality` | int | 0–100 | Zone 2, zone 4 gate |
| `unverifiable_claims` | string[] | first 4 shown | Zone 5 |

### `TeamMember`

| Field | Type | Constraint | Rendered |
|---|---|---|---|
| `name` | string | required | Yes |
| `role` | string \| null | — | Yes |
| `category` | enum | `founder` · `employee` · `advisor` · `board` · `unclear` | Badge |
| `stated_background` | string \| null | deck wording only, never inferred | **JSON only** |
| `full_time` | enum | `yes` · `no` · `not stated` | Badge |
| `relevance_to_business` | string | one line | Yes |
| `citations` | Citation[] | — | Superscript |

### `Finding`

| Field | Type | Constraint |
|---|---|---|
| `title` | string | ≤ 70 chars |
| `detail` | string | ≤ 280 chars |
| `severity` | enum \| null | `critical` · `high` · `medium`. Null on strengths, always set on weaknesses |
| `citations` | Citation[] | — |
| `is_absence` | bool | true when the finding is that the deck is silent |

### `Citation`

| Field | Type | Constraint |
|---|---|---|
| `slide` | int | ≥ 0, 1-based as a human sees it |
| `quote` | string | ≤ 200 chars, verbatim from that slide |

### `TeamScores`

Five integers 0–100: `founder_market_fit`, `founder_product_fit`, `track_record`,
`team_completeness`, `commitment_structure`. There is deliberately **no total field** — the
composite is derived.

---

## Rules the template encodes

These are validated in code, not merely requested of the model.

1. **Every claim is traceable.** A finding must carry at least one citation *or* be marked
   `is_absence`. A named person must be cited *or* have `full_time = "not stated"`.
   Anything else is rejected at validation time.
2. **Absence is a distinct state.** `[NOT IN DECK]` is visually different from a severity
   chip, so a reader can tell a gap in the team from a gap in the deck.
3. **An empty roster is a valid document.** When a deck names no team, `team` is `[]`, the
   roster block says so in plain language, and the weaknesses carry absence findings. The
   template must never be filled in by invention.
4. **Thin evidence is stated, not hidden.** `evidence_quality < 40` forces the low-confidence
   banner and the `LOW CONFIDENCE` tile caption.
5. **One page, always.** Overflow degrades in a fixed order — font size, then leading, then
   detail truncation, then roster rows, then the 5th strength and 5th weakness (never below
   3 of each) — and anything dropped is logged to stderr by name.

---

## Placeholder conventions used in the template

| Convention | Meaning |
|---|---|
| `[UPPERCASE IN SQUARE BRACKETS]` | A field slot. Replaced by generated content |
| `0` in every tile | Score slot. Real documents carry 0–100 |
| `s.1` superscripts | Demonstrates the citation format. Not a reference to any real slide |
| Five roster rows | One per `category`, to show all five badges |
| Five weakness rows | Two `critical`, two `high`, one `medium`; two marked `is_absence`, to show every chip combination |

Because the template is generated from `blank_analysis()`, it satisfies every schema
constraint above — it is a valid document, not a sketch of one.
