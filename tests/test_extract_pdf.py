from __future__ import annotations

from pathlib import Path

import pytest

from onepager.config import IMAGE_TEXT_THRESHOLD
from onepager.extract import extract
from onepager.extract.pdf import extract_pdf_text, needs_vision, pdf_to_deck
from onepager.extract.types import ExtractionError, NoContentError


def test_text_pdf_yields_one_slide_per_page(text_pdf: Path) -> None:
    deck = extract_pdf_text(text_pdf)
    assert len(deck.slides) == 4
    assert [s.index for s in deck.slides] == [1, 2, 3, 4]
    assert deck.slides[0].title == "Northwind Robotics"
    assert deck.total_chars > 200


def test_team_slide_hints_are_detected(text_pdf: Path) -> None:
    deck = extract_pdf_text(text_pdf)
    assert 3 in deck.team_slide_indices  # "Our Team"
    assert 4 not in deck.team_slide_indices  # "The Ask"


def test_char_count_tracks_text(text_pdf: Path) -> None:
    deck = extract_pdf_text(text_pdf)
    for slide in deck.slides:
        assert slide.char_count == len(slide.text)


def test_dense_pdf_does_not_trigger_vision(text_pdf: Path) -> None:
    deck = pdf_to_deck(text_pdf, vision=None)
    assert deck.mean_chars >= IMAGE_TEXT_THRESHOLD
    assert needs_vision(deck) is False
    assert deck.used_vision is False
    assert all(s.image_b64 is None for s in deck.slides)


def test_image_only_pdf_auto_rasterizes(image_only_pdf: Path) -> None:
    deck = pdf_to_deck(image_only_pdf, vision=None)
    assert needs_vision(deck) is True
    assert deck.used_vision is True
    assert all(s.image_b64 for s in deck.slides)
    assert any("image-based" in note for note in deck.notes)


def test_vision_can_be_forced_and_suppressed(text_pdf: Path, image_only_pdf: Path) -> None:
    assert pdf_to_deck(text_pdf, vision=True).used_vision is True
    assert pdf_to_deck(image_only_pdf, vision=False).used_vision is False


def test_image_only_pdf_survives_the_no_content_gate(image_only_pdf: Path) -> None:
    deck = extract(image_only_pdf)
    assert deck.used_vision is True


def test_no_text_and_no_vision_exits_with_a_named_cause(image_only_pdf: Path) -> None:
    with pytest.raises(NoContentError) as exc:
        extract(image_only_pdf, vision=False)
    assert "scan" in str(exc.value) or "image" in str(exc.value)
    assert "--vision" in str(exc.value)


def test_corrupt_pdf_raises_a_readable_error(corrupt_pdf: Path) -> None:
    with pytest.raises(ExtractionError) as exc:
        extract(corrupt_pdf)
    assert corrupt_pdf.name in str(exc.value)
    assert "Traceback" not in str(exc.value)


def test_unsupported_extension_is_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "notes.txt"
    bad.write_text("hello")
    with pytest.raises(ExtractionError, match="unsupported file type"):
        extract(bad)


def test_missing_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ExtractionError, match="does not exist"):
        extract(tmp_path / "nope.pdf")


def test_empty_file_is_rejected(tmp_path: Path) -> None:
    empty = tmp_path / "empty.pdf"
    empty.touch()
    with pytest.raises(ExtractionError, match="empty"):
        extract(empty)


def test_max_slides_caps_and_records_the_cap(text_pdf: Path) -> None:
    deck = extract(text_pdf, max_slides=2)
    assert len(deck.slides) == 2
    assert any("capped at 2 of 4" in note for note in deck.notes)
