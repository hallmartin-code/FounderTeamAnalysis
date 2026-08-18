"""Dispatch on file type and produce a normalized Deck."""

from __future__ import annotations

from pathlib import Path

from ..config import MIN_TOTAL_CHARS
from .pdf import pdf_to_deck
from .pptx import pptx_to_deck
from .types import Deck, ExtractionError, NoContentError, SlideContent

_SUPPORTED = {".pdf", ".pptx", ".ppt"}

__all__ = [
    "Deck",
    "ExtractionError",
    "NoContentError",
    "SlideContent",
    "extract",
]


def extract(path: Path, vision: bool | None = None, max_slides: int | None = None) -> Deck:
    if not path.exists():
        raise ExtractionError(f"{path} does not exist.")
    suffix = path.suffix.lower()
    if suffix not in _SUPPORTED:
        listed = ", ".join(sorted(_SUPPORTED))
        raise ExtractionError(
            f"{path.name}: unsupported file type {suffix or '(none)'!r}. Supported: {listed}."
        )
    if path.stat().st_size == 0:
        raise ExtractionError(f"{path.name} is empty (0 bytes).")

    deck = pdf_to_deck(path, vision) if suffix == ".pdf" else pptx_to_deck(path, vision)

    if max_slides and len(deck.slides) > max_slides:
        deck.notes.append(f"capped at {max_slides} of {len(deck.slides)} slides (--max-slides)")
        deck.slides = deck.slides[:max_slides]

    if deck.total_chars < MIN_TOTAL_CHARS and not deck.used_vision:
        raise NoContentError(
            f"{path.name} yielded only {deck.total_chars} characters of text across "
            f"{len(deck.slides)} slide(s), and no page images are available. "
            "The deck is most likely a scan or an all-image export; re-run with --vision, "
            "or supply a text-based export."
        )
    return deck
