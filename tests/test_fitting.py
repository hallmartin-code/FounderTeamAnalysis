from __future__ import annotations

from dataclasses import replace

from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph

from onepager.util.fitting import (
    BASE_CONFIG,
    LADDER,
    Column,
    FitConfig,
    find_fit,
    first_sentence,
    measure,
)

STYLE = ParagraphStyle("t", fontName="Helvetica", fontSize=9, leading=11)


def _para(text: str) -> Paragraph:
    return Paragraph(text, STYLE)


# --- measurement -----------------------------------------------------------------------


def test_measure_grows_with_content() -> None:
    one = measure([_para("hello world")], 200)
    many = measure([_para("hello world " * 40)], 200)
    assert many > one > 0


def test_measure_grows_as_the_column_narrows() -> None:
    text = "wrap me across several lines please " * 6
    assert measure([_para(text)], 120) > measure([_para(text)], 400)


def test_measure_survives_an_unmeasurable_flowable() -> None:
    class Broken:
        def wrap(self, *_):
            raise RuntimeError("nope")

    assert measure([Broken()], 100) > 0


# --- the ladder ------------------------------------------------------------------------


def test_ladder_starts_at_the_base_config() -> None:
    assert LADDER[0] == BASE_CONFIG == FitConfig()


def test_ladder_degrades_in_the_documented_order() -> None:
    sizes = [c.body_size for c in LADDER]
    assert sizes[:3] == [8.5, 8.0, 7.5]
    # Cosmetic loss is exhausted before any content is dropped.
    first_content_loss = next(
        i for i, c in enumerate(LADDER) if c.max_team_rows < 6 or c.max_strengths < 5
    )
    assert LADDER[first_content_loss - 1].truncate_details is True
    assert all(c.max_strengths >= 3 and c.max_weaknesses >= 3 for c in LADDER)


def test_ladder_never_drops_below_three_findings() -> None:
    assert min(c.max_strengths for c in LADDER) == 3
    assert min(c.max_weaknesses for c in LADDER) == 3


def test_describe_drops_names_each_degradation() -> None:
    cfg = replace(BASE_CONFIG, body_size=7.5, truncate_details=True, max_team_rows=4)
    drops = cfg.describe_drops(BASE_CONFIG)
    assert any("body font" in d for d in drops)
    assert any("first sentence" in d for d in drops)
    assert any("roster trimmed to 4" in d for d in drops)


def test_base_config_reports_no_drops() -> None:
    assert BASE_CONFIG.describe_drops(BASE_CONFIG) == []


# --- find_fit ---------------------------------------------------------------------------


def _builder(paragraphs_per_config):
    def build(cfg: FitConfig) -> dict[str, Column]:
        count = paragraphs_per_config(cfg)
        body = [_para("some content that wraps " * 4) for _ in range(count)]
        return {"only": Column("only", body, 200, 400)}

    return build


def test_find_fit_returns_the_base_config_when_content_already_fits() -> None:
    result = find_fit(_builder(lambda cfg: 1))
    assert result.config == BASE_CONFIG
    assert result.overflowed is False
    assert result.dropped == []


def test_find_fit_walks_down_the_ladder_until_it_fits() -> None:
    # Shrinks only once the roster is trimmed, i.e. several rungs down.
    result = find_fit(_builder(lambda cfg: 3 if cfg.max_team_rows < 6 else 30))
    assert result.overflowed is False
    assert result.config.max_team_rows < 6
    assert result.dropped


def test_find_fit_reports_overflow_when_nothing_fits() -> None:
    result = find_fit(_builder(lambda cfg: 200))
    assert result.overflowed is True
    assert result.config == LADDER[-1]
    assert result.overflow_by_column["only"] > 0


def test_column_overflow_is_zero_when_it_fits() -> None:
    col = Column("c", [_para("short")], 200, 400)
    assert col.overflow == 0


# --- first_sentence -----------------------------------------------------------------------


def test_first_sentence_stops_at_the_first_full_stop() -> None:
    assert first_sentence("One thing. Two thing. Three.") == "One thing."


def test_first_sentence_handles_question_and_exclamation() -> None:
    assert first_sentence("Really? Yes indeed.") == "Really?"


def test_first_sentence_returns_a_single_sentence_whole() -> None:
    assert first_sentence("Just the one sentence.") == "Just the one sentence."


def test_first_sentence_falls_back_to_a_character_cap() -> None:
    trimmed = first_sentence("word " * 100, hard_cap=40)
    assert len(trimmed) <= 44
    assert trimmed.endswith("...")
