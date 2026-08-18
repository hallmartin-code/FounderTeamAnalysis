from __future__ import annotations

from pathlib import Path

import pytest

from onepager.extract import extract
from onepager.extract.pptx import convert_via_libreoffice, extract_pptx_text, pptx_to_deck
from onepager.extract.types import ExtractionError


def test_pptx_yields_one_slide_per_slide(pptx_deck: Path) -> None:
    deck = extract_pptx_text(pptx_deck)
    assert len(deck.slides) == 3
    assert deck.source_kind == "pptx"


def test_table_cells_are_extracted(pptx_deck: Path) -> None:
    deck = extract_pptx_text(pptx_deck)
    text = deck.slides[1].text
    assert "Dana Okonkwo" in text
    assert "Ten years at Amazon Robotics" in text
    assert "|" in text  # cells are joined, not concatenated blindly


def test_speaker_notes_are_captured(pptx_deck: Path) -> None:
    deck = extract_pptx_text(pptx_deck)
    assert deck.slides[1].speaker_notes is not None
    assert "full-time" in deck.slides[1].speaker_notes
    assert deck.slides[0].speaker_notes is None


def test_group_shapes_are_walked_recursively(pptx_deck: Path) -> None:
    deck = extract_pptx_text(pptx_deck)
    text = deck.slides[2].text
    assert "Leadership member 0" in text
    assert "Leadership member 1" in text


def test_notes_and_table_text_feed_the_team_hints(pptx_deck: Path) -> None:
    deck = extract_pptx_text(pptx_deck)
    # slide 2 says "Founder" in a table cell, slide 3 says "Leadership" in a group shape
    assert 2 in deck.team_slide_indices
    assert 3 in deck.team_slide_indices


def test_title_falls_back_to_the_first_line(pptx_deck: Path) -> None:
    deck = extract_pptx_text(pptx_deck)
    # These blank-layout slides carry no title placeholder at all.
    assert deck.slides[0].title == "Northwind Robotics"


def test_dispatch_routes_pptx(pptx_deck: Path) -> None:
    deck = extract(pptx_deck)
    assert deck.source_kind == "pptx"
    assert len(deck.slides) == 3


def test_no_vision_short_circuits_the_libreoffice_fallback(pptx_deck: Path, mocker) -> None:
    spy = mocker.patch("onepager.extract.pptx.convert_via_libreoffice")
    pptx_to_deck(pptx_deck, vision=False)
    spy.assert_not_called()


def test_missing_libreoffice_degrades_instead_of_crashing(pptx_deck: Path, mocker) -> None:
    mocker.patch("onepager.extract.pptx.soffice_path", return_value=None)
    deck = pptx_to_deck(pptx_deck, vision=True)
    assert deck.used_vision is False
    assert any("LibreOffice" in note for note in deck.notes)
    assert len(deck.slides) == 3  # the text pass still stands


def test_missing_libreoffice_is_fatal_for_legacy_ppt(tmp_path: Path, mocker) -> None:
    mocker.patch("onepager.extract.pptx.soffice_path", return_value=None)
    legacy = tmp_path / "old.ppt"
    legacy.write_bytes(b"\xd0\xcf\x11\xe0legacy binary")
    with pytest.raises(ExtractionError, match="LibreOffice"):
        extract(legacy)


def test_libreoffice_failure_reports_the_binary_output(tmp_path: Path, mocker) -> None:
    mocker.patch("onepager.extract.pptx.soffice_path", return_value="soffice")
    proc = mocker.Mock(stderr=b"conversion blew up", stdout=b"")
    mocker.patch("onepager.extract.pptx.subprocess.run", return_value=proc)
    with pytest.raises(ExtractionError, match="conversion blew up"):
        convert_via_libreoffice(tmp_path / "x.pptx", tmp_path)


def test_corrupt_pptx_raises_a_readable_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.pptx"
    bad.write_bytes(b"not a zip archive at all")
    with pytest.raises(ExtractionError) as exc:
        extract(bad)
    assert "PowerPoint" in str(exc.value)
